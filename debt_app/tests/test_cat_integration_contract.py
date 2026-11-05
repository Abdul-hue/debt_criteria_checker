"""
Contract fixes found by tracing the case-assessment tool's real payloads
through this engine (September 2026 audit).

Each test names the behaviour the caller depends on:

* `_parse_case` keeps None for "not known" per-creditor flags, so the
  caseworker-confirmation branches in `_check_creditor_individual` are
  reachable. Coercing with bool() made None read as False, and a False
  `first_payment_made` is a REJECT -- so the caller had to assert True.
* TIG-10 treats a placeholder creditor name ("CCJ (creditor not yet
  identified)", "OTHER", "Unknown Creditor") as an unverified debt.
* Secured creditors are sent tagged `is_secured` so the HP rules can see
  them; every figure measured against the UNSECURED `total_debt` -- the
  75% majority numerator, the qualifying-lender count, the representative
  balance majority, dividend minimums, representative detection -- must
  leave them out, and the API must hand the tag back.
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.engine.criteria import (
    _check_creditor_individual,
    _compute_majority_analysis,
    _count_qualifying_lenders,
    _derive_recommended_solution,
    _is_unidentified_creditor_name,
    _parse_case,
    _tig_10,
    detect_representatives,
)
from debt_app.models import CreditorCriteria

User = get_user_model()


def _creditor(idx, name, balance, secured=False, **extra):
    row = {
        "_idx": idx,
        "name": name,
        "original_name": name,
        "balance": float(balance),
        "crm_balance": Decimal(str(balance)),
        "is_secured": secured,
    }
    row.update(extra)
    return row


def _position(idx, name, status, secured=False):
    return {
        "creditor_name": name,
        "effective_status": status,
        "_creditor_idx": idx,
        "balance": 0,
        "is_secured": secured,
    }


class ParseCaseKeepsUnknownAsNone(TestCase):
    def test_absent_payment_and_asset_flags_stay_none(self):
        c = _parse_case({"creditors": [{"creditor_name": "Lendable", "balance": 500}]})
        self.assertIsNone(c["creditors"][0]["first_payment_made"])
        self.assertIsNone(c["creditors"][0]["client_still_has_asset_in_possession"])

    def test_antecedent_transactions_is_tri_state(self):
        from debt_app.engine.criteria import _watch_22_13
        base = {"creditors": [], "gold_transactions": [{"transaction_date": "2026-08-01",
                                                          "description": "x", "amount": -1,
                                                          "transaction_type": "money_out"}]}
        self.assertIs(False, _parse_case({**base, "antecedent_transactions": False})["antecedent_transactions"])
        self.assertIsNone(_parse_case({**base, "antecedent_transactions": None})["antecedent_transactions"])
        self.assertIs(True, _parse_case({**base, "antecedent_transactions": True})["antecedent_transactions"])
        # A scan that found nothing passes; "never looked" asks the caseworker.
        self.assertFalse(_watch_22_13(_parse_case({**base, "antecedent_transactions": False})).triggered)
        self.assertTrue(_watch_22_13(_parse_case({**base, "antecedent_transactions": None})).triggered)

    def test_explicit_values_are_kept(self):
        c = _parse_case({"creditors": [{
            "creditor_name": "Lendable", "balance": 500,
            "first_payment_made": False, "client_still_has_asset_in_possession": True,
        }]})
        self.assertIs(c["creditors"][0]["first_payment_made"], False)
        self.assertIs(c["creditors"][0]["client_still_has_asset_in_possession"], True)

    def test_unknown_payment_history_asks_the_caseworker_rather_than_rejecting(self):
        CreditorCriteria.objects.create(
            creditor_name="Strict Lender", representative="NONE", status="ACCEPT",
            reject_if_never_made_payment=True, is_active=True,
        )
        case = _parse_case({"creditors": [{"creditor_name": "Strict Lender", "balance": 900}]})
        case.update({"aryza_reference": "T", "client_name": "T"})
        pos = _check_creditor_individual(case)[0]
        codes = [f["code"] for f in pos["findings"]]
        self.assertIn("CREDITOR-PAYMENT-UNVERIFIED", codes)
        self.assertNotIn("CREDITOR-NO-PAYMENT", codes)
        self.assertNotEqual(pos["effective_status"], "REJECT")


class Tig10PlaceholderNames(TestCase):
    def test_placeholder_names_are_unidentified(self):
        for name in ("CCJ (creditor not yet identified)", "Unknown Creditor",
                     "unknown", "OTHER", "CCJ", ""):
            with self.subTest(name=name):
                self.assertTrue(_is_unidentified_creditor_name(name))
        for name in ("Lendable", "CCI Credit Management Limited", "Other Lender Ltd"):
            with self.subTest(name=name):
                self.assertFalse(_is_unidentified_creditor_name(name))

    def test_an_unidentified_debt_over_1k_hard_blocks(self):
        # Case 412926: two CCJs with no named claimant, £1,471 and £712.
        c = {
            "creditors": [
                _creditor(0, "CCJ (creditor not yet identified)", 1471),
                _creditor(1, "CCJ (creditor not yet identified)", 712),
                _creditor(2, "Lendable", 9000),
            ],
            "total_debt": 11183.0,
        }
        r = _tig_10(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertIn("1,471", r.message)

    def test_sub_1k_only_is_a_flag_when_not_load_bearing(self):
        c = {"creditors": [_creditor(0, "OTHER", 712), _creditor(1, "Lendable", 9000)],
             "total_debt": 9712.0}
        r = _tig_10(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")

    def test_secured_rows_are_outside_the_check(self):
        c = {"creditors": [_creditor(0, "CCJ", 5000, secured=True), _creditor(1, "Lendable", 9000)],
             "total_debt": 9000.0}
        self.assertFalse(_tig_10(c).triggered)


class SecuredCreditorsStayOutOfUnsecuredMaths(TestCase):
    def test_majority_numerator_ignores_a_secured_accept(self):
        # £6k unsecured (half ACCEPT, half REJECT) + a £112k mortgage the DB
        # says ACCEPTs. Without the guard the mortgage alone carried the vote.
        rows = [(0, "Lendable", 3000, "ACCEPT"), (1, "Zopa", 3000, "REJECT")]
        creditors = [_creditor(i, n, b) for i, n, b, _ in rows]
        creditors.append(_creditor(2, "Barclays Bank", 112798, secured=True))
        positions = [_position(i, n, s) for i, n, _, s in rows]
        positions.append(_position(2, "Barclays Bank", "ACCEPT", secured=True))
        ma = _compute_majority_analysis({"creditors": creditors, "total_debt": 6000.0}, positions)
        self.assertEqual(ma["voting_debt"], Decimal("3000"))
        self.assertEqual(ma["threshold"], Decimal("4500.00"))
        self.assertFalse(ma["achievable"])
        self.assertEqual(ma["unknown_creditors"], [])

    def test_a_secured_lender_is_not_a_qualifying_lender(self):
        creditors = [
            {"name": "Halifax", "balance": 9000.0},
            {"name": "Newcastle Building Society", "balance": 134386.0, "is_secured": True},
        ]
        self.assertEqual(["Halifax"], _count_qualifying_lenders(creditors, 500.0))

    def test_a_secured_lender_that_does_not_vote_is_not_a_review_trigger(self):
        positions = [
            _position(0, "Lendable", "ACCEPT"),
            _position(1, "Motonovo Finance", "DO_NOT_VOTE", secured=True),
        ]
        self.assertEqual("IVA_VIABLE", _derive_recommended_solution([], [], positions))
        positions.append(_position(2, "Some Council", "DO_NOT_VOTE"))
        self.assertEqual("REVIEW_REQUIRED", _derive_recommended_solution([], [], positions))

    def test_a_secured_lender_alone_does_not_bring_in_its_rep_body(self):
        # The migrations seed the real creditor table; pin the row we rely on.
        CreditorCriteria.objects.update_or_create(
            creditor_name="Black Horse",
            defaults={"representative": "WATCH", "status": "ACCEPT", "is_active": True},
        )
        secured_only = [{"creditor_name": "Black Horse", "balance": 8000.0, "is_secured": True}]
        self.assertEqual(set(), detect_representatives(secured_only, assessment_date=date(2026, 9, 1)))
        with_unsecured = secured_only + [{"creditor_name": "Black Horse", "balance": 400.0, "is_secured": False}]
        self.assertEqual({"WATCH"}, detect_representatives(with_unsecured, assessment_date=date(2026, 9, 1)))


class DeclaredHpInstalment(TestCase):
    """WATCH-22.10 / TIX-04 read the declared instalment on the case's
    vehicle-HP creditors, not only the bank scan (which missed every lender
    outside its keyword list and reported £0.00)."""

    from debt_app.engine.criteria import _tix_04, _watch_22_10  # noqa: E402

    def _case(self, monthly, gold=None, name="Moneybarn"):
        return _parse_case({
            "assessment_date": "2026-09-01",
            "gold_transactions": gold,
            "creditors": [
                {"creditor_name": name, "balance": 5414.0, "creditor_type": "car_hp",
                 "is_secured": True, "monthly_repayment": monthly},
                {"creditor_name": "Lendable", "balance": 3000.0, "creditor_type": "unsecured_loan"},
            ],
        })

    def test_declared_instalment_is_evaluated_without_bank_data(self):
        c = self._case(315.0)
        self.assertEqual(315.0, c["vehicle_hp_monthly"])
        r = self.__class__._tix_04(c)
        self.assertTrue(r.triggered)
        self.assertEqual("flag", r.severity)
        self.assertIn("declared instalment", r.message)
        self.assertFalse(self.__class__._watch_22_10(c).triggered)  # £315 < £400

    def test_no_bank_data_and_no_declared_figure_still_asks_the_caseworker(self):
        r = self.__class__._watch_22_10(self._case(None))
        self.assertTrue(r.triggered)
        self.assertIn("could not be checked", r.message)

    def test_the_bank_scan_recognises_the_named_lender(self):
        gold = [{"transaction_date": "2026-08-20", "description": "DD MONEYBARN NO 1 LTD",
                 "amount": -450.0, "transaction_type": "money_out"}]
        c = self._case(315.0, gold=gold)
        self.assertEqual(450.0, c["vehicle_hp_monthly"])
        self.assertTrue(self.__class__._watch_22_10(c).triggered)


class SingleLenderWithUnidentifiedCreditors(TestCase):
    from debt_app.engine.criteria import _watch_22_5  # noqa: E402

    def test_an_unidentified_creditor_over_500_makes_the_answer_a_flag_not_a_block(self):
        c = {"creditors": [
            {"name": "Halifax", "balance": 9000.0},
            {"name": "CCJ (creditor not yet identified)", "balance": 1471.0},
        ]}
        r = self.__class__._watch_22_5(c)
        self.assertTrue(r.triggered)
        self.assertEqual("flag", r.severity)
        self.assertIn("not yet identified", r.message)

    def test_a_named_second_lender_still_passes_and_a_lone_lender_still_blocks(self):
        two = {"creditors": [{"name": "Halifax", "balance": 9000.0}, {"name": "Zopa", "balance": 600.0}]}
        self.assertFalse(self.__class__._watch_22_5(two).triggered)
        one = {"creditors": [{"name": "Halifax", "balance": 9000.0},
                             {"name": "OTHER", "balance": 200.0}]}
        r = self.__class__._watch_22_5(one)
        self.assertEqual("hard_block", r.severity)


class Watch227ChildrenAges(TestCase):
    """Threshold and severity are the engine's existing ones (over 13, hard
    block); what is tested is that ages are read as sent and that an unknown
    age is neither "under 13" nor "over 13"."""

    from debt_app.engine.criteria import _watch_22_7  # noqa: E402

    def _case(self, ages, paragraph=None):
        return {"children": [{"age": a} for a in ages], "sustainability_paragraph_present": paragraph}

    def test_13_passes_14_15_16_block_without_a_paragraph(self):
        self.assertFalse(self.__class__._watch_22_7(self._case([13])).triggered)
        for age in (14, 15, 16):
            with self.subTest(age=age):
                r = self.__class__._watch_22_7(self._case([age]))
                self.assertTrue(r.triggered)
                self.assertEqual("hard_block", r.severity)

    def test_a_paragraph_clears_the_block(self):
        self.assertFalse(self.__class__._watch_22_7(self._case([15], paragraph=True)).triggered)

    def test_no_children(self):
        self.assertFalse(self.__class__._watch_22_7({"children": [], "sustainability_paragraph_present": None}).triggered)

    def test_mixed_ages_block_on_the_oldest(self):
        r = self.__class__._watch_22_7(self._case([3, 9, 14]))
        self.assertEqual("hard_block", r.severity)
        self.assertFalse(self.__class__._watch_22_7(self._case([3, 9, 13])).triggered)

    def test_a_missing_age_is_a_flag_not_a_pass_or_a_block(self):
        r = self.__class__._watch_22_7(self._case([None]))
        self.assertTrue(r.triggered)
        self.assertEqual("flag", r.severity)
        self.assertIn("no date of birth", r.message)
        r = self.__class__._watch_22_7(self._case([9, None]))
        self.assertEqual("flag", r.severity)
        # A known teenager decides regardless of an undated sibling.
        self.assertEqual("hard_block", self.__class__._watch_22_7(self._case([None, 14])).severity)


# Every rule function `assess_case` runs, by the rule_id it emits.
REGISTERED_RULE_IDS = frozenset({
    "TIG-01", "TIG-02", "TIG-03", "TIG-04", "TIG-05", "TIG-06", "TIG-07", "TIG-08", "TIG-09", "TIG-10",
    "TIG-11", "TIG-11-GAMBLING", "TIG-12", "TIG-13",
    "TIG-15.1", "TIG-15.2", "TIG-15.3", "TIG-15.4", "TIG-15.5", "TIG-15.6", "TIG-15.7", "TIG-15.8",
    "TIG-15.9", "TIG-15.10",
    "TIG-HMRC-VOTE-NOT-GUARANTEED", "TIG-HMRC-VAT-TRADING", "TIG-HMRC-PAYE-OBLIGATIONS",
    "TIG-HMRC-TAX-CREDITS", "TIG-HMRC-NI-CLASS", "TIG-HMRC-ONGOING-TRADING", "TIG-HMRC-ANTECEDENT",
    "TIG-16", "TIG-17", "TIG-18", "EQUITY-AGE", "TIG-19", "TIG-SHOP-DIRECT-4MO-REVIEW", "TIG-19.1",
    "TIG-20", "TIG-20.1", "TIG-21.1", "TIG-21.2", "TIG-21.3", "TIG-21.4", "TIG-21.5",
    "WATCH-22.12", "WATCH-22.7", "WATCH-22.11",
    "PHASE4-VW-TERMINATION", "PHASE4-DMP-REJECT", "PHASE4-COUNTY-COUNCIL",
    "WATCH-22.1", "WATCH-22.2", "WATCH-22.3", "WATCH-22.4", "WATCH-22.5", "WATCH-22.6", "WATCH-22.8",
    "WATCH-22.9", "WATCH-22.10", "WATCH-22.13", "WATCH-22.14",
    "TIX-01", "TIX-02", "TIX-03", "TIX-04", "TIX-05", "TIX-06", "TIX-07",
    "EVOLVE-01", "EVOLVE-02", "EVOLVE-03",
})


class EveryRegisteredRuleAnswersExactlyOnce(TestCase):
    def test_all_bodies_detected(self):
        from debt_app.engine.criteria import assess_case
        from debt_app.models import GlobalCriteria
        disabled = set(GlobalCriteria.objects.filter(is_active=False).values_list("rule_key", flat=True))
        result = assess_case({
            "application_id": "T-ALL", "assessment_date": "2026-09-01",
            "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
            "creditors": [{"creditor_name": "Lendable", "balance": 9000.0, "creditor_type": "unsecured_loan"}],
            "documents": [], "gold_transactions": None, "evidence_ledger": [],
        }, detected_representatives={"WATCH", "TIX", "EVOLVE"})
        seen = []
        for k in ("hard_blocks", "flags", "info", "passed"):
            seen.extend(r.rule_id for r in result[k])
        registered_seen = [rid for rid in seen if rid in REGISTERED_RULE_IDS]
        self.assertEqual(len(registered_seen), len(set(registered_seen)),
                         "a registered rule answered more than once")
        expected = REGISTERED_RULE_IDS - disabled
        self.assertEqual(set(), expected - set(seen), "registered rules missing from the result")
        self.assertEqual(set(), set(registered_seen) & disabled, "a disabled rule still answered")
        self.assertEqual(72, len(REGISTERED_RULE_IDS))

    def test_disabling_by_the_emitted_rule_id_works_for_every_rule(self):
        """⚠️ Several rules emit an id that differs from their function name
        (`_tig_11_gambling` -> TIG-11-GAMBLING, the HMRC rules, TIG-19's
        review). Disabling those in `GlobalCriteria` used to have no effect."""
        from debt_app.engine.criteria import assess_case
        from debt_app.models import GlobalCriteria
        for rid in ("TIG-11-GAMBLING", "TIG-HMRC-VAT-TRADING", "TIG-SHOP-DIRECT-4MO-REVIEW"):
            GlobalCriteria.objects.update_or_create(rule_key=rid, defaults={
                "is_active": False, "criteria_set": "TIG", "rule_name": rid, "severity": "flag"})
        result = assess_case({
            "application_id": "T-DIS", "assessment_date": "2026-09-01",
            "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
            "creditors": [{"creditor_name": "HMRC", "balance": 9000.0, "creditor_type": "vat"}],
            "documents": [], "gold_transactions": None, "evidence_ledger": [],
        }, detected_representatives=set())
        seen = {r.rule_id for k in ("hard_blocks", "flags", "info", "passed") for r in result[k]}
        self.assertNotIn("TIG-11-GAMBLING", seen)
        self.assertNotIn("TIG-HMRC-VAT-TRADING", seen)
        self.assertNotIn("TIG-SHOP-DIRECT-4MO-REVIEW", seen)
        self.assertIn("TIG-HMRC-PAYE-OBLIGATIONS", seen)


class CreditorLookupCacheTests(TestCase):
    def test_a_name_is_resolved_once_per_assessment_and_never_across_them(self):
        from unittest import mock
        from debt_app import helpers
        from debt_app.helpers import creditor_lookup_cache, get_creditor_by_trading_name
        CreditorCriteria.objects.update_or_create(
            creditor_name="Lendable", defaults={"representative": "NONE", "status": "ACCEPT", "is_active": True})
        with mock.patch.object(helpers, "_get_creditor_by_trading_name_uncached",
                               wraps=helpers._get_creditor_by_trading_name_uncached) as inner:
            with creditor_lookup_cache():
                a = get_creditor_by_trading_name("Lendable")
                b = get_creditor_by_trading_name("lendable ")
                with self.assertRaises(CreditorCriteria.DoesNotExist):
                    get_creditor_by_trading_name("No Such Lender")
                with self.assertRaises(CreditorCriteria.DoesNotExist):
                    get_creditor_by_trading_name("No Such Lender")
            self.assertEqual(2, inner.call_count)  # one hit, one miss
            self.assertEqual(a.pk, b.pk)
            get_creditor_by_trading_name("Lendable")  # outside the context: not cached
            self.assertEqual(3, inner.call_count)


class DirectAssessReturnsTheSecuredTag(TestCase):
    """The case-assessment tool splits secured positions back out of its vote
    table; it can only do that if the API says which positions those are."""

    def setUp(self):
        self.client = APIClient()
        # The migrations seed the real creditor table; pin the row we rely on.
        CreditorCriteria.objects.update_or_create(
            creditor_name="Lendable",
            defaults={"representative": "NONE", "status": "ACCEPT", "is_active": True},
        )

    def test_positions_carry_is_secured(self):
        payload = {
            "application_id": "T-SEC-1",
            "assessment_date": "2026-09-01",
            "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
            "creditors": [
                {"creditor_name": "Lendable", "balance": 9000.0, "creditor_type": "unsecured_loan",
                 "is_secured": False},
                {"creditor_name": "Motonovo Finance", "balance": 19975.0,
                 "creditor_type": "hire_purchase_shortfall", "is_secured": True},
            ],
            "documents": [], "gold_transactions": None, "evidence_ledger": [],
        }
        resp = self.client.post("/api/v1/assess/", data=json.dumps(payload),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = json.loads(resp.content)
        by_name = {p["creditor_name"]: p for p in body["creditor_positions"]}
        self.assertIn("is_secured", by_name["Lendable"])
        self.assertFalse(by_name["Lendable"]["is_secured"])
        secured = [p for p in body["creditor_positions"] if p["is_secured"]]
        self.assertEqual(1, len(secured), body["creditor_positions"])
        self.assertEqual(19975.0, secured[0]["balance"])
        # The unsecured book is what the majority is measured over.
        self.assertEqual(9000.0, body["majority_analysis"]["total_debt"])

    def test_a_blocked_hp_lender_and_a_mortgage_are_evaluated_but_do_not_vote(self):
        CreditorCriteria.objects.update_or_create(
            creditor_name="Advantage Finance",
            defaults={"representative": "NONE", "status": "ACCEPT", "is_active": True,
                      "blocked_until_cleared": True, "blocked_reason": "Blocked until car returned"},
        )
        payload = {
            "application_id": "T-SEC-2", "assessment_date": "2026-09-01",
            "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
            "creditors": [
                {"creditor_name": "Lendable", "balance": 9000.0, "creditor_type": "unsecured_loan", "is_secured": False},
                {"creditor_name": "Advantage Finance", "balance": 16010.0, "creditor_type": "car_hp",
                 "is_secured": True, "monthly_repayment": 263.0},
                {"creditor_name": "Newcastle Building Society", "balance": 134386.0,
                 "creditor_type": "mortgage", "is_secured": True, "monthly_repayment": 692.0},
            ],
            "documents": [], "gold_transactions": None, "evidence_ledger": [],
        }
        resp = self.client.post("/api/v1/assess/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = json.loads(resp.content)
        # The HP lender's own rule still surfaces as a case-level hard block...
        self.assertIn("CREDITOR-BLOCKED", [r["rule_id"] for r in body["hard_blocks"]])
        secured = {p["creditor_name"]: p for p in body["creditor_positions"] if p["is_secured"]}
        self.assertEqual({"Advantage Finance", "Newcastle Building Society"}, set(secured))
        self.assertEqual("REJECT", secured["Advantage Finance"]["effective_status"])
        self.assertEqual(16010.0, secured["Advantage Finance"]["balance"])
        # ...and neither secured row is in the vote.
        maj = body["majority_analysis"]
        self.assertEqual(9000.0, maj["total_debt"])
        self.assertEqual(9000.0, maj["voting_pool"])
        self.assertEqual(9000.0, maj["voting_debt"])
        self.assertTrue(maj["achievable"])
        self.assertEqual(1, len([p for p in body["creditor_positions"] if not p["is_secured"]]))

    def test_no_secured_creditors_means_no_secured_positions(self):
        payload = {
            "application_id": "T-SEC-3", "assessment_date": "2026-09-01",
            "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
            "creditors": [{"creditor_name": "Lendable", "balance": 9000.0,
                           "creditor_type": "unsecured_loan", "is_secured": False}],
            "documents": [], "gold_transactions": None, "evidence_ledger": [],
        }
        resp = self.client.post("/api/v1/assess/", data=json.dumps(payload), content_type="application/json")
        body = json.loads(resp.content)
        self.assertEqual([False], [p["is_secured"] for p in body["creditor_positions"]])
