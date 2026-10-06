"""
CAT assessment golden-output regression tests.

Purpose: prove that refactoring the orchestration inside AssessCaseView.post
(extracting it into a shared service for the Lead Gen tool) does NOT change a
single byte of the CAT result. Each scenario POSTs to the real
/api/v1/criteria/assess/ endpoint with Aryza mocked, then compares the FULL
normalised response — plus the side effects the view performs (saved
CriteriaDecision, Application.source_department, CreditorResolutionMiss rows)
— against a golden file captured from the pre-refactor code.

Regenerate the golden file ONLY when an intentional CAT behaviour change is
made (never to make a refactor pass):

    REGENERATE_CAT_GOLDEN=1 python manage.py test debt_app.tests_cat_assessment_golden

The engine reads date.today() for the assessment date, client age and
representative date gates, so the clock is pinned to keep the golden output
stable across days.
"""

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.aryza_client import AryaTimeoutError, AryzaCaseNotFoundError, CaseData
from debt_app.models import (
    Application,
    CouncilRule,
    CreditorCriteria,
    CreditorResolutionMiss,
    CreditReport,
    CriteriaDecision,
    Department,
    GlobalCriteria,
    UserProfile,
)

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "cat_assessment_golden.json"
REGENERATE = os.environ.get("REGENERATE_CAT_GOLDEN") == "1"

# Volatile response keys — differ on every run by construction.
_VOLATILE_KEYS = {"evaluated_at", "decision_id"}

# Rules migration 0050 disabled as "documentation / evidence gathering".
_EVIDENCE_RULES_0050 = ["TIG-05", "TIG-06", "TIG-07", "TIG-08", "TIG-09", "TIG-11", "TIG-12"]


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 1)


def _cr_account(raw_name, matched, balance_pence, monthly_pence=5000, type_code="LN"):
    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": raw_name.lower(),
        "matched_creditor": matched,
        "account_status": "up to date",
        "current_balance": balance_pence,
        "missed_payments_last_3_months": 0,
        "monthly_payment": monthly_pence,
        "account_age_months": 36,
        "payment_history_months": 36,
        "recent_spending": False,
        "credit_limit": None,
        "utilisation_pct": None,
        "start_date": "2023-06-01",
    }


def _case(ref, creditors, income_pence=250_000, expenditure_pence=180_000,
          employment="unemployed", previous_iva=False, uc_pence=0):
    c = CaseData()
    c.aryza_reference = ref
    c.client_name = f"Golden Client {ref}"
    c.dob = "1980-05-05"
    c.employment_status = employment
    c.creditors = creditors
    c.income = {
        "employment": income_pence - uc_pence,
        "universal_credit": uc_pence,
        "dla": 0,
        "pip": 0,
        "other_benefits": 0,
        "third_party_contribution": 0,
        "total": income_pence,
    }
    c.expenditure = {"disability_expenses": 0, "total": expenditure_pence}
    c.flags = dict(c.flags, previous_iva=previous_iva)
    return c


def _creditor(name, balance_pence, type_="personal_loan", ref=None):
    return {"name": name, "type": type_, "balance": balance_pence, "ref": ref or f"REF-{name[:4]}"}


def _normalise(body):
    return json.loads(json.dumps(
        {k: v for k, v in body.items() if k not in _VOLATILE_KEYS},
        sort_keys=True, default=str,
    ))


