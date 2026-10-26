"""
Phase 3B (2026-10-21).

1. Unmatched parking debts. Aryza's "parking_ticket" normalises to pcn, which
   _check_creditor_individual skips as a council type; _check_council_rules then
   skipped it again when no CouncilRule matched, so a private operator such as
   Parkingeye had no position at all while staying in total_debt. It now gets an
   explicit UNKNOWN creditor position (PCN-NO-COUNCIL-RULE) - never a creditor
   lookup, never a council position. The majority already counted the debt as
   unknown, so the vote outcome is unchanged; the equivalence test compares
   against the same debt typed as an ordinary unidentified creditor, which is
   what the case produced before this change.

2. Alias chains. 'monzo' -> 'Monzo Bank' and 'monzo bank' -> 'Monzo' formed a
   loop, and 'home retail group card services' -> 'Home Retail Group' chained
   into 'home retail group' -> 'Argos Card Services'. The engine applies the map
   before the resolver and the resolver applies it again, so these names landed
   on a different row depending on how many hops a call site made.
"""

from django.test import SimpleTestCase, TestCase

from debt_app.engine.criteria import (
    _check_creditor_individual, _parse_case, assess_case, reconcile_creditor_positions,
)
from debt_app.helpers import CREDITOR_ALIAS_MAP, get_creditor_by_trading_name, normalise_creditor_name
from debt_app.models import CouncilRule, CreditorCriteria


def _alias_hop(name):
    return CREDITOR_ALIAS_MAP.get(normalise_creditor_name(name), name)


def _payload(creditors, **extra):
    return {
        "creditors": [{"name": n, "creditor_type": t, "balance": b} for n, t, b in creditors],
        "financial_summary": {"net_balance": 300},
        "documents": [], "gold_transactions": [], "evidence_ledger": [],
        **extra,
    }


def _positions(result, code):
    return [p for p in result["creditor_positions"] if code in (p.get("rule_ids") or [])]


class UnmatchedPcnTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        CouncilRule.objects.all().delete()
        CreditorCriteria.objects.all().delete()
        CouncilRule.objects.create(council_name="Zzyborough District Council", status="WILL_CONSIDER")
        for name, status in (("Barclaycard", "ACCEPT"), ("Lloyds Bank", "ACCEPT"), ("LINK", "WILL_CONSIDER")):
            CreditorCriteria.objects.create(creditor_name=name, representative="NONE", status=status, is_active=True)

    def _assess(self, parking_type="parking_ticket", parking_name="Parkingeye Limited", **extra):
        return assess_case(_payload([
            ("Barclaycard", "credit_card", 5000.0),
            ("Lloyds Bank", "personal_loan", 2000.0),
            (parking_name, parking_type, 3000.0),
            ("Zzyborough District Council", "parking_ticket", 400.0),
        ], **extra), detected_representatives=set())

    def test_unmatched_private_pcn_gets_an_explicit_unknown_position(self):
        result = self._assess()
        [pos] = _positions(result, "PCN-NO-COUNCIL-RULE")
        self.assertEqual(pos["creditor_name"], "Parkingeye Limited")
        self.assertEqual(pos["effective_status"], "UNKNOWN")
        self.assertEqual(pos["representative"], "NONE")
        self.assertEqual(pos["_creditor_idx"], 2)
        self.assertEqual(pos["debt_type_normalised"], "pcn")
        self.assertNotIn("Parkingeye Limited", [cp["creditor_name"] for cp in result["council_positions"]])

    def test_parking_name_is_not_matched_to_an_unrelated_creditor(self):
        # The resolver would substring-match "Link Parking Ltd" to the LINK row
        # (a WILL_CONSIDER, i.e. a YES vote).
        result = self._assess(parking_name="Link Parking Ltd")
        [pos] = _positions(result, "PCN-NO-COUNCIL-RULE")
        self.assertEqual((pos["creditor_name"], pos["effective_status"]), ("Link Parking Ltd", "UNKNOWN"))
        self.assertNotIn("LINK", [p["creditor_name"] for p in result["creditor_positions"]])

    def test_matched_council_pcn_keeps_its_council_position(self):
        result = self._assess()
        [cp] = [cp for cp in result["council_positions"] if cp["council_name"] == "Zzyborough District Council"]
        self.assertEqual(cp["effective_status"], "WILL_CONSIDER")
        self.assertNotIn("Zzyborough District Council", [p["creditor_name"] for p in result["creditor_positions"]])

    def test_tig17_rejects_the_council_but_not_the_unmatched_pcn(self):
        # Council holds > 25% so TIG-17 fires with deductions active.
        result = assess_case(_payload([
            ("Zzyborough District Council", "council_tax", 4000.0),
            ("Parkingeye Limited", "parking_ticket", 1000.0),
        ], income_deductions_active=True), detected_representatives=set())
        [cp] = result["council_positions"]
        self.assertEqual(cp["effective_status"], "REJECT")
        [pos] = _positions(result, "PCN-NO-COUNCIL-RULE")
        self.assertEqual(pos["effective_status"], "UNKNOWN")

    def test_an_unmatched_pcn_alone_does_not_fire_tig17(self):
        result = assess_case(_payload([
            ("Barclaycard", "credit_card", 1000.0),
            ("Parkingeye Limited", "parking_ticket", 4000.0),
        ], income_deductions_active=True), detected_representatives=set())
        self.assertNotIn("TIG-17", [r.rule_id for r in result["flags"] + result["hard_blocks"]])

    def test_debt_stays_in_the_total_and_counts_as_unknown_debt(self):
        ma = self._assess()["majority_analysis"]
        self.assertEqual(float(ma["total_debt"]), 10400.0)
        self.assertEqual(float(ma["unknown_debt"]), 3000.0)
        self.assertEqual([u["name"] for u in ma["unknown_creditors"]], ["Parkingeye Limited"])

    def test_outcome_matches_the_same_debt_as_an_unidentified_creditor(self):
        pcn, other = self._assess(), self._assess(parking_type="other")
        self.assertEqual(pcn["majority_analysis"], other["majority_analysis"])
        self.assertEqual(pcn["dividend_analysis"], other["dividend_analysis"])
        self.assertEqual(pcn["overall"], other["overall"])
        self.assertEqual(pcn["recommended_solution"], other["recommended_solution"])
        self.assertEqual(sorted(r.rule_id for r in pcn["flags"]), sorted(r.rule_id for r in other["flags"]))
        self.assertEqual(sorted(r.rule_id for r in pcn["hard_blocks"]), sorted(r.rule_id for r in other["hard_blocks"]))

    def test_reconcile_shows_the_engine_position_without_a_backfill(self):
        creditors = [{"name": "Parkingeye Limited", "creditor_type": "parking_ticket", "balance": 3000.0}]
        result = assess_case(_payload([(c["name"], c["creditor_type"], c["balance"]) for c in creditors]),
                             detected_representatives=set())
        rows = [p for p in reconcile_creditor_positions(result, creditors) if p["creditor_name"] == "Parkingeye Limited"]
        self.assertEqual([p["rule_ids"] for p in rows], [["PCN-NO-COUNCIL-RULE"]])

    def test_non_parking_council_type_debts_are_untouched(self):
        # Council tax / housing benefit without a rule keep their old path
        # (county routing may still position council tax).
        case = _parse_case(_payload([("Nowhere Borough Council", "council_tax", 500.0),
                                     ("Nowhere Borough Council", "housing benefit", 500.0)]))
        case.update({"aryza_reference": "T", "client_name": "T"})
        self.assertEqual(_check_creditor_individual(case), [])


