"""
Phase 1 regression tests — CCJ / AOE rejection for general creditors.

Covers:
  - extract_public_information() across Experian (detail + summary) and Aryza
    ("CCJs and Insolvencies") report formats.
  - _check_creditor_individual() applying reject_if_ccj / reject_if_aoe.

Admiral Loans and Advantage Finance are seeded with both flags by migration
0053, so they are present in the test database.
"""

from django.test import TestCase

from debt_app.credit_report_extractor import extract_public_information
from debt_app.criteria_engine import _check_creditor_individual
from debt_app.models import CreditorCriteria


EXPERIAN_WITH_CCJ = """
Public Information
• Number: 1
• CCJ's Unsetteled: No Trace
• Total Amount CCJ: 557
• IVA or Bankruptcy Detected: N
• Debt Management: N
• Latest: 29-12-2021
Applicant - Current Address
• Date: 29-12-2021
• Type: Judgement - Judgement
• Amount: 557.0
• Settled: N
• Source: REGISTRY TRUST LTD
"""

EXPERIAN_NO_CCJ = """
Public Information
• Number: 0
• CCJ's Unsetteled: No Item found
• Total Amount CCJ:
• IVA or Bankruptcy Detected: N
• Debt Management: N
No Public Information found.
"""

ARYZA_NO_CCJ = """
Creditors Owed: 9 Accounts in Default: 1
Mortgages: 1 Settled Accounts: 0
Mortgage Balance: CCJs and Insolvencies: 0
"""

ARYZA_WITH_CCJ = """
Creditors Owed: 9 Accounts in Default: 1
Mortgage Balance: CCJs and Insolvencies: 2
"""


class ExtractPublicInformationTests(TestCase):
    def test_experian_detail_record_detected(self):
        info = extract_public_information(EXPERIAN_WITH_CCJ)
        self.assertTrue(info["has_ccj"])
        self.assertEqual(info["ccj_count"], 1)
        self.assertEqual(info["ccj_total_pence"], 55700)
        self.assertEqual(info["ccjs"][0]["settled"], False)
        self.assertEqual(info["ccjs"][0]["date"], "29-12-2021")

    def test_experian_no_ccj(self):
        info = extract_public_information(EXPERIAN_NO_CCJ)
        self.assertFalse(info["has_ccj"])
        self.assertEqual(info["ccj_count"], 0)

    def test_aryza_zero_count(self):
        self.assertFalse(extract_public_information(ARYZA_NO_CCJ)["has_ccj"])

    def test_aryza_nonzero_count(self):
        info = extract_public_information(ARYZA_WITH_CCJ)
        self.assertTrue(info["has_ccj"])
        self.assertEqual(info["ccj_count"], 2)

    def test_empty_text(self):
        self.assertFalse(extract_public_information("")["has_ccj"])


def _case(creditor_name, *, has_ccj=False, aoe=False):
    return {
        "creditors": [{
            "name": creditor_name,
            "original_name": creditor_name,
            "debt_type_normalised": "personal_loan",
            "creditor_type": "personal_loan",
            "crm_balance": 5000.0,
            "balance": 5000.0,
        }],
        "has_ccj": has_ccj,
        "aoe_in_place": aoe,
        "previous_iva": False,
        "has_property": False,
        "total_debt": 5000.0,
        "aryza_reference": "TEST",
        "client_name": "Test Client",
    }


def _position(case):
    return _check_creditor_individual(case)[0]


