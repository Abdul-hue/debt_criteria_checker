"""
Regression tests for get_creditor_by_trading_name()'s matching strategy.

Context: a session-long investigation (case 394638, Michael Chatterton) found
that WATCH/TIX/EVOLVE representative detection was silently skipped for real
creditors whose Aryza/credit-report name didn't align with the shape of
their CreditorCriteria.creditor_name row:

  - "BRAND - IVA" / "PREFIX - BRAND - SUFFIX" rows (the WATCH/TIX seed
    convention, e.g. "Pulse - IVA", "HBOS - Halifax - IVA") were structurally
    unreachable by the old single-direction whole-string substring check.
  - Punctuation-only variants ("Marks & Spencer" vs "Marks and Spencer",
    "Sainsburys Bank" vs "Sainsbury's Bank Plc") needed a hand-written alias
    each time, one incident at a time.
  - A single broken alias (Klarna) can silently orphan every case with that
    creditor, DB-wide, until someone notices by accident.

These tests lock in the two generic matching passes added to close that gap
(cosmetic-normalised exact match, segment substring) and guard against the
adversarial failure mode they're riskiest for: a generic pass incorrectly
merging two genuinely different companies (e.g. real-world "Capital On Tap"
vs "Capital One") into the same representative.

IMPORTANT: all creditor names used here are deliberately FICTIONAL and do
not appear anywhere in the real CREDITOR_ALIAS_MAP (helpers.py) or the seeded
CreditorCriteria data. get_creditor_by_trading_name consults that map
unconditionally (it's a module-level global, not test-scoped) — reusing a
real creditor name here (e.g. "Pulse", "Halifax") would make a test pass via
the pre-existing hand-written alias rather than the generic pass it's meant
to exercise, silently defeating the point of the test.
"""

from django.test import TestCase

from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import CreditorCriteria


def _seed(creditor_name, representative="NONE", trading_names=None, is_active=True):
    return CreditorCriteria.objects.create(
        creditor_name=creditor_name,
        representative=representative,
        trading_names=trading_names or [],
        is_active=is_active,
    )


class SegmentSubstringMatchingTests(TestCase):
    """Step 6: 'BRAND - SUFFIX' shaped DB rows must match on the brand segment
    alone, without a hand-written alias, generalising the Pulse/Halifax fix."""

    def test_brand_dash_suffix_row_matches_bare_brand_name(self):
        _seed("Zeltara - IVA", representative="WATCH")
        row = get_creditor_by_trading_name("Zeltara (Trading Name)")
        self.assertEqual(row.representative, "WATCH")

    def test_prefix_dash_brand_dash_suffix_row_matches_bare_brand_name(self):
        _seed("Vexogroup - Bramholt - IVA", representative="WATCH")
        row = get_creditor_by_trading_name("Bramholt Personal Loan")
        self.assertEqual(row.representative, "WATCH")

    def test_multi_word_suffix_segment_is_not_treated_as_a_brand(self):
        # "IVA or BKY" must never be usable as a standalone match target —
        # every word in it is a pure suffix/connector word.
        _seed("Trellis - IVA or BKY", representative="WATCH")
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("IVA or BKY Consulting Group")

    def test_higher_priority_whole_string_substring_still_wins(self):
        # If a whole-string substring match (step 4) exists, it must be
        # returned even when a different row would also satisfy the lower-
        # priority segment pass — priority order must not depend on row
        # iteration order.
        _seed("Corvane", representative="TIX")
        _seed("Corvane Trading Co - IVA", representative="WATCH")
        row = get_creditor_by_trading_name("Corvane Ltd (Retail)")
        self.assertEqual(row.creditor_name, "Corvane")
        self.assertEqual(row.representative, "TIX")


class CosmeticNormalisationMatchingTests(TestCase):
    """Step 5: punctuation-only variants must match without an alias."""

    def test_ampersand_vs_and(self):
        _seed("Marlowe & Finch", representative="TIX")
        row = get_creditor_by_trading_name("Marlowe and Finch")
        self.assertEqual(row.representative, "TIX")

    def test_apostrophe_variants(self):
        _seed("Kettlewells Bank", representative="TIX")
        row = get_creditor_by_trading_name("Kettlewell's Bank Plc")
        self.assertEqual(row.representative, "TIX")

    def test_bracketed_aside_in_the_middle_of_the_name(self):
        # A legal-entity name with a bracketed aside mid-string (PayPal's
        # real-world "(Europe)" is the motivating case) — the end-anchored
        # suffix stripper in normalise_creditor_name never reaches it, so
        # this must be caught by cosmetic normalisation rather than the
        # alias map.
        _seed("Osprey Systems Sarl", representative="TIX")
        row = get_creditor_by_trading_name("Osprey (Europe) Systems Sarl")
        self.assertEqual(row.representative, "TIX")


class MatcherFalsePositiveGuardTests(TestCase):
    """The generic passes must not merge genuinely distinct companies just
    because they share a generic word or short substring."""

    def test_distinct_companies_sharing_a_generic_suffix_word_stay_separate(self):
        _seed("Meridian Financial Services Ltd", representative="TIX")
        # A genuinely different lender that happens to share the generic
        # phrase "Financial Services" must NOT resolve to Meridian.
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("Harlequin Financial Services Ltd")

    def test_short_generic_segment_is_filtered_out(self):
        # A DB row like "X - Bank - IVA" must not let the standalone segment
        # "Bank" match against an unrelated input just because it contains
        # the word "bank" somewhere.
        _seed("Zempest - Bank - IVA", representative="WATCH")
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("Some Unrelated Community Bank Account")

    def test_inactive_row_is_never_matched(self):
        _seed("Retired Creditor - IVA", representative="WATCH", is_active=False)
        with self.assertRaises(CreditorCriteria.DoesNotExist):
            get_creditor_by_trading_name("Retired Creditor")


class ExistingStrategiesUnaffectedTests(TestCase):
    """Steps 1-4 (alias map, exact match, trading_names, whole-string
    substring) must resolve exactly as before — the new steps are additive
    fallbacks only, never consulted when an earlier step already matched."""

    def test_exact_match_still_wins_over_generic_passes(self):
        _seed("Fenwick Capital", representative="TIX")
        row = get_creditor_by_trading_name("Fenwick Capital")
        self.assertEqual(row.creditor_name, "Fenwick Capital")

    def test_trading_names_match_unaffected(self):
        _seed("Bellcross Finance", representative="NONE", trading_names=["Bellcrossfinance"])
        row = get_creditor_by_trading_name("Bellcrossfinance")
        self.assertEqual(row.creditor_name, "Bellcross Finance")

    def test_whole_string_substring_unaffected(self):
        _seed("Ashgrove", representative="EVOLVE")
        row = get_creditor_by_trading_name("Ashgrove PLC")
        self.assertEqual(row.representative, "EVOLVE")
