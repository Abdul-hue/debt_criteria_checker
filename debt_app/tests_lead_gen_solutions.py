"""
Lead Gen: rent in the £399 rule, and the DRO / Bankruptcy / DMP solution cards
(business decisions 2026-10-13).

  * LeadGenRentEngineTests — lead_gen_disposable_income deducts the SFS rent
    (payload `rent_monthly`) when no credit-report mortgage payment exists.
  * LeadGenSfsRentTests — lead_gen_sfs_rent reads only a usable SFS rent.
  * LeadGenSolutionInterpretationTests — the DRO / Bankruptcy outcomes, the
    DRO limits gating the £399 referral, and the DMP surplus check.
  * LeadGenSolutionEndpointTests — the check end to end: SFS rent read once
    and used, advisor answers reaching the DRO card.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from debt_app.criteria_engine import assess_case, detect_representatives
from debt_app.engine.criteria import _evaluate_dro_solution
from debt_app.helpers import CreditorCriteria
from debt_app.models import CreditReport, LeadGenCheck
from debt_app.services import lead_gen
from debt_app.services.lead_gen import interpret_engine_result, lead_gen_solution_inputs
from debt_app.tests_lead_gen import _LeadGenFixture
from debt_app.tests_leadgen_dro_disposable_income import _build_case_data_obj, _mortgage_account
from debt_app.views.criteria_views import AssessCaseView, lead_gen_sfs_rent

FETCH_HOUSEHOLD = "debt_app.views.lead_gen_views.fetch_sfs_household"


def _engine(case_data_obj, rent=None):
    payload, _prepared, _unmatched = AssessCaseView()._prepare_engine_payload(case_data_obj)
    payload["source_department"] = "Lead Generation"
    if rent is not None:
        payload["rent_monthly"] = rent
    return assess_case(payload, detect_representatives(payload.get("creditors") or []))


class LeadGenRentEngineTests(TestCase):

    def setUp(self):
        CreditorCriteria.objects.create(creditor_name="Test Loan Co", representative="NONE",
                                        status="WILL_CONSIDER", is_active=True)

    def test_rent_is_deducted_for_a_tenant(self):
        result = _engine(_build_case_data_obj("LG-RENT-1", total_income_pence=100_000), rent=700.0)
        self.assertAlmostEqual(result["lead_gen_disposable_income"], 300.0, places=2)
        self.assertEqual(result["lead_gen_housing"], {"source": "rent", "amount": 700.0})
        self.assertEqual(result["recommended_solution"], "FORCED_DRO_LG")

    def test_mortgage_payment_takes_precedence_over_rent(self):
        ref = "LG-RENT-2"
        CreditReport.objects.create(aryza_reference=ref, uploaded_file="fake.pdf", extraction_status="extracted",
                                    extracted_data={"accounts": [],
                                                    "mortgage_accounts": [_mortgage_account(10_000_00, 50_000)]})
        result = _engine(_build_case_data_obj(ref, total_income_pence=200_000), rent=900.0)
        self.assertAlmostEqual(result["lead_gen_disposable_income"], 1500.0, places=2)
        self.assertEqual(result["lead_gen_housing"]["source"], "mortgage")

    def test_no_rent_or_mortgage_uses_income_alone(self):
        result = _engine(_build_case_data_obj("LG-RENT-3", total_income_pence=100_000))
        self.assertAlmostEqual(result["lead_gen_disposable_income"], 1000.0, places=2)
        self.assertIsNone(result["lead_gen_housing"])

    def test_rent_never_touches_the_ordinary_disposable_income(self):
        a = _engine(_build_case_data_obj("LG-RENT-4", total_income_pence=100_000), rent=700.0)
        b = _engine(_build_case_data_obj("LG-RENT-4", total_income_pence=100_000))
        self.assertEqual(a["disposable_income"], b["disposable_income"])


class LeadGenSfsRentTests(SimpleTestCase):

    def test_usable_rent_in_pounds(self):
        self.assertEqual(lead_gen_sfs_rent(None, {"status": "OK", "rent_monthly_pence": 65_000}), 650.0)

    def test_unrecorded_or_unusable_rent_is_none(self):
        for household in ({"status": "OK", "rent_monthly_pence": None}, {"status": "EMPTY_SFS"},
                          {"status": "ERROR"}, {"status": "OK", "rent_monthly_pence": -5}):
            with self.subTest(household=household):
                self.assertIsNone(lead_gen_sfs_rent(None, household))

    def test_no_client_id_skips_the_read(self):
        case = type("Case", (), {"clientid": 0})()
        with patch("debt_app.views.criteria_views.fetch_sfs_household") as fetch:
            self.assertIsNone(lead_gen_sfs_rent(case))
        fetch.assert_not_called()

    def test_failed_read_is_none(self):
        case = type("Case", (), {"clientid": 7})()
        with patch("debt_app.views.criteria_views.fetch_sfs_household", side_effect=RuntimeError("down")):
            self.assertIsNone(lead_gen_sfs_rent(case))


_ELIGIBLE = {"status": "DMP_ELIGIBLE", "reasons": [], "notes": []}
_ACCEPT_POS = [{"creditor_name": "A", "effective_status": "ACCEPT", "is_secured": False}]
_SURPLUS = "Monthly surplus is £200.00. A DRO needs it to be less than £75 a month."


def _card(code, status, reasons=(), to_confirm=(), notes=()):
    return {"code": code, "status": status, "reasons": list(reasons), "to_confirm": list(to_confirm),
            "notes": list(notes)}


def _cards(dro=None, bankruptcy=None, dmp=None):
    return [dmp or _card("DMP", "ELIGIBLE"), dro or _card("DRO", "NEEDS_REVIEW", to_confirm=["Confirm assets."]),
            bankruptcy or _card("BANKRUPTCY", "NEEDS_REVIEW", to_confirm=["Confirm E&W."])]


def _interpret(**kw):
    args = dict(engine_solution="IVA_VIABLE", hard_blocks=[], flags=[], creditor_positions=_ACCEPT_POS,
                dmp_eligibility=_ELIGIBLE, documents_supplied=False, solution_eligibility=_cards())
    args.update(kw)
    return interpret_engine_result(**args)


class LeadGenSolutionInterpretationTests(SimpleTestCase):

    def test_dro_and_bankruptcy_are_shown_with_what_to_confirm(self):
        r = _interpret()
        self.assertEqual(r["dro"]["code"], "NEEDS_REVIEW")
        self.assertEqual(r["dro"]["label"], "DRO — Potentially suitable, details to confirm")
        self.assertEqual(r["dro"]["to_confirm"], ["Confirm assets."])
        self.assertEqual(r["bankruptcy"]["code"], "NEEDS_REVIEW")

    def test_dro_not_eligible_lists_its_reasons(self):
        r = _interpret(solution_eligibility=_cards(dro=_card("DRO", "NOT_ELIGIBLE", reasons=["Debt too high."])))
        self.assertEqual(r["dro"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["dro"]["reasons"], [{"code": "DRO-1", "text": "Debt too high.", "detail": None}])

    def test_a_possible_dro_makes_the_case_potentially_suitable(self):
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[lead_gen_rule("TIG-01")],
                       dmp_eligibility={"status": "DMP_REJECTED", "reasons": ["x"], "notes": []},
                       solution_eligibility=_cards(dmp=_card("DMP", "NOT_ELIGIBLE", reasons=["x"])))
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")

    def test_a_possible_dro_does_not_count_when_income_is_not_recorded(self):
        r = _interpret(engine_solution="IVA_NOT_VIABLE", hard_blocks=[lead_gen_rule("TIG-01")],
                       dmp_eligibility={"status": "DMP_REJECTED", "reasons": ["x"], "notes": []},
                       solution_eligibility=_cards(dmp=_card("DMP", "NOT_ELIGIBLE", reasons=["x"])),
                       income_missing=True)
        self.assertEqual(r["overall"]["code"], "DOES_NOT_MEET_CRITERIA")

    def test_399_rule_refers_when_only_the_surplus_limit_fails(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", lead_gen_disposable_income=250.0,
                       solution_eligibility=_cards(dro=_card("DRO", "NOT_ELIGIBLE", reasons=[_SURPLUS],
                                                             to_confirm=["Confirm assets."])))
        self.assertEqual(r["overall"]["code"], "DRO_REFER")
        self.assertEqual(r["dro"]["code"], "REFER")
        self.assertEqual(r["dro"]["reasons"], [])
        self.assertEqual(r["dro"]["to_confirm"], [_SURPLUS, "Confirm assets."])

    def test_399_rule_does_not_refer_when_a_dro_limit_fails(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", lead_gen_disposable_income=250.0,
                       solution_eligibility=_cards(dro=_card("DRO", "NOT_ELIGIBLE", reasons=[
                           _SURPLUS, "The customer has had a DRO in the last six years."])))
        self.assertNotEqual(r["overall"]["code"], "DRO_REFER")
        self.assertEqual(r["dro"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["iva"]["code"], "NOT_SUITABLE")  # the £399 rule still rules out the IVA
        self.assertIn("a DRO is not possible", r["iva_reasons"][0]["detail"])
        self.assertEqual(r["overall"]["code"], "POTENTIALLY_SUITABLE")  # DMP still works

    def test_forced_dro_detail_names_the_rent(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", lead_gen_disposable_income=300.0,
                       lead_gen_housing={"source": "rent", "amount": 700.0})
        self.assertIn("after rent (£700.00 a month on the SFS) is £300.00", r["iva_reasons"][0]["detail"])

    def test_forced_dro_detail_without_housing(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", lead_gen_disposable_income=300.0)
        self.assertIn("(no rent or mortgage payment is recorded)", r["iva_reasons"][0]["detail"])

    def test_dmp_needs_money_left_each_month(self):
        no_surplus = "The customer has no money left each month after essential spending, so ..."
        r = _interpret(solution_eligibility=_cards(dmp=_card("DMP", "NOT_ELIGIBLE", reasons=[no_surplus])))
        self.assertEqual(r["dmp"]["code"], "NOT_SUITABLE")
        self.assertEqual(r["dmp_reasons"], [{"code": "DMP-NO-SURPLUS",
                                             "text": "No money left each month for a DMP payment",
                                             "detail": no_surplus}])

    def test_dmp_card_repeating_its_own_reasons_adds_nothing(self):
        dmp = {"status": "DMP_REJECTED", "reasons": ["The customer's total debt is £10.00, ..."], "notes": []}
        r = _interpret(dmp_eligibility=dmp,
                       solution_eligibility=_cards(dmp=_card("DMP", "NOT_ELIGIBLE", reasons=dmp["reasons"])))
        self.assertEqual([x["code"] for x in r["dmp_reasons"]], ["DMP-MIN-DEBT"])

    def test_no_cards_keeps_the_previous_behaviour(self):
        r = _interpret(engine_solution="FORCED_DRO_LG", solution_eligibility=None)
        self.assertEqual(r["overall"]["code"], "DRO_REFER")
        self.assertEqual(r["bankruptcy"]["code"], "NOT_ASSESSED")

    def test_engine_surplus_wording_is_pinned(self):
        card = _evaluate_dro_solution({"total_debt": 10_000, "total_income": 2000, "disposable_income": 200})
        self.assertTrue(any(t.startswith(lead_gen._DRO_SURPLUS_PREFIX) for t in card["reasons"]), card["reasons"])

    def test_solution_answers(self):
        self.assertEqual(
            lead_gen_solution_inputs('{"assets_over_2000": "no", "dro_in_last_6_years": true, "x": "yes"}'),
            {"assets_over_2000": False, "england_wales_connection": None, "currently_insolvent": None,
             "dro_in_last_6_years": True},
        )
        self.assertEqual(set(lead_gen_solution_inputs("not json").values()), {None})


def lead_gen_rule(rule_id):
    from debt_app.engine.criteria import RuleResult
    return RuleResult(rule_id=rule_id, severity="hard_block", triggered=True, message="m")


class LeadGenSolutionEndpointTests(_LeadGenFixture):

    def _tenant(self, ref, rent_pence):
        case = self._good_case(ref)  # £2,500 income, £10,500 debt
        case.clientid = 4242
        household = {"status": "OK", "adults": 1, "under_16": 0, "under_18": 0, "rent_monthly_pence": rent_pence}
        return case, household

    def test_sfs_rent_is_read_once_and_feeds_the_399_rule(self):
        case, household = self._tenant("LG-SOL-RENT", 220_000)  # £2,500 - £2,200 = £300
        with patch(FETCH_HOUSEHOLD, return_value=household) as fetch:
            body = self._check(case).json()
        fetch.assert_called_once_with(4242)
        self.assertEqual(body["overall"]["code"], "DRO_REFER")
        self.assertIn("after rent (£2,200.00 a month on the SFS)", body["iva_reasons"][0]["detail"])
        self.assertTrue(body["estimated_disposable_income"]["available"])
        self.assertTrue(LeadGenCheck.objects.get(aryza_reference="LG-SOL-RENT").dro_referral)

    def test_without_rent_the_same_case_is_not_referred(self):
        case, household = self._tenant("LG-SOL-NORENT", None)
        with patch(FETCH_HOUSEHOLD, return_value=household):
            body = self._check(case).json()
        self.assertNotEqual(body["overall"]["code"], "DRO_REFER")

    def test_advisor_answer_can_rule_out_the_dro(self):
        case, household = self._tenant("LG-SOL-PREVDRO", 220_000)
        with patch(FETCH_HOUSEHOLD, return_value=household):
            body = self._check(case, data={"solution_checklist": {"dro_in_last_6_years": True}}).json()
        self.assertEqual(body["dro"]["code"], "NOT_SUITABLE")
        self.assertIn("The customer has had a DRO in the last six years.",
                      [r["text"] for r in body["dro"]["reasons"]])
        self.assertNotEqual(body["overall"]["code"], "DRO_REFER")
        self.assertFalse(LeadGenCheck.objects.get(aryza_reference="LG-SOL-PREVDRO").dro_referral)

    def test_bankruptcy_is_returned(self):
        body = self._check(self._good_case("LG-SOL-BKY")).json()
        self.assertIn(body["bankruptcy"]["code"], ("POTENTIALLY_SUITABLE", "NEEDS_REVIEW", "NOT_SUITABLE"))
        self.assertTrue(body["bankruptcy"]["notes"])