class CreditorCcjAoeRejectTests(TestCase):
    """Engine logic for reject_if_ccj / reject_if_aoe.

    The base creditor rows are seeded into the production DB by a management
    command (not a migration), so the migration-built test DB will not contain
    them. These rows are therefore created here directly to test the engine
    branch in isolation. The migration-applied flags on the real rows are
    verified separately against the live DB.
    """

    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Admiral Loans", representative="NONE", status="WILL_CONSIDER",
            reject_if_ccj=True, reject_if_aoe=True, is_active=True,
        )
        CreditorCriteria.objects.create(
            creditor_name="Advantage Finance", representative="NONE", status="WILL_CONSIDER",
            reject_if_ccj=True, reject_if_aoe=True, is_active=True,
        )
        CreditorCriteria.objects.create(
            creditor_name="Clean Lender", representative="NONE", status="WILL_CONSIDER",
            reject_if_ccj=False, reject_if_aoe=False, is_active=True,
        )

    def test_admiral_rejects_on_ccj(self):
        p = _position(_case("Admiral Loans", has_ccj=True))
        self.assertEqual(p["effective_status"], "REJECT")
        self.assertIn("CREDITOR-CCJ-REJECT", [f["code"] for f in p["findings"]])

    def test_admiral_rejects_on_aoe(self):
        p = _position(_case("Admiral Loans", aoe=True))
        self.assertEqual(p["effective_status"], "REJECT")
        self.assertIn("CREDITOR-AOE-REJECT", [f["code"] for f in p["findings"]])

    def test_admiral_will_consider_when_clean(self):
        p = _position(_case("Admiral Loans"))
        self.assertNotEqual(p["effective_status"], "REJECT")

    def test_advantage_rejects_on_ccj(self):
        p = _position(_case("Advantage Finance", has_ccj=True))
        self.assertEqual(p["effective_status"], "REJECT")

    def test_unflagged_creditor_not_rejected_on_ccj(self):
        # A creditor without reject_if_ccj must not be rejected just because a CCJ exists.
        p = _position(_case("Clean Lender", has_ccj=True))
        self.assertNotIn("CREDITOR-CCJ-REJECT", [f["code"] for f in p.get("findings", [])])
        self.assertNotEqual(p["effective_status"], "REJECT")


# ---------------------------------------------------------------------------
# Phase 2 — structural engine fixes
# ---------------------------------------------------------------------------

from debt_app.criteria_engine import (  # noqa: E402
    _count_qualifying_lenders, _evolve_02, _watch_22_5, _phase4_county_council,
)
from debt_app.models import CouncilRule, CountyCouncilRouting  # noqa: E402


def _asset_case(name, *, still_has_asset):
    return {
        "creditors": [{
            "name": name, "original_name": name,
            "debt_type_normalised": "hire_purchase_unsecured",
            "creditor_type": "personal_loan",
            "crm_balance": 5000.0, "balance": 5000.0,
            "client_still_has_asset_in_possession": still_has_asset,
        }],
        "has_ccj": False, "aoe_in_place": False, "previous_iva": False,
        "has_property": False, "total_debt": 5000.0,
        "aryza_reference": "TEST", "client_name": "Test Client",
    }


class AssetNotReturnedRejectTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Asset Lender", representative="NONE", status="WILL_CONSIDER",
            reject_if_client_still_has_asset=True, is_active=True,
        )

    def test_rejects_when_asset_still_held(self):
        p = _check_creditor_individual(_asset_case("Asset Lender", still_has_asset=True))[0]
        self.assertEqual(p["effective_status"], "REJECT")
        self.assertIn("CREDITOR-ASSET-NOT-RETURNED-REJECT", [f["code"] for f in p["findings"]])

    def test_not_rejected_when_asset_returned(self):
        p = _check_creditor_individual(_asset_case("Asset Lender", still_has_asset=False))[0]
        self.assertNotEqual(p["effective_status"], "REJECT")


