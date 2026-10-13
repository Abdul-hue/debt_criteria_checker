"""
The sheet owner's answers of 2026-10-13 for creditors whose vote
the workbook left blank, unclear, or "unsure".

Checks that
  * every recorded answer parses to the intended stance,
  * an answer only fires on the cell value it was given for,
  * the committed markdown carries the answers (statuses, kept rows, WATCH),
  * the builder proposes Reward Rate's Amigo rule and Finio as a Likely Loan
    trading name,
  * migration 0088 records Hillingdon housing benefit as Do Not Vote.
"""

import datetime
import importlib
import tempfile
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from openpyxl import Workbook

from debt_app.management.commands.seed_creditor_criteria import _parse_status
from debt_app.models import CouncilRule, CreditorCriteria, DebtTypeCouncilVote
from debt_app.services.criteria_change_builder import ProposalSet, _structured_changes
from debt_app.services.excel_criteria import (
    FILE_GENERAL,
    FILE_WHICH_REP,
    OWNER_ANSWERS_2026_10_13,
    existing_rep_sections,
    existing_table_rows,
    export_workbook,
)

CRITERIA_DIR = Path(settings.BASE_DIR) / "Excel Criteria"

EXPECTED = {
    "Reward Rate": "DO_NOT_VOTE",
    "24/7 Moneybox / Active Securities": "DO_NOT_VOTE",
    "A Shade Greener Boilers": "REJECT",
    "1st Stop Personal Loans / Oplo": "REJECT",
    "Billings finance": "ACCEPT",
    "365 Business Finance Ltd": "REJECT",
    "3 Mobile": "DO_NOT_VOTE",
    "3J Finance": "DO_NOT_VOTE",
    "CreditSpring": "DO_NOT_VOTE",
    "SLL Capital": "ACCEPT",
    # rows that are not in the workbook (kept rows)
    "Zilch": "DO_NOT_VOTE",
    "Huddersfield Credit Union": "DO_NOT_VOTE",
    "Sefton Credit Union": "DO_NOT_VOTE",
    "Croydon / Murton & Sutton Credit Union": "UNKNOWN",
}

NOW_WATCH = [
    "Cash Euro Net", "Mint", "NatWest", "NatWest Bank", "Royal Bank of Scotland",
    "The Royal Bank of Scotland Plc", "TSB Bank", "Ulster Bank", "Virgin Money (Loan) WPM",
]


class OwnerAnswerParsingTests(SimpleTestCase):

    def test_every_answer_parses_to_a_stance(self):
        wanted = {"DO NOT VOTE": "DO_NOT_VOTE", "REJECT": "REJECT", "ACCEPT": "ACCEPT"}
        for name, _expect, value in OWNER_ANSWERS_2026_10_13:
            self.assertEqual(_parse_status(value), wanted[value], name)

    def test_answers_cover_the_expected_rows(self):
        names = {name for name, _, _ in OWNER_ANSWERS_2026_10_13}
        self.assertEqual(names, {n.lower() for n in EXPECTED} - {
            "zilch", "huddersfield credit union", "sefton credit union", "croydon / murton & sutton credit union",
        })