class AliasChainTests(SimpleTestCase):

    def test_monzo_family_ends_at_monzo_bank_in_one_hop(self):
        for name in ("Monzo", "MONZO", "Monzo Bank", "Monzo Bank Limited", "Starling", "Monozo Bank"):
            with self.subTest(name=name):
                once = _alias_hop(name)
                self.assertEqual(_alias_hop(once), once, "a second hop must not move the name")
        self.assertEqual(CREDITOR_ALIAS_MAP["monzo"], "Monzo Bank")
        self.assertNotIn("monzo bank", CREDITOR_ALIAS_MAP)

    def test_home_retail_aliases_point_straight_at_argos_card_services(self):
        for name in ("Home Retail Group", "HOME RETAIL GROUP CARD SERVICES", "Home Retail Group Card Services Limited"):
            with self.subTest(name=name):
                self.assertEqual(_alias_hop(name), "Argos Card Services")
                self.assertEqual(_alias_hop(_alias_hop(name)), "Argos Card Services")

    def test_only_the_known_chains_remain(self):
        # The other chains change outcomes (e.g. Barclays Partner Finance WATCH
        # vs TIX) and are left for a business decision.
        chains = sorted(k for k, v in CREDITOR_ALIAS_MAP.items()
                        if CREDITOR_ALIAS_MAP.get(normalise_creditor_name(v), v).lower() != v.lower())
        self.assertEqual(chains, ["barclays partner finance", "creation finance"])


class AliasChainResolutionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        CreditorCriteria.objects.all().delete()
        for name in ("Monzo Bank", "Home Retail Group", "Argos Card Services", "Monzo"):
            CreditorCriteria.objects.create(creditor_name=name, representative="WATCH" if "Monzo" in name else "TIX",
                                            status="ACCEPT", is_active=True)

    def _engine(self, name):
        case = _parse_case({"creditors": [{"creditor_name": name, "balance": 800}]})
        case.update({"aryza_reference": "T", "client_name": "T"})
        return _check_creditor_individual(case)[0]["resolved_canonical_name"]

    def test_every_call_path_agrees(self):
        expected = {
            "Monzo": "Monzo Bank", "Monzo Bank": "Monzo Bank", "Monzo Bank Limited": "Monzo Bank",
            "Monozo Bank": "Monzo Bank",
            "Home Retail Group": "Argos Card Services",
            "HOME RETAIL GROUP CARD SERVICES": "Argos Card Services",
            "Home Retail Group Card Services Limited": "Argos Card Services",
        }
        for name, row in expected.items():
            with self.subTest(name=name):
                self.assertEqual(self._engine(name), row)  # engine: alias hop + resolver
                self.assertEqual(get_creditor_by_trading_name(name).creditor_name, row)  # raw-name rules
                self.assertEqual(self._engine(_alias_hop(name)), row)  # API view hop first
