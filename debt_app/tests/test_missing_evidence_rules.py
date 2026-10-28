"""
Phase 3 of the Case Rejection Criteria (Missing Evidence) work: the evidence
rules. Each applies only when its trigger is met, and reads CAT's tri-state
evidence fields: True passes, None (CAT does not know) flags, False returns
the case (hard_block). POD-OVER-500 is always a flag. All seven are seeded
switched off (migration 0094) until CAT sends the fields.
"""
from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import (
    _arrears_creditor_call,
    _ccj_original_creditor,
    _council_tax_evidence,
    _debt_level_evidenced,
    _hmrc_call_sheet,
    _parse_case,
    _pod_over_500,
    _self_employed_call_sheet,
    assess_case,
)
from debt_app.models import CouncilRule, GlobalCriteria

RULE_KEYS = [
    "HMRC-CALL-SHEET", "SELF-EMPLOYED-CALL-SHEET", "ARREARS-CREDITOR-CALL",
    "DEBT-LEVEL-EVIDENCED", "POD-OVER-500", "COUNCIL-TAX-EVIDENCE", "CCJ-ORIGINAL-CREDITOR",
]


def _parsed(creditors=None, **extra):
    case = {
        "assessment_date": "2026-10-27",
        "creditors": creditors if creditors is not None else [{"creditor_name": "Lendable", "balance": 7000}],
    }
    case.update(extra)
    return _parse_case(case)


def _outcome(r):
    return "pass" if not r.triggered else r.severity


class HmrcCallSheetTest(SimpleTestCase):

    @staticmethod
    def _hmrc(**fields):
        return [{"creditor_name": "HMRC", "balance": 7000, **fields}]

    def test_not_triggered_without_hmrc(self):
        self.assertEqual(_outcome(_hmrc_call_sheet(_parsed())), "pass")

    def test_tri_state_on_the_hmrc_creditor(self):
        self.assertEqual(_outcome(_hmrc_call_sheet(_parsed(self._hmrc(creditor_call_completed=True)))), "pass")
        self.assertEqual(_outcome(_hmrc_call_sheet(_parsed(self._hmrc()))), "flag")
        self.assertEqual(_outcome(_hmrc_call_sheet(_parsed(self._hmrc(creditor_call_completed=False)))), "hard_block")

    def test_client_level_call_sheet_is_not_the_hmrc_call(self):
        c = _parsed(self._hmrc(creditor_call_completed=False), has_call_sheet=True)
        self.assertEqual(_outcome(_hmrc_call_sheet(c)), "hard_block")

    def test_every_hmrc_creditor_needs_its_call(self):
        c = _parsed([
            {"creditor_name": "HMRC", "balance": 7000, "creditor_call_completed": True},
            {"creditor_name": "HM Revenue & Customs (VAT)", "balance": 3000, "creditor_call_completed": False},
        ])
        r = _hmrc_call_sheet(c)
        self.assertEqual(_outcome(r), "hard_block")
        self.assertEqual(r.creditors, ["HM Revenue & Customs (VAT)"])


class SelfEmployedCallSheetTest(SimpleTestCase):

    def _c(self, **extra):
        return _parsed(financial_summary={"income_source": "self_employed"}, **extra)

    def test_not_self_employed(self):
        self.assertEqual(_outcome(_self_employed_call_sheet(_parsed(has_call_sheet=False))), "pass")

    def test_under_12_months_passes(self):
        c = self._c(self_employed_since="2025-10-28", has_call_sheet=False)
        self.assertEqual(_outcome(_self_employed_call_sheet(c)), "pass")

    def test_12_months_or_more_requires_call_sheet(self):
        since = "2025-10-27"
        self.assertEqual(_outcome(_self_employed_call_sheet(self._c(self_employed_since=since, has_call_sheet=True))), "pass")
        self.assertEqual(_outcome(_self_employed_call_sheet(self._c(self_employed_since=since))), "flag")
        self.assertEqual(_outcome(_self_employed_call_sheet(self._c(self_employed_since=since, has_call_sheet=False))), "hard_block")

    def test_unknown_start_date(self):
        self.assertEqual(_outcome(_self_employed_call_sheet(self._c(has_call_sheet=False))), "flag")
        self.assertEqual(_outcome(_self_employed_call_sheet(self._c(has_call_sheet=True))), "pass")


