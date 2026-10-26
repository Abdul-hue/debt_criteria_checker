"""
Phase 3C hyphen parsing (2026-10-21).

_db_name_segments split CreditorCriteria names on EVERY hyphen, so "The
Co-operative Bank" gave the segment "the co" and step 6 matched "The
Co-Operative Credit Union" to the Co-operative Bank rows. A separator hyphen
is now one with whitespace on at least one side: "A - B" and the seed
convention "Ltd- IVA" still split, "Co-operative" does not.
"""

from django.test import SimpleTestCase, TestCase

from debt_app.helpers import _db_name_segments, _get_creditor_by_trading_name_uncached
from debt_app.models import CreditorCriteria


class SegmentParsingTests(SimpleTestCase):

    def test_hyphenated_words_stay_whole(self):
        self.assertEqual(_db_name_segments("Co-operative"), ["co-operative"])
        self.assertEqual(_db_name_segments("Co-operative Bank"), ["co-operative bank"])
        self.assertEqual(_db_name_segments("The Co-operative Credit Union"), ["the co-operative credit union"])
        self.assertEqual(_db_name_segments("The Co-operative Bank - IVA"), ["the co-operative bank"])
        self.assertEqual(_db_name_segments("Co-op Credit Union"), ["co-op credit union"])

    def test_separator_hyphens_still_split(self):
        self.assertEqual(_db_name_segments("HBOS - Halifax - IVA"), ["hbos", "halifax"])
        self.assertEqual(_db_name_segments("Pulse - IVA"), ["pulse"])
        self.assertEqual(_db_name_segments("Zopa - IVA or BKY"), ["zopa"])
        self.assertEqual(_db_name_segments("Somelender - Bank - IVA"), ["somelender"])

    def test_hyphen_with_space_on_one_side_still_splits(self):
        self.assertEqual(_db_name_segments("Arrow Global Massey Ltd- IVA or BKY"), ["arrow global massey ltd"])
        self.assertEqual(_db_name_segments("IDEM / Paragon / Moorgate- TD"), ["idem / paragon / moorgate"])
        self.assertEqual(_db_name_segments("THIS BANK LTD - PREVIOUSLY -JN Bank Limited & Jamaica Bank"),
                         ["this bank ltd", "previously", "jn bank limited & jamaica bank"])


class CooperativeResolutionTests(TestCase):
    # The four Co-operative rows of the scratch Criteria DB, in id order.
    ROWS = (
        ("Co-operative Bank", "NONE", "ACCEPT"),
        ("The Co-operative Bank", "NONE", "ACCEPT"),
        ("The Co-operative Bank - IVA", "WATCH", "ACCEPT"),
        ("The Co-operative Bank - TD", "WATCH", "ACCEPT"),
        ("Arrow Global Massey Ltd- IVA or BKY", "WATCH", "ACCEPT"),
    )

    @classmethod
    def setUpTestData(cls):
        CreditorCriteria.objects.all().delete()
        for name, rep, status in cls.ROWS:
            CreditorCriteria.objects.create(creditor_name=name, representative=rep, status=status, is_active=True)

    def test_cooperative_credit_union_no_longer_matches_the_bank(self):
        for name in ("The Co-Operative Credit Union", "The Co-Operative Credit Union c/o C&L Collections"):
            with self.subTest(name=name), self.assertRaises(CreditorCriteria.DoesNotExist):
                _get_creditor_by_trading_name_uncached(name)

    def test_cooperative_bank_names_still_resolve(self):
        # Step 4 (whole DB name inside the input, lowest id) - unaffected by segments.
        self.assertEqual(_get_creditor_by_trading_name_uncached("The Co-operative Bank PLC").creditor_name,
                         "Co-operative Bank")
        # Step 1: alias 'co-operative bank' -> 'The Co-operative Bank'.
        self.assertEqual(_get_creditor_by_trading_name_uncached("Co-operative Bank").creditor_name,
                         "The Co-operative Bank")

    def test_ltd_hyphen_iva_row_is_still_reached_by_its_brand_segment(self):
        self.assertEqual(_get_creditor_by_trading_name_uncached("Arrow Global Massey Ltd (Account 7)").creditor_name,
                         "Arrow Global Massey Ltd- IVA or BKY")
