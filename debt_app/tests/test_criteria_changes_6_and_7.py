"""
Criteria Changes #6 (rule switches) and #7 (HMRC equity rule TIG-15.4).

#6 switches off WATCH-22.4, WATCH-22.6 and EVOLVE-01..03 (workbook removed
them; sheet owner confirmed 2026-10-12). #7 switches TIG-15.4 on and the
legacy per-creditor 85% equity flag on 'HM Revenue & Customs' off, together.

Pins:
  * the engine stops running the retired rules and nothing else changes;
  * TIG-16 does not point WATCH cases to the retired WATCH equity rule;
  * a trial shows creditor-vote changes (the saved #6 trial reported only the
    removed WATCH-22.6 flag, yet in 11 of its 16 changed cases every WATCH
    creditor's vote moved from WILL_CONSIDER to ACCEPT);
  * seed_rule_meta cannot undo an approved switch;
  * TIG-15.4: equity at 100% of value, strict ">" against the HMRC balance,
    unknown / invalid figures never evaluated, a missing mortgage record never
    read as a £0 mortgage, non-HMRC cases out of scope, and never alongside
    the legacy HMRC flag.

All cases are synthetic. No saved case on this environment is a homeowner
with a recorded valuation, so no real-case TIG-15.4 result is claimed here.
"""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from debt_app.engine.criteria import _parse_case, _tig_15_4, assess_case
from debt_app.models import CreditorCriteria, CriteriaChangeRequest, CriteriaDecision, GlobalCriteria
from debt_app.services import criteria_versioning as cv
from debt_app.tests_cat_assessment_golden import _case, _creditor, _FixedDate
from debt_app.views.criteria_views import AssessCaseView

FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"
RETIRED = ("WATCH-22.4", "WATCH-22.6", "EVOLVE-01", "EVOLVE-02", "EVOLVE-03")
HMRC_ROW = "HM Revenue & Customs"


def _rule(key, active, severity="hard_block"):
    GlobalCriteria.objects.update_or_create(
        rule_key=key,
        defaults=dict(criteria_set=key.split("-")[0], rule_name=key, severity=severity, is_active=active),
    )


def _creditor_row(name, rep="NONE", status="ACCEPT", **kw):
    CreditorCriteria.objects.update_or_create(
        creditor_name=name,
        defaults=dict(representative=rep, status=status, is_active=True, criteria_notes="", **kw),
    )


def _payload(creditors, property_block=None):
    case = _case("SW-1", creditors)
    if property_block is not None:
        case.property = property_block
    payload, _prepared, _unmatched = AssessCaseView()._prepare_engine_payload(case)
    # Like every saved case on this environment: no open banking data, so
    # WATCH-22.6 fires its "could not be checked" flag while it is switched on.
    payload.pop("gold_transactions", None)
    return payload


def _ids(result, bucket):
    return {r.rule_id for r in result[bucket]}


def _all_ids(result):
    return set().union(*(_ids(result, b) for b in ("hard_blocks", "flags", "info", "passed")))


def _votes(result):
    return {p["creditor_name"]: p["effective_status"] for p in result["creditor_positions"]}


class _FixedDateMixin:
    def setUp(self):
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()


