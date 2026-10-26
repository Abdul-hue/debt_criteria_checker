"""
Module 4 shared creditor resolution (2026-10-21).

Module 4 (PHASE4-DMP-REJECT, PHASE4-VW-TERMINATION) looked CreditorCriteria up
by exact, case-sensitive creditor_name, with the alias map keyed by the
un-normalised name - a side effect of the 2026-05 refactor that moved the ORM
out of the rule functions, not a business rule. Module 5 resolved the same
creditors through the full matcher, so the two modules read different rows (or
Module 4 none). Module 4 now gets the row Module 5 uses, via
_resolve_creditor_criteria, resolved once in assess_case.

parent_group is deliberately NOT moved: it still comes from the old exact
lookup, so WATCH-22.5 / EVOLVE-02 lender grouping is unchanged (owner decision
2026-10-21, pending review of questionable matches and group tags).

ROWS mirror the scratch Criteria DB (789 active rows, 2026-10-21) in their real
id order; trading_names are the real values.
"""

import copy
from unittest import mock

from django.test import TestCase

from debt_app import helpers
from debt_app.engine import criteria as engine
from debt_app.engine.criteria import _resolve_creditor_criteria, assess_case
from debt_app.models import CreditorCriteria, GlobalCriteria

RETIRED = ("WATCH-22.4", "WATCH-22.6", "EVOLVE-01", "EVOLVE-02", "EVOLVE-03")

DMP_NAMES = {
    "Cambrian Credit Union Limited": "CAMBRIAN Credit Union",
    "CommSave Credit Union Limited": "Commsave Credit Union",
    "Commsave": "Commsave Credit Union",
}
VW_NAMES = (
    "VOLKSWAGEN FINANCE",
    "Volkswagen Financial Services (UK) Limited",
    "Volkswagen Financial Services (UK) Limited c/o Blake Morgan LLP",
    "Volkswagen Financial Services (UK) Limited c/o Lester Aldridge Solicitors",
    "Volkswagen Financial Services c/o Blake Morgan LLP",
)
# Phase 9 (manager 2026-10-21, option b): the organisation after "c/o" decides
# when it has an exact row, so this name is assessed as Shoosmiths LLP.
VW_CARE_OF_SHOOSMITHS = "Volkswagen Financial Services (UK) Limited c/o Shoosmiths LLP"

# (creditor_name, representative, status, trading_names, extra fields) - ascending real id
ROWS = (
    ("Zedbank", "WATCH", "ACCEPT", [], {"parent_group": "Zed Group"}),  # synthetic banking group
    ("Zedcard", "EVOLVE", "ACCEPT", [], {"parent_group": "Zed Group"}),
    ("EE FLEX PAY", "NONE", "ACCEPT", [], {}),  # #257 in the real data: no group, no Module 4 flags
    ("Volkswagen Financial Services", "NONE", "DO_NOT_VOTE",
     ["VW Financial Services", "Volkswagen Financial Services", "VWFS", "Volkswagen Finance", "VW Finance",
      "Volkswagen Financial Services UK Limited"],
     {"termination_risk_if_vehicle_on_finance": True}),  # #172
    ("Commsave Credit Union", "NONE", "WILL_CONSIDER",
     ["Commsave", "Commsave CU", "Commsave Credit Union Limited", "Commsave Credit Union Ltd"],
     {"reject_if_in_dmp": True}),  # #175
    ("CAMBRIAN Credit Union", "NONE", "WILL_CONSIDER",
     ["Cambrian", "Cambrian CU", "Cambrian Credit Union", "Cambrian Credit Union Limited"],
     {"reject_if_in_dmp": True}),  # #176
    ("Shoosmiths LLP", "NONE", "WILL_CONSIDER", [], {}),  # #706 - competes with VWFS for the c/o Shoosmiths name
)

BASE = {
    "assessment_date": "2026-10-15",
    "client": {"date_of_birth": "1985-01-01", "first_name": "Test", "last_name": "Case"},
    "financial_summary": {"net_balance": 450.0, "total_income": 2400.0, "income_source": "employed"},
    "documents": [
        {"document_type": "payslip", "is_valid": True, "document_date": "2026-10-01"},
        {"document_type": "bank_statement", "is_valid": True, "document_date": "2026-10-01",
         "extracted_data": {"statement_date": "2026-10-01", "account_holder": "Test Case"}},
    ],
    "gold_transactions": [],
    "is_currently_in_dmp": False,
}


