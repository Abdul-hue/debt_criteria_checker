"""
Lead Gen activity tracking: "cases checked per Lead Gen user per day".

Definition under test: one distinct successful check for the same user, same
case reference and same Europe/London calendar day.

BST/GMT in 2026: clocks go forward 29 March (01:00 GMT -> 02:00 BST) and back
25 October (02:00 BST -> 01:00 GMT).
"""

import datetime
from datetime import timezone as dt_tz

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from debt_app.models import (
    AppendOnlyError,
    Department,
    DepartmentFeatureAccess,
    LeadGenCheck,
    UserProfile,
)
from debt_app.services.lead_gen import summarise_activity

ACTIVITY_URL = "/api/v1/criteria/lead-gen/activity/"


def _utc(y, m, d, hh=12, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=dt_tz.utc)


class _ActivityFixture(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Lead Generation", slug="lead-generation")
        self.alice = User.objects.create_user("alice", password=None)
        self.bob = User.objects.create_user("bob", password=None)
        for u in (self.alice, self.bob):
            UserProfile.objects.create(user=u, department=self.dept)

    def _log(self, user, ref, when, status="OK", iva="POTENTIALLY_SUITABLE", dmp="POTENTIALLY_SUITABLE",
             overall="POTENTIALLY_SUITABLE"):
        ok = status == "OK"
        return LeadGenCheck.objects.create(
            user=user, username=user.username, department_name="Lead Generation", aryza_reference=ref,
            checked_at=when, status=status,
            iva_outcome=iva if ok else "", dmp_outcome=dmp if ok else "", overall_outcome=overall if ok else "",
            dro_referral=ok and overall == "DRO_REFER",
        )

    def _row(self, rows, username):
        return next(r for r in rows if r["username"] == username)


class SummariseActivityTests(_ActivityFixture):

    def test_one_user_one_case(self):
        self._log(self.alice, "C1", _utc(2026, 6, 10))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 1)

    def test_one_user_multiple_cases(self):
        for i in range(5):
            self._log(self.alice, f"C{i}", _utc(2026, 6, 10, 9 + i))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 5)

    def test_same_user_same_case_same_day_counts_once_using_latest_outcome(self):
        self._log(self.alice, "C1", _utc(2026, 6, 10, 9), overall="DOES_NOT_MEET_CRITERIA", iva="NOT_SUITABLE",
                  dmp="NOT_SUITABLE")
        self._log(self.alice, "C1", _utc(2026, 6, 10, 11))
        self._log(self.alice, "C1", _utc(2026, 6, 10, 10), overall="DRO_REFER")
        row = self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")
        self.assertEqual(row["cases_checked"], 1)
        self.assertEqual(row["no_solution"], 0)       # the 09:00 outcome was superseded
        self.assertEqual(row["iva_potential"], 1)     # 11:00 (latest) outcome counted

    def test_same_case_on_different_days_counts_per_day(self):
        self._log(self.alice, "C1", _utc(2026, 6, 10))
        self._log(self.alice, "C1", _utc(2026, 6, 11))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 2)

    def test_two_users_same_case(self):
        self._log(self.alice, "C1", _utc(2026, 6, 10))
        self._log(self.bob, "C1", _utc(2026, 6, 10))
        rows = summarise_activity(LeadGenCheck.objects.all())
        self.assertEqual(self._row(rows, "alice")["cases_checked"], 1)
        self.assertEqual(self._row(rows, "bob")["cases_checked"], 1)

    def test_failed_attempts_recorded_not_counted(self):
        self._log(self.alice, "C404", _utc(2026, 6, 10), status="CASE_NOT_FOUND")
        self._log(self.alice, "C1", _utc(2026, 6, 10), status="ARYZA_TIMEOUT")
        self._log(self.bob, "C2", _utc(2026, 6, 10), status="CREDIT_REPORT_FAILED")
        rows = summarise_activity(LeadGenCheck.objects.all())
        self.assertEqual(self._row(rows, "alice")["cases_checked"], 0)
        self.assertEqual(self._row(rows, "alice")["failed_attempts"], 2)
        self.assertEqual(self._row(rows, "bob")["failed_attempts"], 1)

    def test_outcome_columns(self):
        self._log(self.alice, "A", _utc(2026, 6, 10), iva="NEEDS_REVIEW", dmp="NOT_SUITABLE")
        self._log(self.alice, "B", _utc(2026, 6, 10), iva="NOT_SUITABLE", dmp="POTENTIALLY_SUITABLE")
        self._log(self.alice, "C", _utc(2026, 6, 10), iva="NOT_SUITABLE", dmp="NOT_SUITABLE",
                  overall="DOES_NOT_MEET_CRITERIA")
        self._log(self.alice, "D", _utc(2026, 6, 10), iva="NOT_SUITABLE", dmp="POTENTIALLY_SUITABLE",
                  overall="DRO_REFER")
        row = self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")
        self.assertEqual((row["cases_checked"], row["iva_potential"], row["iva_needs_review"],
                          row["dmp_potential"], row["no_solution"], row["dro_referral"]), (4, 1, 1, 2, 1, 1))

    def test_london_midnight_splits_days(self):
        # 22:59 UTC = 23:59 BST on 10 June; 23:01 UTC = 00:01 BST on 11 June.
        self._log(self.alice, "C1", _utc(2026, 6, 10, 22, 59))
        self._log(self.alice, "C1", _utc(2026, 6, 10, 23, 1))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 2)

    def test_bst_day_boundary_is_london_not_utc(self):
        # 23:30 UTC on 1 July is 00:30 BST on 2 July: same London day as 08:00 UTC on 2 July.
        self._log(self.alice, "C1", _utc(2026, 7, 1, 23, 30))
        self._log(self.alice, "C1", _utc(2026, 7, 2, 8, 0))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 1)

    def test_clocks_go_back_day(self):
        # 25 Oct 2026 has 25 hours in London. 23:30 UTC on 24 Oct = 00:30 BST 25 Oct;
        # 23:30 UTC on 25 Oct = 23:30 GMT 25 Oct — both the same London day.
        self._log(self.alice, "C1", _utc(2026, 10, 24, 23, 30))
        self._log(self.alice, "C1", _utc(2026, 10, 25, 23, 30))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 1)

    def test_clocks_go_forward_day(self):
        # 29 Mar 2026: 00:30 UTC = 00:30 GMT; 22:30 UTC = 23:30 BST — same London day.
        self._log(self.alice, "C1", _utc(2026, 3, 29, 0, 30))
        self._log(self.alice, "C1", _utc(2026, 3, 29, 22, 30))
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "alice")["cases_checked"], 1)