class ArrearsCreditorCallTest(SimpleTestCase):

    def test_no_arrears_creditors(self):
        self.assertEqual(_outcome(_arrears_creditor_call(_parsed())), "pass")

    def test_each_arrears_type_is_in_scope(self):
        for creditor_type in ("mortgage", "rent_arrears", "hire purchase"):
            with self.subTest(creditor_type=creditor_type):
                c = _parsed([{"creditor_name": "X", "balance": 900, "creditor_type": creditor_type,
                              "in_arrears": True, "creditor_call_completed": False}])
                self.assertEqual(_outcome(_arrears_creditor_call(c)), "hard_block")

    def test_mixed_missing_and_unknown_is_hard_block_naming_both(self):
        c = _parsed([
            {"creditor_name": "Landlord Ltd", "balance": 1200, "creditor_type": "rent", "creditor_call_completed": False},
            {"creditor_name": "Close Brothers", "balance": 5000, "creditor_type": "hire purchase", "in_arrears": True},
            {"creditor_name": "Nationwide", "balance": 800, "creditor_type": "mortgage", "in_arrears": True,
             "creditor_call_completed": True},
        ])
        r = _arrears_creditor_call(c)
        self.assertEqual(_outcome(r), "hard_block")
        self.assertEqual(r.creditors, ["Landlord Ltd", "Close Brothers"])
        self.assertIn("rent arrears", r.message)

    def test_unknown_only_flags(self):
        c = _parsed([{"creditor_name": "Close Brothers", "balance": 5000, "creditor_type": "hire purchase",
                      "in_arrears": True}])
        self.assertEqual(_outcome(_arrears_creditor_call(c)), "flag")

    def test_mortgage_or_hp_not_in_arrears_needs_no_call(self):
        for creditor_type in ("mortgage", "hire purchase"):
            with self.subTest(creditor_type=creditor_type):
                c = _parsed([{"creditor_name": "X", "balance": 90000, "creditor_type": creditor_type,
                              "in_arrears": False, "creditor_call_completed": False}])
                self.assertEqual(_outcome(_arrears_creditor_call(c)), "pass")

    def test_arrears_not_known_only_flags_never_returns_the_case(self):
        c = _parsed([{"creditor_name": "Nationwide", "balance": 90000, "creditor_type": "mortgage",
                      "creditor_call_completed": False}])
        r = _arrears_creditor_call(c)
        self.assertEqual(_outcome(r), "flag")
        self.assertIn("not known whether these accounts are in arrears", r.message)
        self.assertEqual(r.creditors, ["Nationwide"])

    def test_arrears_not_known_but_call_done_passes(self):
        c = _parsed([{"creditor_name": "Nationwide", "balance": 90000, "creditor_type": "mortgage",
                      "creditor_call_completed": True}])
        self.assertEqual(_outcome(_arrears_creditor_call(c)), "pass")

    def test_current_account_is_not_rent(self):
        c = _parsed([{"creditor_name": "Barclays", "balance": 900, "creditor_type": "current_account",
                      "creditor_call_completed": False}])
        self.assertEqual(_outcome(_arrears_creditor_call(c)), "pass")


class NormaliseRentTest(SimpleTestCase):

    def test_rent_is_a_word_not_a_substring(self):
        from debt_app.helpers import DEBT_TYPE_RENT, normalise_debt_type
        for raw in ("rent", "Rent", "rent_arrears", "Rent Arrears", "rent-arrears"):
            with self.subTest(raw=raw):
                self.assertEqual(normalise_debt_type(raw), DEBT_TYPE_RENT)
        for raw in ("current_account", "Current Account", "parent loan"):
            with self.subTest(raw=raw):
                self.assertNotEqual(normalise_debt_type(raw), DEBT_TYPE_RENT)


class DebtLevelEvidencedTest(SimpleTestCase):

    def test_pod_backed_debt_meets_minimum(self):
        c = _parsed([{"creditor_name": "A", "balance": 6000, "has_pod": True},
                     {"creditor_name": "B", "balance": 3000, "has_pod": False}])
        self.assertEqual(_outcome(_debt_level_evidenced(c)), "pass")

    def test_credit_report_match_counts_as_evidence(self):
        c = _parsed([{"creditor_name": "A", "balance": 6500, "from_credit_report": True}])
        self.assertEqual(_outcome(_debt_level_evidenced(c)), "pass")

    def test_unknown_pods_could_reach_minimum_flags(self):
        c = _parsed([{"creditor_name": "A", "balance": 3000, "has_pod": True},
                     {"creditor_name": "B", "balance": 4000}])
        r = _debt_level_evidenced(c)
        self.assertEqual(_outcome(r), "flag")
        self.assertEqual(r.actual_value, 3000)

    def test_cannot_reach_minimum_returns_case(self):
        c = _parsed([{"creditor_name": "A", "balance": 3000, "has_pod": True},
                     {"creditor_name": "B", "balance": 4000, "has_pod": False}])
        self.assertEqual(_outcome(_debt_level_evidenced(c)), "hard_block")

    def test_secured_debt_ignored(self):
        c = _parsed([{"creditor_name": "A", "balance": 3000, "has_pod": True},
                     {"creditor_name": "Mortgage", "balance": 90000, "has_pod": True, "is_secured": True}])
        self.assertEqual(_outcome(_debt_level_evidenced(c)), "hard_block")


