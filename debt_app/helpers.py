"""
Helper functions and constants for criteria management.
"""
from decimal import Decimal
from django.utils import timezone
from .models import GlobalCriteria, CriteriaDecision, CreditorCriteria

# ---------------------------------------------------------------------------
# Debt type constants
# ---------------------------------------------------------------------------

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
    if "hire purchase" in s or "vehicle finance" in s:
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


# ---------------------------------------------------------------------------
# Creditor name matchers
# ---------------------------------------------------------------------------

def is_asset_link_capital(name: str) -> bool:
    """True when the creditor name refers to Asset Link Capital (not generic Link Financial)."""
    if not name:
        return False
    return "asset link" in name.lower()


def is_link_financial(name: str) -> bool:
    """True when the creditor name matches Link Financial (excluding Asset Link Capital)."""
    if not name:
        return False
    if is_asset_link_capital(name):
        return False
    return "link" in name.lower()


def is_vw_finance(name: str) -> bool:
    """True when the creditor name refers to Volkswagen Financial Services."""
    if not name:
        return False
    s = name.lower()
    return "volkswagen financial" in s or "vwfs" in s


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_rule_threshold(rule_key: str) -> Decimal:
    """Retrieve a rule's threshold value by key."""
    try:
        rule = GlobalCriteria.objects.get(rule_key=rule_key, is_active=True)
        return rule.threshold_value
    except GlobalCriteria.DoesNotExist:
        raise ValueError(f"Rule '{rule_key}' not found or is inactive")


def get_majority_threshold() -> Decimal:
    """Get the majority creditor threshold (75% by default)."""
    return get_rule_threshold('majority_threshold')


def log_criteria_decision(application_id: str, client_name: str,
                          input_data: dict, output_data: dict,
                          recommendation: str, passes_hard_blocks: bool,
                          triggered_by=None, source: str = 'STANDALONE') -> CriteriaDecision:
    """Log a criteria assessment decision."""
    return CriteriaDecision.objects.create(
        application_id=application_id,
        client_name=client_name,
        input_snapshot=input_data,
        decision_output=output_data,
        recommended_solution=recommendation,
        passes_all_hard_blocks=passes_hard_blocks,
        triggered_by=triggered_by,
        source=source
    )


def get_creditor_by_trading_name(
    name: str,
    all_names: list[str] | None = None,
) -> CreditorCriteria:
    """
    Find a creditor using a 3-layer lookup:
    Layer 1 — Exact match on creditor_name (DB index, fast)
    Layer 2 — Exact match on any entry in trading_names (case-insensitive)
    Layer 3 — Fuzzy match via rapidfuzz token_sort_ratio at threshold 50

    Raises CreditorCriteria.DoesNotExist if all three layers miss.

    Parameters
    ----------
    name      : incoming creditor name from case payload
    all_names : pre-loaded list of active creditor_name values.
                Pass this from the calling loop to avoid N+1 DB queries.
                If None, loads from DB automatically.
    """
    # Preprocess name by stripping common business suffixes to ensure higher matching accuracy
    import re
    cleaned_name = re.sub(
        r"\s+(limited|ltd|plc|uk|group|services|retail)\b",
        "",
        name,
        flags=re.IGNORECASE
    ).strip()

    # Layer 1 — exact creditor_name match (try exact incoming name first, then cleaned version)
    try:
        return CreditorCriteria.objects.get(creditor_name=name, is_active=True)
    except CreditorCriteria.DoesNotExist:
        pass

    try:
        return CreditorCriteria.objects.get(creditor_name=cleaned_name, is_active=True)
    except CreditorCriteria.DoesNotExist:
        pass

    # Layer 2 — trading_names exact match (case-insensitive)
    name_lower = name.lower()
    cleaned_name_lower = cleaned_name.lower()
    for creditor in CreditorCriteria.objects.filter(is_active=True):
        if creditor.trading_names:
            if any(t.lower() == name_lower or t.lower() == cleaned_name_lower for t in creditor.trading_names):
                return creditor

    # Layer 3 — fuzzy match
    matched = fuzzy_lookup_creditor(cleaned_name, all_names=all_names)
    if matched is not None:
        return matched

    # Layer 4 — Substring / Word Containment Match (Self-healing fallback)
    # Automatically links names containing primary creditor words (e.g. "Natwest Current Accounts" -> "NatWest")
    active_creditors = list(CreditorCriteria.objects.filter(is_active=True))
    for creditor in active_creditors:
        # Extract the first/primary word of the canonical creditor name
        words = [w for w in re.split(r"\W+", creditor.creditor_name.lower()) if w]
        if words:
            primary_word = words[0]
            # Avoid matching generic short terms or noise words
            if len(primary_word) >= 4 and primary_word not in ("bank", "loan", "ltd", "corp", "coop", "limited"):
                if primary_word in cleaned_name_lower:
                    return creditor

    raise CreditorCriteria.DoesNotExist(
        f"No criteria row found for creditor: {name!r}"
    )


def fuzzy_lookup_creditor(
    name: str,
    all_names: list[str] | None = None,
    threshold: int = 75,
) -> CreditorCriteria | None:
    """
    Fuzzy-match a creditor name against all active CreditorCriteria rows
    using rapidfuzz token_sort_ratio.

    Parameters
    ----------
    name      : incoming creditor name to match
    all_names : pre-loaded list of creditor_name values to avoid N+1 queries.
                If None, loads from DB.
    threshold : minimum score to accept a match (default 75).
                75 is safe for this dataset — lower risks false matches
                e.g. "Bamboo" → "Barclays".

    Returns the matching CreditorCriteria object, or None if no match
    meets the threshold.
    """
    from rapidfuzz import process, fuzz

    if all_names is None:
        all_names = list(
            CreditorCriteria.objects.filter(is_active=True)
            .values_list("creditor_name", flat=True)
        )

    if not all_names:
        return None

    # Normalise inputs to lowercase to ensure case-insensitive fuzzy matching
    name_lower = name.lower()
    name_map = {n.lower(): n for n in all_names}
    all_names_lower = list(name_map.keys())

    result = process.extractOne(
        name_lower,
        all_names_lower,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )

    if result is None:
        return None

    matched_name_lower, score, _ = result
    matched_name = name_map[matched_name_lower]
    try:
        return CreditorCriteria.objects.get(
            creditor_name=matched_name, is_active=True
        )
    except CreditorCriteria.DoesNotExist:
        return None


def check_parent_group_conflict(client_bank_account: str, debtor_creditors: list) -> bool:
    """
    Check if client has a current account with same parent group as any debtor creditor.
    Returns True if conflict found.
    """
    account_bank = CreditorCriteria.objects.filter(
        creditor_name=client_bank_account,
        is_active=True
    ).first()

    if not account_bank or not account_bank.parent_group:
        return False

    return CreditorCriteria.objects.filter(
        creditor_name__in=debtor_creditors,
        parent_group=account_bank.parent_group,
        is_active=True
    ).exists()


def get_criteria_decisions_for_application(application_id: str):
    """Retrieve all decisions for an application."""
    return CriteriaDecision.objects.filter(
        application_id=application_id
    ).order_by('-triggered_at')


def get_rule_by_criteria_set(criteria_set: str):
    """Get all active rules for a criteria set."""
    return GlobalCriteria.objects.filter(
        criteria_set=criteria_set,
        is_active=True
    ).order_by('severity')
