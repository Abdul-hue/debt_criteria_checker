"""
WATCH-22.9 / TIX-07 vehicle-value flag tests.

Manager's requirement (2026-09-15): WATCH and TIX have voting behaviour tied
to car value — WATCH's guideline is £9,000, TIX's is £14,000. If the vehicle
is on hire purchase, the figure that matters is its true value to the
estate: vehicle value minus the outstanding HP balance (the finance company,
not the client, owns the rest). The flag only needs to be raised when the
body in question actually holds the case's majority vote — i.e. controls
the outcome, not merely a blocking minority (contrast the existing
council_is_majority >25%-blocking-minority pattern).

Worked example from the requirement: HP balance £14,000, car value £10,000
-> net value £10,000 - £14,000 = -£4,000 -> below both thresholds -> no flag,
regardless of majority. Covered by both HP-netting test classes below.
"""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from debt_app.aryza_client import CaseData
from debt_app.criteria_engine import (
    _net_vehicle_value,
    _parse_case,
    _representative_balance_majority,
    _tix_07,
    _watch_22_9,
    assess_case,
    detect_representatives,
)
from debt_app.models import CreditorCriteria


def _hp_creditor(balance, creditor_type="car_hp", name="Black Horse"):
    return {
        "name": name,
        "balance": balance,
        "debt_type_normalised": "hire_purchase",
        "creditor_type": creditor_type,
    }


def _case(vehicle_value=None, creditors=None, watch_is_majority=False, tix_is_majority=False):
    return {
        "vehicle_value": vehicle_value,
        "creditors": creditors or [],
        "watch_is_majority": watch_is_majority,
        "tix_is_majority": tix_is_majority,
    }


class NetVehicleValueTests(TestCase):
    def test_no_vehicle_value_returns_none(self):
        self.assertIsNone(_net_vehicle_value(_case(vehicle_value=None)))

    def test_no_hp_creditor_returns_raw_value(self):
        c = _case(vehicle_value=12000.0)
        self.assertEqual(_net_vehicle_value(c), 12000.0)

    def test_hp_balance_deducted_from_value(self):
        c = _case(vehicle_value=20000.0, creditors=[_hp_creditor(5000.0)])
        self.assertEqual(_net_vehicle_value(c), 15000.0)

    def test_manager_worked_example_negative_net_value(self):
        # HP balance £14,000, car value £10,000 -> net £10,000 - £14,000 = -£4,000
        c = _case(vehicle_value=10000.0, creditors=[_hp_creditor(14000.0)])
        self.assertEqual(_net_vehicle_value(c), -4000.0)

    def test_non_vehicle_hp_creditor_ignored(self):
        # Furniture/appliance HP is bucketed under the same debt_type_normalised
        # as car HP — only a vehicle-flagged HP creditor should net against value.
        c = _case(vehicle_value=12000.0, creditors=[
            _hp_creditor(3000.0, creditor_type="furniture", name="Very")
        ])
        self.assertEqual(_net_vehicle_value(c), 12000.0)

    def test_multiple_vehicle_hp_creditors_summed(self):
        c = _case(vehicle_value=20000.0, creditors=[
            _hp_creditor(3000.0, name="Black Horse"),
            _hp_creditor(2000.0, name="MotoNovo"),
        ])
        self.assertEqual(_net_vehicle_value(c), 15000.0)


class Watch229VehicleValueTests(TestCase):
    def test_no_vehicle_value_passes(self):
        r = _watch_22_9(_case(vehicle_value=None, watch_is_majority=True))
        self.assertFalse(r.triggered)

    def test_under_threshold_passes_even_if_majority(self):
        r = _watch_22_9(_case(vehicle_value=8000.0, watch_is_majority=True))
        self.assertFalse(r.triggered)

    def test_over_threshold_not_majority_passes(self):
        r = _watch_22_9(_case(vehicle_value=12000.0, watch_is_majority=False))
        self.assertFalse(r.triggered)
        self.assertIn("majority", r.message.lower())

    def test_over_threshold_and_majority_flags(self):
        r = _watch_22_9(_case(vehicle_value=12000.0, watch_is_majority=True))
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.threshold, 9000.0)
        self.assertEqual(r.actual_value, 12000.0)

    def test_hp_netting_below_threshold_no_flag_even_if_majority(self):
        # Manager's worked example: HP balance £14,000, value £10,000 -> net -£4,000.
        c = _case(vehicle_value=10000.0, creditors=[_hp_creditor(14000.0)], watch_is_majority=True)
        r = _watch_22_9(c)
        self.assertFalse(r.triggered)

    def test_hp_netting_above_threshold_and_majority_flags(self):
        c = _case(vehicle_value=20000.0, creditors=[_hp_creditor(2000.0)], watch_is_majority=True)
        r = _watch_22_9(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.actual_value, 18000.0)


