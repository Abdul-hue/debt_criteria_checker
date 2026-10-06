"""
Lead Generation pre-screen tests.

  * LeadGenInterpretationTests — the presentation layer over engine output
    (pure; RuleResult objects exactly as assess_case() returns them).
  * LeadGenCheckEndpointTests — POST /api/v1/criteria/lead-gen/check/ end to end
    with Aryza mocked: auth (real JWT), permissions, outcomes, credit reports,
    error handling, minimal response, activity recording.
  * LeadGenDepartmentSafetyTests — a Lead Gen check must never change the case
    (Application.source_department, saved CAT CriteriaDecision).
"""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from debt_app.aryza_client import (
    AryaTimeoutError,
    AryzaCaseNotFoundError,
    AryzaConnectionError,
    AryzaDataError,
)
from debt_app.engine.criteria import RuleResult, _evaluate_dmp_eligibility
from debt_app.models import (
    Application,
    CreditorCriteria,
    CreditReport,
    CriteriaDecision,
    Department,
    DepartmentFeatureAccess,
    GlobalCriteria,
    LeadGenCheck,
    UserProfile,
)
from debt_app.services import lead_gen
from debt_app.services.lead_gen import EVIDENCE_STAGE_RULES, interpret_engine_result
from debt_app.tests_cat_assessment_golden import _case, _cr_account, _creditor, _FixedDate
from debt_app.views import criteria_views

URL = "/api/v1/criteria/lead-gen/check/"
FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"


def _hb(rule_id, msg="m"):
    return RuleResult(rule_id=rule_id, severity="hard_block", triggered=True, message=msg)


def _flag(rule_id, msg="m"):
    return RuleResult(rule_id=rule_id, severity="flag", triggered=True, message=msg)


_ELIGIBLE = {"status": "DMP_ELIGIBLE", "reasons": [], "notes": []}
_ACCEPT_POS = [{"creditor_name": "A", "effective_status": "ACCEPT", "is_secured": False}]


def _interpret(**kw):
    args = dict(engine_solution="IVA_VIABLE", hard_blocks=[], flags=[], creditor_positions=_ACCEPT_POS,
                dmp_eligibility=_ELIGIBLE, documents_supplied=False,
                rule_titles={"TIG-01": "Minimum debt", "TIG-02": "Minimum disposable income"})
    args.update(kw)
    return interpret_engine_result(**args)


