"""
Phase 1 of the Case Rejection Criteria (Missing Evidence) work: `_parse_case`
reads the fields agreed with CAT (CA_TOOL_DEPENDENCIES.md, "Proposed: Case
Rejection Criteria"). No rule reads them yet, so these tests pin the parsed
values only:

* evidence flags are tri-state -- None ("CAT does not know") must survive,
  because the rules will flag on None but return the case on False;
* `div_returned` is a decimal fraction; a percentage (25) is rejected, not
  guessed at, since it would inflate the required DI a hundredfold;
* `self_employed_months` counts completed calendar months, because the
  call-sheet rule's 12-month cut-off is exact;
* `ccj_is_majority` is > 50% of the unsecured total, secured debts excluded.
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from debt_app.engine.criteria import _parse_case, _whole_months_between


def _case(**extra):
    base = {
        "assessment_date": "2026-10-27",
        "creditors": [{"creditor_name": "Lendable", "balance": 7000}],
    }
    base.update(extra)
    return base


class CreditorEvidenceFieldsTest(SimpleTestCase):

    def _creditor(self, **fields):
        return _parse_case(_case(creditors=[{"creditor_name": "Lendable", "balance": 7000, **fields}]))["creditors"][0]

    def test_absent_fields_are_not_known(self):
        cr = self._creditor()
        self.assertIsNone(cr["has_pod"])
        self.assertIsNone(cr["creditor_call_completed"])
        self.assertIsNone(cr["div_returned"])
        self.assertIsNone(cr["original_creditor"])
        self.assertIs(cr["has_ccj"], False)

    def test_explicit_false_is_kept_distinct_from_null(self):
        self.assertIs(self._creditor(has_pod=False)["has_pod"], False)
        self.assertIsNone(self._creditor(has_pod=None)["has_pod"])
        self.assertIs(self._creditor(creditor_call_completed=False)["creditor_call_completed"], False)

    def test_true_values(self):
        cr = self._creditor(has_pod=True, creditor_call_completed=True, has_ccj=True)
        self.assertIs(cr["has_pod"], True)
        self.assertIs(cr["creditor_call_completed"], True)
        self.assertIs(cr["has_ccj"], True)

    def test_div_returned_decimal(self):
        self.assertEqual(self._creditor(div_returned=0.25)["div_returned"], Decimal("0.25"))
        self.assertEqual(self._creditor(div_returned="0.5")["div_returned"], Decimal("0.5"))
        self.assertEqual(self._creditor(div_returned=1)["div_returned"], Decimal("1"))

    def test_div_returned_out_of_range_or_unreadable_is_ignored(self):
        for bad in (25, 0, -0.1, "25%", "abc", ""):
            with self.subTest(value=bad):
                self.assertIsNone(self._creditor(div_returned=bad)["div_returned"])

    def test_original_creditor_blank_is_none(self):
        self.assertIsNone(self._creditor(original_creditor="   ")["original_creditor"])
        self.assertEqual(self._creditor(original_creditor=" Vanquis ")["original_creditor"], "Vanquis")


class ClientEvidenceFieldsTest(SimpleTestCase):

    def test_call_sheet_tri_state(self):
        self.assertIsNone(_parse_case(_case())["has_call_sheet"])
        self.assertIs(_parse_case(_case(has_call_sheet=False))["has_call_sheet"], False)
        self.assertIs(_parse_case(_case(has_call_sheet=True))["has_call_sheet"], True)

    def test_call_sheet_top_level_wins_over_client_info(self):
        c = _parse_case(_case(has_call_sheet=False, clientInfo={"has_call_sheet": True}))
        self.assertIs(c["has_call_sheet"], False)
        c = _parse_case(_case(clientInfo={"has_call_sheet": True}))
        self.assertIs(c["has_call_sheet"], True)

    def test_self_employed_months(self):
        c = _parse_case(_case(self_employed_since="2025-10-27"))
        self.assertEqual(c["self_employed_since"], date(2025, 10, 27))
        self.assertEqual(c["self_employed_months"], 12)
        self.assertEqual(_parse_case(_case(self_employed_since="2025-10-28"))["self_employed_months"], 11)

    def test_self_employed_unknown_or_future(self):
        self.assertIsNone(_parse_case(_case())["self_employed_months"])
        self.assertIsNone(_parse_case(_case(self_employed_since="2027-01-01"))["self_employed_months"])
        self.assertIsNone(_parse_case(_case(self_employed_since="not a date"))["self_employed_months"])

    def test_whole_months_between(self):
        self.assertEqual(_whole_months_between(date(2026, 1, 15), date(2026, 2, 15)), 1)
        self.assertEqual(_whole_months_between(date(2026, 1, 15), date(2026, 2, 14)), 0)
        self.assertEqual(_whole_months_between(date(2026, 1, 31), date(2026, 2, 28)), 0)
        self.assertIsNone(_whole_months_between(None, date(2026, 2, 14)))


class CcjMajorityTest(SimpleTestCase):

    def test_ccj_majority_by_flag_type_or_placeholder_name(self):
        c = _parse_case(_case(creditors=[
            {"creditor_name": "Lendable", "balance": 2000, "has_ccj": True},
            {"creditor_name": "Cabot", "balance": 2000, "creditor_type": "CCJ"},
            {"creditor_name": "CCJ (creditor not yet identified)", "balance": 2000},
            {"creditor_name": "Barclaycard", "balance": 3000},
        ]))
        self.assertEqual(len(c["ccj_creditors"]), 3)
        self.assertEqual(c["ccj_balance"], 6000)
        self.assertIs(c["ccj_is_majority"], True)

    def test_exactly_half_is_not_majority(self):
        c = _parse_case(_case(creditors=[
            {"creditor_name": "CCJ", "balance": 3000},
            {"creditor_name": "Barclaycard", "balance": 3000},
        ]))
        self.assertIs(c["ccj_is_majority"], False)

    def test_secured_debt_excluded(self):
        c = _parse_case(_case(creditors=[
            {"creditor_name": "CCJ", "balance": 4000},
            {"creditor_name": "Barclaycard", "balance": 3000},
            {"creditor_name": "Santander Mortgage", "balance": 100000, "is_secured": True, "has_ccj": True},
        ]))
        self.assertEqual(c["ccj_balance"], 4000)
        self.assertIs(c["ccj_is_majority"], True)

    def test_name_containing_ccj_letters_is_not_a_ccj(self):
        c = _parse_case(_case(creditors=[{"creditor_name": "Accjet Finance", "balance": 7000}]))
        self.assertEqual(c["ccj_creditors"], [])
        self.assertIs(c["ccj_is_majority"], False)

    def test_no_debt(self):
        c = _parse_case(_case(creditors=[]))
        self.assertEqual(c["ccj_balance"], 0)
        self.assertIs(c["ccj_is_majority"], False)