class Tix07VehicleValueTests(TestCase):
    def test_no_vehicle_value_passes(self):
        r = _tix_07(_case(vehicle_value=None, tix_is_majority=True))
        self.assertFalse(r.triggered)

    def test_under_threshold_passes(self):
        r = _tix_07(_case(vehicle_value=13000.0, tix_is_majority=True))
        self.assertFalse(r.triggered)

    def test_over_threshold_not_majority_passes(self):
        r = _tix_07(_case(vehicle_value=15000.0, tix_is_majority=False))
        self.assertFalse(r.triggered)
        self.assertIn("majority", r.message.lower())

    def test_over_threshold_and_majority_flags(self):
        r = _tix_07(_case(vehicle_value=15000.0, tix_is_majority=True))
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.threshold, 14000.0)

    def test_hp_netting_below_threshold_no_flag(self):
        # WATCH threshold in the manager's example is £9,000, but the same
        # netted -£4,000 is also below TIX's £14,000 threshold -> no flag.
        c = _case(vehicle_value=10000.0, creditors=[_hp_creditor(14000.0)], tix_is_majority=True)
        r = _tix_07(c)
        self.assertFalse(r.triggered)


class VehicleValuePayloadShapeTests(TestCase):
    """_parse_case must read vehicle_value from EITHER payload shape:
    top-level (the case-assessment tool's own criteria_payload_builder.py
    sends it flat) or nested under "vehicle" (AssessCaseView's own
    _prepare_engine_payload in criteria_views.py sends
    {"vehicle": {"vehicle_value": ...}}) — mirrors the existing
    property/property_value dual-read pattern just above it in _parse_case.
    Without this, WATCH-22.9/TIX-07 could never fire for assessments run
    through this app's own frontend (which hits AssessCaseView)."""

    def _minimal(self, **override):
        base = {"creditors": [], "financial": {"net_balance": 0}, "evidence_ledger": []}
        base.update(override)
        return base

    def test_top_level_vehicle_value(self):
        c = _parse_case(self._minimal(vehicle_value=12000.0))
        self.assertEqual(c["vehicle_value"], 12000.0)

    def test_nested_vehicle_dict_vehicle_value(self):
        c = _parse_case(self._minimal(vehicle={"has_vehicle": True, "vehicle_value": 12000.0}))
        self.assertEqual(c["vehicle_value"], 12000.0)

    def test_nested_takes_precedence_when_both_present(self):
        c = _parse_case(self._minimal(vehicle={"vehicle_value": 12000.0}, vehicle_value=5000.0))
        self.assertEqual(c["vehicle_value"], 12000.0)

    def test_neither_present_is_none(self):
        c = _parse_case(self._minimal())
        self.assertIsNone(c["vehicle_value"])


class RepresentativeBalanceMajorityTests(TestCase):
    """_representative_balance_majority: the body holding the majority vote is
    the one whose combined represented balance exceeds 50% of total_debt."""

    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Watch Lender Test", representative="WATCH",
            status="WILL_CONSIDER", is_active=True,
        )
        CreditorCriteria.objects.create(
            creditor_name="TIX Lender Test", representative="TIX",
            status="WILL_CONSIDER", is_active=True,
        )
        CreditorCriteria.objects.create(
            creditor_name="Generic Lender", representative="NONE",
            status="ACCEPT", is_active=True,
        )

    def test_watch_holds_majority(self):
        creditors = [
            {"name": "Watch Lender Test", "balance": 6000.0},
            {"name": "Generic Lender", "balance": 4000.0},
        ]
        result = _representative_balance_majority(creditors, total_debt=10000.0)
        self.assertTrue(result["WATCH"])
        self.assertFalse(result["TIX"])

    def test_watch_below_majority_share(self):
        creditors = [
            {"name": "Watch Lender Test", "balance": 4000.0},
            {"name": "Generic Lender", "balance": 6000.0},
        ]
        result = _representative_balance_majority(creditors, total_debt=10000.0)
        self.assertFalse(result["WATCH"])

    def test_zero_total_debt_returns_false(self):
        result = _representative_balance_majority([], total_debt=0)
        self.assertEqual(result, {"WATCH": False, "TIX": False})