class LeadGenInterpretationTests(SimpleTestCase):

    def test_iva_and_dmp_potentially_suitable(self):
        r = _interpret()
        self.assertEqual(r["iva"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(r["dmp"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")
        self.assertIsNone(r["dro"])
        self.assertEqual(r["reasons"], [])

    def test_flags_mean_needs_review(self):
        r = _interpret(engine_solution="IVA_WITH_CONDITIONS", flags=[_flag("TIG-18")],
                       rule_titles={"TIG-18": "Recent spending review"})
        self.assertEqual(r["iva"]["code"], "NEEDS_REVIEW")
        self.assertEqual(r["iva"]["label"], "IVA — Potentially suitable, needs review")
        self.assertEqual(r["review_reasons"][0], {"code": "TIG-18", "text": "Recent spending review — needs checking"})
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")

    def test_non_voting_unsecured_creditor_means_needs_review(self):
        # Same signal the engine uses for REVIEW_REQUIRED.
        r = _interpret(engine_solution="REVIEW_REQUIRED", creditor_positions=[
            {"creditor_name": "Council", "effective_status": "DO_NOT_VOTE", "is_secured": False},
        ])
        self.assertEqual(r["iva"]["code"], "NEEDS_REVIEW")
        self.assertEqual(r["review_reasons"][0]["code"], "REVIEW_REQUIRED")

    def test_secured_abstention_is_not_review(self):
        r = _interpret(creditor_positions=[
            {"creditor_name": "Mortgage", "effective_status": "DO_NOT_VOTE", "is_secured": True},
        ])
        self.assertEqual(r["iva"]["code"], "POTENTIALLY_SUITABLE")

    def test_eligibility_hard_block_means_iva_not_suitable(self):
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[_hb("TIG-01", "Debt £4,100 is too low")])
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")  # DMP still works
        self.assertEqual(r["reasons"][0], {"code": "TIG-01", "text": "Minimum debt — criteria not met"})

    def test_dmp_rejected_uses_figure_free_text(self):
        dmp = {"status": "DMP_REJECTED", "reasons": [
            "The customer's total debt is £2,500.00, which is at or below the £3,000.00 minimum ..."
        ], "notes": []}
        r = _interpret(dmp_eligibility=dmp)
        self.assertEqual(r["dmp"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["dmp_reasons"][0]["code"], "DMP-MIN-DEBT")
        self.assertNotIn("2,500", json.dumps(r))

    def test_neither_does_not_meet_criteria_with_ordered_reasons(self):
        dmp = {"status": "DMP_REJECTED", "reasons": ["The customer's total debt is £10.00, ..."], "notes": []}
        r = _interpret(engine_solution="IVA_NOT_VIABLE",
                       hard_blocks=[_hb("TIG-01"), _hb("TIG-02"), _hb("CREDITOR-BLOCKED"), _hb("TIG-21.2")],
                       dmp_eligibility=dmp, rule_titles={"TIG-01": "Minimum debt", "TIG-02": "Minimum disposable income",
                                                         "TIG-21.2": "Link Financial minimum debt"})
        self.assertEqual(r["overall"]["code"], "DOES_NOT_MEET_CRITERIA")
        self.assertEqual(r["overall"]["label"], "Does not currently meet criteria")
        # Engine order, capped at 3 for display; every code kept for the record.
        self.assertEqual([x["code"] for x in r["reasons"]], ["TIG-01", "TIG-02", "CREDITOR-BLOCKED"])
        self.assertEqual(r["reason_codes"], ["TIG-01", "TIG-02", "CREDITOR-BLOCKED", "TIG-21.2", "DMP-MIN-DEBT"])

    def test_forced_dro_is_shown_separately_not_as_failure(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", hard_blocks=[_hb("TIG-02")])
        self.assertEqual(r["overall"]["code"], "DRO_REFER")
        self.assertEqual(r["dro"]["label"], "Debt Relief Order (DRO) — Potentially suitable / Refer for review")
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["iva_reasons"][0]["code"], "FORCED_DRO_LG")
        self.assertEqual(r["dmp"]["code"], "POTENTIALLY_SUITABLE")  # engine's DMP result shown as-is

    def test_forced_vat_dmp(self):
        r = _interpret(engine_solution="FORCED_DMP_VAT")
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["dmp"]["code"], "POTENTIALLY_SUITABLE")

    def test_evidence_stage_rules_become_evidence_required_later(self):
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[_hb("TIG-05"), _hb("TIG-11")],
                       flags=[_flag("TIG-08")])
        self.assertEqual(r["iva"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(r["evidence_required_later"],
                         ["Wage slip", "Bank statement", "Tax return or business bank statement"])
        self.assertEqual(r["reasons"], [])

    def test_evidence_plus_genuine_blocker(self):
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[_hb("TIG-05"), _hb("TIG-02")])
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual([x["code"] for x in r["iva_reasons"]], ["TIG-02"])
        self.assertEqual(r["evidence_required_later"], ["Wage slip"])

    def test_evidence_rule_is_a_blocker_when_documents_were_supplied(self):
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[_hb("TIG-05")], documents_supplied=True)
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["evidence_required_later"], [])

    def test_tig13_remains_a_lead_gen_blocker_pending_business_decision(self):
        self.assertNotIn("TIG-13", EVIDENCE_STAGE_RULES)
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[_hb("TIG-13")])
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")

    def test_gambling_and_proof_of_debt_are_not_evidence_stage(self):
        for rid in ("TIG-11-GAMBLING", "TIG-10"):
            self.assertNotIn(rid, EVIDENCE_STAGE_RULES)

    def test_engine_dmp_reason_wording_is_pinned(self):
        """The Lead Gen DMP reason mapping keys off the engine's wording."""
        low = _evaluate_dmp_eligibility({"dmp_checklist": {"x": False}, "total_debt": 1000})
        self.assertTrue(low["reasons"][0].startswith(lead_gen._DMP_MIN_DEBT_PREFIX))
        ct = _evaluate_dmp_eligibility({"dmp_checklist": {
            "current_year_council_tax": True, "previous_year_council_tax": True,
            "lost_right_to_pay_instalments": True}, "total_debt": 10000})
        self.assertTrue(ct["reasons"][0].startswith(lead_gen._DMP_COUNCIL_TAX_PREFIX))

    def test_display_client_name(self):
        self.assertEqual(lead_gen.display_client_name("Jane Mary Smith"), "J. Smith")
        self.assertEqual(lead_gen.display_client_name(""), "")


