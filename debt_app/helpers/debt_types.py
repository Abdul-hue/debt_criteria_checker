"""Canonical debt-type constants, normalisation and debt totals."""

import re
from decimal import Decimal

DEBT_TYPE_COUNCIL_TAX = "council_tax"


DEBT_TYPE_HP = "hire_purchase"


DEBT_TYPE_PERSONAL_LOAN = "personal_loan"


DEBT_TYPE_UTILITY = "utility"


DEBT_TYPE_STORE_CARD = "store_card"


DEBT_TYPE_CREDIT_CARD = "credit_card"


DEBT_TYPE_PCN = "pcn"


DEBT_TYPE_HOUSING_BENEFIT = "housing_benefit"


DEBT_TYPE_OVERDRAFT = "overdraft"


DEBT_TYPE_CATALOGUE = "catalogue"


DEBT_TYPE_MORTGAGE = "mortgage"


DEBT_TYPE_RENT = "rent"


DEBT_TYPE_MOBILE = "mobile"


DEBT_TYPE_UNKNOWN = "unknown"


_SECURED_TYPES = frozenset({DEBT_TYPE_HP, DEBT_TYPE_MORTGAGE})


def normalise_debt_type(raw: str) -> str:
    """Map a raw creditor_type string to a canonical DEBT_TYPE_* constant."""
    if not raw:
        return DEBT_TYPE_UNKNOWN
    s = raw.lower()
    if "council tax" in s or "council_tax" in s or "ctax" in s:
        return DEBT_TYPE_COUNCIL_TAX
    # Hire purchase / car finance is sent by upstream systems under a lot
    # of shorthand codes ("Car HP", "car_hp", "HP", "Vehicle HP") as well
    # as the full words. Missing a variant here means a genuinely secured
    # car finance debt silently falls through to DEBT_TYPE_UNKNOWN, which
    # is NOT in _SECURED_TYPES — so it gets counted as unsecured debt in
    # total_unsecured_debt. Caught a live case where Aryza's raw value
    # was literally "Car HP" (space-separated, not "car_hp") — an
    # underscore/suffix-only check misses this real-world format, so "hp"
    # is matched as a standalone WORD regardless of the separator
    # (space, underscore, hyphen, or none) around it.
    _tokens = set(re.findall(r"[a-z0-9]+", s))
    if (
        "hire purchase" in s or "hire-purchase" in s or "hire_purchase" in s
        or "vehicle finance" in s or "vehicle_finance" in s or "car finance" in s
        or "car_finance" in s or "conditional sale" in s or "logbook" in s
        or "log book" in s
        or "hp" in _tokens
    ):
        return DEBT_TYPE_HP
    if "housing benefit" in s:
        return DEBT_TYPE_HOUSING_BENEFIT
    if "store card" in s:
        return DEBT_TYPE_STORE_CARD
    if "credit card" in s:
        return DEBT_TYPE_CREDIT_CARD
    if "catalogue" in s:
        return DEBT_TYPE_CATALOGUE
    if "overdraft" in s:
        return DEBT_TYPE_OVERDRAFT
    if "mortgage" in s:
        return DEBT_TYPE_MORTGAGE
    if "rent" in s:
        return DEBT_TYPE_RENT
    if "mobile" in s:
        return DEBT_TYPE_MOBILE
    if "pcn" in s or "parking" in s:
        return DEBT_TYPE_PCN
    if any(kw in s for kw in ("utility", "gas", "electric", "water", "energy")):
        return DEBT_TYPE_UTILITY
    if "loan" in s:
        return DEBT_TYPE_PERSONAL_LOAN
    return DEBT_TYPE_UNKNOWN


def get_unsecured_debt_total(creditors: list) -> float:
    """Sum balances for non-secured debt types (excludes HP and mortgage)."""
    total = 0.0
    for c in creditors:
        dt = normalise_debt_type(c.get("creditor_type") or c.get("debt_type") or "")
        if dt not in _SECURED_TYPES:
            total += float(c.get("balance", 0) or 0)
    return total


def get_secured_debt_total(creditors: list) -> float:
    """Sum balances for secured debt types (HP and mortgage)."""
    total = 0.0
    for c in creditors:
        dt = normalise_debt_type(c.get("creditor_type") or c.get("debt_type") or "")
        if dt in _SECURED_TYPES:
            total += float(c.get("balance", 0) or 0)
    return total