class BankingGroupLenderCountTests(TestCase):
    def test_two_brands_one_bank_count_as_one(self):
        creditors = [
            {"name": "Halifax", "balance": 1000.0, "parent_group": "Lloyds Banking Group"},
            {"name": "Bank of Scotland", "balance": 1000.0, "parent_group": "Lloyds Banking Group"},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 1)
        self.assertTrue(_evolve_02({"creditors": creditors}).triggered)
        self.assertTrue(_watch_22_5({"creditors": creditors}).triggered)

    def test_two_separate_lenders_pass(self):
        creditors = [
            {"name": "Halifax", "balance": 1000.0, "parent_group": "Lloyds Banking Group"},
            {"name": "Barclays", "balance": 1000.0, "parent_group": "Barclays Group"},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 2)
        self.assertFalse(_evolve_02({"creditors": creditors}).triggered)

    def test_below_threshold_ignored(self):
        creditors = [
            {"name": "A", "balance": 100.0},
            {"name": "B", "balance": 2000.0},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 1)

    def test_no_parent_group_falls_back_to_name(self):
        creditors = [
            {"name": "Lender One", "balance": 1000.0},
            {"name": "Lender Two", "balance": 1000.0},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 2)

    def test_multiple_small_entries_one_lender_sum_above_threshold(self):
        # Two £400 accounts with ONE lender total £800 (> £500) → that lender
        # qualifies, even though no single account exceeds £500.
        creditors = [
            {"name": "NatWest", "balance": 400.0, "parent_group": "NatWest Group"},
            {"name": "NatWest Credit Card", "balance": 400.0, "parent_group": "NatWest Group"},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 1)

    def test_two_lenders_each_summed_above_threshold(self):
        # NatWest £800 (2x£400) and Barclays £600 → two qualifying lenders → pass.
        creditors = [
            {"name": "NatWest", "balance": 400.0, "parent_group": "NatWest Group"},
            {"name": "NatWest Card", "balance": 400.0, "parent_group": "NatWest Group"},
            {"name": "Barclays", "balance": 600.0, "parent_group": "Barclays Group"},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 2)
        self.assertFalse(_evolve_02({"creditors": creditors}).triggered)

    def test_small_fragments_below_threshold_still_excluded(self):
        # One lender with 2x£200 = £400 total (< £500) does not qualify.
        creditors = [
            {"name": "Tiny", "balance": 200.0, "parent_group": "Tiny Group"},
            {"name": "Tiny Card", "balance": 200.0, "parent_group": "Tiny Group"},
        ]
        self.assertEqual(_count_qualifying_lenders(creditors, 500.0), 0)


def _loan_age_case(name, *, age_months):
    cr = {
        "name": name, "original_name": name,
        "debt_type_normalised": "personal_loan", "creditor_type": "personal_loan",
        "crm_balance": 5000.0, "balance": 5000.0,
    }
    if age_months is not None:
        cr["account_age_months"] = age_months
    return {
        "creditors": [cr],
        "has_ccj": False, "aoe_in_place": False, "previous_iva": False,
        "has_property": False, "total_debt": 5000.0,
        "aryza_reference": "TEST", "client_name": "Test Client",
    }


class MinLoanAgeTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Recent Lender", representative="NONE", status="WILL_CONSIDER",
            account_age_months=6, is_active=True,
        )

    def test_verified_too_recent_rejects(self):
        p = _check_creditor_individual(_loan_age_case("Recent Lender", age_months=3))[0]
        self.assertEqual(p["effective_status"], "REJECT")
        self.assertIn("CREDITOR-LOAN-TOO-RECENT-REJECT", [f["code"] for f in p["findings"]])

    def test_verified_old_enough_not_rejected(self):
        p = _check_creditor_individual(_loan_age_case("Recent Lender", age_months=9))[0]
        self.assertNotEqual(p["effective_status"], "REJECT")

    def test_at_minimum_not_rejected(self):
        # Exactly the minimum (6) is acceptable — only strictly younger rejects.
        p = _check_creditor_individual(_loan_age_case("Recent Lender", age_months=6))[0]
        self.assertNotEqual(p["effective_status"], "REJECT")

    def test_unverified_age_flags_not_rejects(self):
        # No credit-report match → age unknown → FLAG, never REJECT (must not treat
        # unknown as 0 months old).
        p = _check_creditor_individual(_loan_age_case("Recent Lender", age_months=None))[0]
        self.assertNotEqual(p["effective_status"], "REJECT")
        self.assertIn("CREDITOR-LOAN-AGE-UNVERIFIED", [f["code"] for f in p["findings"]])

    def test_no_minimum_configured_no_finding(self):
        CreditorCriteria.objects.create(
            creditor_name="Any Age Lender", representative="NONE", status="WILL_CONSIDER",
            is_active=True,
        )
        p = _check_creditor_individual(_loan_age_case("Any Age Lender", age_months=1))[0]
        codes = [f["code"] for f in p.get("findings", [])]
        self.assertNotIn("CREDITOR-LOAN-TOO-RECENT-REJECT", codes)
        self.assertNotIn("CREDITOR-LOAN-AGE-UNVERIFIED", codes)