class _LeadGenFixture(TestCase):
    def setUp(self):
        self.api = APIClient()
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, st in (("Alpha Bank", "ACCEPT"), ("Beta Loans", "ACCEPT"), ("Link Financial", "ACCEPT")):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status=st, is_active=True)
        self.lead_gen_dept = Department.objects.create(name="Lead Generation", slug="lead-generation")
        DepartmentFeatureAccess.objects.create(department=self.lead_gen_dept, feature_key="lead_gen_check", is_enabled=True)
        self.default_dept = Department.objects.create(name="Default", slug="default")
        DepartmentFeatureAccess.objects.create(department=self.default_dept, feature_key="run_assessment", is_enabled=True)
        self.lg_user = self._user("lg-user", self.lead_gen_dept)

    def _user(self, username, dept=None, **kw):
        u = User.objects.create_user(username=username, password=None, **kw)  # no hashing; JWT only
        if dept is not None:
            UserProfile.objects.create(user=u, department=dept)
        return u

    def _jwt(self, user):
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")

    def _check(self, case_or_exc, user=None, data=None, fmt="json"):
        self._jwt(user or self.lg_user)
        with patch(FETCH) as fetch:
            if isinstance(case_or_exc, Exception):
                fetch.side_effect = case_or_exc
                ref = (data or {}).get("aryza_reference", "LG-ERR")
            else:
                fetch.return_value = case_or_exc
                ref = case_or_exc.aryza_reference
            return self.api.post(URL, data={"aryza_reference": ref, **(data or {})}, format=fmt)

    @staticmethod
    def _good_case(ref, **kw):
        return _case(ref, [_creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000)], **kw)


