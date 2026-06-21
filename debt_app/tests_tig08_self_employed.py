"""
TIG-08 self-employed evidence tests.

Excel ground truth: only ONE of tax return OR business bank statement is
required — not both.  The engine had `and` where it should have `or`.
"""

from django.test import TestCase

from debt_app.criteria_engine import _tig_08


def _case(**over):
    base = {
        "income_source": "self_employed",
        "tax_return_docs": [],
        "bank_stmt_docs": [],
    }
    base.update(over)
    return base


class Tig08SelfEmployedTests(TestCase):
    def test_not_self_employed_passes(self):
        r = _tig_08(_case(income_source="employed"))
        self.assertFalse(r.triggered)

    def test_neither_present_flags(self):
        r = _tig_08(_case(tax_return_docs=[], bank_stmt_docs=[]))
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")

    def test_tax_return_alone_passes(self):
        # Excel: tax return OR bank statement — one is sufficient.
        r = _tig_08(_case(tax_return_docs=["tax_return_2023.pdf"], bank_stmt_docs=[]))
        self.assertFalse(r.triggered)

    def test_bank_statement_alone_passes(self):
        # Excel: tax return OR bank statement — one is sufficient.
        r = _tig_08(_case(tax_return_docs=[], bank_stmt_docs=["bank_jan.pdf"]))
        self.assertFalse(r.triggered)

    def test_both_present_passes(self):
        r = _tig_08(_case(
            tax_return_docs=["tax_return_2023.pdf"],
            bank_stmt_docs=["bank_jan.pdf"],
        ))
        self.assertFalse(r.triggered)