# --------------------------------------------------------------------------- #6
class RuleSwitchesEngineTests(_FixedDateMixin, TestCase):
    """Draft #6 applied: the five retired rules no longer run."""

    def setUp(self):
        super().setUp()
        _creditor_row("Watch Bank", rep="WATCH")
        _creditor_row("Evolve Bank", rep="EVOLVE")
        _creditor_row("Plain Loans")
        for key in RETIRED:
            _rule(key, True, severity="flag" if key in ("WATCH-22.6", "EVOLVE-03") else "hard_block")
        _rule("WATCH-22.13", False, severity="flag")   # see TrialShowsVoteChangesTests.setUp
        _rule("TIG-16", True, severity="flag")

    def _switch_off(self):
        GlobalCriteria.objects.filter(rule_key__in=RETIRED).update(is_active=False)

    def test_watch_homeowner_equity_rule_and_spend_flag_stop(self):
        # 85% of 300k - 50k = 205k > 11k debt: WATCH-22.4 would hard-block.
        # No open banking: WATCH-22.6 would flag "could not be checked".
        homeowner = {"owns_property": True, "property_value": 30_000_000, "mortgage_balance": 5_000_000,
                     "equity": 25_000_000}
        payload = _payload([_creditor("Watch Bank", 600_000), _creditor("Plain Loans", 500_000)], homeowner)

        before = assess_case(payload, detected_representatives={"WATCH"})
        self.assertIn("WATCH-22.4", _ids(before, "hard_blocks"))
        self.assertIn("WATCH-22.6", _ids(before, "flags"))
        # WATCH-22.4 is case-level only (_BODY_LEVEL_ONLY_RULES): it never set
        # WATCH creditors' votes. WATCH-22.6 did, as the WATCH flag.
        self.assertEqual(before["representative_outcomes"]["WATCH"]["rule_id"], "WATCH-22.6")
        self.assertEqual(_votes(before)["Watch Bank"], "WILL_CONSIDER")

        self._switch_off()
        after = assess_case(payload, detected_representatives={"WATCH"})
        self.assertFalse({"WATCH-22.4", "WATCH-22.6"} & _all_ids(after))
        # Nothing else in WATCH fired here, so WATCH's vote becomes ACCEPT.
        self.assertEqual(_votes(after)["Watch Bank"], "ACCEPT")
        self.assertEqual(_votes(after)["Plain Loans"], _votes(before)["Plain Loans"])

        # TIG-16 stays out of WATCH cases (sheet: NON-WPM only) and no longer
        # points the caseworker at a WATCH equity rule that does not run.
        tig16 = next(r for r in after["passed"] if r.rule_id == "TIG-16")
        self.assertNotIn("assessed under the WATCH equity rule", tig16.message)
        self.assertIn("WATCH no longer has a rule", tig16.message)
        tig16_before = next(r for r in before["passed"] if r.rule_id == "TIG-16")
        self.assertIn("assessed under the WATCH equity rule", tig16_before.message)

    def test_removing_watch_22_6_is_the_only_watch_change_without_property(self):
        payload = _payload([_creditor("Watch Bank", 600_000), _creditor("Plain Loans", 500_000)])
        before = assess_case(payload, detected_representatives={"WATCH"})
        self._switch_off()
        after = assess_case(payload, detected_representatives={"WATCH"})
        self.assertEqual(_ids(before, "flags") - _ids(after, "flags"), {"WATCH-22.6"})
        self.assertEqual(_ids(after, "flags") - _ids(before, "flags"), set())
        self.assertEqual(_ids(before, "hard_blocks"), _ids(after, "hard_blocks"))
        self.assertEqual(before["recommended_solution"], after["recommended_solution"])
        self.assertEqual(before["majority_analysis"]["achievable"], after["majority_analysis"]["achievable"])

    def test_evolve_rules_do_not_run_when_switched_off(self):
        # Single qualifying lender: EVOLVE-02 would hard-block.
        payload = _payload([_creditor("Evolve Bank", 900_000), _creditor("Plain Loans", 30_000)])
        before = assess_case(payload, detected_representatives={"EVOLVE"})
        self.assertIn("EVOLVE-02", _ids(before, "hard_blocks"))
        self._switch_off()
        after = assess_case(payload, detected_representatives={"EVOLVE"})
        self.assertFalse({k for k in _all_ids(after) if k.startswith("EVOLVE-")})


