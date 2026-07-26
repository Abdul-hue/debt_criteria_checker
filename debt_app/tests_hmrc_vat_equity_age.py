"""
Tests for two new rules plus the end-to-end VAT-override wiring:

PART 1 — HMRC previous-year VAT forces the recommended solution to DMP.
  _derive_recommended_solution must return "FORCED_DMP_VAT" whenever
  case["dmp_checklist"]["hmrc_previous_year_vat"] is truthy, at the TOP of the
  precedence chain (above hard_blocks). Everything else must be unchanged when
  the tick is absent/false, including the case=None backwards-compatible path.

PART 2 — _equity_age (EQUITY-AGE): property equity vs debt / £100k ceiling with a
  55+ WATCH skip. IVA-eligible (pass) when equity is low on EITHER count; hard
  block only when equity >= total_debt AND equity >= £100,000; RULE-CANNOT-EVALUATE
  when equity is None; skipped entirely for 55+ on a WATCH case.

PART 3 — Integration test through AssessCaseView.post itself (not just
  _derive_recommended_solution in isolation). This is the exact gap that let
  item 2 look "done" incorrectly the first time: assess_case() correctly
  computed "FORCED_DMP_VAT" internally, but AssessCaseView.post then called
  get_recommendation() (recommendation_engine.py), which rebuilt
  recommended_solution from hard_blocks/flags alone and silently discarded the
  VAT override. get_recommendation() now takes an explicit vat_forced param,
  checked before decision is used for anything.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from debt_app.aryza_client import CaseData
from debt_app.criteria_engine import (
    _derive_recommended_solution,
    _equity_age,
)
from debt_app.helpers import CreditorCriteria
from debt_app.models import CouncilRule


# ---------------------------------------------------------------------------
# PART 1 — HMRC previous-year VAT → FORCED_DMP_VAT
# ---------------------------------------------------------------------------

class HmrcVatForcedDmpTests(SimpleTestCase):

    def _case(self, vat=False):
        return {"dmp_checklist": {"hmrc_previous_year_vat": vat}}

    def test_vat_tick_forces_dmp_with_no_blocks_or_flags(self):
        result = _derive_recommended_solution([], [], [], self._case(vat=True))
        self.assertEqual(result, "FORCED_DMP_VAT")

    def test_vat_tick_overrides_hard_blocks(self):
        # Even with hard blocks present, the VAT tick sits ABOVE them.
        result = _derive_recommended_solution(["some-hard-block"], [], [], self._case(vat=True))
        self.assertEqual(result, "FORCED_DMP_VAT")

    def test_vat_tick_overrides_flags(self):
        result = _derive_recommended_solution([], ["some-flag"], [], self._case(vat=True))
        self.assertEqual(result, "FORCED_DMP_VAT")

    def test_vat_false_behaves_normally_viable(self):
        result = _derive_recommended_solution([], [], [], self._case(vat=False))
        self.assertEqual(result, "IVA_VIABLE")

    def test_vat_false_still_respects_hard_blocks(self):
        result = _derive_recommended_solution(["hb"], [], [], self._case(vat=False))
        self.assertEqual(result, "IVA_NOT_VIABLE")

    def test_no_case_arg_is_backwards_compatible(self):
        # Legacy 3-arg call path must be unaffected.
        self.assertEqual(_derive_recommended_solution([], [], []), "IVA_VIABLE")
        self.assertEqual(_derive_recommended_solution(["hb"], [], []), "IVA_NOT_VIABLE")

    def test_missing_dmp_checklist_behaves_normally(self):
        self.assertEqual(_derive_recommended_solution([], [], [], {}), "IVA_VIABLE")
        self.assertEqual(_derive_recommended_solution([], [], [], {"dmp_checklist": None}), "IVA_VIABLE")

    def test_do_not_vote_still_reached_when_no_vat(self):
        positions = [{"effective_status": "DO_NOT_VOTE"}]
        self.assertEqual(
            _derive_recommended_solution([], [], positions, self._case(vat=False)),
            "REVIEW_REQUIRED",
        )


# ---------------------------------------------------------------------------
# PART 2 — _equity_age
# ---------------------------------------------------------------------------

class EquityAgeRuleTests(SimpleTestCase):

    def _case(self, equity, total_debt, age=None, reps=None):
        return {
            "available_equity": equity,
            "total_debt": total_debt,
            "client_age": age,
            "detected_representatives": reps or set(),
        }

    def test_low_equity_below_debt_is_eligible(self):
        r = _equity_age(self._case(equity=5000.0, total_debt=40000.0))
        self.assertEqual(r.severity, "pass")
        self.assertFalse(r.triggered)

    def test_equity_below_100k_but_above_debt_is_eligible(self):
        # equity 50k > debt 10k, but 50k < £100k → the OR makes it eligible.
        r = _equity_age(self._case(equity=50000.0, total_debt=10000.0))
        self.assertEqual(r.severity, "pass")

    def test_high_equity_both_counts_is_hard_block(self):
        # equity 150k >= debt 40k AND 150k >= £100k → hard block.
        r = _equity_age(self._case(equity=150000.0, total_debt=40000.0))
        self.assertEqual(r.severity, "hard_block")
        self.assertTrue(r.triggered)
        self.assertEqual(r.rule_id, "EQUITY-AGE")

    def test_equity_at_100k_and_above_debt_is_hard_block(self):
        # Boundary: exactly £100k and >= debt → ineligible.
        r = _equity_age(self._case(equity=100000.0, total_debt=90000.0))
        self.assertEqual(r.severity, "hard_block")

    def test_55_plus_watch_skips_entirely(self):
        # Would otherwise hard block, but 55+ on WATCH skips the check.
        r = _equity_age(self._case(equity=200000.0, total_debt=10000.0, age=60, reps={"WATCH"}))
        self.assertEqual(r.severity, "pass")
        self.assertIn("does not apply", r.message)

    def test_55_plus_non_watch_does_not_skip(self):
        r = _equity_age(self._case(equity=200000.0, total_debt=10000.0, age=60, reps={"TIX"}))
        self.assertEqual(r.severity, "hard_block")

    def test_under_55_watch_does_not_skip(self):
        r = _equity_age(self._case(equity=200000.0, total_debt=10000.0, age=40, reps={"WATCH"}))
        self.assertEqual(r.severity, "hard_block")

    def test_equity_none_is_cannot_evaluate_not_block(self):
        r = _equity_age(self._case(equity=None, total_debt=40000.0))
        self.assertEqual(r.severity, "info")
        self.assertIn("RULE-CANNOT-EVALUATE", r.message)


# ---------------------------------------------------------------------------
# PART 3 — end-to-end through AssessCaseView.post
# ---------------------------------------------------------------------------

def _vat_case_data_obj():
    """A case with a real hard_block (total debt below the £6,000 TIG-01
    minimum) AND an HMRC creditor, so the VAT override's precedence over
    hard_blocks is actually exercised, not just assumed."""
    case = CaseData()
    case.aryza_reference = "TEST-VAT-001"
    case.client_name = "VAT Test Client"
    case.dob = "1985-01-01"
    case.employment_status = "employed"
    case.disposable_income = 30000  # £300.00
    case.creditors = [
        {
            "name": "HMRC",
            "type": "hmrc",
            "balance": 200000,  # £2,000.00 — total debt £2,000 < £6,000 TIG-01 minimum
            "ref": "HMRC-REF-1",
        },
    ]
    case.income = {
        "employment": 150000,
        "universal_credit": 0,
        "dla": 0,
        "pip": 0,
        "other_benefits": 0,
        "third_party_contribution": 0,
        "total": 150000,
    }
    case.expenditure = {
        "disability_expenses": 0,
        "total": 120000,
    }
    return case


class VatOverrideIntegrationTests(TestCase):
    """Exercises the real /api/v1/criteria/assess/ endpoint (AssessCaseView.post),
    not _derive_recommended_solution in isolation — this is the layer where the
    override was previously silently discarded by get_recommendation()."""

    def setUp(self):
        self.client = APIClient()

    @patch("debt_app.views.criteria_views.fetch_case_by_reference")
    def test_vat_tick_forces_dmp_through_real_endpoint_despite_hard_block(self, mock_fetch):
        mock_fetch.return_value = _vat_case_data_obj()

        resp = self.client.post(
            "/api/v1/criteria/assess/",
            data={
                "aryza_reference": "TEST-VAT-001",
                "dmp_checklist": {
                    "hmrc_debt_has_vat": True,
                    "hmrc_previous_year_vat": True,
                },
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()

        # Confirm the hard block genuinely fired (total debt £2,000 < £6,000) —
        # proving the VAT override really did win over a real competing signal,
        # not just an absence of any hard_blocks to begin with.
        hard_block_ids = {hb.get("rule_id") for hb in body.get("hard_blocks", [])}
        self.assertIn("TIG-01", hard_block_ids)

        # The bug: this used to be an INELIGIBLE-shaped object built by
        # get_recommendation() from hard_blocks alone (code would still say
        # "DMP", but for the wrong reason and without the VAT rationale) or,
        # if the wiring were entirely broken, some other value entirely. Assert
        # the actual VAT-specific rationale text is present — proves the VAT
        # branch of get_recommendation() executed, not the INELIGIBLE branch.
        solution = body.get("recommended_solution")
        self.assertIsInstance(solution, dict)
        self.assertEqual(solution.get("code"), "DMP")
        self.assertIn("VAT", solution.get("rationale", ""))
        self.assertIn("previous-year", solution.get("rationale", "").lower())

    @patch("debt_app.views.criteria_views.fetch_case_by_reference")
    def test_no_vat_tick_hard_block_still_gives_ordinary_ineligible_dmp(self, mock_fetch):
        """Confirms item 3 (_equity_age) and the ordinary hard-block path are
        unaffected: no VAT tick, TIG-01 hard block fires as before, and
        get_recommendation() takes its normal INELIGIBLE branch (DMP/Breathing
        Space fallback), not the VAT branch."""
        mock_fetch.return_value = _vat_case_data_obj()

        resp = self.client.post(
            "/api/v1/criteria/assess/",
            data={"aryza_reference": "TEST-VAT-001"},
            format="json",
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        hard_block_ids = {hb.get("rule_id") for hb in body.get("hard_blocks", [])}
        self.assertIn("TIG-01", hard_block_ids)

        solution = body.get("recommended_solution")
        self.assertIsInstance(solution, dict)
        self.assertEqual(solution.get("code"), "DMP")
        # The ordinary INELIGIBLE-branch rationale references hard blocks, not VAT.
        self.assertIn("hard blocks", solution.get("rationale", ""))
        self.assertNotIn("VAT", solution.get("rationale", ""))