def _case(creditors, **extra):
    case = copy.deepcopy(BASE)
    case["creditors"] = [{"name": n, "creditor_type": t, "balance": b} for n, t, b in creditors]
    case.update(extra)
    return case


def _ids(result, key):
    return {r.rule_id for r in result[key]}


def _votes(result):
    return [(p["creditor_name"], p["effective_status"]) for p in result["creditor_positions"]]


def _module4_map(payload):
    """The criteria_map assess_case hands to PHASE4-DMP-REJECT."""
    seen = {}
    real = engine._phase4_dmp_reject

    def spy(c, criteria_map):
        seen.update(criteria_map)
        return real(c, criteria_map)

    with mock.patch.object(engine, "_phase4_dmp_reject", spy):
        spy.__name__ = real.__name__
        result = assess_case(payload)
    return seen, result


class _Rows(TestCase):

    @classmethod
    def setUpTestData(cls):
        CreditorCriteria.objects.all().delete()
        for name, rep, status, trading, extra in ROWS:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status,
                                            trading_names=trading, is_active=True, **extra)


class SharedResolverTests(_Rows):

    def test_dmp_names_resolve_to_the_dmp_rejecting_rows(self):
        for name, row in DMP_NAMES.items():
            with self.subTest(name=name):
                crit = _resolve_creditor_criteria(name)
                self.assertEqual(row, crit.creditor_name)
                self.assertTrue(crit.reject_if_in_dmp)

    def test_vw_names_resolve_to_vwfs(self):
        # A solicitor with no row of its own (Blake Morgan, Lester Aldridge)
        # leaves the name on VWFS and its termination rule.
        for name in VW_NAMES:
            with self.subTest(name=name):
                crit = _resolve_creditor_criteria(name)
                self.assertEqual("Volkswagen Financial Services", crit.creditor_name)
                self.assertTrue(crit.termination_risk_if_vehicle_on_finance)

    def test_vw_care_of_shoosmiths_follows_shoosmiths(self):
        self.assertEqual("Shoosmiths LLP", _resolve_creditor_criteria(VW_CARE_OF_SHOOSMITHS).creditor_name)

    def test_other_vw_group_brands_are_still_unmapped(self):
        for name in ("Audi Financial Services", "Seat Financial Services", "Skoda"):
            with self.subTest(name=name), self.assertRaises(CreditorCriteria.DoesNotExist):
                _resolve_creditor_criteria(name)

    def test_module4_reads_the_row_module5_assesses(self):
        names = [*DMP_NAMES, *VW_NAMES, "Zedbank UK Plc", "EE FLEX PAY", "Unknown Lender Ltd"]
        seen, result = _module4_map(_case([(n, "credit_card", 3000.0) for n in names], is_currently_in_dmp=True))
        module5 = {p["original_aryza_name"] or p["creditor_name"]: p["creditor_name"]
                   for p in result["creditor_positions"] if "CREDITOR-UNKNOWN" not in (p.get("rule_ids") or [])}
        self.assertEqual({n: crit.creditor_name for n, crit in seen.items()}, module5)
        self.assertNotIn("Unknown Lender Ltd", seen)

    def test_each_creditor_is_resolved_once_per_assessment(self):
        names = [*DMP_NAMES, "VOLKSWAGEN FINANCE", "EE FLEX PAY", "Unknown Lender Ltd"]
        real = helpers._get_creditor_by_trading_name_uncached
        with mock.patch.object(helpers, "_get_creditor_by_trading_name_uncached", side_effect=real) as uncached:
            assess_case(_case([(n, "credit_card", 3000.0) for n in names], is_currently_in_dmp=True))
        keys = [call.args[0].strip().lower() for call in uncached.call_args_list]
        self.assertEqual(len(keys), len(set(keys)), "a creditor was resolved twice in one assessment")