class LeadGenCheckAppendOnlyTests(_ActivityFixture):

    def test_cannot_modify_or_delete(self):
        rec = self._log(self.alice, "C1", _utc(2026, 6, 10))
        rec.status = "CASE_NOT_FOUND"
        with self.assertRaises(AppendOnlyError):
            rec.save()
        with self.assertRaises(AppendOnlyError):
            rec.delete()
        with self.assertRaises(AppendOnlyError):
            LeadGenCheck.objects.filter(pk=rec.pk).update(status="X")
        with self.assertRaises(AppendOnlyError):
            LeadGenCheck.objects.all().delete()
        self.assertEqual(LeadGenCheck.objects.get(pk=rec.pk).status, "OK")

    def test_deleting_user_keeps_history(self):
        self._log(self.bob, "C1", _utc(2026, 6, 10))
        self.bob.delete()
        rec = LeadGenCheck.objects.get(aryza_reference="C1")
        self.assertIsNone(rec.user_id)
        self.assertEqual(rec.username, "bob")
        self.assertEqual(self._row(summarise_activity(LeadGenCheck.objects.all()), "bob")["cases_checked"], 1)


class LeadGenActivityEndpointTests(_ActivityFixture):

    def setUp(self):
        super().setUp()
        DepartmentFeatureAccess.objects.create(department=self.dept, feature_key="lead_gen_check", is_enabled=True)
        self.mgr_dept = Department.objects.create(name="Managers", slug="managers")
        DepartmentFeatureAccess.objects.create(department=self.mgr_dept, feature_key="lead_gen_reporting", is_enabled=True)
        self.manager = User.objects.create_user("manager", password=None)
        UserProfile.objects.create(user=self.manager, department=self.mgr_dept)
        self.api = APIClient()

    def _get(self, user, **params):
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        return self.api.get(ACTIVITY_URL, params)

    def test_lead_gen_user_cannot_see_reporting(self):
        self.assertEqual(self._get(self.alice).status_code, 403)

    def test_unauthenticated(self):
        self.assertEqual(APIClient().get(ACTIVITY_URL).status_code, 401)

    def test_date_range_and_london_boundaries(self):
        self._log(self.alice, "A", _utc(2026, 6, 9, 22, 59))   # 23:59 BST 9 June -> excluded
        self._log(self.alice, "B", _utc(2026, 6, 9, 23, 1))    # 00:01 BST 10 June -> included
        self._log(self.alice, "C", _utc(2026, 6, 11, 22, 59))  # 23:59 BST 11 June -> included
        self._log(self.alice, "D", _utc(2026, 6, 11, 23, 1))   # 00:01 BST 12 June -> excluded
        self._log(self.bob, "B", _utc(2026, 6, 10, 9))
        body = self._get(self.manager, date_from="2026-06-10", date_to="2026-06-11").json()
        self.assertEqual(self._row(body["users"], "alice")["cases_checked"], 2)
        self.assertEqual(self._row(body["users"], "bob")["cases_checked"], 1)
        self.assertEqual(body["totals"]["cases_checked"], 3)
        self.assertEqual(body["timezone"], "Europe/London")

    def test_single_day_default_is_today(self):
        from django.utils import timezone
        self._log(self.alice, "T", timezone.now())
        body = self._get(self.manager).json()
        self.assertEqual(body["date_from"], timezone.localdate().isoformat())
        self.assertEqual(body["totals"]["cases_checked"], 1)

    def test_bad_dates(self):
        self.assertEqual(self._get(self.manager, date_from="nope").status_code, 400)
        self.assertEqual(self._get(self.manager, date_from="2026-06-10", date_to="2026-06-01").status_code, 400)

    def test_staff_can_see_reporting(self):
        admin = User.objects.create_user("boss", password=None, is_staff=True)
        self.assertEqual(self._get(admin).status_code, 200)


class ActivitySummaryDoesNotTouchHistoryTests(_ActivityFixture):
    def test_summarising_never_alters_stored_rows(self):
        self._log(self.alice, "C1", _utc(2026, 6, 10, 9), overall="DOES_NOT_MEET_CRITERIA")
        self._log(self.alice, "C1", _utc(2026, 6, 10, 11))
        before = list(LeadGenCheck.objects.order_by("id").values())
        summarise_activity(LeadGenCheck.objects.all())
        self.assertEqual(list(LeadGenCheck.objects.order_by("id").values()), before)
        self.assertEqual(LeadGenCheck.objects.count(), 2)  # both attempts kept; only the count dedupes
