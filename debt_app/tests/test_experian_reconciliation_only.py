"""
Experian reports file insurance and multi-comms as reconciliation only.

Bug this pins down
------------------
`RECONCILIATION_ONLY_TYPE_CODES` (MI, MU, BK) is "never debt": an Aryza Advize
report prints "MI" / "MU" in the account header and those accounts go to
`other_accounts`. The two Experian category maps sent the same accounts to
"OT" (motor / car insurance, insurance) and "UT" (multi communications) --
both counted as unsecured IVA debt. So one motor-insurance policy was debt or
not depending on which bureau's layout the report used: sent to the engine,
counted in the totals, and shown in the case assessment tool as a report-only
creditor to add or dismiss.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    RECONCILIATION_ONLY_TYPE_CODES,
    _EXPERIAN_CATEGORY_TO_TYPE,
    _VALID8_CATEGORY_TO_TYPE,
    _parse_experian_account,
    _parse_valid8_account,
)


def _experian(category, balance="250"):
    """One Experian CAIS account: header line, then its block."""
    header = f"ADMIRAL INSURANCE SERVICES - {category}"
    block = "\n".join([
        header,
        "Start Date: 20-01-2024",
        f"Current Balance: £{balance}",
        "Status: Up to date",
    ])
    return header, block


def _valid8(account_type, balance="250"):
    """One Valid8-style account block: status word first, then fields."""
    return "\n".join([
        "Active",
        "Company: ADMIRAL INSURANCE SERVICES",
        f"Account Type: {account_type}",
        f"Current Balance: £{balance}",
        "Start Date: 20-01-2024",
    ])


class ExperianInsuranceIsReconciliationOnly(SimpleTestCase):

    def test_every_insurance_wording_maps_to_mi(self):
        for category in ("motor insurance", "car insurance", "insurance"):
            self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE[category], "MI", category)
            self.assertEqual(_VALID8_CATEGORY_TO_TYPE[category], "MI", category)

    def test_multi_communications_maps_to_mu(self):
        self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE["multi communications"], "MU")
        self.assertEqual(_VALID8_CATEGORY_TO_TYPE["multi communications"], "MU")

    def test_both_codes_are_reconciliation_only(self):
        self.assertTrue({"MI", "MU"} <= RECONCILIATION_ONLY_TYPE_CODES)

    def test_a_cais_motor_insurance_account_is_reconciliation_only(self):
        for category in ("Motor Insurance", "Car Insurance", "Insurance"):
            parsed = _parse_experian_account(*_experian(category))
            self.assertIsNotNone(parsed, category)
            self.assertEqual(parsed["type_code"], "MI", category)
            self.assertTrue(parsed["reconciliation_only"], category)

    def test_a_valid8_insurance_account_is_reconciliation_only(self):
        parsed = _parse_valid8_account("1 High Street", _valid8("Motor Insurance"))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["type_code"], "MI")
        self.assertTrue(parsed["reconciliation_only"])

    def test_a_valid8_multi_comms_account_is_reconciliation_only(self):
        parsed = _parse_valid8_account("1 High Street", _valid8("Multi Communications"))
        self.assertEqual(parsed["type_code"], "MU")
        self.assertTrue(parsed["reconciliation_only"])


class ExperianDebtsAreUnchanged(SimpleTestCase):
    """The fix moves insurance and multi-comms only."""

    def test_ordinary_categories_keep_their_codes(self):
        for category, code in (("credit cards", "CC"), ("communications", "UT"),
                               ("telecommunications", "UT"), ("current accounts", "CA"),
                               ("mail order", "MO")):
            self.assertEqual(_EXPERIAN_CATEGORY_TO_TYPE[category], code, category)
        self.assertEqual(_VALID8_CATEGORY_TO_TYPE["communications"], "UT")

    def test_a_credit_card_is_still_debt(self):
        parsed = _parse_experian_account(*_experian("Credit Cards"))
        self.assertEqual(parsed["type_code"], "CC")
        self.assertFalse(parsed["reconciliation_only"])

    def test_an_unlisted_category_is_still_other_debt(self):
        parsed = _parse_valid8_account("1 High Street", _valid8("Something New"))
        self.assertEqual(parsed["type_code"], "OT")
        self.assertFalse(parsed["reconciliation_only"])