class TrialShowsVoteChangesTests(_FixedDateMixin, TransactionTestCase):
    """The trial must surface creditor-vote changes, not only rule ids."""

    def setUp(self):
        super().setUp()
        _creditor_row("Watch Bank", rep="WATCH")
        _creditor_row("Plain Loans")
        _rule("WATCH-22.6", True, severity="flag")
        # The synthetic case also trips WATCH-22.13 (no bank data); the 16 real
        # trial cases did not. Off here so WATCH-22.6 alone drives WATCH's vote.
        _rule("WATCH-22.13", False, severity="flag")
        self.user = User.objects.create_user("author", password=None)
        with patch(FETCH, return_value=_case("TR-1", [_creditor("Watch Bank", 600_000),
                                                      _creditor("Plain Loans", 500_000)])):
            APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "TR-1"}, format="json")
        decision = CriteriaDecision.objects.get(application_id="TR-1")
        decision.input_snapshot.pop("gold_transactions", None)    # no open banking, as on the real cases
        decision.save()

    def test_switching_off_watch_22_6_reports_watch_creditor_vote_change(self):
        rule = GlobalCriteria.objects.get(rule_key="WATCH-22.6")
        change = cv.create_change_request(self.user, "Rule switches", "Workbook removed WATCH-22.6",
                                          [{"model": "GlobalCriteria", "object_id": rule.pk,
                                            "field": "is_active", "new_value": False}])
        fp = cv.live_fingerprint()
        cv.run_trial(change, self.user)
        change.refresh_from_db()
        self.assertEqual(cv.live_fingerprint(), fp)                       # live criteria untouched
        self.assertTrue(GlobalCriteria.objects.get(pk=rule.pk).is_active)
        self.assertEqual(change.status, CriteriaChangeRequest.STATUS_TRIALLED)

        diff = change.trial_summary["changed"][0]["differences"]
        self.assertIn("WATCH-22.6", diff["flags"]["before"])
        self.assertNotIn("WATCH-22.6", diff["flags"]["after"])
        self.assertIn("Watch Bank: WILL_CONSIDER", diff["creditor_votes"]["before"])
        self.assertIn("Watch Bank: ACCEPT", diff["creditor_votes"]["after"])
        self.assertNotIn("engine_solution", diff)                          # recommendation unchanged


class SeedRuleMetaKeepsApprovedSwitchesTests(TestCase):
    def test_existing_switches_survive_a_reseed_and_new_rules_are_created(self):
        for key in RETIRED:
            _rule(key, False)                                  # #6 approved
        _rule("TIG-15.4", True)                                # #7 approved
        GlobalCriteria.objects.filter(rule_key="TIG-01").delete()

        call_command("seed_rule_meta", stdout=StringIO())

        for key in RETIRED:
            self.assertFalse(GlobalCriteria.objects.get(rule_key=key).is_active, key)
        tig_15_4 = GlobalCriteria.objects.get(rule_key="TIG-15.4")
        self.assertTrue(tig_15_4.is_active)
        self.assertNotIn("STUB", tig_15_4.description)
        self.assertIn("100%", tig_15_4.description)
        self.assertTrue(GlobalCriteria.objects.get(rule_key="TIG-01").is_active)   # created with its seed value


