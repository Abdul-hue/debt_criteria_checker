"""
Lead Gen estimated disposable income (informational guideline only).

  * EstimateCalculationTests — services.lead_gen.estimate_disposable_income:
    the manager's formula, unavailable states, unusual household values.
  * SfsHouseholdFetchTests — AryzaClient.fetch_sfs_household running its real
    SQL against minimal client_sfs / client_expenses tables in the test DB:
    active SFS, empty SFS, rent row selection, frequency normalisation,
    mortgage never substituted.
  * EstimateEndpointTests — the estimate is returned by the Lead Gen check and
    the IVA / DMP / DRO outcomes are identical with or without it.
"""

from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase

from debt_app.aryza_client import AryzaClient
from debt_app.models import LeadGenCheck
from debt_app.services.lead_gen import estimate_disposable_income
from debt_app.tests_lead_gen import _LeadGenFixture

FETCH_HOUSEHOLD = "debt_app.views.lead_gen_views.fetch_sfs_household"


def _household(adults=1, under_16=0, under_18=0, rent=80_000, status="OK"):
    return {"status": status, "adults": adults, "under_16": under_16, "under_18": under_18,
            "rent_monthly_pence": rent}


def _codes(result):
    return [r["code"] for r in result["reasons"]]


class EstimateCalculationTests(SimpleTestCase):

    def test_one_adult_no_children(self):
        r = estimate_disposable_income(_household(adults=1, rent=50_000), 200_000)
        self.assertTrue(r["available"])
        self.assertEqual(r["minimum_expenditure"], 799.0)
        self.assertEqual(r["estimated_disposable_income"], 2000 - 500 - 799)

    def test_two_adults_no_children(self):
        r = estimate_disposable_income(_household(adults=2, rent=50_000), 200_000)
        self.assertEqual(r["minimum_expenditure"], 1378.0)
        self.assertEqual(r["estimated_disposable_income"], 2000 - 500 - 1378)

    def test_two_adults_two_children(self):
        r = estimate_disposable_income(_household(adults=2, under_16=2, rent=50_000), 300_000)
        self.assertEqual((r["adults"], r["children"]), (2, 2))
        self.assertEqual(r["minimum_expenditure"], 799 + 579 + 2 * 331)  # 2,040

    def test_three_adults_three_children(self):
        r = estimate_disposable_income(_household(adults=3, under_16=3, rent=50_000), 400_000)
        self.assertEqual(r["minimum_expenditure"], 799 + 2 * 579 + 3 * 331)  # 2,950
        self.assertEqual(r["estimated_disposable_income"], 4000 - 500 - 2950)

    def test_worked_example_monthly_rent_and_message(self):
        """2 adults, 1 child, £800 rent, £2,500 income -> £1,709 minimum, -£9 estimate."""
        r = estimate_disposable_income(_household(adults=2, under_16=1, rent=80_000), 250_000)
        self.assertEqual(r["monthly_income"], 2500.0)
        self.assertEqual(r["monthly_rent"], 800.0)
        self.assertEqual(r["minimum_expenditure"], 1709.0)
        self.assertEqual(r["estimated_disposable_income"], -9.0)
        self.assertEqual(r["message"], (
            "For 2 adult(s) and 1 child(ren), the estimated disposable income is -£9.00 per month. "
            "Please use this estimate as a guideline only when making your decision. "
            "A full I&E assessment is still required to confirm affordability and suitability."
        ))
        self.assertNotIn("eligible", r["message"].lower())

    def test_16_and_17_year_olds_count_as_children(self):
        r = estimate_disposable_income(_household(adults=1, under_16=1, under_18=2), 300_000)
        self.assertEqual(r["children"], 3)
        self.assertEqual(r["minimum_expenditure"], 799 + 3 * 331)

    def test_unusual_numeric_household_is_not_capped(self):
        r = estimate_disposable_income(_household(adults=6, under_16=5, under_18=3), 900_000)
        self.assertTrue(r["available"])
        self.assertEqual((r["adults"], r["children"]), (6, 8))
        self.assertEqual(r["minimum_expenditure"], 799 + 5 * 579 + 8 * 331)

    def test_zero_adults_is_invalid_not_estimated(self):
        r = estimate_disposable_income(_household(adults=0), 250_000)
        self.assertFalse(r["available"])
        self.assertEqual(_codes(r), ["INVALID_HOUSEHOLD"])

    def test_missing_or_negative_household_counts_are_invalid(self):
        for hh in (_household(adults=None), _household(under_16=None), _household(under_18=-1)):
            self.assertEqual(_codes(estimate_disposable_income(hh, 250_000)), ["INVALID_HOUSEHOLD"])

    def test_no_sfs_and_empty_sfs_are_unavailable(self):
        for status in ("NO_SFS", "EMPTY_SFS"):
            r = estimate_disposable_income({"status": status}, 250_000)
            self.assertFalse(r["available"])
            self.assertEqual(r["reasons"][0]["text"],
                             "Estimated disposable income unavailable — SFS information is not available.")
        self.assertEqual(_codes(estimate_disposable_income(None, 250_000)), ["NO_SFS"])

    def test_unreadable_sfs_is_unavailable(self):
        self.assertEqual(_codes(estimate_disposable_income({"status": "ERROR"}, 250_000)), ["SFS_UNREADABLE"])

    def test_no_rent_is_unavailable_not_zero(self):
        r = estimate_disposable_income(_household(rent=None), 250_000)
        self.assertFalse(r["available"])
        self.assertNotIn("estimated_disposable_income", r)
        self.assertEqual(r["reasons"][0]["text"],
                         "Estimated disposable income unavailable — current rent is not recorded.")

    def test_missing_income_is_unavailable_not_a_zero_estimate(self):
        for income in (0, None):
            r = estimate_disposable_income(_household(), income)
            self.assertFalse(r["available"])
            self.assertEqual(_codes(r), ["INCOME_NOT_RECORDED"])

    def test_every_missing_item_is_reported(self):
        r = estimate_disposable_income(_household(adults=0, rent=None), 0)
        self.assertEqual(_codes(r), ["INVALID_HOUSEHOLD", "RENT_NOT_RECORDED", "INCOME_NOT_RECORDED"])