class CatAssessmentGoldenTests(TestCase):
    """One test per scenario; all compare against the same golden file."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._golden = {}
        if GOLDEN_PATH.exists():
            cls._golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        cls._captured = {}

    @classmethod
    def tearDownClass(cls):
        if REGENERATE:
            merged = dict(cls._golden)
            merged.update(cls._captured)
            GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN_PATH.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        self._date_patch = patch("debt_app.engine.criteria.date", _FixedDate)
        self._date_patch.start()
        self.addCleanup(self._date_patch.stop)

        for name, status in (
            ("Alpha Bank", "ACCEPT"),
            ("Beta Loans", "ACCEPT"),
            ("Gamma Cards", "WILL_CONSIDER"),
            ("Link Financial", "ACCEPT"),
        ):
            CreditorCriteria.objects.create(
                creditor_name=name, representative="NONE", status=status, is_active=True,
            )
        CreditorCriteria.objects.create(
            creditor_name="Blocked Lender", representative="NONE", status="REJECT",
            is_active=True, blocked_until_cleared=True,
            blocked_reason="Account under internal review",
        )
        CouncilRule.objects.create(council_name="Testshire Borough Council", status="ACCEPT")
        self.lead_gen_dept = Department.objects.create(name="Lead Generation", slug="lead-generation")

    # -- helpers ---------------------------------------------------------

    def _disable_evidence_rules(self):
        for key in _EVIDENCE_RULES_0050:
            GlobalCriteria.objects.create(
                criteria_set="TIG", rule_key=key, rule_name=key,
                severity="hard_block", is_active=False,
            )

    def _run(self, scenario, case_obj, body=None, user=None, expect_status=200):
        if user is not None:
            self.client.force_authenticate(user=user)
        with patch("debt_app.views.criteria_views.fetch_case_by_reference") as mock_fetch:
            if isinstance(case_obj, Exception):
                mock_fetch.side_effect = case_obj
            else:
                mock_fetch.return_value = case_obj
            ref = (body or {}).get("aryza_reference") or case_obj.aryza_reference
            resp = self.client.post(
                "/api/v1/criteria/assess/",
                data={"aryza_reference": ref, **(body or {})},
                format="json",
            )
        self.assertEqual(resp.status_code, expect_status, resp.content[:500])

        decision = CriteriaDecision.objects.filter(application_id=ref).first()
        app = Application.objects.filter(aryza_reference=ref).first()
        snapshot = {
            "status_code": resp.status_code,
            "body": _normalise(resp.json()),
            "decision": None if decision is None else {
                "recommended_solution": decision.recommended_solution,
                "passes_all_hard_blocks": decision.passes_all_hard_blocks,
                "source": decision.source,
                "triggered_by": decision.triggered_by.username if decision.triggered_by else None,
                "input_snapshot": json.loads(json.dumps(decision.input_snapshot, sort_keys=True, default=str)),
                "decision_output": json.loads(json.dumps(
                    {k: v for k, v in decision.decision_output.items() if k not in _VOLATILE_KEYS},
                    sort_keys=True, default=str,
                )),
            },
            "decision_count": CriteriaDecision.objects.filter(application_id=ref).count(),
            "application_source_department": app.source_department if app else "<no application>",
            "resolution_misses": sorted(
                CreditorResolutionMiss.objects.filter(case_reference=ref).values_list("raw_name", flat=True)
            ),
        }
        self.__class__._captured[scenario] = snapshot
        if not REGENERATE:
            self.assertIn(scenario, self._golden, f"No golden snapshot for {scenario!r}; regenerate.")
            self.assertEqual(snapshot, self._golden[scenario], f"CAT output changed for {scenario!r}")
        return snapshot

    # -- scenarios -------------------------------------------------------

    def test_iva_viable(self):
        self._disable_evidence_rules()
        snap = self._run("iva_viable", _case("G-IVA-OK", [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ]))
        self.assertEqual(snap["body"]["hard_blocks"], [])

    def test_iva_with_flags(self):
        self._disable_evidence_rules()
        # Unknown creditor holding >10% of debt -> CREDITOR-UNIDENTIFIED-MATERIAL flag.
        snap = self._run("iva_with_flags", _case("G-IVA-FLAG", [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 300_000),
            _creditor("Zeta Mystery Credit", 200_000),
        ]))
        self.assertEqual(snap["body"]["hard_blocks"], [])
        self.assertTrue(snap["body"]["flags"])

    def test_iva_hard_block_min_debt(self):
        self._disable_evidence_rules()
        snap = self._run("iva_hard_block_min_debt", _case("G-IVA-HB", [
            _creditor("Alpha Bank", 250_000), _creditor("Beta Loans", 150_000),
        ]))
        self.assertIn("TIG-01", [r["rule_id"] for r in snap["body"]["hard_blocks"]])

    def test_dmp_rejected_low_debt(self):
        self._disable_evidence_rules()
        snap = self._run("dmp_rejected_low_debt", _case("G-DMP-REJ", [
            _creditor("Alpha Bank", 150_000), _creditor("Beta Loans", 100_000),
        ]))
        self.assertEqual(snap["body"]["dmp_eligibility"]["status"], "DMP_REJECTED")

    def test_iva_and_dmp_with_checklist_and_rows(self):
        self._disable_evidence_rules()
        snap = self._run("iva_and_dmp_with_checklist_and_rows", _case("G-BOTH", [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
            _creditor("Testshire Borough Council", 80_000, type_="council_tax"),
        ]), body={
            "dmp_checklist": {"current_gas_bill": True, "lost_right_to_pay_instalments": True},
            "creditor_rows": [{"debt_type_normalised": "council_tax", "value": "current"}],
        })
        self.assertEqual(snap["body"]["dmp_eligibility"]["status"], "DMP_ELIGIBLE")

    def test_forced_dro_lead_gen_user(self):
        self._disable_evidence_rules()
        ref = "G-DRO"
        Application.objects.create(aryza_reference=ref, client_name="Golden DRO")
        user = User.objects.create_user(username="golden-lg", password="x")
        UserProfile.objects.create(user=user, department=self.lead_gen_dept)
        snap = self._run("forced_dro_lead_gen_user", _case(ref, [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ], income_pence=30_000, expenditure_pence=10_000), user=user)
        self.assertEqual(snap["body"]["recommended_solution"]["code"], "DRO")
        self.assertEqual(snap["application_source_department"], "Lead Generation")

    def test_application_untagged_anonymous(self):
        self._disable_evidence_rules()
        ref = "G-APP-ANON"
        Application.objects.create(aryza_reference=ref, client_name="Golden Anon")
        self._run("application_untagged_anonymous", _case(ref, [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ]))

    def test_creditor_blocked(self):
        self._disable_evidence_rules()
        snap = self._run("creditor_blocked", _case("G-BLOCK", [
            _creditor("Alpha Bank", 600_000), _creditor("Blocked Lender", 450_000),
        ]))
        self.assertIn("CREDITOR-BLOCKED", [r["rule_id"] for r in snap["body"]["hard_blocks"]])

    def test_link_financial_min_debt(self):
        self._disable_evidence_rules()
        snap = self._run("link_financial_min_debt", _case("G-LINK", [
            _creditor("Alpha Bank", 400_000), _creditor("Link Financial", 400_000),
        ]))
        self.assertIn("TIG-21.2", [r["rule_id"] for r in snap["body"]["hard_blocks"]])

    def test_credit_report_only_creditor(self):
        self._disable_evidence_rules()
        ref = "G-CR-ONLY"
        CreditReport.objects.create(
            aryza_reference=ref, uploaded_file="fake.pdf", extraction_status="extracted",
            extracted_data={"accounts": [
                _cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000),
                _cr_account("DELTA UNDECLARED FINANCE", "Delta Undeclared Finance", 120_000),
            ], "mortgage_accounts": []},
        )
        snap = self._run("credit_report_only_creditor", _case(ref, [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ]))
        self.assertIn("CREDITOR-CR-ONLY", json.dumps(snap["body"]["creditor_positions"]))

    def test_pinned_credit_report_id(self):
        self._disable_evidence_rules()
        ref = "G-CR-PIN"
        older = CreditReport.objects.create(
            aryza_reference=ref, uploaded_file="old.pdf", extraction_status="extracted",
            extracted_data={"accounts": [_cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000)],
                            "mortgage_accounts": []},
        )
        CreditReport.objects.create(
            aryza_reference=ref, uploaded_file="new.pdf", extraction_status="extracted",
            extracted_data={"accounts": [_cr_account("BETA LOANS LTD", "Beta Loans", 450_000)],
                            "mortgage_accounts": []},
        )
        self._run("pinned_credit_report_id", _case(ref, [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ]), body={"credit_report_id": older.id})

    def test_evidence_rules_active_employed_no_documents(self):
        # Evidence rules left ACTIVE (no GlobalCriteria disable rows).
        snap = self._run("evidence_rules_active_employed_no_documents", _case("G-EVID", [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ], employment="employed"))
        ids = [r["rule_id"] for r in snap["body"]["hard_blocks"]]
        self.assertIn("TIG-05", ids)
        self.assertIn("TIG-11", ids)

    def test_evidence_rules_previous_iva_uc(self):
        snap = self._run("evidence_rules_previous_iva_uc", _case("G-EVID-UC", [
            _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000),
        ], employment="universal_credit", previous_iva=True, uc_pence=60_000))
        ids = [r["rule_id"] for r in snap["body"]["hard_blocks"]]
        self.assertIn("TIG-13", ids)

    def test_case_not_found(self):
        self._run("case_not_found", AryzaCaseNotFoundError("nope"),
                  body={"aryza_reference": "G-404"}, expect_status=404)

    def test_aryza_timeout(self):
        self._run("aryza_timeout", AryaTimeoutError("slow"),
                  body={"aryza_reference": "G-503"}, expect_status=503)

    def test_missing_reference(self):
        resp = self.client.post("/api/v1/criteria/assess/", data={}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "MISSING_REFERENCE")
