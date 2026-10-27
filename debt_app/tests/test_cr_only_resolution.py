"""
Credit-report-only (undeclared) accounts take their resolved row's standing
position (2026-10-27, case 426399). The CR-only backfill used to hardcode
effective_status UNKNOWN even when the account resolved, so a NONE-represented
row such as Lloyds Bank (ACCEPT) or 3 Mobile (DO NOT VOTE) showed "Unidentified";
only representative-body rows were fixed up afterwards.

The raw PDF name is tried before the extractor's matched_creditor, which is a
display name ("Three", "O2") that need not match any row.
"""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.models import CreditorCriteria, CreditorResolutionMiss, CreditReport
from debt_app.tests_cat_assessment_golden import _FixedDate, _case, _cr_account, _creditor


class CreditReportOnlyResolutionTests(TestCase):
    REF = "T-CR-ONLY-RES"

    def setUp(self):
        date_patch = patch("debt_app.engine.criteria.date", _FixedDate)
        date_patch.start()
        self.addCleanup(date_patch.stop)
        for name, rep, status in (
            ("Alpha Bank", "NONE", "ACCEPT"),
            ("Lloyds Bank", "NONE", "ACCEPT"),
            ("3 Mobile", "NONE", "DO_NOT_VOTE"),
        ):
            CreditorCriteria.objects.update_or_create(
                creditor_name=name,
                defaults={"representative": rep, "status": status, "is_active": True},
            )

    def _positions(self, accounts):
        CreditReport.objects.create(
            aryza_reference=self.REF, uploaded_file="fake.pdf", extraction_status="extracted",
            extracted_data={"accounts": accounts, "mortgage_accounts": []},
        )
        with patch("debt_app.views.criteria_views.fetch_case_by_reference") as mock_fetch:
            mock_fetch.return_value = _case(self.REF, [_creditor("Alpha Bank", 600_000)])
            resp = APIClient().post(
                "/api/v1/criteria/assess/", data={"aryza_reference": self.REF}, format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        return {
            p["cr_raw_name"]: p for p in resp.json()["creditor_positions"]
            if "CREDITOR-CR-ONLY" in (p.get("rule_ids") or [])
        }

    def test_resolved_account_takes_row_status(self):
        pos = self._positions([
            _cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000),
            _cr_account("LLOYDS", "LLOYDS", 0),
        ])["LLOYDS"]
        lloyds = CreditorCriteria.objects.get(creditor_name="Lloyds Bank")
        self.assertEqual(pos["effective_status"], "ACCEPT")
        self.assertEqual(pos["criteria_id"], lloyds.id)
        self.assertEqual(pos["resolved_canonical_name"], "Lloyds Bank")

    def test_raw_name_tried_before_extractor_display_name(self):
        # Extractor maps "hutchison 3g uk limited" -> "Three", which is no row.
        pos = self._positions([
            _cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000),
            _cr_account("HUTCHISON 3G UK LTD", "Three", 0),
        ])["HUTCHISON 3G UK LTD"]
        self.assertEqual(pos["effective_status"], "DO_NOT_VOTE")
        self.assertEqual(pos["resolved_canonical_name"], "3 Mobile")
        self.assertFalse(CreditorResolutionMiss.objects.filter(raw_name="HUTCHISON 3G UK LTD").exists())

    def test_unresolved_account_stays_unknown_and_is_logged(self):
        pos = self._positions([
            _cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000),
            _cr_account("DELTA UNDECLARED FINANCE", "Delta Undeclared Finance", 0),
        ])["DELTA UNDECLARED FINANCE"]
        self.assertEqual(pos["effective_status"], "UNKNOWN")
        self.assertIsNone(pos["criteria_id"])
        self.assertTrue(CreditorResolutionMiss.objects.filter(raw_name="DELTA UNDECLARED FINANCE").exists())