class CountyCouncilRoutingTests(TestCase):
    """County routing must resolve abbreviated district names via _match_council_rule."""

    def setUp(self):
        # Distinctive names that won't collide with migration-seeded routing rows
        # or fuzzy-match any real CouncilRule.
        CouncilRule.objects.create(council_name="Zzyborough District Council", status="ACCEPT")
        CountyCouncilRouting.objects.create(
            county_name="Zzyshire", district_name="Zzyborough DC",
        )

    def test_abbreviated_district_resolves_to_rule(self):
        c = {
            "creditors": [{
                "name": "Zzyshire", "debt_type_normalised": "council_tax",
                "crm_balance": 1000.0, "balance": 1000.0,
            }],
            "has_partner_on_case": False,
        }
        results, positions = _phase4_county_council(c)
        # The abbreviated "Zzyborough DC" must resolve to the full council rule
        # (exact iexact match would have failed → 0 positions).
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["creditor_name"], "Zzyborough District Council")
        self.assertFalse(any(r.rule_id == "COUNTY-COUNCIL-NO-DISTRICT-RULE" for r in results))


class CountyCouncilFkPinTests(TestCase):
    """An explicit council_rule FK must win over (and override) name resolution.

    This is the mechanism Phase 4 uses to (a) avoid wrong fuzzy matches
    (Newcastle Borough -> Newcastle-upon-Tyne) and (b) collapse reorganised
    unitaries (all North Yorkshire districts -> North Yorkshire Council).
    """

    def setUp(self):
        # A name-resolvable decoy the district name WOULD fuzzy-match to...
        CouncilRule.objects.create(council_name="Qq Borough Council", status="ACCEPT")
        # ...and the rule we actually want pinned (a different decision).
        self.pinned = CouncilRule.objects.create(
            council_name="Qq Unitary Authority", status="DO_NOT_VOTE"
        )
        CountyCouncilRouting.objects.create(
            county_name="Qqshire", district_name="Qq Borough",
            council_rule=self.pinned,
        )

    def _run(self):
        c = {
            "creditors": [{
                "name": "Qqshire", "debt_type_normalised": "council_tax",
                "crm_balance": 1000.0, "balance": 1000.0,
            }],
            "has_partner_on_case": False,
        }
        return _phase4_county_council(c)

    def test_fk_pin_overrides_name_resolution(self):
        results, positions = self._run()
        self.assertEqual(len(positions), 1)
        # Must be the PINNED unitary (DO_NOT_VOTE), not the name-matched
        # "Qq Borough Council" (ACCEPT).
        self.assertEqual(positions[0]["creditor_name"], "Qq Unitary Authority")
        self.assertEqual(positions[0]["effective_status"], "DO_NOT_VOTE")
        self.assertFalse(any(r.rule_id == "COUNTY-COUNCIL-NO-DISTRICT-RULE" for r in results))


class ApplyAliasPinsTests(TestCase):
    """apply_alias_pins must pin an EXISTING routing row's FK in place (never
    create a duplicate), be idempotent, and defer when the rule is absent."""

    def _routing_count(self, county, district):
        return CountyCouncilRouting.objects.filter(
            county_name=county, district_name=district
        ).count()

    def test_pins_existing_row_without_duplicating(self):
        from debt_app.county_routing_seed import apply_alias_pins, ALIAS_PINS
        # Use a real ALIAS_PINS entry; its routing row is seeded by migration
        # 0010 (so we get_or_create rather than create), and we supply the rule.
        county, district, tokens, status = ALIAS_PINS[0]  # Fenland DC -> REJECT
        CouncilRule.objects.create(council_name="Fenland District Council", status=status)
        CountyCouncilRouting.objects.get_or_create(county_name=county, district_name=district)
        self.assertEqual(self._routing_count(county, district), 1)

        apply_alias_pins(CouncilRule, CountyCouncilRouting, strict=False)
        # No duplicate row created; the existing one is now pinned.
        self.assertEqual(self._routing_count(county, district), 1)
        row = CountyCouncilRouting.objects.get(county_name=county, district_name=district)
        self.assertIsNotNone(row.council_rule)
        self.assertEqual(row.council_rule.status, status)

        # Idempotent: a second run changes nothing and still no duplicate.
        apply_alias_pins(CouncilRule, CountyCouncilRouting, strict=False)
        self.assertEqual(self._routing_count(county, district), 1)

    def test_strict_raises_on_ambiguous_match(self):
        from debt_app.county_routing_seed import _find_rule
        # Synthetic names so the result can't depend on migration-seeded rows.
        CouncilRule.objects.create(council_name="Zzytown Borough Council", status="DO_NOT_VOTE")
        CouncilRule.objects.create(council_name="Zzytown Borough Council Extra", status="ACCEPT")
        with self.assertRaises(RuntimeError):
            _find_rule(CouncilRule, ["Zzytown Borough Council"], "DO_NOT_VOTE",
                       "Zzytown DC", strict=True)


