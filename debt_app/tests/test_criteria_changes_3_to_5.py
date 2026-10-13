"""
Criteria Changes #3 (creditor statuses / structured criteria), #4 (council
statuses) and #5 (dividends and representatives), from the 2026-10-12 workbook.

#3: the saved trial's only change (case 373236 gains MAJORITY-IMPOSSIBLE) comes
    from Admiral Loans' new reject_if_second_iva ("REJECT IF PREVIOUS IVA
    CONFIRMED THIS 24.08.26"). The rule is right; the input is not: that
    snapshot was saved on 2026-06-25, before the Aryza import stopped reporting
    a previous IVA from td_previous_bankruptcy / the client's own iva_client
    row (c91fa58, 2026-07-15). Aryza holds no previous IVA for the case today.
    The trial now dates every changed case and warns about such snapshots.
#4: none of the 13 councils is on any saved case, so 0/22 proves nothing;
    these tests exercise each new status directly.
#5: a matched creditor whose stance is UNKNOWN (ex-Evolve, e.g. NatWest) is an
    unknown vote, never a yes; the majority flags must say its position is
    unconfirmed, not that it "could not be identified".

All cases are synthetic.
"""

import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from debt_app.engine.criteria import assess_case
from debt_app.models import CouncilRule, CreditorCriteria, CriteriaDecision, GlobalCriteria
from debt_app.services import criteria_versioning as cv
from debt_app.tests_cat_assessment_golden import _case, _creditor, _FixedDate
from debt_app.views.criteria_views import AssessCaseView

FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"


def _row(name, status="ACCEPT", rep="NONE", **kw):
    obj, _ = CreditorCriteria.objects.update_or_create(
        creditor_name=name,
        defaults=dict(status=status, representative=rep, is_active=True, criteria_notes="", **kw),
    )
    return obj


def _council(name, status, **kw):
    obj, _ = CouncilRule.objects.update_or_create(council_name=name, defaults=dict(status=status, **kw))
    return obj


def _payload(ref, creditors, previous_iva=False):
    case = _case(ref, creditors, previous_iva=previous_iva)
    payload, _p, _u = AssessCaseView()._prepare_engine_payload(case)
    return payload


def _flags(result):
    return {r.rule_id: r for r in result["flags"]}


def _vote(result, name):
    return next(p["effective_status"] for p in [*result["creditor_positions"], *result["council_positions"]]
                if p["creditor_name"] == name)


class _FixedDateMixin:
    def setUp(self):
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()


# --------------------------------------------------------------------------- #3
class AdmiralPreviousIvaTests(_FixedDateMixin, TestCase):
    """Case 373236's shape: Admiral holds most of the voting debt."""

    def setUp(self):
        super().setUp()
        _row("Admiral Loans", status="WILL_CONSIDER", account_age_months=6, reject_if_second_iva=True)
        _row("Capital One")
        _row("Monzo Bank")

    def _assess(self, previous_iva):
        return assess_case(_payload("AD-1", [_creditor("Admiral Loans", 637_900), _creditor("Capital One", 222_000),
                                             _creditor("Monzo Bank", 95_800)], previous_iva=previous_iva),
                           detected_representatives=set())

    def test_confirmed_previous_iva_makes_admiral_reject_and_the_majority_impossible(self):
        result = self._assess(previous_iva=True)
        self.assertEqual(_vote(result, "Admiral Loans"), "REJECT")
        self.assertIn("MAJORITY-IMPOSSIBLE", _flags(result))

    def test_no_previous_iva_leaves_admiral_considering_and_the_majority_reachable(self):
        result = self._assess(previous_iva=False)
        self.assertEqual(_vote(result, "Admiral Loans"), "WILL_CONSIDER")
        self.assertNotIn("MAJORITY-IMPOSSIBLE", _flags(result))
        self.assertTrue(result["majority_analysis"]["achievable"])


