"""
Phase 2C exact alias (2026-10-21). Aryza creditor 919785 "Hutchinson 3G UK Ltd"
(Aryza's spelling of Hutchison 3G, the company behind the Three network) was
unknown; it now resolves to the existing '3 Mobile' row and takes its
DO NOT VOTE stance. Normalisation strips "UK Ltd", so "Hutchinson 3G" shares
the key. The correctly spelled "Hutchison 3G UK Ltd" (credit reports) was
aliased on 2026-10-27 (case 426399).

As in the Phase 2A tests, resolutions are asserted with the rows created in
both orders, so a pass cannot come from table order.
"""

from django.test import TestCase

from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import CouncilRule, CreditorCriteria


def _positions(name):
    case = _parse_case({"creditors": [{"creditor_name": name, "balance": 800}]})
    case.update({"aryza_reference": "T", "client_name": "T"})
    return _check_creditor_individual(case)


def _variants(name):
    return (name, name.lower(), name.upper(), f"  {name}  ")


class HutchinsonThreeMobileAliasTests(TestCase):
    # (creditor_name, representative, status) - target first, bystander after
    ROWS = (("3 Mobile", "NONE", "DO_NOT_VOTE"),
            ("Vodafone", "NONE", "DO_NOT_VOTE"))

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

    def test_hutchinson_3g_uk_ltd_resolves_to_3_mobile(self):
        self.assertResolves(_variants("Hutchinson 3G UK Ltd") + _variants("Hutchinson 3G"), "3 Mobile")

    def test_hutchinson_3g_takes_the_do_not_vote_stance(self):
        self.build(True)
        pos = _positions("Hutchinson 3G UK Ltd")[0]
        self.assertEqual(pos["resolved_canonical_name"], "3 Mobile")
        self.assertEqual(pos["representative"], "NONE")
        self.assertEqual(pos["effective_status"], "DO_NOT_VOTE")
        self.assertNotIn("CREDITOR-UNKNOWN", {f["code"] for f in pos["findings"]})

    def test_hutchison_3g_correct_spelling_resolves_to_3_mobile(self):
        self.assertResolves(_variants("HUTCHISON 3G UK LTD"), "3 Mobile")

    def test_existing_names_unchanged(self):
        self.assertResolves(("3 Mobile",), "3 Mobile")
        self.assertResolves(("Vodafone",), "Vodafone")

    def test_three_rivers_council_stays_council_routed(self):
        pks = self.build(True)
        CouncilRule.objects.get_or_create(council_name="Three Rivers District Council",
                                          defaults={"status": "DO_NOT_VOTE"})
        # council names are skipped by the creditor check (handled by council rules)
        self.assertEqual(_positions("Three Rivers District Council"), [])
        try:
            pk = get_creditor_by_trading_name("Three Rivers District Council").pk
        except CreditorCriteria.DoesNotExist:
            pk = None
        self.assertNotEqual(pk, pks["3 Mobile"])