class LeadGenCheckEndpointTests(_LeadGenFixture):

    # ---- authentication / permissions ---------------------------------

    def test_no_authentication_is_rejected(self):
        resp = APIClient().post(URL, data={"aryza_reference": "X"}, format="json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(LeadGenCheck.objects.count(), 0)

    def test_invalid_token_is_rejected(self):
        self.api.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(self.api.post(URL, data={"aryza_reference": "X"}, format="json").status_code, 401)

    def test_real_jwt_lead_gen_user_succeeds(self):
        resp = self._check(self._good_case("LG-OK"))
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_user_without_lead_gen_permission_is_forbidden(self):
        cat_user = self._user("cat-user", self.default_dept)
        self.assertEqual(self._check(self._good_case("LG-NOPE"), user=cat_user).status_code, 403)

    def test_user_with_no_department_is_forbidden(self):
        loner = self._user("loner")
        self.assertEqual(self._check(self._good_case("LG-NODEPT"), user=loner).status_code, 403)

    def test_disabled_feature_row_is_forbidden(self):
        DepartmentFeatureAccess.objects.filter(feature_key="lead_gen_check").update(is_enabled=False)
        self.assertEqual(self._check(self._good_case("LG-OFF")).status_code, 403)

    def test_staff_can_check(self):
        admin = self._user("admin", is_staff=True)
        self.assertEqual(self._check(self._good_case("LG-ADMIN"), user=admin).status_code, 200)

    def test_missing_reference(self):
        self._jwt(self.lg_user)
        resp = self.api.post(URL, data={}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "MISSING_REFERENCE")

    # ---- outcomes -------------------------------------------------------

    def test_valid_case_iva_and_dmp_potentially_suitable_with_evidence_later(self):
        # TIG-15.6 (full & final from savings) is switched off in the live
        # config; the empty test DB has every rule on, and it flags this case.
        GlobalCriteria.objects.create(criteria_set="TIG", rule_key="TIG-15.6", rule_name="x",
                                      severity="hard_block", is_active=False)
        body = self._check(self._good_case("LG-BOTH", employment="employed")).json()
        self.assertEqual(body["iva"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(body["dmp"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(body["overall"]["code"], "POTENTIALLY_SUITABLE")
        # TIG-05 / TIG-11 fire in the engine (no documents) but are evidence-stage here.
        self.assertEqual(body["evidence_required_later"], ["Wage slip", "Bank statement"])
        self.assertEqual(body["reasons"], [])
        self.assertEqual(body["client"], "G. LG-BOTH")  # "Golden Client LG-BOTH" -> initial + surname

    def test_iva_review_when_engine_flags(self):
        case = _case("LG-REV", [_creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 300_000),
                                _creditor("Zeta Mystery Credit", 200_000)])
        body = self._check(case).json()
        self.assertEqual(body["iva"]["code"], "NEEDS_REVIEW")
        self.assertIn("CREDITOR-UNIDENTIFIED-MATERIAL", [r["code"] for r in body["review_reasons"]])

    def test_iva_unsuitable_dmp_suitable(self):
        case = _case("LG-LINK", [_creditor("Alpha Bank", 400_000), _creditor("Link Financial", 400_000)])
        body = self._check(case).json()
        self.assertEqual(body["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(body["dmp"]["code"], "POTENTIALLY_SUITABLE")
        self.assertIn("TIG-21.2", [r["code"] for r in body["reasons"]])

    def test_neither_suitable_multiple_reasons(self):
        case = _case("LG-NONE", [_creditor("Alpha Bank", 150_000), _creditor("Beta Loans", 100_000)])
        body = self._check(case).json()
        self.assertEqual(body["overall"]["code"], "DOES_NOT_MEET_CRITERIA")
        self.assertEqual(body["dmp"]["code"], "NOT_SUITABLE")
        codes = [r["code"] for r in body["reasons"]]
        self.assertIn("TIG-01", codes)
        self.assertLessEqual(len(body["reasons"]), 3)
        rec = LeadGenCheck.objects.get(aryza_reference="LG-NONE")
        self.assertIn("TIG-01", rec.reason_codes)
        self.assertIn("DMP-MIN-DEBT", rec.reason_codes)

    def test_forced_dro_for_low_lead_gen_income(self):
        case = self._good_case("LG-DRO", income_pence=30_000, expenditure_pence=10_000)
        body = self._check(case).json()
        self.assertEqual(body["overall"]["code"], "DRO_REFER")
        self.assertEqual(body["dro"]["code"], "REFER")
        rec = LeadGenCheck.objects.get(aryza_reference="LG-DRO")
        self.assertTrue(rec.dro_referral)
        self.assertEqual(rec.engine_recommended_solution, "FORCED_DRO_LG")

    def test_same_case_through_cat_is_not_forced_dro(self):
        """Lead Gen context applies to the Lead Gen run only."""
        case = self._good_case("LG-DRO-CAT", income_pence=30_000, expenditure_pence=10_000)
        self._check(case)
        with patch(FETCH, return_value=case):
            cat = APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "LG-DRO-CAT"}, format="json")
        self.assertNotEqual(cat.json()["recommended_solution"].get("code"), "DRO")

    # ---- minimal response -------------------------------------------------

    def test_response_contains_no_sensitive_cat_detail(self):
        resp = self._check(self._good_case("LG-MIN", employment="employed"))
        raw = resp.content.decode()
        body = resp.json()
        for forbidden_key in ("creditor_positions", "hard_blocks", "flags", "passed", "majority_analysis",
                              "dividend_analysis", "disposable_income", "total_unsecured_debt",
                              "lead_gen_disposable_income", "council_positions", "accounts"):
            self.assertNotIn(forbidden_key, body)
        for forbidden_text in ("Alpha Bank", "Beta Loans", "6,000", "4,500", "600000", "Golden Client"):
            self.assertNotIn(forbidden_text, raw)
        self.assertEqual(set(body), {
            "success", "check_id", "aryza_reference", "client", "checked_at", "overall", "iva", "dmp", "dro",
            "reasons", "review_reasons", "evidence_required_later", "credit_report", "criteria_version",
        })

    # ---- errors -------------------------------------------------------------

    def test_unknown_case(self):
        resp = self._check(AryzaCaseNotFoundError("x"), data={"aryza_reference": "LG-404"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], "CASE_NOT_FOUND")
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-404").status, "CASE_NOT_FOUND")

    def test_aryza_timeout(self):
        resp = self._check(AryaTimeoutError("x"), data={"aryza_reference": "LG-TO"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-TO").status, "ARYZA_TIMEOUT")

    def test_aryza_unavailable(self):
        resp = self._check(AryzaConnectionError("x"), data={"aryza_reference": "LG-DOWN"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["code"], "ARYZA_UNAVAILABLE")

    def test_aryza_data_error(self):
        resp = self._check(AryzaDataError("x"), data={"aryza_reference": "LG-DATA"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-DATA").status, "ARYZA_DATA_ERROR")

    def test_engine_error_is_recorded(self):
        with patch("debt_app.views.criteria_views.run_standalone_assessment", side_effect=RuntimeError("boom")):
            resp = self._check(self._good_case("LG-BOOM"))
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-BOOM").status, "ENGINE_ERROR")

    # ---- credit reports -----------------------------------------------------

    def test_missing_credit_report(self):
        body = self._check(self._good_case("LG-NOCR")).json()
        self.assertEqual(body["credit_report"]["status"], "none")
        self.assertIn("message", body["credit_report"])

    def test_existing_credit_report_is_used(self):
        cr = CreditReport.objects.create(
            aryza_reference="LG-CR", uploaded_file="x.pdf", extraction_status="extracted",
            extracted_data={"accounts": [_cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000)], "mortgage_accounts": []},
        )
        body = self._check(self._good_case("LG-CR")).json()
        self.assertEqual(body["credit_report"]["status"], "on_file")
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-CR").credit_report_id, cr.id)

    def _upload(self, ref, extractor, name="report.pdf", content=b"%PDF-1.4\n%%EOF"):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = extractor
        try:
            return self._check(self._good_case(ref), data={
                "credit_report": SimpleUploadedFile(name, content, content_type="application/pdf"),
            }, fmt="multipart")
        finally:
            criteria_views.extract_credit_report = original

    def test_credit_report_upload_success(self):
        resp = self._upload("LG-UP", lambda p: {
            "agency": "Experian", "client_name": "X", "accounts": [_cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000)],
            "mortgage_accounts": [], "other_accounts": [], "unmatched_accounts": [], "public_information": {},
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["credit_report"]["status"], "uploaded")
        self.assertNotIn("ALPHA BANK", resp.content.decode())
        rec = LeadGenCheck.objects.get(aryza_reference="LG-UP")
        self.assertEqual(rec.credit_report_id, CreditReport.objects.get(aryza_reference="LG-UP").id)

    def test_credit_report_failed_extraction(self):
        resp = self._upload("LG-UPFAIL", lambda p: {"extraction_error": "layout not recognised"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "EXTRACTION_FAILED")
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-UPFAIL").status, "CREDIT_REPORT_FAILED")

    def test_credit_report_empty_extraction_still_checks_with_warning(self):
        resp = self._upload("LG-UPEMPTY", lambda p: {
            "agency": "Experian", "accounts": [], "mortgage_accounts": [], "other_accounts": [],
            "unmatched_accounts": [], "public_information": {},
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["credit_report"]["status"], "extracted_empty")
        self.assertIn("warning", resp.json()["credit_report"])

    def test_credit_report_invalid_file(self):
        resp = self._upload("LG-UPBAD", lambda p: {}, name="report.txt")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "INVALID_FILE_TYPE")
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="LG-UPBAD").status, "CREDIT_REPORT_INVALID")

    def test_upload_not_stored_when_case_not_found(self):
        self._jwt(self.lg_user)
        with patch(FETCH, side_effect=AryzaCaseNotFoundError("x")):
            self.api.post(URL, data={"aryza_reference": "LG-404UP", "credit_report": SimpleUploadedFile(
                "r.pdf", b"%PDF-1.4", content_type="application/pdf")}, format="multipart")
        self.assertFalse(CreditReport.objects.filter(aryza_reference="LG-404UP").exists())

    def test_credit_report_status_endpoint(self):
        self._jwt(self.lg_user)
        url = "/api/v1/criteria/lead-gen/credit-report-status/"
        self.assertFalse(self.api.get(url, {"aryza_reference": "LG-S"}).json()["has_usable_report"])
        CreditReport.objects.create(aryza_reference="LG-S", uploaded_file="x.pdf", extraction_status="extracted",
                                    agency="Experian", extracted_data={"accounts": [{"raw_name": "A"}]})
        body = self.api.get(url, {"aryza_reference": "LG-S"}).json()
        self.assertTrue(body["has_usable_report"])
        self.assertNotIn("accounts", body)
        self.assertEqual(APIClient().get(url, {"aryza_reference": "LG-S"}).status_code, 401)

    # ---- recording ------------------------------------------------------------

    def test_every_check_records_criteria_and_code_version(self):
        self._check(self._good_case("LG-VER"))
        rec = LeadGenCheck.objects.get(aryza_reference="LG-VER")
        self.assertEqual(rec.status, "OK")
        self.assertEqual(rec.username, "lg-user")
        self.assertEqual(rec.department_name, "Lead Generation")
        self.assertEqual(rec.criteria_version, "unversioned")
        self.assertEqual(len(rec.criteria_fingerprint), 64)
        self.assertTrue(rec.code_version)


class LeadGenDepartmentSafetyTests(_LeadGenFixture):

    def test_lead_gen_check_does_not_set_source_department(self):
        Application.objects.create(aryza_reference="LG-DEPT", client_name="X")
        self._check(self._good_case("LG-DEPT"))
        self.assertIsNone(Application.objects.get(aryza_reference="LG-DEPT").source_department)

    def test_lead_gen_check_does_not_overwrite_existing_source_department(self):
        Application.objects.create(aryza_reference="LG-DEPT2", client_name="X", source_department="Default")
        self._check(self._good_case("LG-DEPT2", income_pence=30_000, expenditure_pence=10_000))
        self.assertEqual(Application.objects.get(aryza_reference="LG-DEPT2").source_department, "Default")

    def test_later_cat_run_does_not_inherit_lead_gen_department(self):
        Application.objects.create(aryza_reference="LG-DEPT3", client_name="X")
        case = self._good_case("LG-DEPT3", income_pence=30_000, expenditure_pence=10_000)
        self.assertEqual(self._check(case).json()["overall"]["code"], "DRO_REFER")
        with patch(FETCH, return_value=case):
            cat = APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "LG-DEPT3"}, format="json")
        self.assertNotEqual(Application.objects.get(aryza_reference="LG-DEPT3").source_department, "Lead Generation")
        self.assertNotEqual(cat.json()["recommended_solution"].get("code"), "DRO")

    def test_lead_gen_check_does_not_touch_saved_cat_decision(self):
        case = self._good_case("LG-KEEP")
        with patch(FETCH, return_value=case):
            APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "LG-KEEP"}, format="json")
        cat_decision = CriteriaDecision.objects.get(application_id="LG-KEEP")
        self._check(case)
        self.assertEqual(list(CriteriaDecision.objects.filter(application_id="LG-KEEP").values_list("id", flat=True)),
                         [cat_decision.id])


class StrictFeatureReportingTests(_LeadGenFixture):
    """The UI must not offer opt-in features the backend will refuse."""

    def _features(self, user):
        self._jwt(user)
        return {f["feature_key"]: f["is_enabled"] for f in self.api.get("/api/v1/criteria/my-features/").json()}

    def test_strict_features_off_without_explicit_row(self):
        cat_user = self._user("cat2", self.default_dept)
        loner = self._user("loner2")
        for user in (cat_user, loner):
            f = self._features(user)
            for key in ("lead_gen_check", "lead_gen_reporting", "criteria_changes", "criteria_approval"):
                self.assertFalse(f[key], (user.username, key))
        # Existing permissive behaviour for pre-existing keys is unchanged.
        self.assertTrue(self._features(loner)["run_assessment"])

    def test_lead_gen_user_sees_only_lead_gen_check(self):
        f = self._features(self.lg_user)
        self.assertTrue(f["lead_gen_check"])
        self.assertFalse(f["lead_gen_reporting"])
        self.assertFalse(f["criteria_approval"])

    def test_admin_department_feature_list_matches_enforcement(self):
        admin = self._user("admin2", is_staff=True)
        self._jwt(admin)
        rows = self.api.get(f"/api/v1/criteria/departments/{self.default_dept.pk}/features/").json()
        f = {r["feature_key"]: r["is_enabled"] for r in rows}
        self.assertFalse(f["criteria_approval"])
        self.assertTrue(f["run_assessment"])


class LeadGenFinalVerificationTests(_LeadGenFixture):
    """Final-verification cases (pinned behaviour; see the implementation report)."""

    def test_tig13_previous_iva_is_not_hidden_through_the_real_api(self):
        # Current behaviour pending a business decision: TIG-13 stays a Lead Gen blocker.
        case = self._good_case("LG-PREV-IVA", previous_iva=True)
        body = self._check(case).json()
        self.assertEqual(body["iva"]["code"], "NOT_SUITABLE")
        self.assertIn("TIG-13", [r["code"] for r in body["reasons"]])
        self.assertNotIn("termination", " ".join(body["evidence_required_later"]).lower())

    def test_zero_income_currently_presents_as_dro_referral(self):
        """Characterisation only, NOT an endorsement. With no income in the fact
        find the engine's Lead Gen DI is 0 (< 399) -> FORCED_DRO_LG, while TIG-02
        simultaneously reports that no income has been entered. Whether Lead Gen
        should present this as a DRO referral is an open business decision; this
        pins today's behaviour so any change is deliberate."""
        case = self._good_case("LG-NO-INCOME", income_pence=0, expenditure_pence=0)
        body = self._check(case).json()
        self.assertEqual(body["overall"]["code"], "DRO_REFER")
        rec = LeadGenCheck.objects.get(aryza_reference="LG-NO-INCOME")
        self.assertEqual(rec.engine_recommended_solution, "FORCED_DRO_LG")
        self.assertIn("TIG-02", rec.reason_codes)

    def test_supplied_document_failure_is_not_hidden(self):
        from debt_app.views.criteria_views import StandaloneAssessmentResult
        outcome = StandaloneAssessmentResult(
            response_body={}, engine_recommended_solution="IVA_NOT_VIABLE",
            engine_creditor_positions=_ACCEPT_POS, hard_blocks=[_hb("TIG-05")], flags=[],
            dmp_eligibility=_ELIGIBLE,
            case_data={"documents": [{"document_type": "payslip", "is_valid": True}]},
        )
        r = lead_gen.to_lead_gen_result(outcome)
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["evidence_required_later"], [])
        outcome.case_data = {}
        self.assertEqual(lead_gen.to_lead_gen_result(outcome)["iva"]["code"], "POTENTIALLY_SUITABLE")

    def test_response_has_no_address_income_thresholds_or_report_detail(self):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = lambda p: {
            "agency": "Experian", "client_name": "JANE SECRETNAME", "client_address": "7 Hidden Road, Leeds",
            "accounts": [_cr_account("ALPHA BANK PLC", "Alpha Bank", 150_000)], "mortgage_accounts": [],
            "other_accounts": [], "unmatched_accounts": [], "public_information": {"ccjs": 1},
        }
        try:
            self._jwt(self.lg_user)
            case = _case("LG-PRIV", [_creditor("Alpha Bank", 150_000), _creditor("Beta Loans", 100_000)],
                         income_pence=250_000, expenditure_pence=180_000)
            with patch(FETCH, return_value=case):
                resp = self.api.post(URL, data={"aryza_reference": "LG-PRIV", "credit_report": SimpleUploadedFile(
                    "r.pdf", b"%PDF-1.4", content_type="application/pdf")}, format="multipart")
        finally:
            criteria_views.extract_credit_report = original
        self.assertEqual(resp.status_code, 200, resp.content)
        raw = resp.content.decode()
        self.assertEqual(resp.json()["overall"]["code"], "DOES_NOT_MEET_CRITERIA")
        for secret in ("Hidden Road", "SECRETNAME", "Alpha Bank", "Beta Loans", "ALPHA BANK",
                       "2,500", "1,800", "1,500", "£3,000", "£6,000", "£100", "399", "Golden Client"):
            self.assertNotIn(secret, raw, secret)


class UserDeleteWithCriteriaAuditTests(TestCase):
    def test_deleting_a_change_author_returns_409_not_500(self):
        from debt_app.models import CriteriaChangeRequest
        admin = User.objects.create_user("admin-del", password=None, is_staff=True)
        author = User.objects.create_user("author-del", password=None)
        CriteriaChangeRequest.objects.create(title="t", reason="r", items=[], created_by=author)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(admin)}")
        resp = api.delete(f"/api/v1/criteria/users/{author.pk}/")
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(User.objects.filter(pk=author.pk).exists())
        plain = User.objects.create_user("plain-del", password=None)
        self.assertEqual(api.delete(f"/api/v1/criteria/users/{plain.pk}/").status_code, 204)