class SnapshotWarningTests(TestCase):
    def _at(self, y, m, d):
        return timezone.make_aware(datetime.datetime(y, m, d, 12, 0))

    def test_pre_fix_snapshot_claiming_a_previous_iva_is_warned(self):
        w = cv._snapshot_warnings({"flags": {"previous_iva": True}}, self._at(2026, 6, 25))
        self.assertEqual(len(w), 1)
        self.assertIn("25 Jun 2026", w[0])
        self.assertIn("previous IVA", w[0])

    def test_no_warning_after_the_fix_or_without_a_previous_iva(self):
        self.assertEqual(cv._snapshot_warnings({"flags": {"previous_iva": True}}, self._at(2026, 7, 15)), [])
        self.assertEqual(cv._snapshot_warnings({"flags": {"previous_iva": False}}, self._at(2026, 6, 25)), [])
        self.assertEqual(cv._snapshot_warnings({}, None), [])


class TrialMarksStaleSnapshotsTests(_FixedDateMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.admiral = _row("Admiral Loans", status="WILL_CONSIDER", reject_if_second_iva=False)
        _row("Capital One")
        self.user = User.objects.create_user("author", password=None)
        case = _case("AD-2", [_creditor("Admiral Loans", 637_900), _creditor("Capital One", 222_000)],
                     previous_iva=True)
        with patch(FETCH, return_value=case):
            APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "AD-2"}, format="json")
        decision = CriteriaDecision.objects.get(application_id="AD-2")
        decision.triggered_at = timezone.make_aware(datetime.datetime(2026, 6, 25, 11, 46))
        decision.save()

    def test_changed_case_carries_its_date_and_the_previous_iva_warning(self):
        change = cv.create_change_request(self.user, "Admiral", "Sheet: reject if previous IVA", [
            {"model": "CreditorCriteria", "object_id": self.admiral.pk, "field": "reject_if_second_iva",
             "new_value": True}])
        cv.run_trial(change, self.user)
        change.refresh_from_db()
        case = change.trial_summary["changed"][0]
        self.assertEqual(case["aryza_reference"], "AD-2")
        self.assertTrue(case["snapshot_saved_at"].startswith("2026-06-25"))
        self.assertEqual(len(case["warnings"]), 1)
        self.assertIn("Admiral Loans: REJECT", case["differences"]["creditor_votes"]["after"])


