"""Sentinel tests for Which Representative seed migration (0008).

Covers:
  - At least 5 TIX creditors have representative="TIX"
  - At least 5 WATCH parent reps exist with representative="WATCH"
  - Ikano Bank AB has its trading names attached
  - Lloyds Banking Group IVA has its HBOS sub-entries attached
  - At least 3 EVOLVE creditors have representative="EVOLVE"
  - Migration is idempotent (running twice doesn't duplicate)
"""

import pytest
from debt_app.models import CreditorCriteria


@pytest.mark.django_db
class TestWhichRepresentativeSeed:
    """Sentinel tests for Which Representative seed data."""

    def test_tix_creditors_exist_and_marked(self):
        """At least 5 TIX creditors exist with representative=TIX."""
        tix_creditors = CreditorCriteria.objects.filter(representative="TIX")
        assert tix_creditors.count() >= 5, "Expected at least 5 TIX creditors"

        # Spot-check a few known TIX creditors
        expected_names = ["118 Money", "Alliance & Leicester", "HSBC", "Santander"]
        for name in expected_names:
            obj = CreditorCriteria.objects.filter(
                creditor_name__iexact=name,
                representative="TIX"
            ).first()
            assert obj is not None, f"TIX creditor '{name}' not found or not marked as TIX"

    def test_watch_representatives_exist(self):
        """At least 5 WATCH parent reps exist with representative=WATCH."""
        watch_reps = CreditorCriteria.objects.filter(representative="WATCH")
        assert watch_reps.count() >= 5, "Expected at least 5 WATCH representatives"

        # Spot-check a few known WATCH reps
        expected_names = [
            "Barclaycard (including cards below) - IVA",
            "Cabot Financial (including DLC) - IVA",
            "Nationwide Building Society - IVA",
        ]
        for name in expected_names:
            obj = CreditorCriteria.objects.filter(
                creditor_name__iexact=name,
                representative="WATCH"
            ).first()
            assert obj is not None, f"WATCH representative '{name}' not found"

    def test_ikano_bank_has_trading_names(self):
        """Ikano Bank AB has its trading names attached."""
        ikano = CreditorCriteria.objects.filter(
            creditor_name__iexact="Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO"
        ).first()
        assert ikano is not None, "Ikano Bank AB not found"
        assert ikano.representative == "WATCH", "Ikano should be WATCH"
        assert ikano.trading_names is not None, "Ikano trading_names should not be None"
        assert len(ikano.trading_names) >= 3, f"Expected at least 3 trading names, got {len(ikano.trading_names)}"

        # Spot-check specific trading names
        expected_trading_names = ["incl. New Look Card", "DFS Loan", "IKEA IFC"]
        for tname in expected_trading_names:
            assert tname in ikano.trading_names, (
                f"Expected trading name '{tname}' not found in Ikano trading names: "
                f"{ikano.trading_names}"
            )

    def test_lloyds_banking_group_iva_has_hbos_entries(self):
        """Lloyds Banking Group IVA has its HBOS sub-entries attached."""
        lloyds_iva = CreditorCriteria.objects.filter(
            creditor_name__iexact="Lloyds Banking Group (Including the Companies/Brands below) - IVA"
        ).first()
        assert lloyds_iva is not None, "Lloyds Banking Group IVA not found"
        assert lloyds_iva.representative == "WATCH", "Lloyds should be WATCH"
        assert lloyds_iva.trading_names is not None, "Lloyds IVA trading_names should not be None"
        assert len(lloyds_iva.trading_names) >= 10, (
            f"Expected at least 10 trading names for Lloyds IVA, got {len(lloyds_iva.trading_names)}"
        )

        # Spot-check HBOS entries
        hbos_entries = [
            "HBOS - AA (HBOS) - IVA",
            "HBOS - Halifax - IVA",
            "HBOS - Bank of Scotland - IVA",
        ]
        for hbos_entry in hbos_entries:
            assert hbos_entry in lloyds_iva.trading_names, (
                f"Expected HBOS entry '{hbos_entry}' not found in Lloyds trading names"
            )

    def test_evolve_creditors_exist_and_marked(self):
        """At least 3 EVOLVE creditors have representative=EVOLVE."""
        evolve_creditors = CreditorCriteria.objects.filter(representative="EVOLVE")
        assert evolve_creditors.count() >= 3, "Expected at least 3 EVOLVE creditors"

        # Spot-check known EVOLVE creditors
        expected_names = ["Mint", "NatWest Bank", "TSB Bank"]
        for name in expected_names:
            obj = CreditorCriteria.objects.filter(
                creditor_name__iexact=name,
                representative="EVOLVE"
            ).first()
            assert obj is not None, f"EVOLVE creditor '{name}' not found or not marked as EVOLVE"

    def test_migration_idempotent(self):
        """Verify the seed migration is idempotent by checking for duplicates.
        
        The migration uses filter(__iexact).first() + update pattern, so
        running it twice should not create duplicate rows.
        """
        # Count unique creditor names by representative type
        tix_names = CreditorCriteria.objects.filter(
            representative="TIX"
        ).values_list("creditor_name", flat=True)
        watch_names = CreditorCriteria.objects.filter(
            representative="WATCH"
        ).values_list("creditor_name", flat=True)
        evolve_names = CreditorCriteria.objects.filter(
            representative="EVOLVE"
        ).values_list("creditor_name", flat=True)

        # Verify no duplicate creditor names within each representative type
        tix_unique = set(name.lower() for name in tix_names)
        watch_unique = set(name.lower() for name in watch_names)
        evolve_unique = set(name.lower() for name in evolve_names)

        assert len(tix_unique) == len(tix_names), "Duplicate TIX creditor names found"
        assert len(watch_unique) == len(watch_names), "Duplicate WATCH representative names found"
        assert len(evolve_unique) == len(evolve_names), "Duplicate EVOLVE creditor names found"

        # Also check that there are no records with the same name but different representative
        all_creditors = CreditorCriteria.objects.all()
        name_to_rep = {}
        for creditor in all_creditors:
            name_lower = creditor.creditor_name.lower()
            if name_lower in name_to_rep:
                # If we see the same name again, it should have the same representative
                assert name_to_rep[name_lower] == creditor.representative, (
                    f"Creditor '{creditor.creditor_name}' has conflicting representatives: "
                    f"{name_to_rep[name_lower]} vs {creditor.representative}"
                )
            else:
                name_to_rep[name_lower] = creditor.representative

    def test_all_tix_creditors_active(self):
        """All seeded TIX creditors are active."""
        tix_creditors = CreditorCriteria.objects.filter(representative="TIX")
        inactive_tix = tix_creditors.filter(is_active=False)
        assert inactive_tix.count() == 0, (
            f"Found {inactive_tix.count()} inactive TIX creditors"
        )

    def test_all_watch_representatives_active(self):
        """All seeded WATCH representatives are active."""
        watch_reps = CreditorCriteria.objects.filter(representative="WATCH")
        inactive_watch = watch_reps.filter(is_active=False)
        assert inactive_watch.count() == 0, (
            f"Found {inactive_watch.count()} inactive WATCH representatives"
        )

    def test_all_evolve_creditors_active(self):
        """All seeded EVOLVE creditors are active."""
        evolve_creditors = CreditorCriteria.objects.filter(representative="EVOLVE")
        inactive_evolve = evolve_creditors.filter(is_active=False)
        assert inactive_evolve.count() == 0, (
            f"Found {inactive_evolve.count()} inactive EVOLVE creditors"
        )

    def test_barclaycard_trading_names_valid(self):
        """Barclaycard trading names are properly attached."""
        barclaycard_iva = CreditorCriteria.objects.filter(
            creditor_name__iexact="Barclaycard (including cards below) - IVA"
        ).first()
        assert barclaycard_iva is not None, "Barclaycard IVA not found"
        assert barclaycard_iva.trading_names is not None, "Barclaycard trading_names should not be None"
        assert len(barclaycard_iva.trading_names) >= 5, (
            f"Expected at least 5 Barclaycard trading names, got {len(barclaycard_iva.trading_names)}"
        )

        # Spot-check specific trading names
        expected = ["Argos Mastercard - IVA", "Goldfish - IVA"]
        for tname in expected:
            assert tname in barclaycard_iva.trading_names, (
                f"Expected trading name '{tname}' not found in Barclaycard trading names"
            )