# ---------------------------------------------------------------------------
# Phase 5 — TIG-10 "debt level issue" caveat (formerly the phantom TIG-14)
# ---------------------------------------------------------------------------

from debt_app.criteria_engine import _tig_10  # noqa: E402


def _pod_case(creditors, total_debt):
    """Minimal case for TIG-10 (proof of debt). No evidence ledger → every
    creditor is unverified."""
    return {"creditors": creditors, "evidence_ledger": [], "total_debt": total_debt}


def _unverified(name, balance):
    # No linked_creditor → no evidence → treated as unverified by _tig_10.
    return {
        "name": name, "original_name": name,
        "debt_type_normalised": "personal_loan", "balance": balance,
    }


class Tig10VerbalDebtLevelTests(TestCase):
    """Sub-£1,000 unverified debts are normally a flag ('verbal OK'), but a
    hard block when they are load-bearing for the £6,000 minimum (TIG-01)."""

    def test_subk_unverified_flags_when_not_load_bearing(self):
        # Two sub-£1,000 unverified debts but total debt comfortably clears
        # £6,000 without them → verbal acceptable → flag, not block.
        r = _tig_10(_pod_case(
            [_unverified("Lender A", 500.0), _unverified("Lender B", 400.0)],
            total_debt=10000.0,
        ))
        self.assertEqual(r.severity, "flag")
        self.assertTrue(r.triggered)

    def test_subk_unverified_hard_blocks_when_load_bearing(self):
        # Same two sub-£1,000 debts, but without them the case falls below
        # £6,000 (provable 5500-900=4600) → verbal NOT acceptable → hard block.
        r = _tig_10(_pod_case(
            [_unverified("Lender A", 500.0), _unverified("Lender B", 400.0)],
            total_debt=5500.0,
        ))
        self.assertEqual(r.severity, "hard_block")
        self.assertIn("debt level issue", r.message.lower())

    def test_large_unverified_still_hard_blocks(self):
        # Existing behaviour unchanged: a >=£1,000 unverified debt hard-blocks
        # regardless of total debt level.
        r = _tig_10(_pod_case(
            [_unverified("Big Lender", 1500.0)],
            total_debt=50000.0,
        ))
        self.assertEqual(r.severity, "hard_block")
        self.assertNotIn("debt level issue", r.message.lower())


# ---------------------------------------------------------------------------
# Phase 6 — flag -> hard_block escalations (Excel "Reject" wording)
# ---------------------------------------------------------------------------

from debt_app.criteria_engine import _tig_21_5, _watch_22_7  # noqa: E402


class Tig21_5ArrearsRejectTests(TestCase):
    """Excel (Link Financial): 'REJECT if previous IVA failed due to arrears.'"""

    def _case(self, **over):
        base = {
            "link_is_creditor": True, "previous_iva": True,
            "previous_iva_failed_reason": None, "previous_iva_failed": False,
        }
        base.update(over)
        return base

    def test_arrears_hard_blocks(self):
        r = _tig_21_5(self._case(previous_iva_failed_reason="failed due to arrears"))
        self.assertEqual(r.severity, "hard_block")
        self.assertTrue(r.triggered)

    def test_fraud_still_hard_blocks(self):
        r = _tig_21_5(self._case(previous_iva_failed_reason="terminated for fraud"))
        self.assertEqual(r.severity, "hard_block")

    def test_not_link_creditor_passes(self):
        r = _tig_21_5(self._case(link_is_creditor=False))
        self.assertFalse(r.triggered)

    def test_completed_iva_passes(self):
        r = _tig_21_5(self._case(previous_iva_failed_reason="completed successfully"))
        self.assertFalse(r.triggered)


