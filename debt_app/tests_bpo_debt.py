"""
BPO-DEBT tests.

A debt entered in Aryza under a debt collector (BPO, e.g. Marston) is not the
actual debt. The engine flags it (never blocks) so the caseworker changes the
creditor name to the debt provider and uploads POD from that provider. The
collectors live in the DebtCollector table.
"""

import io
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from debt_app.criteria_engine import _bpo_debt, _name_words, assess_case
from debt_app.models import DebtCollector, GlobalCriteria


def _collectors(*entries):
    """entries: (name, [aliases]) -> the pre-fetched shape _assess_case_impl builds."""
    return [(name, [_name_words(n) for n in [name, *aliases]]) for name, aliases in entries]


def _case(*creditors, collectors=None):
    return {
        "_debt_collectors": collectors if collectors is not None else _collectors(("Marston", [])),
        "creditors": [
            {"name": name, "original_name": original or name, "balance": balance}
            for name, original, balance in creditors
        ],
    }


class BpoDebtRuleTests(TestCase):
    def test_no_collector_debt_passes(self):
        r = _bpo_debt(_case(("Barclays", None, 5000.0)))
        self.assertFalse(r.triggered)
        self.assertEqual(r.severity, "pass")

    def test_collector_name_flags_with_remedy(self):
        r = _bpo_debt(_case(("Marston", None, 1250.0), ("Barclays", None, 5000.0)))
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.creditors, ["Marston"])
        self.assertIn("'Marston', balance £1,250, is with Marston, a debt collector", r.message)
        self.assertIn("Change the creditor name in Aryza to the actual debt provider", r.message)
        self.assertIn("upload proof of debt from that provider", r.message)

    def test_longer_name_and_punctuation_still_match(self):
        r = _bpo_debt(_case(("MARSTON (Holdings) Ltd.", None, 800.0)))
        self.assertTrue(r.triggered)

    def test_letters_inside_another_word_do_not_flag(self):
        r = _bpo_debt(_case(("Abmarstonia Finance", None, 900.0)))
        self.assertFalse(r.triggered)

    def test_alias_flags_and_names_the_collector(self):
        collectors = _collectors(("Marston", ["Jacobs Enforcement"]))
        r = _bpo_debt(_case(("Jacobs Enforcement Agents", None, 700.0), collectors=collectors))
        self.assertTrue(r.triggered)
        self.assertIn("is with Marston", r.message)

    def test_collector_only_in_original_aryza_name_flags(self):
        # Alias resolution can replace the Aryza name — the original still counts.
        r = _bpo_debt(_case(("Some Canonical Lender", "Marston Holdings", 900.0)))
        self.assertTrue(r.triggered)
        self.assertIn("'Marston Holdings'", r.message)

    def test_multi_word_collector_needs_whole_phrase(self):
        collectors = _collectors(("CCS Collect", []))
        self.assertTrue(_bpo_debt(_case(("CCS Collect Ltd", None, 100.0), collectors=collectors)).triggered)
        self.assertFalse(_bpo_debt(_case(("CCS Finance", None, 100.0), collectors=collectors)).triggered)

    def test_one_line_per_collector_debt(self):
        collectors = _collectors(("Marston", []), ("Moorcroft", []))
        r = _bpo_debt(_case(
            ("Marston", None, 100.0), ("Moorcroft Debt Recovery", None, 200.0), collectors=collectors,
        ))
        self.assertEqual(len(r.message.splitlines()), 2)
        self.assertEqual(r.creditors, ["Marston", "Moorcroft Debt Recovery"])

    def test_empty_list_never_flags(self):
        r = _bpo_debt(_case(("Marston", None, 100.0), collectors=[]))
        self.assertFalse(r.triggered)


class BpoDebtAssessCaseTests(TestCase):
    def _case_json(self, collector_name="Marston Holdings"):
        return {
            "creditors": [
                {"name": collector_name, "balance": 1250.0, "creditor_type": "personal_loan"},
                {"name": "Generic Lender", "balance": 9000.0, "creditor_type": "personal_loan"},
            ],
            "evidence_ledger": [],
        }

    def test_seeded_collector_flags_through_assess_case(self):
        # "Marston" is seeded by migration 0085.
        result = assess_case(self._case_json(), set())
        self.assertIn("BPO-DEBT", [f.rule_id for f in result["flags"]])
        self.assertNotIn("BPO-DEBT", [r.rule_id for r in result["hard_blocks"]])

    def test_inactive_collector_does_not_flag(self):
        DebtCollector.objects.filter(name="Marston").update(is_active=False)
        result = assess_case(self._case_json(), set())
        self.assertNotIn("BPO-DEBT", [f.rule_id for f in result["flags"]])

    def test_renamed_in_aryza_clears_flag(self):
        # The remedy: once Aryza holds the real debt provider, nothing is flagged.
        result = assess_case(self._case_json(collector_name="Barclays"), set())
        self.assertNotIn("BPO-DEBT", [f.rule_id for f in result["flags"]])

    def test_disabled_in_admin_does_not_run(self):
        GlobalCriteria.objects.filter(rule_key="BPO-DEBT").update(is_active=False)
        result = assess_case(self._case_json(), set())
        all_ids = [r.rule_id for key in ("flags", "hard_blocks", "info", "passed") for r in result[key]]
        self.assertNotIn("BPO-DEBT", all_ids)


class ImportDebtCollectorsCommandTests(TestCase):
    def _import(self, text, *args):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "collectors.csv"
            path.write_text(text, encoding="utf-8")
            call_command("import_debt_collectors", str(path), *args, stdout=io.StringIO())

    def test_creates_new_and_merges_aliases(self):
        self._import("name,aliases\nNew Collector,NC Ltd; New Coll\nMarston,Marston Holdings\n")
        self.assertEqual(DebtCollector.objects.get(name="New Collector").aliases, ["NC Ltd", "New Coll"])
        self.assertEqual(DebtCollector.objects.get(name="Marston").aliases, ["Marston Holdings"])

    def test_reactivates_existing_and_never_deletes(self):
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        before = DebtCollector.objects.count()
        self._import("moorcroft\n")
        self.assertTrue(DebtCollector.objects.get(name="Moorcroft").is_active)
        self.assertEqual(DebtCollector.objects.count(), before)

    def test_dry_run_saves_nothing(self):
        self._import("Dry Run Collector\n", "--dry-run")
        self.assertFalse(DebtCollector.objects.filter(name="Dry Run Collector").exists())