# --------------------------------------------------------------------------- #7
class HmrcEquityRuleTests(_FixedDateMixin, TestCase):
    """TIG-15.4 with draft #7 applied (rule on, legacy HMRC flag off)."""

    def setUp(self):
        super().setUp()
        CreditorCriteria.objects.filter(creditor_name="HMRC").delete()
        _creditor_row(HMRC_ROW, status="WILL_CONSIDER", reject_if_equity_exceeds_debt=True)
        _creditor_row("Alpha Bank")
        _rule("TIG-15.4", False)
        # Draft #7's two items, applied the way approval applies them.
        hmrc = CreditorCriteria.objects.get(creditor_name=HMRC_ROW)
        rule = GlobalCriteria.objects.get(rule_key="TIG-15.4")
        cv._apply_items_to("default", [
            {"model": "CreditorCriteria", "object_id": hmrc.pk, "field": "reject_if_equity_exceeds_debt",
             "old_value": True, "new_value": False},
            {"model": "GlobalCriteria", "object_id": rule.pk, "field": "is_active",
             "old_value": False, "new_value": True},
        ])

    def _homeowner(self, value_pence, mortgage_pence, hmrc_pence=500_000, hmrc_name="HMRC"):
        return _payload(
            [_creditor(hmrc_name, hmrc_pence, type_="unsecured"), _creditor("Alpha Bank", 600_000)],
            {"owns_property": True, "property_value": value_pence, "mortgage_balance": mortgage_pence,
             "equity": None if value_pence is None else value_pence - mortgage_pence},
        )

    def _tig_15_4(self, result):
        return next(r for r in [*result["hard_blocks"], *result["flags"], *result["info"], *result["passed"]]
                    if r.rule_id == "TIG-15.4")

    def _equity_findings(self, result):
        return {f["code"] for p in result["creditor_positions"] for f in p.get("findings", [])
                if "EQUITY" in (f.get("code") or "")}

    def test_equity_greater_than_hmrc_debt_rejects_at_100_percent(self):
        # 250k - 100k = 150k > 5k. (At 85% it would be 112.5k: the figure must be 150k.)
        result = assess_case(self._homeowner(25_000_000, 10_000_000))
        r = self._tig_15_4(result)
        self.assertEqual((r.severity, r.triggered), ("hard_block", True))
        self.assertEqual((r.actual_value, r.threshold), (150_000.0, 5_000.0))
        self.assertIn("TIG-15.4", _ids(result, "hard_blocks"))

    def test_one_penny_over_rejects(self):
        r = self._tig_15_4(assess_case(self._homeowner(10_500_001, 10_000_000)))   # 5,000.01 > 5,000
        self.assertEqual(r.severity, "hard_block")

    def test_equity_equal_to_hmrc_debt_does_not_reject(self):
        result = assess_case(self._homeowner(10_500_000, 10_000_000))              # 5,000 == 5,000
        r = self._tig_15_4(result)
        self.assertEqual((r.severity, r.triggered), ("pass", False))
        self.assertNotIn("TIG-15.4", _ids(result, "hard_blocks"))

    def test_equity_below_hmrc_debt_does_not_reject(self):
        result = assess_case(self._homeowner(10_400_000, 10_000_000))              # 4,000 < 5,000
        self.assertEqual(self._tig_15_4(result).severity, "pass")
        self.assertNotIn("TIG-15.4", _ids(result, "hard_blocks"))

    def test_missing_valuation_is_not_evaluated(self):
        result = assess_case(self._homeowner(None, 10_000_000))
        r = self._tig_15_4(result)
        self.assertEqual((r.severity, r.triggered), ("info", False))
        self.assertIn("no property value has been entered", r.message)

    def test_invalid_figures_are_not_evaluated(self):
        base = self._homeowner(25_000_000, 10_000_000)
        bad = [
            ("property_value", "not a number"), ("property_value", ""), ("property_value", 0),
            ("property_value", -250_000), ("property_value", "nan"), ("property_value", "inf"),
            ("mortgage_balance", -1),
        ]
        for field, value in bad:
            with self.subTest(field=field, value=value):
                payload = {**base, "property": {**base["property"], field: value}}
                c = _parse_case(payload)
                r = _tig_15_4(c)
                self.assertEqual((r.severity, r.triggered), ("info", False))
                self.assertIn("could not be completed", r.message)
                self.assertNotIn("TIG-15.4", _ids(assess_case(payload), "hard_blocks"))

    def test_no_mortgage_record_is_not_assumed_to_be_zero(self):
        """Valuation recorded, no mortgage record: equity is not known, so no rejection."""
        payload = self._homeowner(25_000_000, 0)
        payload["property"]["mortgage_balance_known"] = False
        result = assess_case(payload)
        r = self._tig_15_4(result)
        self.assertEqual((r.severity, r.triggered), ("info", False))
        self.assertIn("no mortgage balance is recorded", r.message)
        self.assertNotIn("TIG-15.4", _ids(result, "hard_blocks"))

    def test_no_mortgage_record_but_value_within_hmrc_debt_is_a_safe_pass(self):
        payload = self._homeowner(400_000, 0)               # £4,000 home vs £5,000 HMRC: equity cannot exceed it
        payload["property"]["mortgage_balance_known"] = False
        self.assertEqual(self._tig_15_4(assess_case(payload)).severity, "pass")

    def test_recorded_zero_mortgage_is_evaluated(self):
        payload = self._homeowner(25_000_000, 0)
        payload["property"]["mortgage_balance_known"] = True
        self.assertEqual(self._tig_15_4(assess_case(payload)).severity, "hard_block")

    def test_does_not_apply_without_hmrc(self):
        payload = _payload([_creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 500_000)],
                           {"owns_property": True, "property_value": 50_000_000, "mortgage_balance": 0,
                            "equity": 50_000_000})
        result = assess_case(payload)
        r = self._tig_15_4(result)
        self.assertEqual(r.severity, "pass")
        self.assertIn("HMRC is not one of the customer's creditors", r.message)
        self.assertNotIn("TIG-15.4", _ids(result, "hard_blocks"))

    def test_only_tig_15_4_decides_hmrc_equity(self):
        """No legacy CREDITOR-EQUITY-* finding and no HMRC REJECT from it, in either direction."""
        for value, expect_block in ((25_000_000, True), (10_400_000, False)):
            with self.subTest(value=value):
                result = assess_case(self._homeowner(value, 10_000_000))
                self.assertEqual("TIG-15.4" in _ids(result, "hard_blocks"), expect_block)
                self.assertEqual(self._equity_findings(result), set())
                hmrc = next(p for p in result["creditor_positions"] if p["resolved_canonical_name"] == HMRC_ROW)
                self.assertEqual(hmrc["effective_status"], "WILL_CONSIDER")

    def test_no_other_hmrc_row_carries_the_legacy_flag(self):
        self.assertFalse(CreditorCriteria.objects.filter(
            creditor_name__icontains="hm revenue", reject_if_equity_exceeds_debt=True).exists())


