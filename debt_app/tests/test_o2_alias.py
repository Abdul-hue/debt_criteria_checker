"""
O2 name resolution (2026-10-13, case 415929).

The workbook's GENERAL CREDITOR row is "O2 UK | DO NOT VOTE". Aryza sends
"O2 (UK)" and credit reports say "O2 Uk Limited". Normalisation reduces every
one of them to "o2", so without an alias they all resolved as unidentified.
"""

from django.test import TestCase

from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import CreditorCriteria


def _position(name):
    case = _parse_case({"creditors": [{"creditor_name": name, "balance": 800}]})
    case.update({"aryza_reference": "T", "client_name": "T"})
    return _check_creditor_individual(case)[0]


class O2AliasTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.filter(creditor_name__icontains="o2").delete()
        self.o2 = CreditorCriteria.objects.create(
            creditor_name="O2 UK", representative="NONE", status="DO_NOT_VOTE", is_active=True,
        )

    def test_every_o2_spelling_resolves_to_the_workbook_row(self):
        for name in ("O2 (UK)", "O2 UK", "O2 Uk Limited", "O2", "o2 (uk) limited"):
            with self.subTest(name=name):
                self.assertEqual(get_creditor_by_trading_name(name).pk, self.o2.pk)

    def test_aryza_name_takes_the_do_not_vote_stance(self):
        self.assertEqual(_position("O2 (UK)")["effective_status"], "DO_NOT_VOTE")

    def test_names_merely_containing_o2_are_not_matched(self):
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("Go2 Finance")