# --------------------------------------------------------------------------- #4
class CouncilStatusTests(_FixedDateMixin, TestCase):
    """The four statuses #4 moves councils between, on a council-tax debt."""

    def setUp(self):
        super().setUp()
        _row("Alpha Bank")

    def _assess(self, council_name, status, debt_name=None, type_="council_tax"):
        _council(council_name, status)
        payload = _payload("CO-1", [_creditor(debt_name or council_name, 400_000, type_=type_),
                                    _creditor("Alpha Bank", 600_000)])
        return assess_case(payload, detected_representatives=set())

    def test_reject_counts_against_the_majority(self):
        result = self._assess("Tameside Borough Council", "REJECT")
        self.assertEqual(_vote(result, "Tameside Borough Council"), "REJECT")
        self.assertFalse(result["majority_analysis"]["achievable"])        # 6,000 of 10,000 < 75%

    def test_do_not_vote_leaves_the_voting_pool(self):
        result = self._assess("Thanet District Council", "DO_NOT_VOTE")
        self.assertEqual(_vote(result, "Thanet District Council"), "DO_NOT_VOTE")
        self.assertEqual(float(result["majority_analysis"]["voting_pool"]), 6_000.0)
        self.assertTrue(result["majority_analysis"]["achievable"])

    def test_will_consider_counts_as_support(self):
        result = self._assess("Oldham Borough Council", "WILL_CONSIDER")
        self.assertEqual(_vote(result, "Oldham Borough Council"), "WILL_CONSIDER")
        self.assertTrue(result["majority_analysis"]["achievable"])

    def test_unknown_deductions_do_not_turn_a_council_vote_into_reject(self):
        """TIG-17 asks the caseworker to confirm deductions when it is not known
        whether any are active. Until confirmed, the council keeps its sheet
        status; it was being forced to REJECT with an "already taking money" reason."""
        _council("Oldham Borough Council", "WILL_CONSIDER")
        payload = _payload("CO-3", [_creditor("Oldham Borough Council", 400_000, type_="council_tax"),
                                    _creditor("Alpha Bank", 600_000)])
        self.assertIsNone(payload.get("income_deductions_active"))
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("TIG-17", _flags(result))
        self.assertIn("confirm whether any deductions", _flags(result)["TIG-17"].message)
        position = next(p for p in result["council_positions"] if p["creditor_name"] == "Oldham Borough Council")
        self.assertEqual(position["effective_status"], "WILL_CONSIDER")
        self.assertNotIn("COUNCIL-TIG17-INCOME-DEDUCTION", {f["code"] for f in position.get("findings", [])})

        payload["income_deductions_active"] = True                  # confirmed deduction: sheet says reject
        result = assess_case(payload, detected_representatives=set())
        self.assertEqual(_vote(result, "Oldham Borough Council"), "REJECT")

    def test_case_324901_shape_unknown_deductions_no_false_majority_impossible(self):
        """Case 324901: an ACCEPT council (Brighton & Hove) holds ~33% of the voting
        debt and deductions are unknown. Forcing it to REJECT made the majority
        impossible. Synthetic figures in the same proportions as the real case."""
        _council("Brighton & Hove City Council", "ACCEPT")
        _row("Beta Loans")
        creditors = [_creditor("Brighton & Hove City Council", 458_700, type_="council_tax"),
                     _creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 344_100)]
        unknown = assess_case(_payload("CO-4", creditors), detected_representatives=set())
        self.assertIn("TIG-17", _flags(unknown))                              # rule stays active
        self.assertEqual(_vote(unknown, "Brighton & Hove City Council"), "ACCEPT")
        self.assertNotIn("MAJORITY-IMPOSSIBLE", _flags(unknown))
        self.assertTrue(unknown["majority_analysis"]["achievable"])

        none = _payload("CO-4", creditors)
        none["income_deductions_active"] = False
        no_deductions = assess_case(none, detected_representatives=set())
        # Unknown deductions now differ from "no deductions" only by the TIG-17 confirm flag.
        self.assertEqual(set(_flags(unknown)) - set(_flags(no_deductions)), {"TIG-17"})
        self.assertEqual(unknown["majority_analysis"]["achievable"], no_deductions["majority_analysis"]["achievable"])
        self.assertEqual(_vote(no_deductions, "Brighton & Hove City Council"), "ACCEPT")

        confirmed = _payload("CO-4", creditors)
        confirmed["income_deductions_active"] = True
        result = assess_case(confirmed, detected_representatives=set())
        self.assertEqual(_vote(result, "Brighton & Hove City Council"), "REJECT")
        self.assertIn("MAJORITY-IMPOSSIBLE", _flags(result))                   # 4,587 of 14,028 > 25%

    def test_sheet_name_with_trailing_space_and_general_debt_type_still_routes_to_the_council(self):
        # The sheet stores 'Suffolk Coastal District Council ' (trailing space) and
        # Aryza can tag council debts as GENERAL.
        result = self._assess("Suffolk Coastal District Council", "REJECT",
                              debt_name="Suffolk Coastal District Council ", type_="personal_loan")
        self.assertIn("REJECT", {p["effective_status"] for p in result["council_positions"]})

    def test_applying_a_status_item_changes_the_vote(self):
        rule = _council("Worcester City Council", "ACCEPT")
        cv._apply_items_to("default", [{"model": "CouncilRule", "object_id": rule.pk, "field": "status",
                                        "old_value": "ACCEPT", "new_value": "WILL_CONSIDER"}])
        payload = _payload("CO-2", [_creditor("Worcester City Council", 400_000, type_="council_tax"),
                                    _creditor("Alpha Bank", 600_000)])
        result = assess_case(payload, detected_representatives=set())
        self.assertEqual(_vote(result, "Worcester City Council"), "WILL_CONSIDER")


