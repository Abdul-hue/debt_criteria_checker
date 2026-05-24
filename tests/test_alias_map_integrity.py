import pytest
from debt_app.helpers import CREDITOR_ALIAS_MAP
from debt_app.models import CreditorCriteria

@pytest.mark.django_db
def test_creditor_alias_map_integrity():
    """
    Ensure every value in CREDITOR_ALIAS_MAP points to an active CreditorCriteria row.
    Ensure keys are lowercase and unique.
    """
    
    # Assert: no duplicate keys exist
    # (The dictionary literal naturally prevents duplicates, but we assert per instructions)
    assert len(CREDITOR_ALIAS_MAP) == len(set(CREDITOR_ALIAS_MAP.keys())), "Duplicate keys found in CREDITOR_ALIAS_MAP"

    for key, value in CREDITOR_ALIAS_MAP.items():
        # Assert: every key in the map is lowercase
        assert key == key.lower(), f"Key '{key}' is not lowercase"
        
        # For each value in the map, assert CreditorCriteria exists
        exists = CreditorCriteria.objects.filter(creditor_name__iexact=value, is_active=True).exists()
        
        # On failure, provide details so it is visible in CI output
        if not exists:
            print(f"\nFAILED ALIAS CHECK:")
            print(f"  Key:   {key}")
            print(f"  Value: {value}")
            assert exists is True, f"Broken alias found: {key} -> {value}"