class Watch22_7OverThirteenTests(TestCase):
    """Excel (Watch Rejection Rules): children OVER 13 with no sustainability
    paragraph -> Reject. Boundary is strictly > 13. (Rule is disabled in the
    live DB; these test the function's logic, which is Excel-correct.)"""

    def _case(self, ages, sustainability=False):
        return {
            "children": [{"age": a} for a in ages],
            "sustainability_paragraph_present": sustainability,
        }

    def test_age_14_no_paragraph_hard_blocks(self):
        r = _watch_22_7(self._case([14]))
        self.assertEqual(r.severity, "hard_block")
        self.assertTrue(r.triggered)

    def test_age_13_does_not_trigger(self):
        # "over 13" => strictly > 13, so exactly 13 must NOT trigger.
        r = _watch_22_7(self._case([13]))
        self.assertFalse(r.triggered)

    def test_age_14_with_paragraph_passes(self):
        r = _watch_22_7(self._case([14], sustainability=True))
        self.assertFalse(r.triggered)

    def test_no_children_passes(self):
        r = _watch_22_7(self._case([]))
        self.assertFalse(r.triggered)


# ---------------------------------------------------------------------------
# Phase 6 — TIG-16 Excel-aligned (equity > liabilities, non-WPM, flag)
# ---------------------------------------------------------------------------

from debt_app.criteria_engine import _tig_16  # noqa: E402


class Tig16EquityLiabilitiesTests(TestCase):
    """TIG-16: flag when equity > total liabilities, NON-WPM only. Replaces the
    old flat-£5,000 hard block (which had no Excel basis and over-rejected)."""

    def _case(self, *, has_property=True, property_value=0.0, mortgage=0.0,
              total_debt=0.0, reps=None):
        return {
            "has_property": has_property,
            "property_value": property_value,
            "mortgage_balance": mortgage,
            "total_debt": total_debt,
            "detected_representatives": reps or set(),
        }

    def test_equity_exceeds_liabilities_flags(self):
        # Equity £40k (200k-160k) > £10k debt → flag.
        r = _tig_16(self._case(property_value=200000.0, mortgage=160000.0, total_debt=10000.0))
        self.assertEqual(r.severity, "flag")
        self.assertTrue(r.triggered)

    def test_equity_below_liabilities_passes(self):
        # THE FIX: equity £8k (>old £5k) but debt £30k → equity < liabilities →
        # PASS. The old rule hard-blocked this; it must not now.
        r = _tig_16(self._case(property_value=108000.0, mortgage=100000.0, total_debt=30000.0))
        self.assertFalse(r.triggered)

    def test_old_5000_threshold_no_longer_blocks(self):
        # Equity exactly £6k, debt £20k → previously hard_block (>£5k), now passes.
        r = _tig_16(self._case(property_value=106000.0, mortgage=100000.0, total_debt=20000.0))
        self.assertNotEqual(r.severity, "hard_block")
        self.assertFalse(r.triggered)

    def test_wpm_case_not_applicable(self):
        # WATCH detected → handled by WATCH-22.4, TIG-16 stands down even with
        # large equity.
        r = _tig_16(self._case(property_value=300000.0, mortgage=50000.0,
                               total_debt=10000.0, reps={"WATCH"}))
        self.assertFalse(r.triggered)

    def test_owns_property_no_valuation_flags(self):
        r = _tig_16(self._case(has_property=True, property_value=0.0, total_debt=10000.0))
        self.assertEqual(r.severity, "flag")

    def test_no_property_passes(self):
        r = _tig_16(self._case(has_property=False, total_debt=10000.0))
        self.assertFalse(r.triggered)

    def test_never_hard_blocks(self):
        # TIG-16 is now flag-only — must never emit a hard_block.
        for tot in (0.0, 5000.0, 50000.0):
            r = _tig_16(self._case(property_value=200000.0, mortgage=100000.0, total_debt=tot))
            self.assertNotEqual(r.severity, "hard_block")
