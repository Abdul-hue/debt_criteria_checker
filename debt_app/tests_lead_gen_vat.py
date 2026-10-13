"""
Lead Gen HMRC VAT question.

The check returns the engine's own hmrc_is_creditor so the screen can offer
the CAT screen's two VAT ticks only for a case with an HMRC creditor. The
answers go through the same checklist fields, so the engine's FORCED_DMP_VAT
(previous-year VAT is an automatic IVA fail) decides the outcome. A VAT tick
on a case with no HMRC creditor is dropped before the outcome is reported.
"""

from django.test import SimpleTestCase

from debt_app.models import LeadGenCheck
from debt_app.services.lead_gen import lead_gen_dmp_inputs, without_vat_answers
from debt_app.tests_cat_assessment_golden import _case, _creditor
from debt_app.tests_lead_gen import _LeadGenFixture, _interpret
from debt_app.views.criteria_views import build_dmp_checklist

BOTH_VAT = {"hmrc_debt_has_vat": True, "hmrc_previous_year_vat": True}


def _hmrc_case(ref, **kw):
    return _case(ref, [
        _creditor("Alpha Bank", 600_000),
        _creditor("Beta Loans", 450_000),
        _creditor("HMRC", 200_000, type_="vat"),
    ], **kw)


class LeadGenVatInputsTests(SimpleTestCase):

    def test_vat_answers_reach_the_checklist(self):
        rows, case_level = lead_gen_dmp_inputs(BOTH_VAT)
        checklist = build_dmp_checklist(rows, case_level)
        self.assertTrue(checklist["hmrc_debt_has_vat"])
        self.assertTrue(checklist["hmrc_previous_year_vat"])

    def test_previous_year_without_has_vat_is_ignored(self):
        rows, case_level = lead_gen_dmp_inputs({"hmrc_previous_year_vat": True})
        self.assertFalse(build_dmp_checklist(rows, case_level)["hmrc_previous_year_vat"])

    def test_unticked_vat_answers_are_not_sent(self):
        _, case_level = lead_gen_dmp_inputs({"hmrc_debt_has_vat": False, "current_gas_bill": True})
        self.assertNotIn("hmrc_debt_has_vat", case_level)
        self.assertTrue(case_level["current_gas_bill"])

    def test_without_vat_answers_keeps_the_other_answers(self):
        _, case_level = lead_gen_dmp_inputs(dict(BOTH_VAT, current_gas_bill=True))
        self.assertEqual(without_vat_answers(case_level), {k: v for k, v in case_level.items()
                                                           if not k.startswith("hmrc_")})


