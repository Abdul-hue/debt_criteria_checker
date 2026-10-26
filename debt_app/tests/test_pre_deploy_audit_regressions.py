"""
Regressions for the two pre-deployment audit failures found on 2026-10-13.

1. AssessCaseView._prepare_engine_payload returns three values (payload,
   prepared creditors, unmatched credit-report accounts); the audit unpacked
   two and every reference case failed with "too many values to unpack".
2. The alias map pointed 'zilch', 'zilch technology limited' and
   'united trust bank limited' at creditor rows that existed nowhere (not in
   the database, the migrations or the workbook). United Trust Bank was
   removed. Zilch appears on real cases, so it now has a row of its own
   (General_Creditors.md, stance UNKNOWN until confirmed) and the aliases
   point at it; every alias target must be a creditor the markdown knows.
"""

import io
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.core.management import call_command

from debt_app.helpers import _RAW_CREDITOR_ALIAS_MAP, get_creditor_by_trading_name
from debt_app.models import CreditorCriteria
from debt_app.tests_cat_assessment_golden import _FixedDate, _case, _creditor

FETCH = "debt_app.aryza_client.fetch_case_by_reference"

# Alias targets that are legitimately absent from the markdown sources: rows
# that still exist in the database from the retired Evolve list. Anything else
# an alias points at must be a creditor the workbook knows about.
ALIAS_TARGETS_NOT_IN_WORKBOOK = {
    "Barclaycard", "NatWest", "TSB Bank",
    # Phase 9 rows, created by migration 0091 (manager decisions 2026-10-21).
    "Parkingeye Limited", "Quidie Limited t/a Fernovo", "Propel Holdings UK T/A Quidmarket",
}


class AuditUnpacksThreeValuesTests(TestCase):
    def setUp(self):
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        CreditorCriteria.objects.update_or_create(
            creditor_name="Alpha Bank", defaults=dict(representative="NONE", status="ACCEPT", is_active=True),
        )

    def test_reference_cases_are_processed_and_unmatched_accounts_reported(self):
        def fake_fetch(ref):
            return _case(ref, [_creditor("Alpha Bank", 600_000)])

        out = io.StringIO()
        with patch(FETCH, side_effect=fake_fetch):
            call_command("pre_deploy_audit", stdout=out)
        text = out.getvalue()
        self.assertNotIn("_prepare_engine_payload", text.split("PART 2")[0].replace("Build engine payload", ""))
        self.assertNotIn("[ERROR]", text.split("PART 2")[0])
        self.assertEqual(text.count("  Creditors   : 1"), 4)
        self.assertEqual(text.count("CR unmatched: 0 credit-report account(s)"), 4)
        self.assertIn("PART 1 SUMMARY:  detect_representatives identical on all cases", text)
        self.assertIn("BACKFILL CHECK:  reconcile_creditor_positions correctly surfaces all creditors", text)


class AliasMapIntegrityTests(SimpleTestCase):
    def test_dead_aliases_are_gone(self):
        # United Trust Bank: no row anywhere and no real-case hits -> alias removed.
        self.assertNotIn("united trust bank limited", _RAW_CREDITOR_ALIAS_MAP)
        self.assertNotIn("United Trust Bank", _RAW_CREDITOR_ALIAS_MAP.values())
        # Zilch: seen on real cases, so it now has a row (General_Creditors.md, stance
        # UNKNOWN) and live aliases. The old 'zilch technology limited' key could never
        # match because normalisation strips "limited"; the normalised key is used.
        self.assertEqual(_RAW_CREDITOR_ALIAS_MAP.get("zilch"), "Zilch")
        self.assertEqual(_RAW_CREDITOR_ALIAS_MAP.get("zilch technology"), "Zilch")
        self.assertNotIn("zilch technology limited", _RAW_CREDITOR_ALIAS_MAP)

    def test_every_alias_target_is_a_creditor_the_workbook_knows(self):
        """Guards against adding an alias for a creditor that will never be
        seeded (the exporter / notes-only sync create rows from the markdown)."""
        from debt_app.management.commands.seed_creditor_criteria import (
            TRADING_NAMES_OVERRIDES, _parse_strict_sources,
        )
        self.assertTrue((settings.BASE_DIR / "Excel Criteria" / "General_Creditors.md").exists())
        known = {n.lower() for n in _parse_strict_sources()}
        known |= {t.lower() for names in TRADING_NAMES_OVERRIDES.values() for t in names}
        known |= {n.lower() for n in ALIAS_TARGETS_NOT_IN_WORKBOOK}
        unknown = sorted({v for v in _RAW_CREDITOR_ALIAS_MAP.values() if v.lower() not in known})
        self.assertEqual(unknown, [], f"alias targets with no creditor in the markdown sources: {unknown}")


class DeadAliasFallthroughTests(TestCase):
    def test_zilch_resolves_to_unknown_not_a_wrong_creditor(self):
        CreditorCriteria.objects.filter(creditor_name__icontains="zilch").delete()
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("ZILCH TECHNOLOGY LIMITED")
