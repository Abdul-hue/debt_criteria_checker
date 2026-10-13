"""
UNKNOWN stance (2026-10-13):

  * A creditor whose status is UNKNOWN is never treated as an acceptance: the
    engine reports "no recorded standing position", flags
    CREDITOR-STANCE-UNCONFIRMED and keeps effective_status UNKNOWN (which the
    majority logic treats as "could flip either way").
  * Removing a representative body (Evolve) must not turn a creditor into an
    Accept just because the row's model default is ACCEPT.
  * Zilch resolves to its own record from every form seen on real cases and no
    longer falls through to CREDITOR-UNKNOWN, while its stance stays UNKNOWN
    until the sheet owner confirms it.
"""

import io
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.helpers import get_creditor_by_trading_name
from debt_app.management.commands.seed_creditor_criteria import _parse_status
from debt_app.models import CreditorCriteria
from debt_app.services import criteria_versioning as cv


def _position(name, balance=1500):
    case = _parse_case({"creditors": [{"creditor_name": name, "balance": balance}]})
    case.update({"aryza_reference": "T", "client_name": "T"})
    return _check_creditor_individual(case)[0]


def _codes(pos):
    return {f["code"] for f in pos["findings"]}


class UnknownStanceTests(TestCase):
    def test_unknown_status_is_flagged_and_never_an_acceptance(self):
        CreditorCriteria.objects.update_or_create(
            creditor_name="NatWest", defaults=dict(representative="NONE", status="UNKNOWN", is_active=True),
        )
        pos = _position("NatWest")
        self.assertEqual(pos["effective_status"], "UNKNOWN")
        self.assertIn("CREDITOR-STANCE-UNCONFIRMED", _codes(pos))
        self.assertNotIn("CREDITOR-UNKNOWN", _codes(pos))
        self.assertEqual(pos["resolved_canonical_name"], "NatWest")
        self.assertIn("no recorded standing position", pos["reason"])

    def test_ex_evolve_creditor_with_default_status_would_be_accept_without_the_fix(self):
        """Documents the hazard the UNKNOWN stance exists to prevent: a row that
        merely loses its representative inherits the model default ACCEPT."""
        CreditorCriteria.objects.update_or_create(
            creditor_name="Mint", defaults=dict(representative="NONE", is_active=True),   # status left at the model default
        )
        self.assertEqual(CreditorCriteria.objects.get(creditor_name="Mint").status, "ACCEPT")
        self.assertEqual(_position("Mint")["effective_status"], "ACCEPT")
        # ...and with the stance recorded as UNKNOWN it is not
        CreditorCriteria.objects.filter(creditor_name="Mint").update(status="UNKNOWN")
        self.assertEqual(_position("Mint")["effective_status"], "UNKNOWN")

    def test_unknown_is_a_valid_managed_choice_for_change_requests(self):
        obj = CreditorCriteria.objects.create(creditor_name="Ulster Bank Test", representative="NONE", status="ACCEPT")
        self.assertEqual(cv._coerce("CreditorCriteria", "status", "UNKNOWN"), "UNKNOWN")
        items = cv.build_items([{"model": "CreditorCriteria", "object_id": obj.pk, "field": "status", "new_value": "UNKNOWN"}])
        self.assertEqual((items[0]["old_value"], items[0]["new_value"]), ("ACCEPT", "UNKNOWN"))

    def test_parse_status_recognises_unknown(self):
        self.assertEqual(_parse_status("UNKNOWN"), "UNKNOWN")
        self.assertEqual(_parse_status("Accept"), "ACCEPT")
        self.assertIsNone(_parse_status("TRADING STYLE OF AMIGO"))


class ZilchResolutionTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.filter(creditor_name__icontains="zilch").delete()
        self.zilch = CreditorCriteria.objects.create(
            creditor_name="Zilch", representative="NONE", status="UNKNOWN", is_active=True,
            trading_names=["Zilch Technology Limited", "Zilch Technology LTD"],
        )

    def test_every_real_world_form_resolves_to_the_single_record(self):
        for raw in ("Zilch", "ZILCH TECHNOLOGY LIMITED", "Zilch Technology LTD", "Zilch Technology LTD BD"):
            with self.subTest(raw=raw):
                self.assertEqual(get_creditor_by_trading_name(raw).pk, self.zilch.pk)
        self.assertEqual(CreditorCriteria.objects.filter(creditor_name__icontains="zilch").count(), 1)

    def test_engine_position_is_resolved_but_unconfirmed(self):
        pos = _position("ZILCH TECHNOLOGY LIMITED", balance=265)
        self.assertEqual(pos["resolved_canonical_name"], "Zilch")
        self.assertNotIn("CREDITOR-UNKNOWN", _codes(pos))
        self.assertIn("CREDITOR-STANCE-UNCONFIRMED", _codes(pos))
        self.assertEqual(pos["effective_status"], "UNKNOWN")


GENERAL_WITH_ZILCH = """# GENERAL CREDITOR

| Creditor | Accept / Reject | Notes / Criteria | updated criteria | Phone Number | Email | Contact |
| --- | --- | --- | --- | --- | --- | --- |
| Zilch | UNKNOWN | Added for name matching only; stance to be confirmed. |  |  |  |  |
"""


class ZilchSeedingTests(TestCase):
    def test_notes_only_sync_creates_zilch_with_unknown_stance_and_trading_names(self):
        CreditorCriteria.objects.filter(creditor_name__icontains="zilch").delete()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Excel Criteria").mkdir()
            (root / "Excel Criteria" / "General_Creditors.md").write_text(GENERAL_WITH_ZILCH, encoding="utf-8")
            out = io.StringIO()
            with override_settings(BASE_DIR=root):
                call_command("seed_creditor_criteria", stdout=out)
                call_command("seed_creditor_criteria", stdout=io.StringIO())   # idempotent
        rows = CreditorCriteria.objects.filter(creditor_name__icontains="zilch")
        self.assertEqual(rows.count(), 1)
        z = rows.get()
        self.assertEqual(z.status, "UNKNOWN")
        self.assertEqual(z.representative, "NONE")
        self.assertEqual(z.trading_names, ["Zilch Technology Limited", "Zilch Technology LTD"])
        self.assertIn("[CREATE] 'Zilch' (status UNKNOWN", out.getvalue())
