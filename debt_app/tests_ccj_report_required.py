"""
Item #11 — has_ccj default and CREDIT-REPORT-REQUIRED flag.

Excel says "no CCJ" / "REJECT IF ALREADY HAVE CCJ" — the creditor rejects
when a CCJ is CONFIRMED present.  When no credit report exists, has_ccj
correctly defaults to False (we can't confirm a CCJ) and the creditor is
not rejected.

The GAP: cases with Admiral Loans / Advantage Finance (reject_if_ccj=True)
can pass without a credit report ever being uploaded, because has_ccj stays
False and the CCJ branch never fires.

FIX: when reject_if_ccj=True or reject_if_aoe=True and the case dict
shows credit_report_status != "present", emit FLAG
CREDITOR-CCJ-REPORT-REQUIRED so the caseworker is prompted to upload a
credit report.  This must NOT hard-block (Excel doesn't say reject without
evidence) and must NOT change has_ccj default or any other rule.
"""

from django.test import TestCase

from debt_app.criteria_engine import _check_creditor_individual
from debt_app.models import CreditorCriteria


def _case(creditor_name, *, credit_report_status="absent", has_ccj=False, aoe=False):
    return {
        "creditors": [{
            "name": creditor_name,
            "original_name": creditor_name,
            "debt_type_normalised": "personal_loan",
            "creditor_type": "personal_loan",
            "crm_balance": 5000.0,
            "balance": 5000.0,
        }],
        "has_ccj": has_ccj,
        "aoe_in_place": aoe,
        "previous_iva": False,
        "has_property": False,
        "total_debt": 5000.0,
        "aryza_reference": "TEST",
        "client_name": "Test Client",
        "credit_report_status": credit_report_status,
    }


class CcjReportRequiredFlagTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="CCJ Lender", representative="NONE", status="WILL_CONSIDER",
            reject_if_ccj=True, reject_if_aoe=True, is_active=True,
        )
        CreditorCriteria.objects.create(
            creditor_name="Clean Lender", representative="NONE", status="WILL_CONSIDER",
            reject_if_ccj=False, reject_if_aoe=False, is_active=True,
        )

    def _pos(self, case):
        return _check_creditor_individual(case)[0]

    # --- REPORT ABSENT: should FLAG, not REJECT ---

    def test_ccj_lender_absent_report_flags_not_rejects(self):
        p = self._pos(_case("CCJ Lender", credit_report_status="absent"))
        self.assertNotEqual(p["effective_status"], "REJECT",
                            "No report → cannot confirm CCJ → must NOT reject")
        codes = [f["code"] for f in p.get("findings", [])]
        self.assertIn("CREDITOR-CCJ-REPORT-REQUIRED", codes,
                      "No report for ccj/aoe creditor → must flag REPORT-REQUIRED")

    def test_ccj_lender_extraction_failed_flags_not_rejects(self):
        p = self._pos(_case("CCJ Lender", credit_report_status="extraction_failed"))
        codes = [f["code"] for f in p.get("findings", [])]
        self.assertIn("CREDITOR-CCJ-REPORT-REQUIRED", codes)
        self.assertNotEqual(p["effective_status"], "REJECT")

    def test_ccj_lender_report_present_no_flag(self):
        # Report uploaded and no CCJ confirmed → no flag, no reject.
        p = self._pos(_case("CCJ Lender", credit_report_status="present", has_ccj=False))
        codes = [f["code"] for f in p.get("findings", [])]
        self.assertNotIn("CREDITOR-CCJ-REPORT-REQUIRED", codes)
        self.assertNotEqual(p["effective_status"], "REJECT")

    def test_ccj_lender_report_present_ccj_confirmed_rejects(self):
        # Report uploaded AND CCJ confirmed → REJECT (existing behaviour).
        p = self._pos(_case("CCJ Lender", credit_report_status="present", has_ccj=True))
        self.assertEqual(p["effective_status"], "REJECT")
        codes = [f["code"] for f in p["findings"]]
        self.assertIn("CREDITOR-CCJ-REJECT", codes)
        self.assertNotIn("CREDITOR-CCJ-REPORT-REQUIRED", codes)

    # --- Clean lender should NOT flag regardless of report status ---

    def test_clean_lender_no_report_no_flag(self):
        p = self._pos(_case("Clean Lender", credit_report_status="absent"))
        codes = [f["code"] for f in p.get("findings", [])]
        self.assertNotIn("CREDITOR-CCJ-REPORT-REQUIRED", codes)

    # --- AOE path same behaviour ---

    def test_ccj_lender_absent_report_aoe_in_place_rejects(self):
        # AOE is confirmed from case data (not credit report) → reject still fires.
        p = self._pos(_case("CCJ Lender", credit_report_status="absent", aoe=True))
        self.assertEqual(p["effective_status"], "REJECT")
        codes = [f["code"] for f in p["findings"]]
        self.assertIn("CREDITOR-AOE-REJECT", codes)
