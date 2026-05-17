"""Verify Banking Groups seed has populated correctly.
These run against the actual DB state after migrations have applied."""
import pytest
from debt_app.models import CreditorCriteria


# Sentinel mappings — pick one creditor per group that we know is in the spec
SENTINEL_MAPPINGS = [
    ("Halifax", "Lloyds Group"),
    ("Black Horse", "Lloyds Group"),
    ("Birmingham Midshires", "Lloyds Group"),
    ("NatWest", "RBS Group"),
    ("Ulster Bank", "RBS Group"),
    ("Coutts", "RBS Group"),
    ("First Direct", "HSBC Group"),
    ("Smile", "Co-op Group"),
    ("Britannia Building Society", "Co-op Group"),
    ("Woolwich", "Barclays Group"),
    ("Cahoot", "Santander Group"),
    ("Abbey National", "Santander Group"),
    ("Cheshire Building Society", "Nationwide Group"),
    ("Chelsea Building Society", "Yorkshire Group"),
    ("Yorkshire Bank", "Clydesdale Group"),
    ("Post Office", "BoI Group"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("creditor_name,expected_group", SENTINEL_MAPPINGS)
def test_creditor_has_correct_parent_group(creditor_name, expected_group):
    row = CreditorCriteria.objects.filter(
        creditor_name__iexact=creditor_name
    ).first()
    assert row is not None, f"{creditor_name} not seeded"
    assert row.parent_group == expected_group, (
        f"{creditor_name}: expected {expected_group!r}, got {row.parent_group!r}"
    )


@pytest.mark.django_db
def test_all_twelve_banking_groups_present():
    """All 12 banking groups from the spec should have at least 2 members."""
    expected_groups = {
        "RBS Group", "Barclays Group", "Co-op Group", "Lloyds Group",
        "HSBC Group", "Nationwide Group", "Santander Group",
        "Yorkshire Group", "Clydesdale Group", "Skipton Group",
        "Coventry Group", "BoI Group",
    }
    for group in expected_groups:
        count = CreditorCriteria.objects.filter(parent_group=group).count()
        assert count >= 2, f"{group} has only {count} member(s) — expected >=2"


@pytest.mark.django_db
def test_lloyds_family_groups_to_single_lender():
    """The case that motivated this seed: Lloyds + Halifax + Bank of Scotland
    should all resolve to Lloyds Group, so a case with all three reads as
    one lender for WATCH-22.5 / EVOLVE-02."""
    names = ["Lloyds", "Halifax", "Bank of Scotland"]
    groups = set()
    for name in names:
        row = CreditorCriteria.objects.filter(creditor_name__iexact=name).first()
        assert row is not None, f"{name} not seeded"
        groups.add(row.parent_group)
    assert groups == {"Lloyds Group"}, (
        f"Expected all three to map to Lloyds Group, got {groups}"
    )
