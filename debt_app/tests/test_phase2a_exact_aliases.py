"""
Phase 2A exact aliases (2026-10-20). Four Aryza creditor names that were either
unknown or reached their row only through step 4 of
_get_creditor_by_trading_name_uncached (first row, in table order, whose name
appears inside the input):

  * "Elevate Credit International Limited" -> 'Elevate Credit International (Sunny)'
  * "Credit Spring"                        -> 'CreditSpring'
  * "Fluid Credit (NewDay Limited)"        -> 'Fluid' (WATCH), never 'NewDay' (TIX)
  * "Lantern Debt Recovery previously SLL Capital Ltd"
                                           -> 'Lantern' (WATCH), never 'SLL Capital'

Each resolution is asserted with the rows created in both orders (target
first, then competitor first), so a pass cannot come from table order.
"""

from django.test import TestCase

from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import CreditorCriteria


def _position(name):
    case = _parse_case({"creditors": [{"creditor_name": name, "balance": 800}]})
    case.update({"aryza_reference": "T", "client_name": "T"})
    return _check_creditor_individual(case)[0]


def _variants(name):
    return (name, name.lower(), name.upper(), f"  {name}  ")


class _OrderedRows(TestCase):
    # (creditor_name, representative, status) - target first, competitors after
    ROWS = ()

    def build(self, target_first):
        names = [r[0] for r in self.ROWS]
        CreditorCriteria.objects.filter(creditor_name__in=names).delete()
        order = self.ROWS if target_first else tuple(reversed(self.ROWS))
        for name, rep, status in order:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status, is_active=True)
        return {n: CreditorCriteria.objects.get(creditor_name=n).pk for n in names}

    def assertResolves(self, inputs, expected):
        for target_first in (True, False):
            pks = self.build(target_first)
            for raw in inputs:
                with self.subTest(raw=raw, target_first=target_first):
                    self.assertEqual(get_creditor_by_trading_name(raw).pk, pks[expected])


class ElevateAliasTests(_OrderedRows):
    ROWS = (("Elevate Credit International (Sunny)", "NONE", "DO_NOT_VOTE"),
            ("Sunny Loans", "NONE", "DO_NOT_VOTE"))

    def test_legal_name_resolves_to_elevate_row(self):
        self.assertResolves(_variants("Elevate Credit International Ltd")
                            + _variants("Elevate Credit International Limited"),
                            "Elevate Credit International (Sunny)")
        self.assertEqual(_position("Elevate Credit International Limited")["resolved_canonical_name"],
                         "Elevate Credit International (Sunny)")

    def test_competing_names_unchanged(self):
        self.assertResolves(("Sunny Loans",), "Sunny Loans")
        self.assertResolves(("Elevate Credit International (Sunny)",), "Elevate Credit International (Sunny)")


class CreditSpringAliasTests(_OrderedRows):
    ROWS = (("CreditSpring", "NONE", "DO_NOT_VOTE"),)

    def test_spaced_name_resolves_to_creditspring_row(self):
        self.assertResolves(_variants("Credit Spring") + ("Credit Spring Limited",), "CreditSpring")
        self.assertEqual(_position("Credit Spring")["resolved_canonical_name"], "CreditSpring")

    def test_existing_spelling_unchanged(self):
        self.assertResolves(("CreditSpring", "Creditspring Limited"), "CreditSpring")

    def test_inclusive_finance_trading_as_credit_spring_resolves_to_creditspring(self):
        # Confirmed 2026-10-20: names that explicitly identify the Credit Spring
        # brand map to the CreditSpring row.
        self.assertResolves(("INCLUSIVE FINANCE T/A CREDIT SPRING",), "CreditSpring")

    def test_plain_inclusive_finance_stays_unknown(self):
        # Confirmed 2026-10-20: without the Credit Spring brand in the name,
        # Inclusive Finance has no parent until separately validated.
        self.build(True)
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("Inclusive Finance Limited")

    def test_unrelated_credit_names_do_not_reach_creditspring(self):
        pks = self.build(True)
        for raw in ("Credit Resource Solutions Limited", "Spring", "Credit"):
            with self.subTest(raw=raw):
                try:
                    pk = get_creditor_by_trading_name(raw).pk
                except CreditorCriteria.DoesNotExist:
                    pk = None
                self.assertNotEqual(pk, pks["CreditSpring"])


class FluidCreditAliasTests(_OrderedRows):
    ROWS = (("Fluid", "WATCH", "ACCEPT"),
            ("NewDay", "TIX", "ACCEPT"))

    def test_fluid_credit_newday_resolves_to_watch_fluid_in_any_row_order(self):
        self.assertResolves(_variants("Fluid Credit (NewDay)") + _variants("Fluid Credit (NewDay Limited)"), "Fluid")
        pos = _position("Fluid Credit (NewDay Limited)")
        self.assertEqual(pos["resolved_canonical_name"], "Fluid")
        self.assertEqual(pos["representative"], "WATCH")

    def test_competing_names_unchanged(self):
        self.assertResolves(("NewDay", "NewDay Limited"), "NewDay")
        self.assertResolves(("Fluid",), "Fluid")


class LanternAliasTests(_OrderedRows):
    ROWS = (("Lantern", "WATCH", "ACCEPT"),
            ("SLL Capital", "NONE", "ACCEPT"))

    def test_lantern_previously_sll_resolves_to_watch_lantern_in_any_row_order(self):
        self.assertResolves(_variants("Lantern Debt Recovery previously SLL Capital Ltd")
                            + _variants("Lantern Debt Recovery"), "Lantern")
        pos = _position("Lantern Debt Recovery previously SLL Capital Ltd")
        self.assertEqual(pos["resolved_canonical_name"], "Lantern")
        self.assertEqual(pos["representative"], "WATCH")

    def test_competing_names_unchanged(self):
        self.assertResolves(("SLL Capital", "SLL Capital Ltd"), "SLL Capital")
        self.assertResolves(("Lantern", "Lantern Debt Recovery Services Ltd"), "Lantern")
