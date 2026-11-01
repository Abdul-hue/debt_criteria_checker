"""
BPO-DEBT tests.

A debt entered in Aryza under a debt collector (BPO, e.g. Marston) is not the
actual debt. The engine flags it (never blocks) so the caseworker changes the
creditor name to the debt provider and uploads POD from that provider. The
collectors live in the DebtCollector table.
"""

import dataclasses
import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.criteria_engine import DEBT_COLLECTOR_LIST_FAILED_MESSAGE, _bpo_debt, _collector_key, assess_case
from debt_app.models import DebtCollector, GlobalCriteria


def _collectors(*entries):
    """entries: (name, [aliases]) -> the pre-fetched shape _assess_case_impl builds."""
    return [(name, {_collector_key(n) for n in [name, *aliases]}) for name, aliases in entries]


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
        self.assertIn("'Marston', balance £1,250, is with Marston, a Debt Collection Agency (DCA)", r.message)
        self.assertIn("Identify the actual creditor and correct the creditor name in Aryza", r.message)
        # The DCA's proof of debt is kept at this stage; the creditor's is needed too.
        self.assertIn("Do not reject the proof of debt from Marston at this stage", r.message)
        self.assertIn("proof of debt from the actual creditor will also be needed", r.message)
        self.assertNotIn("not from the collector", r.message)

    def test_case_punctuation_spacing_and_legal_form_are_ignored(self):
        collectors = _collectors(("Marston Holdings", []))
        for name in ("MARSTON (Holdings) Ltd.", "  marston   holdings ", "Marston-Holdings Limited",
                     "Marston Holdings PLC"):
            self.assertTrue(_bpo_debt(_case((name, None, 800.0), collectors=collectors)).triggered, name)

    def test_ampersand_and_and_are_the_same(self):
        collectors = _collectors(("Bristow & Sutor", []))
        self.assertTrue(_bpo_debt(_case(("Bristow and Sutor", None, 100.0), collectors=collectors)).triggered)
        collectors = _collectors(("Wilson and Roe", []))
        self.assertTrue(_bpo_debt(_case(("WILSON & ROE", None, 100.0), collectors=collectors)).triggered)

    def test_exact_not_contains(self):
        # The collector's words inside a longer name are not a match -- a
        # trading-name variant has to be an alias.
        for name in ("Marston Holdings", "Abmarstonia Finance", "Marston Council Tax", "Lend Marston"):
            self.assertFalse(_bpo_debt(_case((name, None, 900.0))).triggered, name)
        collectors = _collectors(("CCS Collect", []))
        self.assertTrue(_bpo_debt(_case(("CCS Collect Ltd", None, 100.0), collectors=collectors)).triggered)
        self.assertFalse(_bpo_debt(_case(("CCS Collect Services", None, 100.0), collectors=collectors)).triggered)
        self.assertFalse(_bpo_debt(_case(("CCS Finance", None, 100.0), collectors=collectors)).triggered)

    def test_co_is_part_of_the_name_not_a_legal_form(self):
        collectors = _collectors(("Constant & Co", []))
        self.assertTrue(_bpo_debt(_case(("Constant and Co.", None, 100.0), collectors=collectors)).triggered)
        self.assertFalse(_bpo_debt(_case(("Constant", None, 100.0), collectors=collectors)).triggered)

    def test_blank_name_never_flags(self):
        collectors = _collectors(("Marston", []))
        self.assertFalse(_bpo_debt(_case(("", "", 100.0), ("...", None, 1.0), collectors=collectors)).triggered)

    def test_alias_flags_and_names_the_collector(self):
        collectors = _collectors(("Direct Collection Bailiffs", ["DCBL"]))
        r = _bpo_debt(_case(("DCBL Ltd", None, 700.0), collectors=collectors))
        self.assertTrue(r.triggered)
        self.assertIn("is with Direct Collection Bailiffs", r.message)

    def test_collector_only_in_original_aryza_name_flags(self):
        # Alias resolution can replace the Aryza name — the original still counts.
        r = _bpo_debt(_case(("Some Canonical Lender", "Marston", 900.0)))
        self.assertTrue(r.triggered)
        self.assertIn("'Marston'", r.message)

    def test_same_collector_on_two_debts_is_two_lines(self):
        r = _bpo_debt(_case(("Marston", None, 100.0), ("MARSTON", None, 250.0)))
        self.assertEqual(len(r.message.splitlines()), 2)
        self.assertEqual(r.creditors, ["Marston", "MARSTON"])

    def test_one_line_per_collector_debt(self):
        collectors = _collectors(("Marston", []), ("Moorcroft", ["Moorcroft Debt Recovery"]))
        r = _bpo_debt(_case(
            ("Marston", None, 100.0), ("Moorcroft Debt Recovery", None, 200.0), collectors=collectors,
        ))
        self.assertEqual(len(r.message.splitlines()), 2)
        self.assertEqual(r.creditors, ["Marston", "Moorcroft Debt Recovery"])

    def test_empty_list_never_flags(self):
        r = _bpo_debt(_case(("Marston", None, 100.0), collectors=[]))
        self.assertFalse(r.triggered)

    # ⚠️ Penham Excel Ltd and Penham Excel High Court Enforcement Officers are
    # separate legal entities (Hammonds Group, 2026-10-30): two records, never
    # one the alias of the other.
    PENHAM = ("Penham Excel", ["Penham Excel Ltd", "Penham Excel Limited"])
    PENHAM_HCEO = ("Penham Excel High Court Enforcement Officers",
                   ["Penham Excel High Court Enforcement Officers Ltd",
                    "Penham Excel High Court Enforcement Officers Limited"])

    def test_penham_excel_names_match_their_own_record(self):
        collectors = _collectors(self.PENHAM, self.PENHAM_HCEO, ("Excel Civil Enforcement", []))
        for name, owner in (
            ("Penham Excel", "Penham Excel"),
            ("PENHAM EXCEL LTD.", "Penham Excel"),
            ("Penham Excel Limited", "Penham Excel"),
            ("Penham Excel High Court Enforcement Officers", "Penham Excel High Court Enforcement Officers"),
            ("Penham Excel High Court Enforcement Officers Ltd",
             "Penham Excel High Court Enforcement Officers"),
        ):
            r = _bpo_debt(_case((name, None, 500.0), collectors=collectors))
            self.assertTrue(r.triggered, name)
            self.assertIn(f"is with {owner}, a Debt Collection Agency", r.message, name)

    def test_advantis_and_advantis_credit_are_separate_organisations(self):
        # Advantis Credit keeps its own brand and identity (business, 2026-11-01):
        # its own record, never an alias of Advantis.
        both = _collectors(("Advantis", []), ("Advantis Credit", []))
        for name, owner in (("Advantis", "Advantis"), ("ADVANTIS LTD", "Advantis"),
                            ("Advantis Credit", "Advantis Credit"), ("Advantis Credit Limited", "Advantis Credit")):
            r = _bpo_debt(_case((name, None, 100.0), collectors=both))
            self.assertIn(f"is with {owner}, a Debt Collection Agency", r.message, name)
        self.assertFalse(_bpo_debt(_case(("Advantis Credit", None, 1.0),
                                          collectors=_collectors(("Advantis", [])))).triggered)
        self.assertFalse(_bpo_debt(_case(("Advantis", None, 1.0),
                                          collectors=_collectors(("Advantis Credit", [])))).triggered)
        self.assertFalse(_bpo_debt(_case(("Advantis Credit Card Services", None, 1.0), collectors=both)).triggered)

    def test_proof_of_debt_never_changes_the_result(self):
        # BPO-DEBT reads the name only: a DCA's POD is not rejected, and a
        # missing one adds nothing to this rule.
        results = []
        for has_pod in (True, False, None):
            case = _case(("Marston", None, 500.0))
            case["creditors"][0]["has_pod"] = has_pod
            r = _bpo_debt(case)
            results.append((r.severity, r.triggered, r.message))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(results[0][0], "flag")

    def test_penham_excel_records_are_not_merged(self):
        # Each record alone matches only its own names.
        only_ltd = _collectors(self.PENHAM)
        only_hceo = _collectors(self.PENHAM_HCEO)
        self.assertFalse(_bpo_debt(_case(("Penham Excel High Court Enforcement Officers", None, 1.0),
                                          collectors=only_ltd)).triggered)
        self.assertFalse(_bpo_debt(_case(("Penham Excel Ltd", None, 1.0), collectors=only_hceo)).triggered)
        # Neither is caught by the unrelated Excel Civil Enforcement, nor it by them.
        excel = _collectors(("Excel Civil Enforcement", []))
        self.assertFalse(_bpo_debt(_case(("Penham Excel", None, 1.0), collectors=excel)).triggered)
        both = _collectors(self.PENHAM, self.PENHAM_HCEO)
        self.assertFalse(_bpo_debt(_case(("Excel Civil Enforcement", None, 1.0), collectors=both)).triggered)
        self.assertEqual(_collector_key("Penham Excel Ltd"), "penham excel")
        self.assertNotEqual(_collector_key("Penham Excel Ltd"),
                            _collector_key("Penham Excel High Court Enforcement Officers Ltd"))