class HmrcEquityFullAssessmentPathTests(_FixedDateMixin, TransactionTestCase):
    """Synthetic homeowner through the full CAT path: Aryza CaseData (pence) ->
    AssessCaseView -> engine -> saved CriteriaDecision."""

    def setUp(self):
        super().setUp()
        CreditorCriteria.objects.filter(creditor_name="HMRC").delete()
        _creditor_row(HMRC_ROW, status="WILL_CONSIDER", reject_if_equity_exceeds_debt=False)
        _creditor_row("Alpha Bank")
        _rule("TIG-15.4", True)

    def _assess(self, ref, value_pence, mortgage_pence):
        case = _case(ref, [_creditor("HMRC", 500_000, type_="unsecured"), _creditor("Alpha Bank", 600_000)])
        case.property = {"owns_property": True, "property_value": value_pence, "mortgage_balance": mortgage_pence,
                         "equity": None if value_pence is None else value_pence - mortgage_pence}
        with patch(FETCH, return_value=case):
            resp = APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": ref}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        return resp.json()

    @staticmethod
    def _find(body, rule_id):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("rule_id") == rule_id:
                    found.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(body)
        return found

    def test_homeowner_with_equity_over_hmrc_debt_is_blocked(self):
        body = self._assess("HP-1", 25_000_000, 10_000_000)
        hits = self._find(body, "TIG-15.4")
        self.assertTrue(hits)
        self.assertTrue(all(h.get("severity") == "hard_block" for h in hits), hits)
        self.assertTrue(CriteriaDecision.objects.filter(application_id="HP-1").exists())

    def test_homeowner_without_mortgage_record_is_not_blocked(self):
        """Aryza: valuation recorded, no slam_mortgage row (as _fetch_property_data builds it)."""
        case = _case("HP-3", [_creditor("HMRC", 500_000, type_="unsecured"), _creditor("Alpha Bank", 600_000)])
        case.property = {"owns_property": True, "property_value": 25_000_000, "mortgage_balance": 0,
                         "mortgage_balance_known": False, "equity": 25_000_000}
        with patch(FETCH, return_value=case):
            body = APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "HP-3"}, format="json").json()
        hits = self._find(body, "TIG-15.4")
        self.assertTrue(hits)
        self.assertTrue(all(h.get("severity") == "info" for h in hits), hits)

    def _assess_property(self, ref, prop):
        case = _case(ref, [_creditor("HMRC", 500_000, type_="unsecured"), _creditor("Alpha Bank", 600_000)])
        case.property = prop
        with patch(FETCH, return_value=case):
            resp = APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": ref}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        return {h.get("severity") for h in self._find(resp.json(), "TIG-15.4")}

    def test_recorded_zero_mortgage_is_evaluated_through_the_api(self):
        # A slam_mortgage row with £0 outstanding: equity 250k > 5k HMRC.
        self.assertEqual(self._assess_property("HP-5", {
            "owns_property": True, "property_value": 25_000_000, "mortgage_balance": 0,
            "mortgage_balance_known": True, "equity": 25_000_000}), {"hard_block"})

    def test_zero_or_negative_valuation_is_not_evaluated_through_the_api(self):
        for ref, value in (("HP-6", 0), ("HP-7", -25_000_000)):
            with self.subTest(value=value):
                self.assertEqual(self._assess_property(ref, {
                    "owns_property": True, "property_value": value, "mortgage_balance": 10_000_000,
                    "mortgage_balance_known": True, "equity": value - 10_000_000}), {"info"})

    def test_equity_equal_to_hmrc_debt_is_not_rejected_through_the_api(self):
        self.assertEqual(self._assess_property("HP-8", {
            "owns_property": True, "property_value": 10_500_000, "mortgage_balance": 10_000_000,
            "mortgage_balance_known": True, "equity": 500_000}), {"pass"})

    def test_secured_creditor_balance_counts_as_a_recorded_mortgage(self):
        case = _case("HP-4", [_creditor("HMRC", 500_000, type_="unsecured"), _creditor("Alpha Bank", 600_000),
                              _creditor("Home Lender", 10_000_000, type_="mortgage")])
        case.property = {"owns_property": True, "property_value": 25_000_000, "mortgage_balance": 0,
                         "mortgage_balance_known": False, "equity": 25_000_000}
        payload, _p, _u = AssessCaseView()._prepare_engine_payload(case)
        self.assertTrue(payload["property"]["mortgage_balance_known"])
        self.assertEqual(payload["property"]["mortgage_balance"], 100_000.0)

    def test_homeowner_without_valuation_is_not_blocked(self):
        body = self._assess("HP-2", None, 10_000_000)
        hits = self._find(body, "TIG-15.4")
        self.assertTrue(hits)
        self.assertTrue(all(h.get("severity") == "info" for h in hits), hits)