# --------------------------------------------------------------------------- #5
class UnconfirmedStanceWordingTests(_FixedDateMixin, TestCase):
    """Case 324991's shape: NatWest (ex-Evolve, now UNKNOWN) holds 25% of the debt."""

    def setUp(self):
        super().setUp()
        _row("NatWest", status="UNKNOWN")
        _row("Lloyds Bank", status="WILL_CONSIDER")

    def _assess(self, extra=()):
        payload = _payload("NW-1", [_creditor("NatWest", 803_900), _creditor("Lloyds Bank", 2_386_600), *extra])
        return assess_case(payload, detected_representatives=set())

    def test_unknown_stance_is_not_a_yes_and_is_described_as_unconfirmed(self):
        result = self._assess()
        ma = result["majority_analysis"]
        self.assertEqual(_vote(result, "NatWest"), "UNKNOWN")
        self.assertEqual(float(ma["unknown_debt"]), 8_039.0)                 # not counted as support
        self.assertEqual(float(ma["voting_debt"]), 23_866.0)
        self.assertTrue(ma["indeterminate"])
        self.assertEqual(ma["unknown_creditors"], [{"name": "NatWest", "balance": 8039.0, "stance_unconfirmed": True}])

        flags = _flags(result)
        for rule_id in ("MAJORITY-INDETERMINATE", "CREDITOR-UNIDENTIFIED-MATERIAL"):
            msg = flags[rule_id].message
            self.assertIn("position on IVA proposals has not been confirmed", msg, rule_id)
            self.assertIn("NatWest", msg)
            self.assertNotIn("could not be identified", msg, rule_id)
            self.assertNotIn("not yet been identified", msg, rule_id)
            self.assertIn("confirm these creditors' positions", msg, rule_id)

    def test_mixed_unidentified_and_unconfirmed_names_each_group(self):
        result = self._assess(extra=[_creditor("Zzyzx Unmatched Lender Ltd", 900_000)])
        msg = _flags(result)["CREDITOR-UNIDENTIFIED-MATERIAL"].message
        self.assertIn("not yet been identified (Zzyzx Unmatched Lender Ltd", msg)
        self.assertIn("has not been confirmed (NatWest", msg)

    def test_unidentified_only_wording_is_unchanged(self):
        CreditorCriteria.objects.filter(creditor_name="NatWest").delete()
        _row("Lloyds Bank", status="WILL_CONSIDER")
        payload = _payload("NW-2", [_creditor("Zzyzx Unmatched Lender Ltd", 803_900),
                                    _creditor("Lloyds Bank", 2_386_600)])
        result = assess_case(payload, detected_representatives=set())
        flags = _flags(result)
        self.assertIn("could not be identified", flags["CREDITOR-UNIDENTIFIED-MATERIAL"].message)
        self.assertIn("have not yet been identified", flags["MAJORITY-INDETERMINATE"].message)
        self.assertNotIn("stance_unconfirmed", result["majority_analysis"]["unknown_creditors"][0])


class RepresentativeMovesTests(_FixedDateMixin, TestCase):
    def test_barclaycard_on_watch_follows_the_watch_outcome(self):
        """Case 332591's shape: Barclaycard moves EVOLVE -> WATCH (Which Representative sheet,
        WPM column), so the WATCH rules now run and set its vote."""
        _row("Barclaycard", rep="WATCH")
        _row("Capital One", rep="NONE")
        GlobalCriteria.objects.update_or_create(rule_key="WATCH-22.6", defaults=dict(
            criteria_set="WATCH", rule_name="WATCH-22.6", severity="flag", is_active=True))
        GlobalCriteria.objects.update_or_create(rule_key="WATCH-22.13", defaults=dict(
            criteria_set="WATCH", rule_name="WATCH-22.13", severity="flag", is_active=False))
        payload = _payload("BC-1", [_creditor("Barclaycard", 66_000), _creditor("Capital One", 900_000)])
        payload.pop("gold_transactions", None)                  # no bank data, as on the real case
        result = assess_case(payload)
        self.assertIn("WATCH", result["representatives_detected"])
        self.assertIn("WATCH-22.6", _flags(result))
        self.assertEqual(_vote(result, "Barclaycard"), "WILL_CONSIDER")
        GlobalCriteria.objects.filter(rule_key="WATCH-22.6").update(is_active=False)   # draft #6
        self.assertEqual(_vote(assess_case(payload), "Barclaycard"), "ACCEPT")

    def test_shell_energy_keeps_accept_with_no_representative(self):
        _row("Shell Energy", status="ACCEPT", rep="NONE")
        _row("Capital One")
        payload = _payload("SE-1", [_creditor("Shell Energy", 50_000), _creditor("Capital One", 900_000)])
        result = assess_case(payload)
        self.assertEqual(_vote(result, "Shell Energy"), "ACCEPT")
        self.assertNotIn("EVOLVE", result["representatives_detected"])