class PodOver500Test(SimpleTestCase):

    def test_only_debts_over_500_and_only_ever_a_flag(self):
        c = _parsed([
            {"creditor_name": "Small", "balance": 500, "has_pod": False},
            {"creditor_name": "Missing", "balance": 501, "has_pod": False},
            {"creditor_name": "Unknown", "balance": 2000},
            {"creditor_name": "Held", "balance": 4000, "has_pod": True},
        ])
        r = _pod_over_500(c)
        self.assertEqual(_outcome(r), "flag")
        self.assertEqual(r.creditors, ["Missing", "Unknown"])

    def test_all_held_passes(self):
        c = _parsed([{"creditor_name": "Held", "balance": 7000, "has_pod": True},
                     {"creditor_name": "Small", "balance": 200, "has_pod": False}])
        self.assertEqual(_outcome(_pod_over_500(c)), "pass")


class CouncilTaxEvidenceTest(SimpleTestCase):

    def _run(self, status, findings=(), **creditor_fields):
        c = _parsed([{"creditor_name": "Testshire Council", "balance": 1500,
                      "creditor_type": "council tax", **creditor_fields}])
        positions = [{"_creditor_idx": 0, "effective_status": status,
                      "findings": [{"code": code} for code in findings]}]
        return _council_tax_evidence(c, positions)

    def test_no_council_tax(self):
        self.assertEqual(_outcome(_council_tax_evidence(_parsed(), [])), "pass")

    def test_non_voting_council_needs_pod(self):
        self.assertEqual(_outcome(self._run("DO_NOT_VOTE", has_pod=True)), "pass")
        self.assertEqual(_outcome(self._run("DO_NOT_VOTE")), "flag")
        r = self._run("DO_NOT_VOTE", has_pod=False, creditor_call_completed=True)
        self.assertEqual(_outcome(r), "hard_block")
        self.assertIn("proof of debt", r.message)

    def test_accepting_and_rejecting_councils_need_call_sheet(self):
        for status in ("ACCEPT", "REJECT"):
            with self.subTest(status=status):
                self.assertEqual(_outcome(self._run(status, creditor_call_completed=True)), "pass")
                r = self._run(status, creditor_call_completed=False, has_pod=True)
                self.assertEqual(_outcome(r), "hard_block")
                self.assertIn("before SIP", r.message)

    def test_div_council_needs_call_sheet(self):
        r = self._run("WILL_CONSIDER", findings=["INFO-MIN-DIVIDEND"], creditor_call_completed=False)
        self.assertEqual(_outcome(r), "hard_block")
        self.assertIn("DIV council", r.message)
        r = self._run("WILL_CONSIDER", div_returned=0.25, creditor_call_completed=False)
        self.assertEqual(_outcome(r), "hard_block")

    def test_will_consider_without_div_not_checked(self):
        self.assertEqual(_outcome(self._run("WILL_CONSIDER", creditor_call_completed=False)), "pass")

    def test_council_not_in_criteria_flags(self):
        c = _parsed([{"creditor_name": "Nowhere Council", "balance": 1500, "creditor_type": "council tax"}])
        r = _council_tax_evidence(c, [])
        self.assertEqual(_outcome(r), "flag")
        self.assertEqual(r.required_before, "drafting")

    # Phase 4: call sheets are needed before SIP; a POD has no stage, so it blocks drafting.
    def test_call_sheet_only_is_required_before_sip(self):
        self.assertEqual(self._run("ACCEPT", creditor_call_completed=False).required_before, "sip")
        self.assertEqual(self._run("ACCEPT").required_before, "sip")

    def test_missing_pod_is_required_before_drafting(self):
        self.assertEqual(self._run("DO_NOT_VOTE", has_pod=False).required_before, "drafting")

    def test_mixed_pod_and_call_sheet_is_drafting(self):
        c = _parsed([
            {"creditor_name": "A Council", "balance": 1500, "creditor_type": "council tax", "has_pod": False},
            {"creditor_name": "B Council", "balance": 1500, "creditor_type": "council tax", "creditor_call_completed": False},
        ])
        positions = [{"_creditor_idx": 0, "effective_status": "DO_NOT_VOTE", "findings": []},
                     {"_creditor_idx": 1, "effective_status": "REJECT", "findings": []}]
        self.assertEqual(_council_tax_evidence(c, positions).required_before, "drafting")