class VehicleValueEndToEndTests(TestCase):
    """assess_case wiring: watch_is_majority/tix_is_majority land on the
    parsed case and gate WATCH-22.9/TIX-07 exactly as the unit tests above."""

    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Watch Lender Test", representative="WATCH",
            status="WILL_CONSIDER", is_active=True,
        )

    def _case_json(self, vehicle_value, watch_balance):
        creditors = [{"name": "Watch Lender Test", "balance": watch_balance, "creditor_type": "personal_loan"}]
        return {
            "vehicle_value": vehicle_value,
            "creditors": creditors,
            "financial": {"net_balance": 100},
            "evidence_ledger": [],
        }

    def test_watch_majority_and_vehicle_over_threshold_flags(self):
        case = self._case_json(vehicle_value=12000.0, watch_balance=6000.0)
        detected_reps = detect_representatives(case["creditors"])
        result = assess_case(case, detected_reps)
        flag_ids = [f.rule_id for f in result["flags"]]
        self.assertIn("WATCH-22.9", flag_ids)

    def test_watch_not_majority_vehicle_over_threshold_no_flag(self):
        case = self._case_json(vehicle_value=12000.0, watch_balance=100.0)
        case["creditors"].append({"name": "Other Lender", "balance": 9900.0, "creditor_type": "personal_loan"})
        detected_reps = detect_representatives(case["creditors"])
        result = assess_case(case, detected_reps)
        flag_ids = [f.rule_id for f in result["flags"]]
        self.assertNotIn("WATCH-22.9", flag_ids)


class AssessCaseViewFrontendEndToEndTests(TestCase):
    """
    Proves the fix through the REAL code path this app's own frontend hits
    (useAssessCase.js -> POST /api/v1/criteria/assess/ -> AssessCaseView.post
    -> _prepare_engine_payload, which nests vehicle_value under
    payload["vehicle"]["vehicle_value"] in pence) — not a hand-simulated
    payload. Before the _parse_case fix, vehicle_value never reached the
    engine on this path and WATCH-22.9/TIX-07 could never fire for an
    assessment run through the app's own UI.
    """

    def setUp(self):
        self.client = APIClient()
        CreditorCriteria.objects.create(
            creditor_name="Watch Lender Test", representative="WATCH",
            status="WILL_CONSIDER", is_active=True,
        )

    def _case_data(self, ref, vehicle_value_pence, extra_creditors=None):
        case = CaseData()
        case.aryza_reference = ref
        case.client_name = "Vehicle Flag Test Client"
        case.dob = "1985-01-01"
        case.employment_status = "employed"
        case.disposable_income = 30000  # £300.00
        case.creditors = [
            {"name": "Watch Lender Test", "type": "personal_loan", "balance": 800000, "ref": "WL-1"},
        ] + (extra_creditors or [])
        case.income = {
            "employment": 150000, "universal_credit": 0, "dla": 0, "pip": 0,
            "other_benefits": 0, "third_party_contribution": 0, "total": 150000,
        }
        case.expenditure = {"disability_expenses": 0, "total": 120000}
        case.vehicle = {
            "has_vehicle": True,
            "vehicle_value": vehicle_value_pence,
            "vehicle_make": None,
            "hp_monthly_payment": None,
            "car_finance_start_date": None,
        }
        return case

    def _post_assess(self, ref, case_data):
        with patch("debt_app.views.criteria_views.fetch_case_by_reference", return_value=case_data):
            return self.client.post("/api/v1/criteria/assess/", data={"aryza_reference": ref}, format="json")

    def test_watch_flags_via_real_frontend_endpoint(self):
        # £12,000 vehicle, no HP, WATCH holds 100% of debt -> majority.
        case_data = self._case_data("FE-WATCH-1", vehicle_value_pence=1200000)
        resp = self._post_assess("FE-WATCH-1", case_data)
        self.assertEqual(resp.status_code, 200, resp.content)
        flag_ids = [f["rule_id"] for f in resp.json()["flags"]]
        self.assertIn("WATCH-22.9", flag_ids)

    def test_managers_worked_example_via_real_frontend_endpoint_no_flag(self):
        # HP balance £14,000, car value £10,000 -> net -£4,000 -> no flag,
        # even though WATCH still holds the majority (£8,000 of £22,000... but
        # the HP creditor is secured/excluded from unsecured total either way —
        # what matters here is WATCH-22.9 must NOT fire regardless).
        hp_creditor = {"name": "Black Horse", "type": "car_hp", "balance": 1400000, "ref": "HP-1"}
        case_data = self._case_data("FE-WATCH-2", vehicle_value_pence=1000000, extra_creditors=[hp_creditor])
        resp = self._post_assess("FE-WATCH-2", case_data)
        self.assertEqual(resp.status_code, 200, resp.content)
        flag_ids = [f["rule_id"] for f in resp.json()["flags"]]
        self.assertNotIn("WATCH-22.9", flag_ids)
