"""
Lead Gen DMP checklist (council tax questions).

The Lead Gen check used to send no DMP checklist answers, so the engine's
council tax rejection could never fire and DMP showed "Potentially suitable"
whenever total debt cleared the minimum. These tests pin that the three
answers now reach _evaluate_dmp_eligibility through the same inputs the CAT
screen uses.
"""

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from debt_app.services.lead_gen import lead_gen_dmp_inputs
from debt_app.tests_cat_assessment_golden import _cr_account
from debt_app.tests_lead_gen import _LeadGenFixture
from debt_app.views import criteria_views
from debt_app.views.criteria_views import build_dmp_checklist

ALL_YES = {
    "council_tax_current_year": True,
    "council_tax_previous_year": True,
    "lost_right_to_pay_instalments": True,
}


class LeadGenDmpInputsTests(SimpleTestCase):

    def test_no_answers_means_no(self):
        for raw in (None, {}, "", "not json", ["x"]):
            rows, case_level = lead_gen_dmp_inputs(raw)
            self.assertEqual(rows, [])
            self.assertEqual(case_level, {"lost_right_to_pay_instalments": False})

    def test_all_yes_builds_the_council_tax_checklist(self):
        rows, case_level = lead_gen_dmp_inputs(ALL_YES)
        checklist = build_dmp_checklist(rows, case_level)
        self.assertTrue(checklist["current_year_council_tax"])
        self.assertTrue(checklist["previous_year_council_tax"])
        self.assertTrue(checklist["lost_right_to_pay_instalments"])
        others = {k: v for k, v in checklist.items() if k not in (
            "current_year_council_tax", "previous_year_council_tax", "lost_right_to_pay_instalments")}
        self.assertFalse(any(others.values()))

    def test_json_string_from_multipart(self):
        rows, case_level = lead_gen_dmp_inputs(json.dumps(ALL_YES))
        self.assertEqual(len(rows), 2)
        self.assertTrue(case_level["lost_right_to_pay_instalments"])

    def test_unknown_keys_cannot_set_other_checklist_fields(self):
        rows, case_level = lead_gen_dmp_inputs({"hmrc_previous_year_vat": True, "current_gas_bill": True})
        checklist = build_dmp_checklist(rows, case_level)
        self.assertFalse(any(checklist.values()))


class LeadGenDmpChecklistEndpointTests(_LeadGenFixture):

    def test_all_three_council_tax_answers_make_dmp_not_suitable(self):
        body = self._check(self._good_case("LG-CT-ALL"), data={"dmp_checklist": ALL_YES}).json()
        self.assertEqual(body["dmp"]["code"], "NOT_SUITABLE")
        self.assertIn("DMP-COUNCIL-TAX", [r["code"] for r in body["reasons"]])

    def test_two_of_three_answers_keep_dmp_suitable(self):
        answers = dict(ALL_YES, lost_right_to_pay_instalments=False)
        body = self._check(self._good_case("LG-CT-TWO"), data={"dmp_checklist": answers}).json()
        self.assertEqual(body["dmp"]["code"], "POTENTIALLY_SUITABLE")

    def test_no_answers_keep_dmp_suitable(self):
        body = self._check(self._good_case("LG-CT-NONE")).json()
        self.assertEqual(body["dmp"]["code"], "POTENTIALLY_SUITABLE")

    def test_answers_sent_with_a_credit_report_upload(self):
        original = criteria_views.extract_credit_report
        criteria_views.extract_credit_report = lambda p: {
            "agency": "Experian", "client_name": "X", "accounts": [_cr_account("ALPHA BANK PLC", "Alpha Bank", 600_000)],
            "mortgage_accounts": [], "other_accounts": [], "unmatched_accounts": [], "public_information": {},
        }
        try:
            resp = self._check(self._good_case("LG-CT-UP"), data={
                "credit_report": SimpleUploadedFile("r.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
                "dmp_checklist": json.dumps(ALL_YES),
            }, fmt="multipart")
        finally:
            criteria_views.extract_credit_report = original
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["dmp"]["code"], "NOT_SUITABLE")