class LeadGenVatInterpretationTests(SimpleTestCase):

    def test_forced_vat_is_an_iva_fail(self):
        r = _interpret(engine_solution="FORCED_DMP_VAT", previous_year_vat=True)
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["reasons"][0]["code"], "FORCED_DMP_VAT")
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")  # DMP still open

    def test_vat_and_dro_conflict_is_flagged_for_review(self):
        r = _interpret(engine_solution="REVIEW_REQUIRED", previous_year_vat=True, lead_gen_disposable_income=200.0)
        self.assertEqual(r["overall"]["code"], "REVIEW_REQUIRED")
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["iva_reasons"][0]["text"], "IVA is not currently suitable for this conflict")
        self.assertEqual(r["reason_codes"], ["FORCED-SOLUTION-CONFLICT"])
        self.assertNotEqual(r["dro"]["code"], "REFER")
        # DMP passed its own checks but is not chosen while the conflict stands.
        self.assertEqual(r["dmp"], {"code": "REVIEW_REQUIRED", "label": "DMP — Caseworker review needed"})
        self.assertEqual([x["code"] for x in r["review_reasons"]], ["FORCED-SOLUTION-CONFLICT"])
        self.assertIn("£200.00", r["review_reasons"][0]["detail"])

    def test_conflict_keeps_a_dmp_that_fails_its_own_checks(self):
        rejected = {"status": "DMP_REJECTED", "notes": [],
                    "reasons": ["The customer's total debt is £2,000.00, which is at or below the minimum."]}
        r = _interpret(engine_solution="REVIEW_REQUIRED", previous_year_vat=True, dmp_eligibility=rejected)
        self.assertEqual(r["overall"]["code"], "REVIEW_REQUIRED")
        self.assertEqual(r["dmp"]["code"], "NOT_SUITABLE")
        self.assertIn("DMP-MIN-DEBT", r["reason_codes"])

    def test_vat_alone_keeps_the_dmp_as_potentially_suitable(self):
        r = _interpret(engine_solution="FORCED_DMP_VAT", previous_year_vat=True)
        self.assertEqual(r["dmp"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(r["iva_reasons"][0]["code"], "FORCED_DMP_VAT")

    def test_dro_alone_is_unchanged(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", lead_gen_disposable_income=250.0)
        self.assertEqual(r["overall"]["code"], "DRO_REFER")
        self.assertEqual(r["dmp"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(r["iva_reasons"][0]["code"], "FORCED_DRO_LG")
        self.assertEqual(r["review_reasons"], [])

    def test_conflict_with_no_income_recorded_keeps_the_vat_outcome_only(self):
        r = _interpret(engine_solution="REVIEW_REQUIRED", previous_year_vat=True, income_missing=True)
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")
        self.assertIn("FORCED_DMP_VAT", r["reason_codes"])
        self.assertEqual(r["review_reasons"], [])

    def test_review_required_without_vat_is_unchanged(self):
        dnv = [{"creditor_name": "A", "effective_status": "DO_NOT_VOTE", "is_secured": False}]
        r = _interpret(engine_solution="REVIEW_REQUIRED", creditor_positions=dnv)
        self.assertEqual(r["iva"]["code"], "NEEDS_REVIEW")
        self.assertNotIn("FORCED_DMP_VAT", r["reason_codes"])


class LeadGenVatEndpointTests(_LeadGenFixture):

    def _record(self, ref):
        return LeadGenCheck.objects.get(aryza_reference=ref)

    def test_hmrc_creditor_is_reported(self):
        body = self._check(_hmrc_case("LG-VAT-HMRC")).json()
        self.assertIs(body["hmrc_is_creditor"], True)
        self.assertNotEqual(self._record("LG-VAT-HMRC").engine_recommended_solution, "FORCED_DMP_VAT")

    def test_no_hmrc_creditor_is_reported(self):
        self.assertIs(self._check(self._good_case("LG-VAT-NONE")).json()["hmrc_is_creditor"], False)

    def test_previous_year_vat_forces_dmp(self):
        body = self._check(_hmrc_case("LG-VAT-PREV"), data={"dmp_checklist": BOTH_VAT}).json()
        self.assertEqual(body["iva"]["code"], "NOT_SUITABLE")
        self.assertIn("FORCED_DMP_VAT", [r["code"] for r in body["reasons"]])
        self.assertEqual(body["dmp"]["code"], "POTENTIALLY_SUITABLE")
        self.assertEqual(self._record("LG-VAT-PREV").engine_recommended_solution, "FORCED_DMP_VAT")

    def test_has_vat_alone_changes_nothing(self):
        plain = self._check(_hmrc_case("LG-VAT-A")).json()
        ticked = self._check(_hmrc_case("LG-VAT-B"), data={"dmp_checklist": {"hmrc_debt_has_vat": True}}).json()
        for key in ("overall", "iva", "dmp", "dro"):
            self.assertEqual(plain[key], ticked[key], key)
        self.assertNotEqual(self._record("LG-VAT-B").engine_recommended_solution, "FORCED_DMP_VAT")

    def test_previous_year_without_has_vat_changes_nothing(self):
        self._check(_hmrc_case("LG-VAT-CHILD"), data={"dmp_checklist": {"hmrc_previous_year_vat": True}})
        self.assertNotEqual(self._record("LG-VAT-CHILD").engine_recommended_solution, "FORCED_DMP_VAT")

    def test_vat_answers_are_ignored_without_an_hmrc_creditor(self):
        plain = self._check(self._good_case("LG-VAT-X1")).json()
        ticked = self._check(self._good_case("LG-VAT-X2"), data={"dmp_checklist": BOTH_VAT}).json()
        self.assertIs(ticked["hmrc_is_creditor"], False)
        for key in ("overall", "iva", "dmp", "dro", "reasons"):
            self.assertEqual(plain[key], ticked[key], key)
        self.assertNotEqual(self._record("LG-VAT-X2").engine_recommended_solution, "FORCED_DMP_VAT")

    def test_ignoring_vat_keeps_the_other_dmp_answers(self):
        body = self._check(self._good_case("LG-VAT-X3"), data={"dmp_checklist": dict(
            BOTH_VAT, council_tax_current_year=True, council_tax_previous_year=True,
            lost_right_to_pay_instalments=True, current_gas_bill=True,
        )}).json()
        self.assertEqual(body["dmp"]["code"], "NOT_SUITABLE")
        self.assertIn("current gas bill", " ".join(body["dmp_notes"]))

    # ---- VAT and the low-income DRO rule together (engine: REVIEW_REQUIRED) ----

    def test_vat_with_low_income_dro_is_flagged_for_caseworker_review(self):
        case = _hmrc_case("LG-VAT-DRO", income_pence=30_000, expenditure_pence=10_000)
        body = self._check(case, data={"dmp_checklist": BOTH_VAT}).json()
        rec = self._record("LG-VAT-DRO")
        self.assertEqual(rec.engine_recommended_solution, "REVIEW_REQUIRED")
        self.assertEqual(body["overall"]["code"], "REVIEW_REQUIRED")
        self.assertEqual(body["overall"]["label"], "Caseworker review needed — DRO or DMP")
        self.assertEqual(rec.overall_outcome, "REVIEW_REQUIRED")
        # No automatic DRO referral and no route chosen.
        self.assertNotEqual(body["dro"]["code"], "REFER")
        self.assertFalse(rec.dro_referral)
        self.assertEqual(body["iva"]["code"], "NOT_SUITABLE")
        self.assertEqual(rec.iva_outcome, "NOT_SUITABLE")
        self.assertEqual(body["reasons"][0]["text"], "IVA is not currently suitable for this conflict")
        self.assertEqual(body["dmp"]["code"], "REVIEW_REQUIRED")
        self.assertEqual(rec.dmp_outcome, "REVIEW_REQUIRED")
        self.assertNotIn("FORCED_DMP_VAT", rec.reason_codes)
        conflict = [r for r in body["review_reasons"] if r["code"] == "FORCED-SOLUTION-CONFLICT"]
        self.assertEqual(len(conflict), 1)
        self.assertIn("caseworker needs to decide between a DRO and a DMP", conflict[0]["text"])
        self.assertIn("below the £399.00 Lead Gen threshold", conflict[0]["detail"])

    def test_vat_alone_is_not_flagged_for_review(self):
        body = self._check(_hmrc_case("LG-VAT-ONLY"), data={"dmp_checklist": BOTH_VAT}).json()
        self.assertEqual(body["overall"]["code"], "POTENTIALLY_SUITABLE")
        self.assertNotIn("FORCED-SOLUTION-CONFLICT", [r["code"] for r in body["review_reasons"]])
        self.assertNotEqual(body["dro"]["code"], "REFER")

    def test_vat_with_no_income_recorded_keeps_the_vat_outcome(self):
        case = _hmrc_case("LG-VAT-NOINC", income_pence=0, expenditure_pence=0)
        body = self._check(case, data={"dmp_checklist": BOTH_VAT}).json()
        self.assertEqual(self._record("LG-VAT-NOINC").engine_recommended_solution, "REVIEW_REQUIRED")
        self.assertNotEqual(body["overall"]["code"], "REVIEW_REQUIRED")
        self.assertNotEqual(body["dro"]["code"], "REFER")
        self.assertEqual(body["iva"]["code"], "NOT_SUITABLE")
        self.assertIn("FORCED_DMP_VAT", [r["code"] for r in body["reasons"]])
        self.assertNotIn("FORCED-SOLUTION-CONFLICT", [r["code"] for r in body["review_reasons"]])
        self.assertIn("INCOME-NOT-RECORDED", [w["code"] for w in body["warnings"]])

    def test_no_income_recorded_without_vat_is_unchanged(self):
        body = self._check(_hmrc_case("LG-NOINC", income_pence=0, expenditure_pence=0)).json()
        self.assertEqual(self._record("LG-NOINC").engine_recommended_solution, "FORCED_DRO_LG")
        self.assertNotEqual(body["dro"]["code"], "REFER")
        self.assertNotEqual(body["overall"]["code"], "REVIEW_REQUIRED")
        self.assertIn("INCOME-NOT-RECORDED", [w["code"] for w in body["warnings"]])

    def test_low_income_dro_without_vat_is_unchanged(self):
        case = _hmrc_case("LG-VAT-DRO2", income_pence=30_000, expenditure_pence=10_000)
        body = self._check(case).json()
        self.assertEqual(body["overall"]["code"], "DRO_REFER")
        self.assertEqual(body["dro"]["code"], "REFER")
        # Engine flags are listed for review; the conflict reason is not.
        self.assertNotIn("FORCED-SOLUTION-CONFLICT", [r["code"] for r in body["review_reasons"]])
        self.assertEqual(self._record("LG-VAT-DRO2").engine_recommended_solution, "FORCED_DRO_LG")
