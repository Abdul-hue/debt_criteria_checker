"""
record_criteria_baseline: a rollback point for live criteria that drifted
since the last approved version. Records nothing when nothing drifted.
(CriteriaVersion rows are append-only, so the tests work relative to whatever
versions already exist rather than clearing the table.)
"""

import io

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from debt_app.models import CreditorCriteria, CriteriaVersion
from debt_app.services import criteria_versioning as cv


class RecordBaselineTests(TestCase):
    def setUp(self):
        self.start = CriteriaVersion.objects.count()
        self.row = CreditorCriteria.objects.create(creditor_name="Baseline Co", representative="NONE", status="ACCEPT")

    def _run(self, *args):
        out = io.StringIO()
        call_command("record_criteria_baseline", "--note", "Before the October update", *args, stdout=out)
        return out.getvalue()

    def _latest(self):
        return CriteriaVersion.objects.order_by("-number").first()

    def test_records_a_version_matching_the_live_state(self):
        out = self._run()
        self.assertEqual(CriteriaVersion.objects.count(), self.start + 1)
        v = self._latest()
        self.assertEqual(v.fingerprint, cv.live_fingerprint())
        self.assertEqual(v.snapshot["CreditorCriteria"][str(self.row.pk)]["status"], "ACCEPT")
        self.assertIsNone(v.change_request)
        self.assertIn(f"Recorded {v.label}", out)
        # live rows untouched
        self.assertEqual(CreditorCriteria.objects.get(pk=self.row.pk).status, "ACCEPT")

    def test_is_a_no_op_when_nothing_drifted(self):
        self._run()
        out = self._run()
        self.assertEqual(CriteriaVersion.objects.count(), self.start + 1)
        self.assertIn("already match", out)

    def test_records_again_after_an_edit_outside_the_workflow(self):
        self._run()
        CreditorCriteria.objects.filter(pk=self.row.pk).update(status="REJECT")
        self._run()
        self.assertEqual(CriteriaVersion.objects.count(), self.start + 2)
        self.assertEqual(self._latest().snapshot["CreditorCriteria"][str(self.row.pk)]["status"], "REJECT")

    def test_can_record_the_author(self):
        User.objects.create_user("baseliner")
        self._run("--created-by", "baseliner")
        self.assertEqual(self._latest().created_by.username, "baseliner")
