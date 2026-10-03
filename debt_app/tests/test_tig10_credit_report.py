"""
TIG-10 honours `from_credit_report`, and Aryza's Amex / EON names resolve.

Bugs this pins down (case 416326)
---------------------------------
1. `_parse_case` never copied `from_credit_report` from the case JSON, so
   TIG-10 judged a placeholder-named debt on its name alone: three CCJs the
   credit report carries (£2,181, £6,165, £5,984) were a hard block "could not
   be verified from Aryza's records or a credit report match".
2. Aryza's "American Express Services Ltd" normalises to "american express
   services", which no alias reached -- three WILL_CONSIDER cards (£13,800)
   were UNKNOWN, so the majority read "£0.00 of confirmed support".
3. "EON ENERGY LIMITED" had no alias to E.ON (confirmed the same creditor).
"""
from django.test import SimpleTestCase

from debt_app.engine.criteria import _parse_case, _tig_10
from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name


def _case(*creditors):
    return _parse_case({"creditors": list(creditors)})


class Tig10ReadsFromCreditReport(SimpleTestCase):

    def test_case_416326_report_backed_ccjs_pass(self):
        c = _case(
            {"creditor_name": "CCJ (creditor not yet identified)", "balance": 2181, "from_credit_report": True},
            {"creditor_name": "Other", "balance": 6165, "from_credit_report": True},
            {"creditor_name": "Other", "balance": 5984, "from_credit_report": True},
            {"creditor_name": "American Express Services Ltd", "balance": 4600},
        )
        self.assertFalse(_tig_10(c).triggered)

    def test_the_flag_survives_parsing(self):
        c = _case({"creditor_name": "Other", "balance": 6165, "from_credit_report": True},
                  {"creditor_name": "Lendable", "balance": 9000})
        self.assertEqual([cr["from_credit_report"] for cr in c["creditors"]], [True, False])

    def test_an_unproven_placeholder_still_blocks(self):
        c = _case({"creditor_name": "CCJ (creditor not yet identified)", "balance": 2181,
                   "from_credit_report": False},
                  {"creditor_name": "Lendable", "balance": 9000})
        r = _tig_10(c)
        self.assertEqual(r.severity, "hard_block")
        self.assertIn("2,181", r.message)

    def test_absent_means_not_on_the_report(self):
        c = _case({"creditor_name": "Other", "balance": 6165},
                  {"creditor_name": "Lendable", "balance": 9000})
        self.assertEqual(_tig_10(c).severity, "hard_block")

    def test_only_the_unproven_one_is_named(self):
        c = _case({"creditor_name": "Other", "balance": 6165, "from_credit_report": True},
                  {"creditor_name": "CCJ (creditor not yet identified)", "balance": 2181},
                  {"creditor_name": "Lendable", "balance": 9000})
        r = _tig_10(c)
        self.assertIn("2,181", r.message)
        self.assertNotIn("6,165", r.message)


class AryzaNamesResolve(SimpleTestCase):

    def _resolve(self, raw):
        return CREDITOR_ALIAS_MAP.get(normalise_creditor_name(raw))

    def test_american_express_services_ltd(self):
        self.assertEqual(self._resolve("American Express Services Ltd"), "American Express Service")
        self.assertEqual(self._resolve("AMERICAN EXPRESS SERVICES LIMITED"), "American Express Service")

    def test_the_existing_amex_spellings_are_unchanged(self):
        for raw in ("American Express", "American Express Services Europe Ltd", "Amex"):
            self.assertEqual(self._resolve(raw), "American Express Service", raw)

    def test_eon_energy_limited_is_eon(self):
        self.assertEqual(self._resolve("EON ENERGY LIMITED"), "E.ON")
        self.assertEqual(self._resolve("Eon Energy Ltd"), "E.ON")