class OwnerAnswerExportTests(SimpleTestCase):

    def _export(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wb = Workbook()
            ws = wb.active
            ws.title = "GENERAL CREDITOR"
            ws.append(["Creditor", "Accept / Reject", "Notes / Criteria", "updated criteria", "Phone Number", "Email", "Contact"])
            for row in rows:
                ws.append(row)
            xlsx = root / "criteria.xlsx"
            wb.save(xlsx)
            out = root / "out"
            out.mkdir()
            report, outputs = export_workbook(xlsx, out, today=datetime.date(2026, 10, 13), write=False)
            return report, outputs[FILE_GENERAL]

    def test_answer_fills_a_blank_cell_and_replaces_a_remark(self):
        report, md = self._export([
            ["3 Mobile", None, None, None, None, None, None],
            ["SLL Capital", "croydon", None, None, None, None, None],
        ])
        self.assertIn("| 3 Mobile | DO NOT VOTE |", md)
        self.assertIn("| SLL Capital | ACCEPT | Sheet says: 'croydon'. |", md)
        self.assertEqual(len(report.files[FILE_GENERAL]["fixes"]), 2)

    def test_answer_is_a_no_op_once_the_workbook_has_a_vote(self):
        report, md = self._export([
            ["3 Mobile", "Accept", None, None, None, None, None],
            ["SLL Capital", "Reject", None, None, None, None, None],
        ])
        self.assertIn("| 3 Mobile | Accept |", md)
        self.assertIn("| SLL Capital | Reject |", md)
        self.assertEqual(report.files[FILE_GENERAL]["fixes"], [])


LEFT_AS_THEY_ARE = {
    # Sheet owner: "leave with no answer until we know more": the workbook wording stays, so nothing is proposed.
    "CAPITAL ON TAP (NEW WAVE)": "NOT SURE", "Leap Utilites": "UNSURE HOW THEY VOTE", "Kroo Bank": "NO VOTING HISTORY",
    "Peabody Housing": "UNAWARE HOW THEY VOTE", "WESTERN CIRCLE LTD": "UNAWARE HOW THEY VOTE",
    "Reevo Money": "TRADING STYLE OF Amplifi Capital", "Clonard Credit Union": "", "Hull University": "",
    "RIA financial services": "", "Claims Advisory Group": "", "Glasgow Credit Union Limited": "", "Malden Housing Authority": "",
}


class CommittedMarkdownTests(SimpleTestCase):

    def test_rows_the_owner_said_to_leave_keep_the_workbook_wording(self):
        rows = {r[0]: r[1] for r in existing_table_rows(CRITERIA_DIR / FILE_GENERAL, 7)}
        for name, cell in LEFT_AS_THEY_ARE.items():
            self.assertEqual(rows[name], cell, name)

    def test_general_creditors_carry_the_answers(self):
        rows = {r[0]: r[1] for r in existing_table_rows(CRITERIA_DIR / FILE_GENERAL, 7)}
        for name, stance in EXPECTED.items():
            self.assertIn(name, rows)
            self.assertEqual(_parse_status(rows[name]), stance, name)

    def test_watch_section_lists_the_ex_evolve_banks_and_wpm_rows(self):
        watch = existing_rep_sections(CRITERIA_DIR / FILE_WHICH_REP)["(WATCH) WPM"]
        for name in NOW_WATCH:
            self.assertIn(name, watch)
        tix = existing_rep_sections(CRITERIA_DIR / FILE_WHICH_REP)["TIX"]
        for name in NOW_WATCH:
            self.assertNotIn(name, tix)


class StructuredAnswerTests(TestCase):

    def test_reward_rate_gets_amigo_rule_and_finio_resolves_to_likely_loan(self):
        CreditorCriteria.objects.update_or_create(creditor_name="Reward Rate", defaults={"status": "ACCEPT"})
        CreditorCriteria.objects.update_or_create(creditor_name="Likely Loan", defaults={"status": "ACCEPT", "trading_names": []})
        ps = ProposalSet()
        _structured_changes(ps)
        got = {(p["object_label"], p["field"]): p["new_value"] for p in ps.groups["creditor_statuses"]}
        self.assertEqual(got[("Reward Rate", "reject_if_debt_repayable_within_months")], 84)
        self.assertEqual(got[("Likely Loan", "trading_names")], ["Finio Loans", "Finio"])


class HillingdonHousingBenefitMigrationTests(TestCase):

    def setUp(self):
        self.migration = importlib.import_module("debt_app.migrations.0088_hillingdon_housing_benefit_vote")
        self.council, _ = CouncilRule.objects.get_or_create(
            council_name="Hillingdon Council (London Borough)", defaults={"status": "WILL_CONSIDER"},
        )
        DebtTypeCouncilVote.objects.filter(council=self.council).delete()

    def test_housing_benefit_is_do_not_vote_and_the_council_keeps_its_status(self):
        self.migration.forwards(django_apps, None)
        vote = DebtTypeCouncilVote.objects.get(council=self.council, debt_type="HOUSING_BENEFIT")
        self.assertEqual(vote.status, "DO_NOT_VOTE")
        self.council.refresh_from_db()
        self.assertEqual(self.council.status, "WILL_CONSIDER")
        self.assertFalse(DebtTypeCouncilVote.objects.filter(council=self.council, debt_type="PCN").exists())

    def test_existing_vote_is_not_overwritten_and_rerun_is_safe(self):
        DebtTypeCouncilVote.objects.create(council=self.council, debt_type="HOUSING_BENEFIT", status="REJECT")
        self.migration.forwards(django_apps, None)
        self.migration.forwards(django_apps, None)
        self.assertEqual(
            list(DebtTypeCouncilVote.objects.filter(council=self.council).values_list("status", flat=True)), ["REJECT"],
        )


class HuddersfieldCouncilTaxMigrationTests(TestCase):

    def setUp(self):
        self.migration = importlib.import_module("debt_app.migrations.0089_huddersfield_council_tax_vote")
        CouncilRule.objects.filter(council_name__iexact="Huddersfield Council").delete()
        CouncilRule.objects.update_or_create(council_name="Kirklees Borough Council", defaults={"status": "ACCEPT"})

    def test_huddersfield_is_do_not_vote_and_kirklees_is_unchanged(self):
        from debt_app.engine.criteria import _match_council_rule
        self.migration.forwards(django_apps, None)
        self.migration.forwards(django_apps, None)  # re-run is safe
        self.assertEqual(CouncilRule.objects.filter(council_name__iexact="Huddersfield Council").count(), 1)
        for name in ("Huddersfield Council", "huddersfield council"):
            rule = _match_council_rule(name)
            self.assertEqual((rule.council_name, rule.status), ("Huddersfield Council", "DO_NOT_VOTE"), name)
        for name in ("Kirklees Council", "Kirklees Borough Council"):
            rule = _match_council_rule(name)
            self.assertEqual((rule.council_name, rule.status), ("Kirklees Borough Council", "ACCEPT"), name)
