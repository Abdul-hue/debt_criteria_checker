"""
HMRC equity rule (TIG-15.4) end to end: property value from the Aryza client,
through AssessCaseView._prepare_engine_payload (pence -> pounds), _parse_case
(available_equity at 100% of the value) and the rule itself.

Also pins the fix made on 2026-10-13: a property with a mortgage but no
recorded valuation used to arrive at the engine as a £0 property (equity =
-mortgage, rule silently passes). It now arrives as None, so the rule reports
"could not be completed" exactly as the credit-report fallback path already did.
"""

from unittest.mock import patch

from django.test import TestCase

from debt_app.aryza_client import AryzaClient, CaseData
from debt_app.engine.criteria import _parse_case, _tig_15_4, assess_case
from debt_app.models import CreditorCriteria, GlobalCriteria
from debt_app.tests_cat_assessment_golden import _FixedDate, _case, _creditor
from debt_app.views.criteria_views import AssessCaseView


class _StubCursor:
    def __init__(self, row):
        self.row = row

    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _StubConnection:
    def __init__(self, row):
        self.row = row

    def cursor(self):
        return _StubCursor(self.row)


def _fetch_property(row):
    client = AryzaClient.__new__(AryzaClient)  # no connection needed for this method
    case = CaseData()
    client._fetch_property_data(_StubConnection(row), case, clientid=1)
    return case.property


class AryzaPropertyFetchTests(TestCase):
    def test_valuation_and_mortgage_present(self):
        p = _fetch_property((100_000, 250_000))          # pounds from SQL
        self.assertEqual(p, {"owns_property": True, "property_value": 25_000_000,
                             "mortgage_balance": 10_000_000, "mortgage_balance_known": True,
                             "equity": 15_000_000})  # pence

    def test_valuation_but_no_mortgage_record_is_not_a_known_zero_mortgage(self):
        p = _fetch_property((None, 250_000))             # SUM over no slam_mortgage rows is NULL
        self.assertEqual(p["mortgage_balance"], 0)       # unchanged for the rules that read it
        self.assertFalse(p["mortgage_balance_known"])

    def test_recorded_zero_mortgage_is_known(self):
        self.assertTrue(_fetch_property((0, 250_000))["mortgage_balance_known"])

    def test_mortgage_but_no_valuation_is_unknown_not_zero(self):
        p = _fetch_property((100_000, None))
        self.assertTrue(p["owns_property"])
        self.assertIsNone(p["property_value"])
        self.assertIsNone(p["equity"])
        self.assertEqual(p["mortgage_balance"], 10_000_000)

    def test_recorded_zero_valuation_is_a_known_zero(self):
        p = _fetch_property((100_000, 0))
        self.assertEqual(p["property_value"], 0)
        self.assertEqual(p["equity"], -10_000_000)

    def test_no_property_rows(self):
        p = _fetch_property((None, None))
        self.assertEqual(p, {"owns_property": False, "property_value": 0, "mortgage_balance": 0, "equity": 0})


