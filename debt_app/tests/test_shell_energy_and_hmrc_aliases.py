"""
Name resolution for two confirmed decisions (2026-10-13).

Shell Energy: the user confirmed that the 'Shell Energy' row is the creditor the
General sheet lists as 'Shell Energy Retail Limited (NOW OCTOPUS) | Accept'.
Resolution as it actually works, with the duplicate row deactivated:
  * "Shell Energy" (what cases send)            -> the 'Shell Energy' row, Accept
  * "Shell Energy Retail Limited" (any suffix)  -> Octopus Energy, whose trading
    names migration 0030 seeded with that name (the sheet says "NOW OCTOPUS"),
    also Accept
  * "Shell Energy Retail Limited (NOW OCTOPUS)" -> no longer the duplicate row
Nothing resolves as unknown and nothing becomes UNKNOWN or Reject.

HMRC: Aryza sends "HMRC"; the October workbook's GENERAL CREDITOR row 174 is
'HM Revenue & Customs' and calls itself "HMRC" in its notes, and the TIG sheet
states the HMRC rules under "HMRC". The short name resolves to that row and
carries its Will Consider stance and notes flag; "HMRC - benefits overpayments"
is a different row and is not matched.
"""

from django.test import TestCase

from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import CreditorCriteria
from debt_app.services.criteria_change_builder import SHELL_ENERGY_CANONICAL, SHELL_ENERGY_DUPLICATE


def _position(name):
    case = _parse_case({"creditors": [{"creditor_name": name, "balance": 800}]})
    case.update({"aryza_reference": "T", "client_name": "T"})
    return _check_creditor_individual(case)[0]


def _codes(pos):
    return {f["code"] for f in pos["findings"]}


class ShellEnergyResolutionTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.filter(creditor_name__icontains="shell").delete()
        # state after the proposed changes are applied
        self.shell = CreditorCriteria.objects.create(
            creditor_name=SHELL_ENERGY_CANONICAL, representative="NONE", status="ACCEPT", is_active=True,
        )
        self.duplicate = CreditorCriteria.objects.create(
            creditor_name=SHELL_ENERGY_DUPLICATE, representative="NONE", status="ACCEPT", is_active=False,
        )
        # Octopus Energy as migration 0030 seeds it (takeover of Shell Energy Retail)
        self.octopus, _ = CreditorCriteria.objects.update_or_create(
            creditor_name="Octopus Energy",
            defaults=dict(representative="NONE", status="ACCEPT", is_active=True,
                          trading_names=["Bulb Energy", "Shell Energy Retail Limited"]),
        )
        self.bystander = CreditorCriteria.objects.create(
            creditor_name="Shellfish Finance", representative="NONE", status="REJECT", is_active=True,
        )

    def test_shell_energy_resolves_to_its_own_row_with_accept(self):
        for raw in ("Shell Energy", "SHELL ENERGY", "Shell Energy Limited"):
            with self.subTest(raw=raw):
                self.assertEqual(get_creditor_by_trading_name(raw).pk, self.shell.pk)
        pos = _position("Shell Energy")
        self.assertEqual(pos["resolved_canonical_name"], SHELL_ENERGY_CANONICAL)
        self.assertEqual(pos["effective_status"], "ACCEPT")
        self.assertFalse({"CREDITOR-UNKNOWN", "CREDITOR-STANCE-UNCONFIRMED"} & _codes(pos))

    def test_retail_variants_resolve_to_octopus_energy_as_seeded(self):
        for raw in ("Shell Energy Retail Limited", "SHELL ENERGY RETAIL LIMITED"):
            with self.subTest(raw=raw):
                self.assertEqual(get_creditor_by_trading_name(raw).pk, self.octopus.pk)
        pos = _position("Shell Energy Retail Limited")
        self.assertEqual(pos["effective_status"], "ACCEPT")
        self.assertNotIn("CREDITOR-UNKNOWN", _codes(pos))

    def test_duplicate_row_is_kept_but_no_longer_matched(self):
        self.assertTrue(CreditorCriteria.objects.filter(pk=self.duplicate.pk, is_active=False).exists())
        self.assertNotEqual(get_creditor_by_trading_name(SHELL_ENERGY_DUPLICATE).pk, self.duplicate.pk)
        self.assertEqual(_position(SHELL_ENERGY_DUPLICATE)["effective_status"], "ACCEPT")

    def test_unrelated_rows_untouched(self):
        self.assertEqual(get_creditor_by_trading_name("Shellfish Finance").pk, self.bystander.pk)
        self.assertEqual(CreditorCriteria.objects.get(pk=self.bystander.pk).status, "REJECT")


class HmrcAliasTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.filter(creditor_name="HMRC").delete()
        self.main, _ = CreditorCriteria.objects.update_or_create(
            creditor_name="HM Revenue & Customs",
            defaults=dict(representative="NONE", status="WILL_CONSIDER", is_active=True,
                          criteria_notes="HMRC majority - MUST NOT have a deduction from income or benefits (will reject)."),
        )
        self.overpayments, _ = CreditorCriteria.objects.update_or_create(
            creditor_name="HMRC - benefits overpayments",
            defaults=dict(representative="NONE", status="WILL_CONSIDER", is_active=True),
        )

    def test_short_name_resolves_to_the_sheet_row_only(self):
        for raw in ("HMRC", "hmrc", "HM Revenue & Customs"):
            with self.subTest(raw=raw):
                self.assertEqual(get_creditor_by_trading_name(raw).pk, self.main.pk)
        self.assertEqual(get_creditor_by_trading_name("HMRC - benefits overpayments").pk, self.overpayments.pk)

    def test_engine_applies_will_consider_and_the_notes_flag(self):
        pos = _position("HMRC")
        self.assertEqual(pos["resolved_canonical_name"], "HM Revenue & Customs")
        self.assertEqual(pos["effective_status"], "WILL_CONSIDER")
        self.assertNotIn("CREDITOR-UNKNOWN", _codes(pos))
        self.assertIn("CREDITOR-MANUAL-CHECK-REQUIRED", _codes(pos))