class EvaluateViewPayloadTests(_FixedDateMixin, TestCase):
    """POST criteria/cases/<id>/evaluate builds its own payload; it must carry the
    same "mortgage not recorded" and "previous IVA unanswered" signals."""

    def setUp(self):
        super().setUp()
        CreditorCriteria.objects.filter(creditor_name="HMRC").delete()
        _creditor_row(HMRC_ROW, status="WILL_CONSIDER", reject_if_equity_exceeds_debt=False)
        _creditor_row("Alpha Bank")
        _rule("TIG-15.4", True)

    def _payload(self, prop, flags=None):
        from debt_app.views.evaluate_view import EvaluateCaseView
        case = _case("EV-1", [_creditor("HMRC", 500_000, type_="unsecured"), _creditor("Alpha Bank", 600_000)])
        case.property = prop
        case.flags.update(flags or {})
        return EvaluateCaseView()._prepare_engine_payload(case)

    def _tig(self, payload):
        result = assess_case(payload)
        return next(r for r in [*result["hard_blocks"], *result["flags"], *result["info"], *result["passed"]]
                    if r.rule_id == "TIG-15.4"), result

    def test_missing_mortgage_record_is_not_a_zero_balance(self):
        payload = self._payload({"owns_property": True, "property_value": 25_000_000, "mortgage_balance": 0,
                                 "mortgage_balance_known": False, "equity": 25_000_000})
        self.assertFalse(payload["property"]["mortgage_balance_known"])
        r, _ = self._tig(payload)
        self.assertEqual((r.severity, r.triggered), ("info", False))

    def test_credit_report_mortgage_makes_the_balance_known(self):
        from debt_app.models import CreditReport
        report = CreditReport(aryza_reference="EV-1",
                              extracted_data={"mortgage_accounts": [{"current_balance": 24_900_000}]})
        with patch("debt_app.models.CreditReport.objects.filter") as filt:
            filt.return_value.order_by.return_value.first.return_value = report
            payload = self._payload({"owns_property": True, "property_value": 25_000_000, "mortgage_balance": 0,
                                     "mortgage_balance_known": False, "equity": 25_000_000})
        self.assertTrue(payload["property"]["mortgage_balance_known"])
        self.assertEqual(payload["property"]["mortgage_balance"], 249_000.0)
        r, _ = self._tig(payload)                       # 250k - 249k = 1k < 5k HMRC
        self.assertEqual(r.severity, "pass")

    def test_recorded_mortgage_is_evaluated(self):
        payload = self._payload({"owns_property": True, "property_value": 25_000_000, "mortgage_balance": 10_000_000,
                                 "mortgage_balance_known": True, "equity": 15_000_000})
        r, _ = self._tig(payload)
        self.assertEqual(r.severity, "hard_block")

    def test_unanswered_previous_iva_reaches_the_engine(self):
        payload = self._payload({"owns_property": False}, flags={"previous_iva_answered": False})
        _, result = self._tig(payload)
        self.assertIn("PREVIOUS-IVA-UNCONFIRMED", {r.rule_id for r in result["flags"]})