class HmrcEquityPipelineTests(TestCase):
    """Synthetic homeowner: no stored decision on this environment involves a
    homeowner, and the Aryza instance returned no property rows for any case
    fetched, so the path is exercised with a representative fixture."""

    def setUp(self):
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        # The case names the creditor "HMRC"; the alias resolves it to the sheet's row.
        CreditorCriteria.objects.filter(creditor_name="HMRC").delete()
        for name, status in (("HM Revenue & Customs", "WILL_CONSIDER"), ("Alpha Bank", "ACCEPT")):
            CreditorCriteria.objects.update_or_create(
                creditor_name=name, defaults=dict(representative="NONE", status=status, is_active=True,
                                                  reject_if_equity_exceeds_debt=False, criteria_notes=""),
            )
        self.rule, _ = GlobalCriteria.objects.update_or_create(
            rule_key="TIG-15.4",
            defaults=dict(criteria_set="TIG", rule_name="HMRC equity exceeds debt", severity="hard_block", is_active=False),
        )

    def _payload(self, property_block):
        case = _case("HM-1", [_creditor("HMRC", 500_000, type_="unsecured"), _creditor("Alpha Bank", 600_000)])
        case.property = property_block
        payload, prepared, unmatched = AssessCaseView()._prepare_engine_payload(case)
        return payload

    def test_value_reaches_the_rule_in_pounds_at_one_hundred_percent(self):
        payload = self._payload({"owns_property": True, "property_value": 25_000_000,
                                 "mortgage_balance": 10_000_000, "equity": 15_000_000})
        self.assertEqual(payload["property"]["property_value"], 250_000.0)
        self.assertEqual(payload["property"]["mortgage_balance"], 100_000.0)
        c = _parse_case(payload)
        self.assertTrue(c["has_property"])
        self.assertTrue(c["hmrc_is_creditor"])
        self.assertEqual(c["hmrc_balance"], 5_000.0)
        self.assertEqual(c["available_equity"], 150_000.0)          # 250,000 - 100,000: no 85% haircut
        self.assertNotEqual(c["available_equity"], 250_000.0 * 0.85 - 100_000.0)
        r = _tig_15_4(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual((r.actual_value, r.threshold), (150_000.0, 5_000.0))

    def test_equity_below_hmrc_debt_passes(self):
        payload = self._payload({"owns_property": True, "property_value": 10_400_000,
                                 "mortgage_balance": 10_000_000, "equity": 400_000})
        r = _tig_15_4(_parse_case(payload))
        self.assertFalse(r.triggered)
        self.assertEqual(r.severity, "pass")

    def test_unknown_value_cannot_be_evaluated(self):
        payload = self._payload({"owns_property": True, "property_value": None,
                                 "mortgage_balance": 10_000_000, "equity": None})
        self.assertIsNone(payload["property"]["property_value"])
        c = _parse_case(payload)
        self.assertIsNone(c["available_equity"])
        r = _tig_15_4(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.severity, "info")
        self.assertIn("no property value has been entered", r.message)

    def test_recorded_zero_value_is_not_a_valuation(self):
        """A £0 valuation is not a real figure for a property the customer owns
        (TIG-16 treats it as "no valuation" too): it must not produce a silent pass."""
        payload = self._payload({"owns_property": True, "property_value": 0,
                                 "mortgage_balance": 10_000_000, "equity": -10_000_000})
        c = _parse_case(payload)
        self.assertEqual(c["available_equity"], -100_000.0)
        r = _tig_15_4(c)
        self.assertEqual((r.severity, r.triggered), ("info", False))
        self.assertIn("could not be completed", r.message)

    def test_no_property(self):
        payload = self._payload({"owns_property": False, "property_value": 0, "mortgage_balance": 0, "equity": 0})
        c = _parse_case(payload)
        self.assertEqual(c["available_equity"], 0.0)
        self.assertEqual(_tig_15_4(c).severity, "pass")

    def test_intended_configuration_legacy_flag_off_tig_15_4_on(self):
        """After the HMRC draft is approved: the per-creditor 85% flag is off, TIG-15.4
        is on, and only TIG-15.4 evaluates HMRC equity. Missing valuations stay unknown."""
        from debt_app.management.commands.seed_creditor_criteria import STRUCTURED_CRITERIA
        self.assertNotIn("HM Revenue & Customs", STRUCTURED_CRITERIA)   # a reseed cannot re-apply the legacy flag

        ROW = "HM Revenue & Customs"
        CreditorCriteria.objects.filter(creditor_name=ROW).update(reject_if_equity_exceeds_debt=False)
        GlobalCriteria.objects.filter(pk=self.rule.pk).update(is_active=True)
        homeowner = {"owns_property": True, "property_value": 25_000_000, "mortgage_balance": 10_000_000, "equity": 15_000_000}

        result = assess_case(self._payload(homeowner))
        self.assertIn("TIG-15.4", {r.rule_id for r in result["hard_blocks"]})
        hmrc_pos = next(p for p in result["creditor_positions"] if p["resolved_canonical_name"] == ROW)
        self.assertEqual(hmrc_pos["effective_status"], "WILL_CONSIDER")   # "HMRC" resolved through the alias
        self.assertNotIn("CREDITOR-EQUITY-EXCEEDS-DEBT", {f["code"] for f in hmrc_pos["findings"]})

        # the two must not both operate: with the legacy flag still on, both would fire
        CreditorCriteria.objects.filter(creditor_name=ROW).update(reject_if_equity_exceeds_debt=True)
        result = assess_case(self._payload(homeowner))
        hmrc_pos = next(p for p in result["creditor_positions"] if p["resolved_canonical_name"] == ROW)
        self.assertIn("CREDITOR-EQUITY-EXCEEDS-DEBT", {f["code"] for f in hmrc_pos["findings"]})
        CreditorCriteria.objects.filter(creditor_name=ROW).update(reject_if_equity_exceeds_debt=False)

        # missing valuation: not £0, not a silent pass
        unknown = {"owns_property": True, "property_value": None, "mortgage_balance": 10_000_000, "equity": None}
        result = assess_case(self._payload(unknown))
        self.assertNotIn("TIG-15.4", {r.rule_id for r in result["hard_blocks"]})
        info = next(r for r in result["info"] if r.rule_id == "TIG-15.4")
        self.assertEqual(info.severity, "info")
        self.assertIn("no property value has been entered", info.message)

    def test_rule_only_blocks_when_switched_on(self):
        payload = self._payload({"owns_property": True, "property_value": 25_000_000,
                                 "mortgage_balance": 10_000_000, "equity": 15_000_000})
        blocked = {r.rule_id for r in assess_case(payload)["hard_blocks"]}
        self.assertNotIn("TIG-15.4", blocked)             # inactive: the draft has not been approved
        GlobalCriteria.objects.filter(pk=self.rule.pk).update(is_active=True)
        blocked = {r.rule_id for r in assess_case(payload)["hard_blocks"]}
        self.assertIn("TIG-15.4", blocked)