class SfsHouseholdFetchTests(TestCase):
    """Real fetch_sfs_household SQL against the test database."""

    CLIENT = 501

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as c:
            c.execute("CREATE TABLE client_sfs (id INTEGER PRIMARY KEY, clientid INTEGER, active INTEGER, "
                      "no_adults INTEGER, under_16 INTEGER, under_18 INTEGER)")
            c.execute("CREATE TABLE client_expenses (id INTEGER PRIMARY KEY, clientid INTEGER, type TEXT, "
                      "field TEXT, value DECIMAL(11,2), statement_id INTEGER, frequency TEXT)")

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as c:
            c.execute("DROP TABLE client_sfs")
            c.execute("DROP TABLE client_expenses")
        super().tearDownClass()

    def _sfs(self, sfs_id, adults=2, under_16=1, under_18=0, active=1, clientid=None):
        with connection.cursor() as c:
            c.execute("INSERT INTO client_sfs VALUES (%s, %s, %s, %s, %s, %s)",
                      [sfs_id, clientid or self.CLIENT, active, adults, under_16, under_18])

    def _expense(self, row_id, sfs_id, field, value, frequency="monthly", type_="sfs", clientid=None):
        with connection.cursor() as c:
            c.execute("INSERT INTO client_expenses VALUES (%s, %s, %s, %s, %s, %s, %s)",
                      [row_id, clientid or self.CLIENT, type_, field, value, sfs_id, frequency])

    def _fetch(self):
        return AryzaClient().fetch_sfs_household(self.CLIENT, connection=connection)

    def test_household_and_monthly_rent_from_active_sfs(self):
        self._sfs(10, adults=2, under_16=1, under_18=1)
        self._expense(1, 10, "rent", "800.00")
        hh = self._fetch()
        self.assertEqual(hh, {"status": "OK", "adults": 2, "under_16": 1, "under_18": 1,
                              "rent_monthly_pence": 80_000})

    def test_weekly_rent_uses_existing_normalisation(self):
        self._sfs(10)
        self._expense(1, 10, "rent", "150.00", frequency="weekly")
        expected = AryzaClient()._normalise_to_monthly(15_000, "weekly")
        self.assertEqual(expected, 65_000)  # 150 x 52 / 12
        self.assertEqual(self._fetch()["rent_monthly_pence"], expected)

    def test_multiple_rent_rows_use_latest_only(self):
        self._sfs(10)
        self._expense(1, 10, "rent", "582.00")
        self._expense(2, 10, "rent", "200.00")
        self._expense(3, 10, "rent", None)  # a blank later row is not an applicable rent
        self.assertEqual(self._fetch()["rent_monthly_pence"], 20_000)

    def test_inactive_and_older_sfs_are_ignored(self):
        self._sfs(5, adults=1, under_16=0)
        self._expense(1, 5, "rent", "300.00")
        self._sfs(20, adults=4, under_16=0, active=0)
        self._expense(2, 20, "rent", "999.00")
        self._sfs(10, adults=2, under_16=3)
        self._expense(3, 10, "rent", "700.00")
        hh = self._fetch()
        self.assertEqual((hh["adults"], hh["under_16"], hh["rent_monthly_pence"]), (2, 3, 70_000))

    def test_rent_row_for_another_client_is_ignored(self):
        self._sfs(10)
        self._expense(1, 10, "food", "300.00")
        self._expense(2, 10, "rent", "800.00", clientid=999)
        self.assertIsNone(self._fetch()["rent_monthly_pence"])

    def test_no_active_sfs(self):
        self._sfs(10, active=0)
        self._expense(1, 10, "rent", "800.00")
        self.assertEqual(self._fetch()["status"], "NO_SFS")

    def test_empty_sfs(self):
        self._sfs(10)
        self._expense(1, 10, "rent", "800.00", type_="cfs")  # other statement types don't fill the SFS
        hh = self._fetch()
        self.assertEqual(hh["status"], "EMPTY_SFS")
        self.assertIsNone(hh["adults"])
        self.assertFalse(estimate_disposable_income(hh, 250_000)["available"])

    def test_no_rent_row(self):
        self._sfs(10)
        self._expense(1, 10, "food", "300.00")
        hh = self._fetch()
        self.assertEqual(hh["status"], "OK")
        self.assertIsNone(hh["rent_monthly_pence"])
        self.assertEqual(_codes(estimate_disposable_income(hh, 250_000)), ["RENT_NOT_RECORDED"])

    def test_mortgage_without_rent_is_not_substituted(self):
        self._sfs(10)
        self._expense(1, 10, "mortgage", "900.00")
        self._expense(2, 10, "rent", None)
        hh = self._fetch()
        self.assertIsNone(hh["rent_monthly_pence"])
        r = estimate_disposable_income(hh, 250_000)
        self.assertFalse(r["available"])
        self.assertEqual(_codes(r), ["RENT_NOT_RECORDED"])

    def test_mortgage_is_not_added_to_rent(self):
        self._sfs(10)
        self._expense(1, 10, "mortgage", "900.00")
        self._expense(2, 10, "rent", "400.00")
        self.assertEqual(self._fetch()["rent_monthly_pence"], 40_000)

    def test_query_failure_is_reported_not_zeroed(self):
        hh = AryzaClient().fetch_sfs_household(self.CLIENT, connection=_BrokenConnection())
        self.assertEqual(hh["status"], "ERROR")
        self.assertEqual(_codes(estimate_disposable_income(hh, 250_000)), ["SFS_UNREADABLE"])


