"""
seed_creditor_criteria after the October 2026 safety rework.

  * never deletes rows it does not recognise
  * notes-only mode (default) touches free text / contacts only, creates new
    creditors, applies the agreed renames in place (same primary key)
  * rows edited by hand in admin are skipped unless --include-manual
  * repeated runs change nothing
  * --full still overwrites parsed fields (legacy) but still never deletes
"""

import io
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from debt_app.models import CreditorCriteria

GENERAL = """# GENERAL CREDITOR

| Creditor | Accept / Reject | Notes / Criteria | updated criteria | Phone Number | Email | Contact |
| --- | --- | --- | --- | --- | --- | --- |
| Existing Co | REJECT | new notes from the sheet | 01/09/2026 | 0161 000 000 | debt@existing.example | Pat |
| Manual Co | REJECT | sheet notes for manual co |  |  |  |  |
| Brand New Lender | Will Consider | brand new | 02/09/2026 |  |  |  |
| Clevr Money (Blackpool, Fylde & Wyre Credit Union Ltd) | REJECT | policy to reject |  |  |  |  |
"""

WHICH_REP = """# Which Representative

## (WATCH) WPM
- Existing Co
- New Watch Co
"""

DIVIDENDS = """# Dividends

| Creditor | Div Required | Notes |
| --- | --- | --- |
| Existing Co | 60p | sixty |
"""


class SafeSeederTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        d = self.root / "Excel Criteria"
        d.mkdir()
        (d / "General_Creditors.md").write_text(GENERAL, encoding="utf-8")
        (d / "Which_Representative_Criteria.md").write_text(WHICH_REP, encoding="utf-8")
        (d / "Dividends_Criteria.md").write_text(DIVIDENDS, encoding="utf-8")

        self.admin = User.objects.create_user("admin", is_staff=True)
        # The test database already holds migration-seeded creditors; make sure
        # the names used here are ours alone.
        CreditorCriteria.objects.filter(creditor_name__in=[
            "Existing Co", "Manual Co", "Orphan Co", "Brand New Lender", "New Watch Co",
            "Clever Money (Blackpool, Fylde & Wyre Credit Union Ltd)",
            "Clevr Money (Blackpool, Fylde & Wyre Credit Union Ltd)",
        ]).delete()
        self.existing = CreditorCriteria.objects.create(
            creditor_name="Existing Co", representative="NONE", status="WILL_CONSIDER",
            criteria_notes="old notes", min_dividend_pence=50, account_age_months=3,
            trading_names=["Existing Company"], reject_if_ccj=True,
        )
        self.manual = CreditorCriteria.objects.create(
            creditor_name="Manual Co", representative="NONE", status="ACCEPT",
            criteria_notes="hand-written notes", updated_by=self.admin,
        )
        self.orphan = CreditorCriteria.objects.create(creditor_name="Orphan Co", representative="NONE", status="ACCEPT")
        self.clever = CreditorCriteria.objects.create(
            creditor_name="Clever Money (Blackpool, Fylde & Wyre Credit Union Ltd)",
            representative="NONE", status="REJECT", criteria_notes="old policy",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        out = io.StringIO()
        with override_settings(BASE_DIR=self.root):
            call_command("seed_creditor_criteria", *args, stdout=out)
        return out.getvalue()

    # ---------------------------------------------------------------- notes-only

    def test_notes_only_updates_text_creates_new_and_never_touches_managed_fields(self):
        out = self._run()
        e = CreditorCriteria.objects.get(pk=self.existing.pk)
        # free text / contacts updated
        self.assertEqual(e.criteria_notes, "new notes from the sheet")
        self.assertEqual(e.raw_updated_criteria, "01/09/2026")
        self.assertEqual(e.contact_phone, "0161 000 000")
        self.assertEqual(e.contact_email, "debt@existing.example")
        self.assertEqual(e.contact_name, "Pat")
        self.assertEqual(e.dividend_notes, "sixty")
        # managed fields untouched although the sheet says otherwise
        self.assertEqual(e.status, "WILL_CONSIDER")          # sheet: REJECT
        self.assertEqual(e.representative, "NONE")           # sheet: WATCH
        self.assertEqual(e.min_dividend_pence, 50)           # sheet: 60p
        self.assertEqual(e.account_age_months, 3)
        self.assertEqual(e.trading_names, ["Existing Company"])
        self.assertTrue(e.reject_if_ccj)
        # new creditors are created with the sheet's stance
        new = CreditorCriteria.objects.get(creditor_name="Brand New Lender")
        self.assertEqual(new.status, "WILL_CONSIDER")
        self.assertEqual(new.criteria_notes, "brand new")
        self.assertEqual(CreditorCriteria.objects.get(creditor_name="New Watch Co").representative, "WATCH")
        self.assertIn("[CREATE] 'Brand New Lender'", out)
        self.assertIn("Managed fields", out)

    def test_never_deletes_orphans_but_reports_them(self):
        total_before = CreditorCriteria.objects.count()
        out = self._run()
        self.assertTrue(CreditorCriteria.objects.filter(pk=self.orphan.pk).exists())
        # nothing removed: only the two new creditors were added
        self.assertEqual(CreditorCriteria.objects.count(), total_before + 2)
        self.assertIn("NOT deleted", out)
        self.assertIn("[ORPHAN]", out)

    def test_manual_rows_are_skipped_unless_asked(self):
        out = self._run()
        self.assertEqual(CreditorCriteria.objects.get(pk=self.manual.pk).criteria_notes, "hand-written notes")
        self.assertIn("[SKIP manual] 'Manual Co'", out)
        self._run("--include-manual")
        m = CreditorCriteria.objects.get(pk=self.manual.pk)
        self.assertEqual(m.criteria_notes, "sheet notes for manual co")
        self.assertEqual(m.status, "ACCEPT")   # still not a managed-field write
        self.assertEqual(m.updated_by, self.admin)

    def test_rename_keeps_primary_key_and_does_not_duplicate(self):
        out = self._run()
        self.assertIn("[RENAME] #%d" % self.clever.pk, out)
        row = CreditorCriteria.objects.get(pk=self.clever.pk)
        self.assertEqual(row.creditor_name, "Clevr Money (Blackpool, Fylde & Wyre Credit Union Ltd)")
        self.assertEqual(row.criteria_notes, "policy to reject")     # notes then synced under the new name
        self.assertEqual(CreditorCriteria.objects.filter(creditor_name__icontains="Blackpool").count(), 1)
        self.assertFalse(CreditorCriteria.objects.filter(creditor_name__istartswith="Clever Money").exists())

    def test_rename_is_skipped_when_both_names_exist(self):
        CreditorCriteria.objects.create(
            creditor_name="Clevr Money (Blackpool, Fylde & Wyre Credit Union Ltd)", representative="NONE", status="REJECT",
        )
        out = self._run()
        self.assertIn("[RENAME SKIPPED]", out)
        self.assertTrue(CreditorCriteria.objects.filter(pk=self.clever.pk, creditor_name__istartswith="Clever Money").exists())

    def test_repeated_runs_are_idempotent(self):
        self._run()
        before = list(CreditorCriteria.objects.order_by("pk").values())
        out = self._run()
        after = list(CreditorCriteria.objects.order_by("pk").values())
        self.assertEqual(before, after)
        self.assertIn("created 0, updated 0", out)
        self.assertIn("renamed 0", out)

    def test_dry_run_writes_nothing(self):
        before = list(CreditorCriteria.objects.order_by("pk").values())
        out = self._run("--dry-run")
        self.assertEqual(before, list(CreditorCriteria.objects.order_by("pk").values()))
        self.assertIn("DRY RUN", out)
        self.assertIn("[CREATE] 'Brand New Lender'", out)
        self.assertIn("[RENAME]", out)

    # ---------------------------------------------------------------- --full

    def test_full_mode_overwrites_parsed_fields_but_still_never_deletes_or_touches_manual_rows(self):
        out = self._run("--full")
        e = CreditorCriteria.objects.get(pk=self.existing.pk)
        self.assertEqual(e.status, "REJECT")
        self.assertEqual(e.representative, "WATCH")
        self.assertEqual(e.min_dividend_pence, 60)
        self.assertTrue(CreditorCriteria.objects.filter(pk=self.orphan.pk).exists())
        self.assertEqual(CreditorCriteria.objects.get(pk=self.manual.pk).criteria_notes, "hand-written notes")
        self.assertIn("outside the criteria change workflow", out)
        self.assertIn("[ORPHAN]", out)