class BpoDebtAssessCaseTests(TestCase):
    def _case_json(self, collector_name="Marston Ltd"):
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

    def test_the_rule_row_is_named_dca_and_keeps_the_dca_pod(self):
        # Migration 0096: advisor-facing text; BPO-DEBT stays the key.
        rule = GlobalCriteria.objects.get(rule_key="BPO-DEBT")
        self.assertEqual(rule.rule_name, "Debt Collection Agency (DCA) listed instead of the actual creditor")
        self.assertIn("Do not reject the proof of debt from the DCA", rule.action)
        self.assertNotIn("not from the collector", rule.action)
        self.assertEqual((rule.severity, rule.is_active), ("flag", True))


class ImportDebtCollectorsCommandTests(TestCase):
    def _import(self, text, *args, filename="collectors.csv"):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / filename
            path.write_text(text, encoding="utf-8")
            call_command("import_debt_collectors", str(path), *args, stdout=out)
        return out.getvalue()

    def _keys_owned_once(self):
        keys = [_collector_key(n) for dc in DebtCollector.objects.all() for n in {dc.name, *(dc.aliases or [])}]
        keys = [k for k in keys if k]
        return len(keys) == len(set(keys))

    def test_a_name_another_collector_answers_to_is_a_reported_conflict(self):
        # "Marston Ltd" IS "Marston" once normalised: a second record would split the match.
        out = self._import("Marston Ltd\n")
        self.assertFalse(DebtCollector.objects.filter(name="Marston Ltd").exists())
        self.assertIn("[CONFLICT] skipped Marston Ltd", out)
        self.assertIn("1 conflicts skipped", out)

    def test_an_alias_already_on_another_collector_is_a_reported_conflict(self):
        out = self._import("name,aliases\nNew Agency,Moorcroft\n")
        self.assertFalse(DebtCollector.objects.filter(name="New Agency").exists())
        self.assertIn("[CONFLICT] skipped New Agency", out)

    def test_two_rows_in_one_file_with_the_same_key_keep_the_first(self):
        out = self._import("Zeta Collect\nZETA COLLECT LIMITED\n")
        self.assertEqual(list(DebtCollector.objects.filter(name__istartswith="zeta").values_list("name", flat=True)),
                         ["Zeta Collect"])
        self.assertIn("[CONFLICT] skipped ZETA COLLECT LIMITED", out)
        self.assertTrue(self._keys_owned_once())

    def test_a_repeated_row_is_reported_and_merges(self):
        out = self._import("name,aliases\nQuality Bailiffs,QB Ltd\nQuality Bailiffs,Quality Bailiff Services\n")
        self.assertEqual(DebtCollector.objects.get(name="Quality Bailiffs").aliases,
                         ["QB Ltd", "Quality Bailiff Services"])
        self.assertIn("[DUPLICATE ROW] Quality Bailiffs", out)

    def test_a_legal_name_alias_of_the_same_collector_is_not_a_conflict(self):
        out = self._import("name,aliases\nPenham Excel,Penham Excel Ltd; Penham Excel Limited\n")
        self.assertIn("1 created", out)
        self.assertIn("0 conflicts skipped", out)

    def test_txt_and_xlsx_files_import(self):
        self._import("Txt Agency\n", filename="list.txt")
        self.assertTrue(DebtCollector.objects.filter(name="Txt Agency").exists())
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "list.xlsx"
            wb = Workbook()
            wb.active.append(["name", "aliases"])
            wb.active.append(["Xlsx Agency", "Xlsx Agency Trading; XA Recoveries"])
            wb.active.append([None, None])
            wb.save(path)
            call_command("import_debt_collectors", str(path), stdout=io.StringIO())
        self.assertEqual(DebtCollector.objects.get(name="Xlsx Agency").aliases,
                         ["Xlsx Agency Trading", "XA Recoveries"])

    def _state(self):
        return list(DebtCollector.objects.order_by("name").values_list("name", "aliases", "is_active"))

    def test_dry_run_writes_nothing_even_for_updates(self):
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        before = self._state()
        out = self._import("name,aliases\nBrand New Agency,BNA\nMarston,Marston Holdings\nmoorcroft\n", "--dry-run")
        self.assertIn("[DRY RUN] 1 created, 1 updated, 0 unchanged, 0 reactivated, 1 inactive kept", out)
        self.assertEqual(before, self._state())

    def test_creates_new_and_merges_aliases(self):
        self._import("name,aliases\nNew Collector,NC Ltd; New Coll\nMarston,Marston Holdings\n")
        self.assertEqual(DebtCollector.objects.get(name="New Collector").aliases, ["NC Ltd", "New Coll"])
        self.assertEqual(DebtCollector.objects.get(name="Marston").aliases, ["Marston Holdings"])

    # ── an inactive collector (2026-11-01) ──────────────────────────────────

    def test_an_inactive_collector_stays_inactive_and_is_never_deleted(self):
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        before = DebtCollector.objects.count()
        out = self._import("moorcroft\n")
        self.assertFalse(DebtCollector.objects.get(name="Moorcroft").is_active)
        self.assertEqual(DebtCollector.objects.count(), before)
        self.assertIn("[INACTIVE — kept] Moorcroft", out)
        self.assertNotIn("[REACTIVATED]", out)
        self.assertIn("0 updated, 0 unchanged, 0 reactivated, 1 inactive kept", out)

    def test_an_inactive_collector_s_new_aliases_merge_but_it_stays_off(self):
        # Merged so a later switch-on has them; inactive, so they match nothing now.
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        out = self._import("name,aliases\nMoorcroft,Moorcroft Debt Recovery\nmoorcroft\n")
        dc = DebtCollector.objects.get(name="Moorcroft")
        self.assertEqual((dc.is_active, dc.aliases), (False, ["Moorcroft Debt Recovery"]))
        self.assertEqual(out.count("[INACTIVE — kept] Moorcroft"), 1, "reported once, though named twice")
        result = assess_case({"creditors": [{"name": "Moorcroft Debt Recovery", "balance": 100.0,
                                             "creditor_type": "personal_loan"}],
                              "evidence_ledger": []}, set())
        self.assertNotIn("BPO-DEBT", [f.rule_id for f in result["flags"]])

    def test_an_inactive_collector_s_names_still_block_a_conflicting_row(self):
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        out = self._import("Moorcroft Ltd\n")
        self.assertFalse(DebtCollector.objects.filter(name="Moorcroft Ltd").exists())
        self.assertIn("[CONFLICT] skipped Moorcroft Ltd", out)

    def test_reactivate_switches_on_only_the_inactive_collectors_named(self):
        DebtCollector.objects.filter(name__in=["Moorcroft", "BPO Collections"]).update(is_active=False)
        out = self._import("name,aliases\nmoorcroft,Moorcroft Debt Recovery\n", "--reactivate")
        moorcroft = DebtCollector.objects.get(name="Moorcroft")
        self.assertEqual((moorcroft.is_active, moorcroft.aliases), (True, ["Moorcroft Debt Recovery"]))
        self.assertFalse(DebtCollector.objects.get(name="BPO Collections").is_active, "not named: untouched")
        self.assertIn("[REACTIVATED] Moorcroft", out)
        self.assertNotIn("[INACTIVE — kept]", out)
        self.assertIn("1 updated, 0 unchanged, 1 reactivated, 0 inactive kept", out)

    def test_reactivate_without_new_aliases_still_switches_it_on(self):
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        out = self._import("moorcroft\n", "--reactivate")
        self.assertTrue(DebtCollector.objects.get(name="Moorcroft").is_active)
        self.assertIn("0 updated, 0 unchanged, 1 reactivated", out)

    def test_reactivate_leaves_active_collectors_as_they_were(self):
        before = self._state()
        out = self._import("Marston\nCCS Collect\n", "--reactivate")
        self.assertEqual(before, self._state())
        self.assertIn("0 created, 0 updated, 2 unchanged, 0 reactivated, 0 inactive kept", out)

    def test_a_dry_run_never_persists_a_reactivation_or_its_aliases(self):
        DebtCollector.objects.filter(name="Moorcroft").update(is_active=False)
        before = self._state()
        out = self._import("name,aliases\nMoorcroft,Moorcroft Debt Recovery\n", "--dry-run", "--reactivate")
        self.assertIn("[DRY RUN] [REACTIVATED] Moorcroft", out, "reported exactly as the real run would")
        self.assertIn("[DRY RUN] 0 created, 1 updated, 0 unchanged, 1 reactivated", out)
        self.assertEqual(before, self._state())
        real = self._import("name,aliases\nMoorcroft,Moorcroft Debt Recovery\n", "--reactivate")
        self.assertEqual(out.replace("[DRY RUN] ", ""), real, "dry run and real run say the same")

    def test_dry_run_saves_nothing(self):
        self._import("Dry Run Collector\n", "--dry-run")
        self.assertFalse(DebtCollector.objects.filter(name="Dry Run Collector").exists())

    def test_penham_excel_imports_as_two_records_and_flags_each_on_its_own(self):
        self._import(
            "name,aliases\n"
            "Penham Excel High Court Enforcement Officers,"
            "Penham Excel High Court Enforcement Officers Ltd; Penham Excel High Court Enforcement Officers Limited\n"
            "Penham Excel,Penham Excel Ltd; Penham Excel Limited\n")
        penham = DebtCollector.objects.filter(name__istartswith="Penham Excel").order_by("name")
        self.assertEqual(
            [(dc.name, dc.aliases) for dc in penham],
            [("Penham Excel", ["Penham Excel Ltd", "Penham Excel Limited"]),
             ("Penham Excel High Court Enforcement Officers",
              ["Penham Excel High Court Enforcement Officers Ltd",
               "Penham Excel High Court Enforcement Officers Limited"])])
        result = assess_case({
            "creditors": [
                {"name": "Penham Excel Ltd", "balance": 300.0, "creditor_type": "personal_loan"},
                {"name": "Penham Excel High Court Enforcement Officers", "balance": 700.0,
                 "creditor_type": "personal_loan"},
            ],
            "evidence_ledger": [],
        }, set())
        [flag] = [f for f in result["flags"] if f.rule_id == "BPO-DEBT"]
        lines = flag.message.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("is with Penham Excel, a Debt Collection Agency", lines[0])
        self.assertIn("is with Penham Excel High Court Enforcement Officers, a Debt Collection Agency", lines[1])