class DmpRuleTests(_Rows):

    def test_resolved_names_now_block_a_client_in_a_dmp(self):
        for name in DMP_NAMES:
            with self.subTest(name=name):
                in_dmp = assess_case(_case([(name, "credit_card", 15000.0), ("EE FLEX PAY", "credit_card", 15000.0)],
                                           is_currently_in_dmp=True))
                not_in_dmp = assess_case(_case([(name, "credit_card", 15000.0), ("EE FLEX PAY", "credit_card", 15000.0)]))
                self.assertIn("PHASE4-DMP-REJECT", _ids(in_dmp, "hard_blocks"))
                self.assertNotIn("PHASE4-DMP-REJECT", _ids(not_in_dmp, "hard_blocks"))
                self.assertEqual(_votes(not_in_dmp), _votes(in_dmp))  # a case-level block, not a vote

    def test_exact_name_behaves_as_before(self):
        r = assess_case(_case([("Commsave Credit Union", "credit_card", 15000.0), ("EE FLEX PAY", "credit_card", 15000.0)],
                              is_currently_in_dmp=True))
        self.assertIn("PHASE4-DMP-REJECT", _ids(r, "hard_blocks"))

    def test_unrelated_creditors_do_not_block(self):
        r = assess_case(_case([("EE FLEX PAY", "credit_card", 15000.0), ("Unknown Lender Ltd", "credit_card", 15000.0)],
                              is_currently_in_dmp=True))
        self.assertNotIn("PHASE4-DMP-REJECT", _ids(r, "hard_blocks"))


class VwTerminationRuleTests(_Rows):

    def _assess(self, name):
        return assess_case(_case([(name, "hire_purchase", 5000.0), ("EE FLEX PAY", "credit_card", 30000.0)]))

    def test_resolved_vwfs_names_on_hp_block(self):
        for name in VW_NAMES:
            with self.subTest(name=name):
                self.assertIn("PHASE4-VW-TERMINATION", _ids(self._assess(name), "hard_blocks"))

    def test_hp_votes_are_unchanged_by_the_block(self):
        blocked = self._assess("VOLKSWAGEN FINANCE")
        exact = self._assess("Volkswagen Financial Services")
        self.assertEqual(dict(_votes(exact)), dict(_votes(blocked)))

    def test_exact_name_behaves_as_before(self):
        self.assertIn("PHASE4-VW-TERMINATION", _ids(self._assess("Volkswagen Financial Services"), "hard_blocks"))

    def test_unmapped_vw_group_brands_do_not_block(self):
        for name in ("Audi Financial Services", "Seat Financial Services", "Skoda"):
            with self.subTest(name=name):
                self.assertNotIn("PHASE4-VW-TERMINATION", _ids(self._assess(name), "hard_blocks"))


class ParentGroupUnchangedTests(_Rows):
    """'Zedbank UK Plc' resolves to Zedbank (Zed Group) through the substring step;
    the exact lookup misses it, so it must still count as its own lender."""

    def test_resolved_name_gets_no_parent_group(self):
        seen, result = _module4_map(_case([("Zedbank UK Plc", "credit_card", 15000.0),
                                           ("Zedcard", "credit_card", 15000.0)]))
        self.assertEqual("Zed Group", seen["Zedbank UK Plc"].parent_group)  # resolved for Module 4...
        self.assertNotIn("WATCH-22.5", _ids(result, "hard_blocks"))       # ...but not grouped

    def test_exact_names_are_still_grouped(self):
        r = assess_case(_case([("Zedbank", "credit_card", 15000.0), ("Zedcard", "credit_card", 15000.0)]))
        self.assertIn("WATCH-22.5", _ids(r, "hard_blocks"))


class EvolveStaysRetiredTests(_Rows):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for key in RETIRED:
            GlobalCriteria.objects.update_or_create(
                rule_key=key,
                defaults=dict(criteria_set=key.split("-")[0], rule_name=key, severity="hard_block", is_active=False),
            )

    def test_evolve_rules_do_not_run_and_evolve_votes_do_not_move(self):
        creditors = [("Zedcard", "credit_card", 15000.0), ("Commsave", "credit_card", 15000.0)]
        in_dmp = assess_case(_case(creditors, is_currently_in_dmp=True))
        not_in_dmp = assess_case(_case(creditors))
        for r in (in_dmp, not_in_dmp):
            self.assertFalse({"EVOLVE-01", "EVOLVE-02", "EVOLVE-03"} & (_ids(r, "hard_blocks") | _ids(r, "flags")))
            self.assertEqual("ACCEPT", r["representative_outcomes"]["EVOLVE"]["status"])
        self.assertIn("PHASE4-DMP-REJECT", _ids(in_dmp, "hard_blocks"))
        self.assertEqual(_votes(not_in_dmp), _votes(in_dmp))
        self.assertEqual(not_in_dmp["majority_analysis"], in_dmp["majority_analysis"])
