"""
Controlled criteria changes: Draft -> Trial -> Second-manager sign-off -> Live,
versions, audit, rollback, permissions, and the direct-edit guard.

Trials copy the database with SQLite's backup API, so these use
TransactionTestCase (committed data) rather than TestCase's open transaction.
"""

import glob
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from debt_app.models import (
    CreditorCriteria,
    CriteriaChangeAudit,
    CriteriaChangeRequest,
    CriteriaDecision,
    CriteriaVersion,
    Department,
    DepartmentFeatureAccess,
    DepartmentFeaturePermission,
    GlobalCriteria,
    LeadGenCheck,
    UserProfile,
)
from debt_app.services import criteria_versioning as cv
from debt_app.tests_cat_assessment_golden import _case, _creditor, _FixedDate

BASE = "/api/v1/criteria/criteria-changes/"
FETCH = "debt_app.views.criteria_views.fetch_case_by_reference"


class CriteriaChangeControlTests(TransactionTestCase):

    def setUp(self):
        patcher = patch("debt_app.engine.criteria.date", _FixedDate)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.alpha = CreditorCriteria.objects.create(creditor_name="Alpha Bank", representative="NONE",
                                                     status="ACCEPT", is_active=True)
        self.beta = CreditorCriteria.objects.create(creditor_name="Beta Loans", representative="NONE",
                                                    status="ACCEPT", is_active=True)
        self.rule = GlobalCriteria.objects.create(criteria_set="TIG", rule_key="TIG-18", rule_name="Recent spending",
                                                  severity="flag", is_active=True)

        self.mgr_dept = Department.objects.create(name="Managers", slug="managers")
        for key in ("criteria_changes", "criteria_approval"):
            DepartmentFeatureAccess.objects.create(department=self.mgr_dept, feature_key=key, is_enabled=True)
        self.author = self._user("author", self.mgr_dept)
        self.approver = self._user("approver", self.mgr_dept)

        self.lg_dept = Department.objects.create(name="Lead Generation", slug="lead-generation")
        DepartmentFeatureAccess.objects.create(department=self.lg_dept, feature_key="lead_gen_check", is_enabled=True)
        DepartmentFeaturePermission.objects.create(department=self.lg_dept, feature_key="general_creditors",
                                                   permission_level="READ")
        self.lg_user = self._user("lg", self.lg_dept)

        # A saved CAT assessment snapshot for trials to evaluate.
        with patch(FETCH, return_value=_case("CC-1", [_creditor("Alpha Bank", 600_000),
                                                      _creditor("Beta Loans", 450_000)])):
            APIClient().post("/api/v1/criteria/assess/", data={"aryza_reference": "CC-1"}, format="json")
        assert CriteriaDecision.objects.filter(application_id="CC-1").exists()

    def _user(self, name, dept=None, **kw):
        u = User.objects.create_user(name, password=None, **kw)
        if dept:
            UserProfile.objects.create(user=u, department=dept)
        return u

    def _api(self, user):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        return api

    def _draft(self, user=None, items=None):
        return self._api(user or self.author).post(BASE, data={
            "title": "Block Beta Loans", "reason": "Creditor has instructed us to block IVAs",
            "items": items or [{"model": "CreditorCriteria", "object_id": self.beta.pk,
                                "field": "blocked_until_cleared", "new_value": True}],
        }, format="json")

    def _live_beta_blocked(self):
        return CreditorCriteria.objects.get(pk=self.beta.pk).blocked_until_cleared

    # ---- Draft --------------------------------------------------------------

    def test_draft_does_not_affect_live(self):
        fp = cv.live_fingerprint()
        resp = self._draft()
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertEqual(body["items"][0]["old_value"], False)
        self.assertEqual(body["items"][0]["new_value"], True)
        self.assertEqual(body["created_by"], "author")
        self.assertFalse(self._live_beta_blocked())
        self.assertEqual(cv.live_fingerprint(), fp)

    def test_reason_required(self):
        resp = self._api(self.author).post(BASE, data={"title": "t", "reason": "", "items": []}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_code_managed_fields_are_refused(self):
        for item in (
            {"model": "GlobalCriteria", "object_id": self.rule.pk, "field": "threshold_value", "new_value": 5},
            {"model": "GlobalCriteria", "object_id": self.rule.pk, "field": "severity", "new_value": "hard_block"},
            {"model": "CreditorCriteria", "object_id": self.beta.pk, "field": "creditor_name", "new_value": "X"},
        ):
            resp = self._draft(items=[item])
            self.assertEqual(resp.status_code, 400, item)
            self.assertEqual(resp.json()["code"], "NOT_MANAGED")

    def test_invalid_value_is_refused(self):
        resp = self._draft(items=[{"model": "CreditorCriteria", "object_id": self.beta.pk,
                                   "field": "status", "new_value": "MAYBE"}])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "INVALID_VALUE")

    # ---- Trial --------------------------------------------------------------

    def test_trial_does_not_affect_live_and_reports_differences(self):
        change_id = self._draft().json()["id"]
        fp = cv.live_fingerprint()
        resp = self._api(self.author).post(f"{BASE}{change_id}/trial/", format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        summary = resp.json()["trial_summary"]
        self.assertEqual(resp.json()["status"], "TRIALLED")
        self.assertEqual(summary["cases_evaluated"], 1)
        self.assertEqual(summary["cases_changed"], 1)
        diff = summary["changed"][0]["differences"]
        self.assertIn("CREDITOR-BLOCKED", diff["hard_blocks"]["after"])
        self.assertNotIn("CREDITOR-BLOCKED", diff["hard_blocks"]["before"])
        self.assertEqual(diff["lead_gen_iva"]["after"], "NOT_SUITABLE")
        self.assertNotEqual(diff["lead_gen_iva"]["before"], "NOT_SUITABLE")
        # Live untouched; no trial connection or temporary database left behind.
        self.assertFalse(self._live_beta_blocked())
        self.assertEqual(cv.live_fingerprint(), fp)
        self.assertFalse([a for a in connections.settings if a.startswith("criteria_trial_")])
        self.assertFalse(glob.glob(os.path.join(tempfile.gettempdir(), "criteria_trial_*")))

    def test_trial_refused_on_non_sqlite_database(self):
        change = CriteriaChangeRequest.objects.get(pk=self._draft().json()["id"])
        with patch.dict(connections["default"].settings_dict, {"ENGINE": "django.db.backends.mysql"}):
            with self.assertRaises(cv.CriteriaChangeError) as ctx:
                cv.run_trial(change, self.author)
        self.assertEqual(ctx.exception.code, "TRIAL_UNSUPPORTED_DB")
        self.assertEqual(CriteriaChangeRequest.objects.get(pk=change.pk).status, "DRAFT")

    # ---- Sign-off / Live ------------------------------------------------------

    def _trialled(self):
        change_id = self._draft().json()["id"]
        self._api(self.author).post(f"{BASE}{change_id}/trial/", format="json")
        return change_id

    def test_approval_requires_trial(self):
        change_id = self._draft().json()["id"]
        resp = self._api(self.approver).post(f"{BASE}{change_id}/approve/", format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "NOT_TRIALLED")

    def test_author_cannot_approve_own_change(self):
        change_id = self._trialled()
        resp = self._api(self.author).post(f"{BASE}{change_id}/approve/", format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "SELF_APPROVAL")
        self.assertFalse(self._live_beta_blocked())

    def test_author_cannot_reject_own_change(self):
        change_id = self._trialled()
        resp = self._api(self.author).post(f"{BASE}{change_id}/reject/", data={"note": "no"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_second_manager_approval_applies_atomically_with_version_and_audit(self):
        change_id = self._trialled()
        resp = self._api(self.approver).post(f"{BASE}{change_id}/approve/", data={"note": "Agreed"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(self._live_beta_blocked())
        self.assertEqual(CreditorCriteria.objects.get(pk=self.beta.pk).updated_by, self.approver)
        # v1 = automatic baseline (pre-change), v2 = this change.
        self.assertEqual(list(CriteriaVersion.objects.order_by("number").values_list("number", flat=True)), [1, 2])
        v1, v2 = CriteriaVersion.objects.order_by("number")
        self.assertFalse(v1.snapshot["CreditorCriteria"][str(self.beta.pk)]["blocked_until_cleared"])
        self.assertTrue(v2.snapshot["CreditorCriteria"][str(self.beta.pk)]["blocked_until_cleared"])
        self.assertEqual(v2.created_by, self.approver)
        self.assertTrue(v2.code_version)
        audit = CriteriaChangeAudit.objects.get(version=v2)
        self.assertEqual((audit.field, audit.old_value, audit.new_value), ("blocked_until_cleared", False, True))
        self.assertEqual((audit.proposed_by, audit.approved_by), (self.author, self.approver))
        change = CriteriaChangeRequest.objects.get(pk=change_id)
        self.assertEqual(change.status, "LIVE")
        self.assertEqual(change.applied_version, v2)
        self.assertEqual(cv.current_criteria_version()[0], "v2")

    def test_approval_is_atomic_on_failure(self):
        change_id = self._draft(items=[
            {"model": "CreditorCriteria", "object_id": self.beta.pk, "field": "blocked_until_cleared", "new_value": True},
            {"model": "CreditorCriteria", "object_id": self.alpha.pk, "field": "status", "new_value": "REJECT"},
        ]).json()["id"]
        self._api(self.author).post(f"{BASE}{change_id}/trial/", format="json")
        with patch("debt_app.services.criteria_versioning.CriteriaChangeAudit.objects.create",
                   side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                cv.approve_and_apply(CriteriaChangeRequest.objects.get(pk=change_id), self.approver)
        self.assertFalse(self._live_beta_blocked())
        self.assertEqual(CreditorCriteria.objects.get(pk=self.alpha.pk).status, "ACCEPT")
        self.assertFalse(CriteriaVersion.objects.exists())
        self.assertEqual(CriteriaChangeRequest.objects.get(pk=change_id).status, "TRIALLED")

    def test_live_change_after_trial_requires_retrial(self):
        change_id = self._trialled()
        CreditorCriteria.objects.filter(pk=self.alpha.pk).update(min_dividend_pence=20)  # out-of-band edit
        resp = self._api(self.approver).post(f"{BASE}{change_id}/approve/", format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "RETRIAL_REQUIRED")
        self.assertFalse(self._live_beta_blocked())

    def test_stale_draft_is_refused(self):
        change_id = self._draft().json()["id"]
        CreditorCriteria.objects.filter(pk=self.beta.pk).update(blocked_until_cleared=True)
        resp = self._api(self.author).post(f"{BASE}{change_id}/trial/", format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "STALE")

    def test_reject_and_cancel(self):
        change_id = self._trialled()
        self.assertEqual(self._api(self.approver).post(f"{BASE}{change_id}/reject/", data={"note": ""},
                                                       format="json").status_code, 400)
        resp = self._api(self.approver).post(f"{BASE}{change_id}/reject/", data={"note": "Not agreed"}, format="json")
        self.assertEqual(resp.json()["status"], "REJECTED")
        other = self._draft().json()["id"]
        self.assertEqual(self._api(self.approver).post(f"{BASE}{other}/cancel/", format="json").status_code, 403)
        self.assertEqual(self._api(self.author).post(f"{BASE}{other}/cancel/", format="json").json()["status"],
                         "CANCELLED")
        self.assertFalse(self._live_beta_blocked())

    # ---- Rollback -------------------------------------------------------------

    def test_rollback_restores_previous_version_through_the_same_controls(self):
        change_id = self._trialled()
        self._api(self.approver).post(f"{BASE}{change_id}/approve/", format="json")
        self.assertTrue(self._live_beta_blocked())

        resp = self._api(self.author).post("/api/v1/criteria/criteria-versions/1/rollback/",
                                           data={"reason": "Creditor withdrew the instruction"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        rb = resp.json()
        self.assertTrue(rb["is_rollback"])
        self.assertEqual(rb["items"][0]["new_value"], False)
        self.assertTrue(self._live_beta_blocked())  # draft only — nothing changed yet

        self._api(self.author).post(f"{BASE}{rb['id']}/trial/", format="json")
        self.assertEqual(self._api(self.author).post(f"{BASE}{rb['id']}/approve/", format="json").status_code, 403)
        resp = self._api(self.approver).post(f"{BASE}{rb['id']}/approve/", format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(self._live_beta_blocked())
        self.assertEqual(CriteriaVersion.objects.order_by("-number").first().number, 3)
        self.assertEqual(CriteriaVersion.objects.get(number=3).fingerprint,
                         CriteriaVersion.objects.get(number=1).fingerprint)

    def test_versions_are_immutable(self):
        change_id = self._trialled()
        self._api(self.approver).post(f"{BASE}{change_id}/approve/", format="json")
        v = CriteriaVersion.objects.get(number=2)
        v.note = "tamper"
        with self.assertRaises(Exception):
            v.save()
        with self.assertRaises(Exception):
            CriteriaChangeAudit.objects.all().delete()

    def test_version_detail_shows_audit(self):
        change_id = self._trialled()
        self._api(self.approver).post(f"{BASE}{change_id}/approve/", format="json")
        body = self._api(self.author).get("/api/v1/criteria/criteria-versions/2/").json()
        self.assertEqual(body["audit"][0]["approved_by"], "approver")
        self.assertEqual(body["audit"][0]["proposed_by"], "author")

    # ---- Permissions ------------------------------------------------------------

    def test_lead_gen_user_cannot_edit_or_approve_criteria(self):
        api = self._api(self.lg_user)
        self.assertEqual(self._draft(user=self.lg_user).status_code, 403)
        self.assertEqual(api.get(BASE).status_code, 403)
        change_id = self._trialled()
        self.assertEqual(api.post(f"{BASE}{change_id}/approve/", format="json").status_code, 403)
        self.assertEqual(api.post(f"{BASE}{change_id}/trial/", format="json").status_code, 403)
        # Existing direct-edit endpoint: Lead Gen has READ only.
        self.assertEqual(api.put(f"/api/v1/criteria/creditors/{self.beta.pk}/",
                                 data={"status": "REJECT"}, format="json").status_code, 403)
        self.assertFalse(self._live_beta_blocked())

    def test_proposer_without_approval_feature_cannot_approve(self):
        prop_dept = Department.objects.create(name="Proposers", slug="proposers")
        DepartmentFeatureAccess.objects.create(department=prop_dept, feature_key="criteria_changes", is_enabled=True)
        proposer = self._user("proposer", prop_dept)
        change_id = self._trialled()
        self.assertEqual(self._api(proposer).post(f"{BASE}{change_id}/approve/", format="json").status_code, 403)

    def test_unauthenticated(self):
        self.assertEqual(APIClient().get(BASE).status_code, 401)
        self.assertEqual(APIClient().post(BASE, data={}, format="json").status_code, 401)

    # ---- Direct-edit guard + version recording ------------------------------------

    def test_direct_edit_guard_off_by_default_and_blocks_when_enforced(self):
        admin = self._user("root", is_staff=True)
        url = f"/api/v1/criteria/creditors/{self.alpha.pk}/"
        self.assertEqual(self._api(admin).put(url, data={"min_dividend_pence": 5}, format="json").status_code, 200)
        with override_settings(CRITERIA_CHANGE_CONTROL_ENFORCED=True):
            resp = self._api(admin).put(url, data={"min_dividend_pence": 7}, format="json")
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(self._api(admin).get(url).status_code, 200)  # reads unaffected
            self.assertEqual(self._api(admin).put(f"/api/v1/criteria/rules/{self.rule.rule_key}/",
                                                  data={"is_active": False}, format="json").status_code, 403)
        self.assertEqual(CreditorCriteria.objects.get(pk=self.alpha.pk).min_dividend_pence, 5)

    def test_lead_gen_check_records_live_version_and_flags_unapproved_edits(self):
        change_id = self._trialled()
        self._api(self.approver).post(f"{BASE}{change_id}/approve/", format="json")
        lg = self._api(self.lg_user)
        case = _case("CC-LG", [_creditor("Alpha Bank", 600_000), _creditor("Beta Loans", 450_000)])
        with patch(FETCH, return_value=case):
            lg.post("/api/v1/criteria/lead-gen/check/", data={"aryza_reference": "CC-LG"}, format="json")
        self.assertEqual(LeadGenCheck.objects.get(aryza_reference="CC-LG").criteria_version, "v2")
        CreditorCriteria.objects.filter(pk=self.alpha.pk).update(min_dividend_pence=99)  # outside the workflow
        with patch(FETCH, return_value=case):
            lg.post("/api/v1/criteria/lead-gen/check/", data={"aryza_reference": "CC-LG"}, format="json")
        latest = LeadGenCheck.objects.filter(aryza_reference="CC-LG").order_by("-id").first()
        self.assertEqual(latest.criteria_version, "v2+unapproved-changes")


class CriteriaChangeChoiceFieldTests(TransactionTestCase):
    """Choice fields (e.g. representative) must offer and store the exact allowed values."""

    def setUp(self):
        self.cred = CreditorCriteria.objects.create(creditor_name="118 Test Money", representative="NONE",
                                                    status="ACCEPT", is_active=True)
        dept = Department.objects.create(name="Managers", slug="managers")
        DepartmentFeatureAccess.objects.create(department=dept, feature_key="criteria_changes", is_enabled=True)
        self.user = User.objects.create_user("mgr", password=None)
        UserProfile.objects.create(user=self.user, department=dept)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}")

    def _draft(self, value):
        return self.api.post(BASE, data={"title": "Rep change", "reason": "Test", "items": [
            {"model": "CreditorCriteria", "object_id": self.cred.pk, "field": "representative", "new_value": value},
        ]}, format="json")

    def test_choice_typed_in_other_case_is_stored_as_exact_value(self):
        for typed in ("watch", "Watch"):
            resp = self._draft(typed)
            self.assertEqual(resp.status_code, 201, resp.content)
            self.assertEqual(resp.json()["items"][0]["new_value"], "WATCH")
        self.assertEqual(CreditorCriteria.objects.get(pk=self.cred.pk).representative, "NONE")  # draft only

    def test_invalid_choice_still_rejected(self):
        resp = self._draft("WATCHDOG")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "INVALID_VALUE")

    def test_managed_fields_exposes_choices(self):
        body = self.api.get(f"{BASE}managed-fields/").json()
        rep = body["field_info"]["CreditorCriteria"]["representative"]
        self.assertIn("WATCH", [c[0] for c in rep["choices"]])
        self.assertEqual(body["field_info"]["GlobalCriteria"]["is_active"]["type"], "BooleanField")