class RequiredBeforeDefaultTest(SimpleTestCase):

    def test_other_rules_default_to_drafting(self):
        c = _parsed([{"creditor_name": "HMRC", "balance": 7000, "creditor_call_completed": False}])
        self.assertEqual(_hmrc_call_sheet(c).required_before, "drafting")
        self.assertEqual(_pod_over_500(c).required_before, "drafting")


class CcjOriginalCreditorTest(SimpleTestCase):

    def test_not_majority(self):
        c = _parsed([{"creditor_name": "CCJ", "balance": 3000},
                     {"creditor_name": "Barclaycard", "balance": 4000}])
        self.assertEqual(_outcome(_ccj_original_creditor(c)), "pass")

    def test_majority_needs_original_creditor_for_each(self):
        c = _parsed([{"creditor_name": "CCJ", "balance": 4000, "original_creditor": "Vanquis"},
                     {"creditor_name": "Cabot", "balance": 2000, "has_ccj": True},
                     {"creditor_name": "Barclaycard", "balance": 1000}])
        r = _ccj_original_creditor(c)
        self.assertEqual(_outcome(r), "hard_block")
        self.assertEqual(r.creditors, ["Cabot"])

    def test_linked_creditor_counts(self):
        c = _parsed([{"creditor_name": "CCJ", "balance": 4000, "linked_creditor": "Vanquis"},
                     {"creditor_name": "Barclaycard", "balance": 1000}])
        self.assertEqual(_outcome(_ccj_original_creditor(c)), "pass")


class MissingEvidenceRulesAssessCaseTest(TestCase):
    """Through assess_case, with the GlobalCriteria rows migration 0094 seeds."""

    @staticmethod
    def _all_ids(result):
        return [r.rule_id for key in ("flags", "hard_blocks", "info", "passed") for r in result[key]]

    def _hmrc_case(self):
        return {
            "application_id": "ME-HMRC-1",
            "assessment_date": "2026-10-27",
            "creditors": [{"name": "HMRC", "balance": 9000.0, "creditor_type": "income_tax",
                           "creditor_call_completed": False}],
        }

    def test_migration_seeds_every_rule_switched_off(self):
        rows = {r.rule_key: r for r in GlobalCriteria.objects.filter(rule_key__in=RULE_KEYS)}
        self.assertEqual(set(rows), set(RULE_KEYS))
        self.assertTrue(all(not r.is_active for r in rows.values()))
        self.assertEqual(rows["POD-OVER-500"].severity, "flag")

    def test_switched_off_rules_do_not_run(self):
        ids = self._all_ids(assess_case(self._hmrc_case(), set()))
        for key in RULE_KEYS:
            self.assertNotIn(key, ids)

    def test_switched_on_rule_returns_the_case(self):
        GlobalCriteria.objects.filter(rule_key="HMRC-CALL-SHEET").update(is_active=True)
        result = assess_case(self._hmrc_case(), set())
        self.assertIn("HMRC-CALL-SHEET", [r.rule_id for r in result["hard_blocks"]])

    def test_council_tax_evidence_uses_the_councils_voting_position(self):
        GlobalCriteria.objects.filter(rule_key="COUNCIL-TAX-EVIDENCE").update(is_active=True)
        CouncilRule.objects.create(council_name="Testshire District Council", status="DO_NOT_VOTE")
        result = assess_case({
            "application_id": "ME-CT-1",
            "assessment_date": "2026-10-27",
            "creditors": [
                {"name": "Testshire District Council", "balance": 1500.0, "creditor_type": "council_tax",
                 "has_pod": False, "creditor_call_completed": True},
                {"name": "Generic Lender", "balance": 8000.0, "creditor_type": "personal_loan"},
            ],
        }, set())
        block = next(r for r in result["hard_blocks"] if r.rule_id == "COUNCIL-TAX-EVIDENCE")
        self.assertIn("Testshire District Council: proof of debt", block.message)
        self.assertEqual(block.required_before, "drafting")

    def test_required_before_reaches_the_criteria_api_dict(self):
        from debt_app.engine.criteria import RuleResult
        from debt_app.views.criteria_views import _rule_to_dict
        r = RuleResult(rule_id="X", severity="hard_block", triggered=True, message="m", required_before="sip")
        self.assertEqual(_rule_to_dict(r)["required_before"], "sip")
        self.assertEqual(_rule_to_dict({"rule_id": "X"})["required_before"], "drafting")
