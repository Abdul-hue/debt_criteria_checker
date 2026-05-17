"""
Phase 2 Module 1 tests: Representative & Banking Group Resolution.

Covers:
  - EVERYDAY_LOANS representative choice added to model
  - detect_representatives() date-gating for Monzo (WATCH from 30/04/2024)
  - detect_representatives() date-gating for La Redoute (WATCH from 16/07/2025)
  - UKAR deregistration from TIX (30/06/2023)
  - assessment_date parsed from case_json and stored in _parse_case() output
  - Correct representative seeding: Barclays Bank → TIX, EVOLVE creditors,
    EVERYDAY_LOANS creditors
  - George Banco / Trust Two → EVERYDAY_LOANS representative
  - trading_name alias matching (e.g. "Monzo" matches "Monzo Bank")
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from debt_app.criteria_engine import (
    _MONZO_NAMES_LOWER,
    _MONZO_WATCH_DATE,
    _LA_REDOUTE_NAMES_LOWER,
    _LA_REDOUTE_WATCH_DATE,
    _DEREGISTERED_TIX,
    _parse_case,
    detect_representatives,
)
from debt_app.models import CreditorCriteria


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_creditor(name: str) -> dict:
    return {"creditor_name": name, "balance": 1000.0, "creditor_type": "credit_card"}


def _payload_with(*creditor_names: str, assessment_date: str | None = None) -> dict:
    payload = {
        "creditors": [_make_creditor(n) for n in creditor_names],
        "financial_summary": {"net_balance": 200},
    }
    if assessment_date:
        payload["assessment_date"] = assessment_date
    return payload


# ---------------------------------------------------------------------------
# Constant sanity checks (no DB required)
# ---------------------------------------------------------------------------

class TestPhase2Constants(SimpleTestCase):
    """Verify date-gating constants match the Excel exactly."""

    def test_monzo_watch_date_is_30_april_2024(self):
        # GENERAL CREDITOR row 219: "ARE WATCH now confirmed on 30/4/24!"
        self.assertEqual(_MONZO_WATCH_DATE, date(2024, 4, 30))

    def test_la_redoute_watch_date_is_16_july_2025(self):
        # GENERAL CREDITOR row 190: "NOW WPM 30.06.25 - VOTING FROM 16.07.25"
        self.assertEqual(_LA_REDOUTE_WATCH_DATE, date(2025, 7, 16))

    def test_monzo_names_frozenset_contains_aliases(self):
        self.assertIn("monzo", _MONZO_NAMES_LOWER)
        self.assertIn("monzo bank", _MONZO_NAMES_LOWER)

    def test_la_redoute_names_frozenset_contains_aliases(self):
        self.assertIn("la redoute", _LA_REDOUTE_NAMES_LOWER)
        self.assertIn("lr uk", _LA_REDOUTE_NAMES_LOWER)

    def test_deregistered_tix_contains_four_creditors(self):
        # TIX Criteria row 14: UKAR, Whistletree, Computershare, Landmark
        for name in ("ukar", "whistletree", "computershare", "landmark"):
            self.assertIn(name, _DEREGISTERED_TIX)


# ---------------------------------------------------------------------------
# assessment_date parsing in _parse_case()
# ---------------------------------------------------------------------------

class TestAssessmentDateParsing(SimpleTestCase):
    """assessment_date is read from case_json and stored in the parsed dict."""

    def test_iso_string_parsed_correctly(self):
        payload = {"assessment_date": "2024-03-01", "financial_summary": {}}
        c = _parse_case(payload)
        self.assertEqual(c["assessment_date"], date(2024, 3, 1))

    def test_date_object_accepted(self):
        d = date(2023, 6, 15)
        payload = {"assessment_date": d, "financial_summary": {}}
        c = _parse_case(payload)
        self.assertEqual(c["assessment_date"], d)

    def test_missing_assessment_date_defaults_to_today(self):
        payload = {"financial_summary": {}}
        c = _parse_case(payload)
        self.assertEqual(c["assessment_date"], date.today())

    def test_invalid_string_defaults_to_today(self):
        payload = {"assessment_date": "not-a-date", "financial_summary": {}}
        c = _parse_case(payload)
        self.assertEqual(c["assessment_date"], date.today())


# ---------------------------------------------------------------------------
# EVERYDAY_LOANS representative choice on model
# ---------------------------------------------------------------------------

class TestEverydayLoansChoiceOnModel(SimpleTestCase):
    """EVERYDAY_LOANS must be a valid choice in CreditorCriteria.REPRESENTATIVE_CHOICES."""

    def test_everyday_loans_in_representative_choices(self):
        choice_values = [v for v, _ in CreditorCriteria.REPRESENTATIVE_CHOICES]
        self.assertIn("EVERYDAY_LOANS", choice_values)

    def test_max_length_accommodates_everyday_loans(self):
        # 'EVERYDAY_LOANS' is 14 chars; field must allow it
        field = CreditorCriteria._meta.get_field("representative")
        self.assertGreaterEqual(field.max_length, len("EVERYDAY_LOANS"))


# ---------------------------------------------------------------------------
# detect_representatives() date-gating — uses mocked DB
# ---------------------------------------------------------------------------

def _mock_criteria(name: str, rep: str, trading: list | None = None) -> MagicMock:
    """Create a mock CreditorCriteria instance."""
    m = MagicMock()
    m.creditor_name = name
    m.representative = rep
    m.trading_names = trading or []
    return m


class TestDetectRepresentativesDateGating(SimpleTestCase):
    """
    detect_representatives() must apply date-gated corrections without hitting the DB.
    We mock CreditorCriteria.objects.filter(...).
    """

    def _run_detect(self, creditor_names: list[str], mock_rows: list, assessment_date: date) -> set:
        """Helper: call detect_representatives() with mocked DB rows.

        detect_representatives() uses 'from debt_app.models import CreditorCriteria'
        as a local import, so we patch the model class on debt_app.models directly.
        """
        creditors = [_make_creditor(n) for n in creditor_names]
        qs_mock = MagicMock()
        qs_mock.filter.return_value = qs_mock
        qs_mock.exclude.return_value = qs_mock
        qs_mock.__iter__ = MagicMock(return_value=iter(mock_rows))
        mock_model = MagicMock()
        mock_model.objects = qs_mock
        with patch("debt_app.models.CreditorCriteria", mock_model):
            return detect_representatives(creditors, assessment_date=assessment_date)

    # --- Monzo date-gate ---

    def test_monzo_not_watch_before_30_april_2024(self):
        """Monzo should NOT trigger WATCH if assessment_date < 30/04/2024."""
        mock_rows = [_mock_criteria("Monzo Bank", "WATCH", ["Monzo"])]
        result = self._run_detect(
            ["Monzo"], mock_rows, assessment_date=date(2024, 4, 29)
        )
        self.assertNotIn("WATCH", result)

    def test_monzo_is_watch_on_30_april_2024(self):
        """Monzo SHOULD trigger WATCH on 30/04/2024 (the effective date)."""
        mock_rows = [_mock_criteria("Monzo Bank", "WATCH", ["Monzo"])]
        result = self._run_detect(
            ["Monzo"], mock_rows, assessment_date=date(2024, 4, 30)
        )
        self.assertIn("WATCH", result)

    def test_monzo_is_watch_after_30_april_2024(self):
        """Monzo SHOULD trigger WATCH after 30/04/2024."""
        mock_rows = [_mock_criteria("Monzo Bank", "WATCH", ["Monzo"])]
        result = self._run_detect(
            ["Monzo Bank"], mock_rows, assessment_date=date(2025, 1, 1)
        )
        self.assertIn("WATCH", result)

    def test_monzo_gate_does_not_remove_watch_if_other_watch_creditors_present(self):
        """If Monzo AND another WATCH creditor are in the case before 30/04/2024,
        WATCH should still be present (other creditor keeps it)."""
        mock_rows = [
            _mock_criteria("Monzo Bank", "WATCH", ["Monzo"]),
            _mock_criteria("Barclaycard", "WATCH", []),
        ]
        result = self._run_detect(
            ["Monzo", "Barclaycard"], mock_rows, assessment_date=date(2024, 4, 1)
        )
        self.assertIn("WATCH", result)

    # --- La Redoute date-gate ---

    def test_la_redoute_not_watch_before_16_july_2025(self):
        """La Redoute should NOT trigger WATCH if assessment_date < 16/07/2025."""
        mock_rows = [_mock_criteria("La Redoute", "WATCH", [])]
        result = self._run_detect(
            ["La Redoute"], mock_rows, assessment_date=date(2025, 7, 15)
        )
        self.assertNotIn("WATCH", result)

    def test_la_redoute_is_watch_on_16_july_2025(self):
        """La Redoute SHOULD trigger WATCH on 16/07/2025."""
        mock_rows = [_mock_criteria("La Redoute", "WATCH", [])]
        result = self._run_detect(
            ["La Redoute"], mock_rows, assessment_date=date(2025, 7, 16)
        )
        self.assertIn("WATCH", result)

    def test_la_redoute_alias_lr_uk_also_gated(self):
        """Trading name 'LR UK' should be subject to the same La Redoute gate."""
        mock_rows = [_mock_criteria("La Redoute", "WATCH", ["LR UK", "LR UK (Retail) Limited"])]
        result = self._run_detect(
            ["LR UK"], mock_rows, assessment_date=date(2025, 7, 15)
        )
        self.assertNotIn("WATCH", result)

    # --- UKAR / deregistered TIX ---

    def test_ukar_seeded_as_none_does_not_trigger_tix(self):
        """UKAR should have representative=NONE in the seed — returns no TIX."""
        mock_rows = [_mock_criteria("UKAR", "NONE", [])]
        # NONE is filtered out by the query's .exclude(representative="NONE")
        # so this mock row should never appear in the result
        result = self._run_detect(
            ["UKAR"], mock_rows, assessment_date=date(2024, 1, 1)
        )
        # NONE is excluded by DB query — rep_triggers will be empty for NONE
        self.assertNotIn("TIX", result)


# ---------------------------------------------------------------------------
# DB-backed integration tests (require Django test DB)
# ---------------------------------------------------------------------------

class TestSeedRepresentatives(TestCase):
    """
    After running the seed command, verify representative assignments.
    These tests seed data directly so they are self-contained.
    """

    @classmethod
    def setUpTestData(cls):
        # Seed a representative sample from the Excel
        rows = [
            # TIX — Which Representative sheet col A
            {"creditor_name": "Barclays Bank",      "representative": "TIX",
             "trading_names": ["Barclays", "Barclays Bank PLC"]},
            {"creditor_name": "Capital One",         "representative": "TIX",
             "trading_names": ["Capital One Credit Card"]},
            {"creditor_name": "Creation Consumer Finance", "representative": "TIX",
             "trading_names": ["Sygma Bank Limited", "Laser UK", "Creation"]},
            {"creditor_name": "HSBC",               "representative": "TIX",
             "trading_names": ["HSBC Bank", "HSBC UK"]},
            # WATCH — Which Representative sheet col C
            {"creditor_name": "Barclaycard",        "representative": "WATCH",
             "trading_names": ["Barclaycard Credit Card"]},
            {"creditor_name": "Lloyds Banking Group","representative": "WATCH",
             "trading_names": ["MBNA", "Halifax", "Blackhorse"]},
            {"creditor_name": "Monzo Bank",         "representative": "WATCH",
             "trading_names": ["Monzo"]},
            {"creditor_name": "La Redoute",         "representative": "WATCH",
             "trading_names": ["LR UK", "Redcats UK"]},
            {"creditor_name": "Thames Water",       "representative": "WATCH",
             "trading_names": []},
            {"creditor_name": "Tesco Bank",         "representative": "WATCH",
             "trading_names": ["Tesco Personal Finance"]},
            # EVOLVE — Which Representative sheet col E
            {"creditor_name": "NatWest Bank",       "representative": "EVOLVE",
             "trading_names": ["NatWest", "National Westminster Bank"]},
            {"creditor_name": "The Royal Bank of Scotland Plc", "representative": "EVOLVE",
             "trading_names": ["RBS", "Royal Bank of Scotland"]},
            {"creditor_name": "TSB Bank",           "representative": "EVOLVE",
             "trading_names": ["TSB"]},
            {"creditor_name": "Ulster Bank",        "representative": "EVOLVE",
             "trading_names": []},
            # EVERYDAY_LOANS — Which Representative sheet col G
            # Col G row 3: "GEORGE BANCO"; row 4: "TRUST II"
            {"creditor_name": "George Banco",       "representative": "EVERYDAY_LOANS",
             "trading_names": ["George Banco Ltd"]},
            {"creditor_name": "Trust Two",          "representative": "EVERYDAY_LOANS",
             "trading_names": ["Trust II", "Trust 2"]},
            # NONE — deregistered TIX (TIX Criteria row 14)
            {"creditor_name": "UKAR",               "representative": "NONE",
             "trading_names": ["UK Asset Resolution"]},
            {"creditor_name": "Whistletree",        "representative": "NONE", "trading_names": []},
        ]
        for row in rows:
            CreditorCriteria.objects.update_or_create(
                creditor_name=row["creditor_name"],
                defaults={
                    "representative": row["representative"],
                    "trading_names": row.get("trading_names", []),
                    "is_active": True,
                },
            )

    # --- TIX detection ---

    def test_barclays_bank_detects_tix(self):
        """Barclays Bank → TIX (col A row 5). Previously incorrectly WATCH in old seed."""
        result = detect_representatives([_make_creditor("Barclays Bank")])
        self.assertIn("TIX", result)
        self.assertNotIn("WATCH", result)

    def test_barclays_alias_detects_tix(self):
        """Trading name 'Barclays' should also match TIX via Barclays Bank."""
        result = detect_representatives([_make_creditor("Barclays")])
        self.assertIn("TIX", result)

    def test_creation_sygma_alias_detects_tix(self):
        """'Sygma Bank Limited' is a trading name of Creation Consumer Finance → TIX."""
        result = detect_representatives([_make_creditor("Sygma Bank Limited")])
        self.assertIn("TIX", result)

    def test_creation_laser_alias_detects_tix(self):
        """'Laser UK' is a trading name of Creation Consumer Finance → TIX."""
        result = detect_representatives([_make_creditor("Laser UK")])
        self.assertIn("TIX", result)

    # --- WATCH detection ---

    def test_barclaycard_detects_watch(self):
        result = detect_representatives([_make_creditor("Barclaycard")])
        self.assertIn("WATCH", result)
        self.assertNotIn("TIX", result)

    def test_mbna_via_lloyds_group_detects_watch(self):
        """MBNA is a trading name of Lloyds Banking Group → WATCH (col C row 143)."""
        result = detect_representatives([_make_creditor("MBNA")])
        self.assertIn("WATCH", result)

    def test_thames_water_detects_watch(self):
        """Thames Water → WATCH (GENERAL CREDITOR row 332: NOW VOTE THROUGH WPM 06/04)."""
        result = detect_representatives([_make_creditor("Thames Water")])
        self.assertIn("WATCH", result)

    def test_tesco_bank_detects_watch(self):
        """Tesco Bank → WATCH (Which Representative col C row 288)."""
        result = detect_representatives([_make_creditor("Tesco Bank")])
        self.assertIn("WATCH", result)

    def test_monzo_alias_detects_watch_with_default_date(self):
        """'Monzo' (trading name of Monzo Bank) → WATCH with default assessment date (today)."""
        result = detect_representatives([_make_creditor("Monzo")])
        self.assertIn("WATCH", result)

    # --- EVOLVE detection ---

    def test_natwest_detects_evolve(self):
        """NatWest → EVOLVE (col E row 5). 'NatWest' is a trading name of NatWest Bank."""
        result = detect_representatives([_make_creditor("NatWest")])
        self.assertIn("EVOLVE", result)
        self.assertNotIn("TIX", result)
        self.assertNotIn("WATCH", result)

    def test_rbs_alias_detects_evolve(self):
        """'RBS' (trading name of The Royal Bank of Scotland Plc) → EVOLVE (col E row 6)."""
        result = detect_representatives([_make_creditor("RBS")])
        self.assertIn("EVOLVE", result)

    def test_tsb_detects_evolve(self):
        """TSB (trading name of TSB Bank) → EVOLVE (col E row 7)."""
        result = detect_representatives([_make_creditor("TSB")])
        self.assertIn("EVOLVE", result)

    # --- EVERYDAY_LOANS detection ---

    def test_george_banco_detects_everyday_loans(self):
        """George Banco → EVERYDAY_LOANS (col G row 3).
        GENERAL CREDITOR row 150: 'REFER TO EVERYDAY LOANS'."""
        result = detect_representatives([_make_creditor("George Banco")])
        self.assertIn("EVERYDAY_LOANS", result)

    def test_trust_two_detects_everyday_loans(self):
        """Trust Two → EVERYDAY_LOANS (col G row 4).
        GENERAL CREDITOR row 325: 'REFER TO EVERYDAY LOANS'."""
        result = detect_representatives([_make_creditor("Trust Two")])
        self.assertIn("EVERYDAY_LOANS", result)

    def test_trust_ii_alias_detects_everyday_loans(self):
        """'Trust II' is a trading name of Trust Two → EVERYDAY_LOANS."""
        result = detect_representatives([_make_creditor("Trust II")])
        self.assertIn("EVERYDAY_LOANS", result)

    # --- UKAR deregistration ---

    def test_ukar_does_not_detect_tix_after_deregistration(self):
        """UKAR is seeded as NONE — should never trigger TIX.
        TIX Criteria row 14: 'close of business 30th June 2023 TIX Ltd will no longer
        be representing UKAR, Whistletree, Computershare and Landmark'."""
        result = detect_representatives([_make_creditor("UKAR")])
        self.assertNotIn("TIX", result)

    def test_whistletree_does_not_detect_tix(self):
        result = detect_representatives([_make_creditor("Whistletree")])
        self.assertNotIn("TIX", result)

    # --- Mixed case ---

    def test_mixed_case_detects_multiple_representatives(self):
        """A case with creditors spanning TIX, WATCH, and EVOLVE returns all three."""
        result = detect_representatives([
            _make_creditor("Barclays Bank"),   # TIX
            _make_creditor("Barclaycard"),     # WATCH
            _make_creditor("NatWest"),         # EVOLVE
        ])
        self.assertIn("TIX", result)
        self.assertIn("WATCH", result)
        self.assertIn("EVOLVE", result)

    # --- La Redoute date-gate (DB-backed) ---

    def test_la_redoute_not_watch_before_16_july_2025_db(self):
        """La Redoute must NOT trigger WATCH for a historical case before 16/07/2025."""
        result = detect_representatives(
            [_make_creditor("La Redoute")],
            assessment_date=date(2025, 7, 15),
        )
        self.assertNotIn("WATCH", result)

    def test_la_redoute_is_watch_from_16_july_2025_db(self):
        """La Redoute SHOULD trigger WATCH for cases from 16/07/2025 onward."""
        result = detect_representatives(
            [_make_creditor("La Redoute")],
            assessment_date=date(2025, 7, 16),
        )
        self.assertIn("WATCH", result)

    # --- Monzo date-gate (DB-backed) ---

    def test_monzo_not_watch_before_30_april_2024_db(self):
        """Monzo must NOT trigger WATCH for a historical case before 30/04/2024."""
        result = detect_representatives(
            [_make_creditor("Monzo")],
            assessment_date=date(2024, 4, 29),
        )
        self.assertNotIn("WATCH", result)

    def test_monzo_is_watch_from_30_april_2024_db(self):
        """Monzo SHOULD trigger WATCH for cases from 30/04/2024 onward."""
        result = detect_representatives(
            [_make_creditor("Monzo")],
            assessment_date=date(2024, 4, 30),
        )
        self.assertIn("WATCH", result)

    def test_assessment_date_in_parse_case_matches_payload(self):
        """assessment_date from the payload is propagated to the _parse_case() dict."""
        payload = _payload_with("Barclays Bank", assessment_date="2024-01-15")
        c = _parse_case(payload)
        self.assertEqual(c["assessment_date"], date(2024, 1, 15))