class BpoDebtLiabilityKeyTests(TestCase):
    """Each DCA hit names its debt by the caller's own key (CAT: the Aryza debt
    id, `aryza:<id>`) -- `liability_keys[i]` for `creditors[i]` -- never by
    name or balance (2026-10-31)."""

    def _keyed(self, *debts, collectors=None):
        return {
            "_debt_collectors": collectors if collectors is not None else _collectors(("Marston", [])),
            "creditors": [{"name": n, "original_name": n, "balance": b, "liability_key": k} for n, b, k in debts],
        }

    def test_same_dca_same_balance_two_keys(self):
        r = _bpo_debt(self._keyed(("Marston", 500.0, "aryza:1"), ("Barclays", 500.0, "aryza:2"),
                                  ("Marston", 500.0, "aryza:3")))
        self.assertEqual(r.creditors, ["Marston", "Marston"])
        self.assertEqual(r.liability_keys, ["aryza:1", "aryza:3"])

    def test_a_key_per_line_in_order(self):
        r = _bpo_debt(self._keyed(("Marston", 900.0, "aryza:7"), ("Marston", 100.0, "aryza:8")))
        lines = r.message.splitlines()
        self.assertEqual(list(zip(r.liability_keys, ["£900" in lines[0], "£100" in lines[1]])),
                         [("aryza:7", True), ("aryza:8", True)])

    def test_no_key_sent_is_none_not_a_guess(self):
        r = _bpo_debt(_case(("Marston", None, 100.0)))
        self.assertEqual(r.liability_keys, [None])

    def test_the_pass_result_carries_no_keys(self):
        r = _bpo_debt(self._keyed(("Barclays", 100.0, "aryza:1")))
        self.assertNotIn("liability_keys", dataclasses.asdict(r))

    def test_the_api_returns_each_hit_s_aryza_key(self):
        payload = {
            "application_id": "T-DCA-1", "assessment_date": "2026-09-01",
            "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
            "creditors": [
                {"creditor_name": "Marston", "balance": 750.0, "creditor_type": "unsecured_loan",
                 "liability_key": "aryza:101"},
                {"creditor_name": "Marston Ltd", "balance": 750.0, "creditor_type": "car_hp",
                 "is_secured": True, "liability_key": "aryza:102"},
                {"creditor_name": "Generic Lender", "balance": 9000.0, "creditor_type": "unsecured_loan",
                 "liability_key": "aryza:103"},
            ],
            "documents": [], "gold_transactions": None, "evidence_ledger": [],
        }
        resp = APIClient().post("/api/v1/assess/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        [flag] = [f for f in json.loads(resp.content)["flags"] if f["rule_id"] == "BPO-DEBT"]
        self.assertEqual(flag["creditors"], ["Marston", "Marston Ltd"])
        self.assertEqual(flag["liability_keys"], ["aryza:101", "aryza:102"])
        others = [f for f in json.loads(resp.content)["flags"] if f["rule_id"] != "BPO-DEBT"]
        self.assertTrue(all("liability_keys" not in f for f in others))


class BpoDebtListLoadingTests(TestCase):
    """How `_assess_case_impl` reads the DebtCollector list (2026-11-01)."""

    LOG = "debt_app.engine.criteria"

    def _flagged(self, *names):
        result = assess_case({"creditors": [{"name": n, "balance": 100.0, "creditor_type": "personal_loan"}
                                            for n in names], "evidence_ledger": []}, set())
        hit = [f for f in result["flags"] if f.rule_id == "BPO-DEBT"]
        return hit[0].creditors if hit else []

    def test_a_text_alias_is_one_alias_not_one_per_letter(self):
        DebtCollector.objects.create(name="Zeta Collect", aliases="Zeta Recoveries")
        self.assertEqual(self._flagged("Zeta Recoveries", "Z", "e", "Zeta Collect"),
                         ["Zeta Recoveries", "Zeta Collect"])

    def test_one_bad_row_does_not_empty_the_list(self):
        DebtCollector.objects.create(name="Number Agency", aliases=5)
        with self.assertLogs(self.LOG, "ERROR") as logs:
            flagged = self._flagged("Marston", "Number Agency", "Generic Lender")
        self.assertEqual(flagged, ["Marston", "Number Agency"], "every other collector still loads")
        self.assertIn("aliases is int, not a list", "\n".join(logs.output))

    def test_non_text_aliases_are_ignored_the_rest_kept(self):
        DebtCollector.objects.create(name="Mixed Agency", aliases=["Mixed Recoveries", 7, None])
        with self.assertLogs(self.LOG, "ERROR") as logs:
            self.assertEqual(self._flagged("Mixed Recoveries", "7"), ["Mixed Recoveries"])
        self.assertIn("2 non-text aliases ignored", "\n".join(logs.output))



class BpoDebtFailsClosedTests(TestCase):
    """The Debt Collectors list cannot be read: BPO-DEBT is a HARD BLOCK, not a
    pass (2026-11-01, approved). Only that failure; nothing else changes."""

    LOG = "debt_app.engine.criteria"
    SECRET = "no such table: debt_app_debtcollector"

    def _case(self, *names, ref="DCA-FAIL-1"):
        return {"aryza_reference": ref, "evidence_ledger": [],
                "creditors": [{"name": n, "balance": 900.0, "creditor_type": "personal_loan"} for n in names]}

    def _broken(self):
        from unittest import mock
        broken = mock.Mock()
        broken.filter.side_effect = RuntimeError(self.SECRET)
        return mock.patch.object(DebtCollector, "objects", broken)

    def _ids(self, result, key):
        return [r.rule_id for r in result[key]]

    def test_an_unreadable_list_is_a_hard_block_not_a_pass(self):
        with self._broken(), self.assertLogs(self.LOG, "ERROR") as logs:
            result = assess_case(self._case("Marston", "Generic Lender"), set())
        [block] = [r for r in result["hard_blocks"] if r.rule_id == "BPO-DEBT"]
        self.assertEqual((block.severity, block.triggered, block.message),
                         ("hard_block", True, DEBT_COLLECTOR_LIST_FAILED_MESSAGE))
        self.assertNotIn("BPO-DEBT", self._ids(result, "flags") + self._ids(result, "passed"))
        self.assertEqual(result["overall"], "blocked")
        self.assertFalse(hasattr(block, "liability_keys"), "no debt is named")
        self.assertEqual(block.failure_code, "DCA_LIST_UNAVAILABLE", "the contract CAT reads")
        # The cause is logged, with the case; never put in the result.
        log = "\n".join(logs.output)
        self.assertIn("DCA-FAIL-1", log)
        self.assertIn(self.SECRET, log)
        self.assertNotIn(self.SECRET, block.message)

    def test_an_empty_list_is_not_a_failure(self):
        DebtCollector.objects.all().update(is_active=False)
        result = assess_case(self._case("Marston"), set())
        self.assertIn("BPO-DEBT", self._ids(result, "passed"))
        self.assertNotIn("BPO-DEBT", self._ids(result, "hard_blocks"))
        DebtCollector.objects.all().delete()
        result = assess_case(self._case("Marston"), set())
        self.assertIn("BPO-DEBT", self._ids(result, "passed"))

    def test_a_loaded_list_still_gives_the_soft_flag(self):
        result = assess_case(self._case("Marston"), set())
        self.assertIn("BPO-DEBT", self._ids(result, "flags"))
        self.assertNotIn("BPO-DEBT", self._ids(result, "hard_blocks"))

    def test_a_bad_alias_row_is_not_a_failed_list(self):
        DebtCollector.objects.create(name="Number Agency", aliases=5)
        with self.assertLogs(self.LOG, "ERROR"):
            result = assess_case(self._case("Number Agency", "Z"), set())
        self.assertNotIn("BPO-DEBT", self._ids(result, "hard_blocks"))
        [flag] = [f for f in result["flags"] if f.rule_id == "BPO-DEBT"]
        self.assertEqual(flag.creditors, ["Number Agency"])

    def test_every_other_rule_result_is_unchanged(self):
        case = self._case("Generic Lender", "Barclays")
        shape = lambda res: {k: [(r.rule_id, r.severity, r.triggered, r.message)  # noqa: E731
                                 for r in res[k] if r.rule_id != "BPO-DEBT"]
                             for k in ("hard_blocks", "flags", "info", "passed")}
        normal = assess_case(case, set())
        with self._broken(), self.assertLogs(self.LOG, "ERROR"):
            failed = assess_case(case, set())
        self.assertEqual(shape(normal), shape(failed))

    def test_switched_off_in_the_admin_it_does_not_block(self):
        GlobalCriteria.objects.filter(rule_key="BPO-DEBT").update(is_active=False)
        with self._broken(), self.assertLogs(self.LOG, "ERROR"):
            result = assess_case(self._case("Marston"), set())
        self.assertNotIn("BPO-DEBT", self._ids(result, "hard_blocks"))

    def test_the_api_returns_the_hard_block_without_the_cause(self):
        # What CAT reads (`/api/v1/assess/`): a hard block, the plain message,
        # no database text anywhere in the response.
        payload = {"application_id": "T-DCA-FAIL", "assessment_date": "2026-09-01",
                   "financial_summary": {"net_balance": 200, "total_income": 2000, "income_source": "employed"},
                   "creditors": [{"creditor_name": "Marston", "balance": 750.0, "creditor_type": "unsecured_loan",
                                  "liability_key": "aryza:101"}],
                   "documents": [], "gold_transactions": None, "evidence_ledger": []}
        with self._broken(), self.assertLogs(self.LOG, "ERROR"):
            resp = APIClient().post("/api/v1/assess/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = json.loads(resp.content)
        [block] = [r for r in body["hard_blocks"] if r["rule_id"] == "BPO-DEBT"]
        self.assertEqual((block["severity"], block["message"], block["failure_code"]),
                         ("hard_block", DEBT_COLLECTOR_LIST_FAILED_MESSAGE, "DCA_LIST_UNAVAILABLE"))
        self.assertNotIn("BPO-DEBT", [f["rule_id"] for f in body["flags"]])
        self.assertEqual(body["overall"], "blocked")
        self.assertNotIn("no such table", resp.content.decode())
        others = [r for r in body["hard_blocks"] + body["flags"] + body["passed"] if r["rule_id"] != "BPO-DEBT"]
        self.assertTrue(all("failure_code" not in r for r in others), "no other result grows the field")

    def test_a_rule_crash_is_not_the_list_failure(self):
        # BPO-DEBT raising for any other reason is `_run`'s generic hard block --
        # no `failure_code`, so CAT never reads it as "the list was unreadable".
        from unittest import mock
        with mock.patch("debt_app.engine.criteria._matching_debt_collector", side_effect=RuntimeError("boom")), \
                self.assertLogs(self.LOG, "ERROR"):
            result = assess_case(self._case("Marston"), set())
        [block] = [r for r in result["hard_blocks"] if r.rule_id == "BPO-DEBT"]
        self.assertFalse(hasattr(block, "failure_code"))

    def test_lead_gen_reads_it_as_not_suitable_for_an_iva(self):
        from debt_app.services.lead_gen import interpret_engine_result
        with self._broken(), self.assertLogs(self.LOG, "ERROR"):
            result = assess_case(self._case("Generic Lender"), set())
        out = interpret_engine_result(
            engine_solution=result["recommended_solution"], hard_blocks=result["hard_blocks"],
            flags=result["flags"], creditor_positions=result["creditor_positions"],
            dmp_eligibility=result["dmp_eligibility"], documents_supplied=False,
            rule_titles={"BPO-DEBT": "Debt Collection Agency (DCA) listed instead of the actual creditor"})
        self.assertEqual(out["iva"]["code"], "NOT_SUITABLE")
        [reason] = [r for r in out["iva_reasons"] if r["code"] == "BPO-DEBT"]
        self.assertEqual(reason["detail"], DEBT_COLLECTOR_LIST_FAILED_MESSAGE)


class CommittedDcaListTests(TestCase):
    """`Excel Criteria/dca/dca_collectors_import.csv` -- the list as it will be
    loaded on TEST and production -- imports cleanly over the seeded rows."""

    PATH = Path(__file__).resolve().parent.parent / "Excel Criteria" / "dca" / "dca_collectors_import.csv"

    def setUp(self):
        out = io.StringIO()
        call_command("import_debt_collectors", str(self.PATH), stdout=out)
        self.out = out.getvalue()

    def _flags(self, name):
        result = assess_case({"creditors": [{"name": name, "balance": 100.0, "creditor_type": "personal_loan"}],
                              "evidence_ledger": []}, set())
        hit = [f for f in result["flags"] if f.rule_id == "BPO-DEBT"]
        return hit[0].message.split("is with ")[1].split(", a Debt")[0] if hit else None

    def test_it_imports_with_no_conflict_or_duplicate(self):
        self.assertIn("73 created, 2 updated, 1 unchanged, 0 reactivated, 0 inactive kept, "
                      "0 conflicts skipped, 0 duplicate rows.", self.out)
        self.assertEqual(DebtCollector.objects.filter(is_active=True).count(), 77)

    def test_c_a_r_s_and_cars_stay_unmatched(self):
        for name in ("C.A.R.S", "CARS", "C.A.R.S Ltd", "c a r s"):
            self.assertIsNone(self._flags(name), name)

    def test_separate_organisations_stay_separate(self):
        for name, owner in (("Advantis", "Advantis"), ("Advantis Credit Ltd", "Advantis Credit"),
                            ("Penham Excel Ltd", "Penham Excel"),
                            ("Penham Excel High Court Enforcement Officers", "Penham Excel High Court Enforcement Officers"),
                            ("Excel Civil Enforcement", "Excel Civil Enforcement"),
                            ("Marston Holdings Ltd", "Marston"), ("DCBL", "Direct Collection Bailiffs")):
            self.assertEqual(self._flags(name), owner, name)

    def test_excluded_organisations_stay_unmatched(self):
        for name in ("Postbridge", "Enforcement Training & Services", "Enforcement of Judgments Office"):
            self.assertIsNone(self._flags(name), name)