class _BrokenConnection:
    def cursor(self):
        raise RuntimeError("down")


class EstimateEndpointTests(_LeadGenFixture):

    OUTCOME_KEYS = ("overall", "iva", "dmp", "dro", "reasons", "review_reasons", "evidence_required_later")

    def _check_with(self, case, household):
        case.clientid = 4242
        with patch(FETCH_HOUSEHOLD, return_value=household) as fetch:
            body = self._check(case).json()
        fetch.assert_called_once_with(4242)
        return body

    def _record(self, ref):
        rec = LeadGenCheck.objects.filter(aryza_reference=ref).latest("id")
        return (rec.iva_outcome, rec.dmp_outcome, rec.dro_referral, rec.overall_outcome,
                rec.engine_recommended_solution, rec.reason_codes)

    def test_estimate_returned_with_breakdown(self):
        body = self._check_with(self._good_case("LG-EDI"), _household(adults=2, under_16=1, rent=80_000))
        edi = body["estimated_disposable_income"]
        self.assertTrue(edi["available"])
        # _good_case income is £2,500 (CaseData.income["total"]).
        self.assertEqual((edi["monthly_income"], edi["monthly_rent"], edi["minimum_expenditure"],
                          edi["estimated_disposable_income"]), (2500.0, 800.0, 1709.0, -9.0))

    def test_aryza_non_monthly_figures_accompany_the_estimate(self):
        case = self._good_case("LG-EDI-WEEKLY")
        case.non_monthly_income = [{"source": "Child Benefit", "amount": 27.0, "frequency": "weekly", "monthly": 117.0}]
        edi = self._check_with(case, _household())["estimated_disposable_income"]
        self.assertEqual(edi["non_monthly_income"], case.non_monthly_income)
        self.assertEqual(self._check_with(self._good_case("LG-EDI-MONTHLY"), _household())
                         ["estimated_disposable_income"]["non_monthly_income"], [])

    def test_unavailable_when_case_has_no_sfs(self):
        body = self._check(self._good_case("LG-EDI-NONE")).json()  # clientid 0 -> no lookup
        self.assertEqual(_codes(body["estimated_disposable_income"]), ["NO_SFS"])

    def test_estimate_failure_never_breaks_the_check(self):
        case = self._good_case("LG-EDI-ERR")
        case.clientid = 7
        with patch(FETCH_HOUSEHOLD, side_effect=RuntimeError("boom")):
            resp = self._check(case)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_codes(resp.json()["estimated_disposable_income"]), ["SFS_UNREADABLE"])

    def test_iva_result_unchanged_by_estimate(self):
        """A strongly negative estimate does not change a potentially-suitable IVA."""
        baseline = self._check(self._good_case("LG-EDI-IVA")).json()
        with_estimate = self._check_with(self._good_case("LG-EDI-IVA"), _household(adults=5, under_16=4, rent=150_000))
        self.assertLess(with_estimate["estimated_disposable_income"]["estimated_disposable_income"], 0)
        for key in self.OUTCOME_KEYS:
            self.assertEqual(with_estimate[key], baseline[key], key)
        recs = LeadGenCheck.objects.filter(aryza_reference="LG-EDI-IVA").order_by("id")
        self.assertEqual(len({(r.iva_outcome, r.overall_outcome, r.engine_recommended_solution) for r in recs}), 1)

    def test_dro_result_unchanged_by_estimate(self):
        """Low income still forces the existing £399 DRO route; the separate estimate does not alter it."""
        case = lambda: self._good_case("LG-EDI-DRO", income_pence=30_000, expenditure_pence=10_000)
        baseline = self._check(case()).json()
        before = self._record("LG-EDI-DRO")
        with_estimate = self._check_with(case(), _household(adults=1, rent=0))
        self.assertEqual(baseline["overall"]["code"], "DRO_REFER")
        for key in self.OUTCOME_KEYS:
            self.assertEqual(with_estimate[key], baseline[key], key)
        self.assertEqual(self._record("LG-EDI-DRO"), before)
        self.assertEqual(before[4], "FORCED_DRO_LG")
