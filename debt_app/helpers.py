"""
Helper functions and constants for criteria management.
"""
from decimal import Decimal
from django.utils import timezone
from .models import (
    GlobalCriteria, CriteriaDecision, CreditorCriteria,
    CouncilRule, Application, EvidenceLedger, Voter,
    Department, UserProfile,
    DepartmentRuleVisibility, DepartmentCreditorVisibility, DepartmentCouncilVisibility,
)

import re

def normalise_creditor_name(name: str) -> str:
    """
    Normalise a creditor name by stripping legal suffixes and noise words.
    """
    if not name:
        return ""

    # 1. Lowercase and 2. Strip whitespace
    name = name.lower().strip()

    # 4. Handle "t/a" or "trading as" - keep part after
    # Do this early as the prefix might have suffixes we want to ignore anyway
    # We use regex to handle various cases of t/a (e.g. T/A, t/a, T / A)
    name = re.split(r"\s+t/a\s+|\s+trading as\s+", name, flags=re.IGNORECASE)[-1].strip()

    # 6. Strip double spaces (repeated after steps)
    name = re.sub(r"\s+", " ", name).strip()

    # List of suffixes to remove from the END (must follow a space or be in parentheses)
    # Ordered by length descending to avoid partial matches (e.g. "limited uk" before "limited")
    suffixes = [
        "group limited", "group plc", "group ltd",
        "uk limited", "uk ltd", "limited uk",
        "limited", "ltd.", "ltd", "plc.", "plc", "llp", "llc",
        "(uk)", "uk", "(europe) plc", "(europe)"
    ]

    # 3 & 5. Remove suffixes from the end
    # We loop until no more changes to handle "Capital One Bank (Europe) Plc"
    changed = True
    while changed:
        changed = False
        original = name
        
        # Handle parenthetical suffixes specifically first if they are at the end
        # This catches (europe), (uk), etc.
        name = re.sub(r"\s*\([^)]+\)$", "", name).strip()
        
        # Handle the specific suffix list
        for suffix in suffixes:
            # Match suffix at the end, either preceded by space or as the entire string
            pattern = rf"(?:\s+|^){re.escape(suffix)}$"
            name = re.sub(pattern, "", name).strip()
            
        if name != original:
            changed = True
            name = re.sub(r"\s+", " ", name).strip()

    return name.strip()


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


# ---------------------------------------------------------------------------
# Creditor name matchers
# ---------------------------------------------------------------------------

_RAW_CREDITOR_ALIAS_MAP = {
    # 'Salaryfinance' is one word in Aryza, so the substring match against the
    # DB row 'Salary Finance' (two words) misses — alias it explicitly.
    'salaryfinance': 'Salary Finance',
    'salaryfinance loan': 'Salary Finance',
    'salary finance loan': 'Salary Finance',
    'natwest group plc': 'NatWest',
    'natwest plc': 'NatWest',
    'natwest': 'NatWest',
    'rbs': 'NatWest',
    'royal bank of scotland': 'NatWest',
    'natwest current accounts': 'NatWest',
    'lloyds banking group': 'Lloyds Bank',
    'lloyds bank plc': 'Lloyds Bank',
    'lloyds tsb': 'Lloyds Bank',
    'lloyds': 'Lloyds Bank',
    'lloyds bank': 'Lloyds Bank',
    'lloyds bank plc hp': 'Lloyds Bank',
    'mbna': 'MBNA - IVA',
    'mbna limited': 'MBNA - IVA',
    'mbna europe bank': 'MBNA - IVA',
    'barclaycard': 'Barclaycard',
    'barclaycard (including cards below) - iva': 'Barclaycard',
    'barclays bank plc': 'Barclays Bank',
    'barclays': 'Barclays Bank',
    'barclays partner finance': 'Barclays',
    'link financial outsourcing limited': 'Link Financial - IVA',
    'link financial outsourcing': 'Link Financial - IVA',
    'link financial ltd': 'Link Financial - IVA',
    'link financial': 'Link Financial - IVA',
    'link financial limited': 'Link Financial - IVA',
    'asset link': 'Asset Link',
    'jd williams (n brown group)': 'Shop Direct',
    'jd williams company limited': 'JD WIlliams (N Brown Group)',
    'jd williams & company limited': 'JD WIlliams (N Brown Group)',
    'jd williams and company limited': 'JD WIlliams (N Brown Group)',
    'jd williams': 'JD WIlliams (N Brown Group)',
    'n brown': 'Shop Direct',
    'n brown group': 'Shop Direct',
    'shop direct': 'Shop Direct',
    'shop direct group': 'Shop Direct',
    'jd williams (n brown group plc)': 'Shop Direct',
    'the very group limited (wpm)': 'Very',
    'capital one': 'Capital One',
    'capital one bank (europe) plc': 'Capital One',
    '118 118 money': '118 Money',
    '118118 money': '118 Money',
    '118 money': '118 Money',
    'madison cf uk ltd t/a 118 118 money': '118 Money',
    'creation': 'Creation',
    'creation consumer finance': 'Creation',
    'creation consumer finance ltd': 'Creation Consumer Finance',
    'creation financial services': 'Creation',
    'creation finance': 'Creation Financial Services',
    'novuna': 'Hitachi Capital/Credit / Novuna',
    'hitachi capital': 'Hitachi Capital/Credit / Novuna',
    'zopa': 'Zopa - IVA or BKY',
    'zopa bank limited': 'Zopa - IVA or BKY',
    'zopa limited': 'Zopa - IVA or BKY',
    'halifax': 'HBOS - Halifax - IVA',
    'hsbc': 'HSBC',
    'santander': 'Santander',
    'santander cards': 'Santander Cards',
    'santander consumer finance': 'Santander Consumer Finance',
    'virgin credit card': 'Virgin Credit Card',
    'virgin media': 'Virgin Media',
    'virgin money': 'Virgin Money (Loan) WPM',
    'tesco bank': 'Tesco Bank',
    'tesco mobile': 'Tesco Mobile',
    'american express': 'American Express Service',
    'american express services europe ltd': 'American Express Service',
    'amex': 'American Express Service',
    'vanquis': 'Vanquis Bank',
    'vanquis bank': 'Vanquis Bank',
    'vanquis bank limited': 'Vanquis Bank',
    'aqua': 'Aqua - IVA',
    'newday': 'NewDay',
    'newday limited': 'NewDay',
    'paypal': 'Paypal Europe Ltd',
    'very': 'Very',
    'every day loans': 'Every Day Loans',
    'everyday loans': 'Everyday Loans',
    'next': 'Next Directory',
    'next directory': 'Next Directory',
    'littlewoods': 'Littlewoods',
    'littlewoods.com': 'Littlewoods',
    'studio': 'Studio Cards & Gifts',
    'lowell': 'Lowell',
    'lowell portfolio': 'Lowell',
    'lowell group': 'Lowell',
    'lowell financial': 'Lowell',
    'lowell portfolio i ltd': 'Lowell',
    'pra': 'PRA (Portfolio Recovery Associates) - IVA',
    'portfolio recovery associates': 'PRA (Portfolio Recovery Associates) - IVA',
    'pra group': 'PRA (Portfolio Recovery Associates) - IVA',
    'portfolio recovery': 'PRA (Portfolio Recovery Associates) - IVA',
    'pra group (uk) limited (tix)': 'PRA Group',
    'pra group (uk) ltd c/o wpm': 'PRA Group',
    'lantern': 'Lantern',
    'lantern debt recovery': 'Lantern',
    'lantern debt recovery services ltd': 'Lantern',
    'lantern debt recovery limited - iva or bky': 'Lantern',
    'lantern debt recovery limited - td or das or seq': 'Lantern',
    'perch capital': 'PCO Holdco Sarl - IVA',
    'perch capital limited': 'Perch Capital Limited',
    'cabot': 'Cabot Financial',
    'cabot financial': 'Cabot Financial',
    'cabot financial (europe) ltd': 'Cabot Financial',
    'cabot credit management group limited': 'Cabot Financial',
    'intrum': 'Intrum UK Ltd (previously 1st Credit) - IVA or BKY',
    '1st credit': 'Intrum UK Ltd (previously 1st Credit) - IVA or BKY',
    'arrow global': 'Arrow Global',
    'marlin': 'Marlin Financial - IVA',
    'hoist': 'Hoist Financial',
    'hoist financial': 'Hoist Financial',
    'moorcroft': 'Moorcroft Debt Recovery',
    'moorcroft debt recovery': 'Moorcroft Debt Recovery',
    'jefferson capital': 'Jefferson Capital International Acquisition (JCIA, or their UK operation Creditlink Account Recovery Services CARS)',
    'jcia': 'Jefferson Capital International Acquisition (JCIA, or their UK operation Creditlink Account Recovery Services CARS)',
    'cars': 'Jefferson Capital International Acquisition (JCIA, or their UK operation Creditlink Account Recovery Services CARS)',
    'jc international acquisition': 'Jefferson Capital International Acquisition (JCIA, or their UK operation Creditlink Account Recovery Services CARS)',
    'jc international acquisition llc': 'Jefferson Capital International Acquisition (JCIA, or their UK operation Creditlink Account Recovery Services CARS)',
    'nationwide recovery': 'Nationwide Recovery (SDG) - IVA or TD',
    'max recovery': 'Max Recovery',
    'grove': 'Grove / TTI SPC CarVal (including previous Egg Loans /Britannica Recovery) - IVA',
    'tti spc': 'TTI SPC CarVal / Grove (including previous Egg Loans /Britannica Recovery) - IVA',
    'klarna': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'klarna uk ltd': 'Klarna',
    'klarna pay later and pay in 3': 'Klarna',
    'zilch': 'Zilch',
    'zilch technology limited': 'Zilch',
    'zable': 'NewDay',
    'lendable limited t/a zable': 'Zable',
    'aquis': 'Aquis',
    'fluid': 'Fluid',
    'opus': 'Opus',
    'jaja': 'Jaja Finance Ltd',
    'lendable': 'Lendable',
    'lendable limited t/a autolend': 'Lendable',
    'plata': 'Plata Loans (BAMBOO)',
    'salary finance': 'Salary Finance',
    'ratesetter': 'Ratesetter',
    'funding circle': 'Funding Circle',
    'updraft': 'Updraft',
    'fairscore limited t/a updraft': 'Updraft',
    'tsb': 'TSB Bank',
    'tsb bank': 'TSB Bank',
    'tsb bank plc': 'TSB Bank',
    'nationwide': 'Nationwide Building Society',
    'nationwide building society': 'Nationwide Building Society',
    'first direct': 'First Direct',
    'monzo': 'Monzo Bank',
    'monzo bank': 'Monzo',
    'starling': 'Monzo Bank',
    'argos': 'Argos Card Services',
    'home retail group': 'Argos Card Services',
    'freemans': 'Freemans Catalogue',
    'kaleidoscope': 'Kaleidoscope',
    'look again': 'Look Again',
    'grattan': 'Grattan',
    'octopus energy limited': 'Octopus Energy',
    'british gas consumer': 'British Gas',
    'amigo': 'Amigo',
    'amigo loans': 'Amigo',
    'bamboo': 'Bamboo',
    'bamboo loans': 'Bamboo',
    'bamboo limited (link financial)': 'Bamboo',
    'guarantor my loan': 'Guarantor My Loan',
    'buddy loans': 'Buddy Loans t/a Advancis Ltd',
    'moneybarn': 'Moneybarn',
    'black horse': 'Blackhorse - Blackhorse Finance - IVA',
    'black horse limited': 'Blackhorse - Blackhorse Finance - IVA',
    'black horse - td': 'Blackhorse - Blackhorse Finance - TD',
    'blue motor finance': 'Blue Motor Finance',
    'blue motor finance limited': 'Blue Motor Finance',
    'specialist motor finance': 'Specialist Motor Finance',
    'volkswagen financial services': 'Volkswagen Financial Services',
    'vw financial services': 'Volkswagen Financial Services',
    'fce bank': 'FCE Bank',
    'ford credit': 'FCE Bank',
    'hitachi': 'Hitachi',
    'ikano': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'granite': 'Granite (Vanquis)',
    'gracombex ltd t/a the money platform': 'The Money Platform',
    'brighton & hove city council': 'Brighton and Hove City Council',
    'north east lincolnshire borough council': 'North East Lincolnshire Council',
    'mansfield district council': 'Mansfield District Council',
    'west sussex & surrey credit union limited t/a boom community bank': 'Boom Credit Union ALSO known as East Sussex Credit Union Ltd t/a Wave Community Bank:',
    'department for work & pensions (dwp)': 'DWP',
    'hm revenue & customs': 'HM Revenue & Customs',
    'northridge finance ltd': 'Northridge Finance',
    'castle community bank': 'Castle Community Bank',
    'advanced payment solutions ltd t/a cashplus bank': 'Cashplus',
    'zempler bank limited': 'Cashplus',
    'ccc debt management': 'CCC Debt Management',
    'united trust bank limited': 'United Trust Bank',
    'anderson brookes': 'Anderson Brookes',
    'credit4 limited': 'Credit4',
    'travis perkins plc': 'Travis Perkins',
    'tyrell carpentry contractors limited': 'Tyrell Carpentry',
    'huws gray builders merchant': 'Huws Gray',
    'zopa limited': 'Zopa - IVA or BKY',
    'halifax credit card': 'HBOS - Halifax - IVA',
    'v12 finance': 'V12 Personal Finance',
    'v12 personal finance': 'V12 Personal Finance',
    'admiral financial services ltd': 'Admiral Loans',
    'admiral financial services limited': 'Admiral Loans',
    'shop direct finance company ltd': 'Shop Direct Finance Company - IVA or TD',
    'home retail group card services': 'Home Retail Group',
    'hbos - halifax - iva': 'HBOS - Halifax - IVA',
    'secure trust bank plc': 'Secure Trust Bank',
    'mbna ltd': 'MBNA - IVA',
    'jd williams ta jacamo': 'Shop Direct',
}

# Apply normalisation to all keys in the alias map to ensure robust lookups
CREDITOR_ALIAS_MAP = {normalise_creditor_name(k): v for k, v in _RAW_CREDITOR_ALIAS_MAP.items()}


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


def get_creditor_by_trading_name(name: str, all_names=None):
    """
    Find CreditorCriteria row for a given creditor name.

    Search order:
    1. CREDITOR_ALIAS_MAP exact match
    2. Exact match on creditor_name (case-insensitive)
    3. Search trading_names field for any row where this name is a known trading name
    4. Substring: creditor_name is contained in the input name
       e.g. DB="NatWest", Aryza="Natwest Group Plc"
       "natwest" is in "natwest group plc" → match
    5. Raise DoesNotExist
    """
    from debt_app.models import CreditorCriteria

    cleaned = name.strip()
    cleaned_lower = cleaned.lower()
    normalised = normalise_creditor_name(name)

    # 1. Alias map
    alias = CREDITOR_ALIAS_MAP.get(normalised)
    if alias:
        try:
            return CreditorCriteria.objects.get(
                creditor_name__iexact=alias,
                is_active=True
            )
        except CreditorCriteria.DoesNotExist:
            pass
        except CreditorCriteria.MultipleObjectsReturned:
            # Guard against duplicate active rows — return a deterministic match
            # rather than crashing the whole assessment.
            return CreditorCriteria.objects.filter(
                creditor_name__iexact=alias, is_active=True
            ).order_by("id").first()

    # 2. Exact creditor_name match
    try:
        return CreditorCriteria.objects.get(
            creditor_name__iexact=cleaned,
            is_active=True
        )
    except CreditorCriteria.DoesNotExist:
        pass
    except CreditorCriteria.MultipleObjectsReturned:
        return CreditorCriteria.objects.filter(
            creditor_name__iexact=cleaned, is_active=True
        ).order_by("id").first()

    # 3. Trading names search
    row = CreditorCriteria.objects.filter(
        trading_names__icontains=cleaned,
        is_active=True
    ).first()
    if row:
        return row

    # 4. Substring: DB name contained in Aryza name
    # Only match if DB name is >= 5 chars to avoid short false matches
    # e.g. "NatWest" (7 chars) in "Natwest Group Plc" → match
    # NOT "AO" (2 chars) in "MBNA" → no match
    all_active = CreditorCriteria.objects.filter(is_active=True)
    for row in all_active:
        db_lower = row.creditor_name.strip().lower()
        if len(db_lower) >= 5 and db_lower in cleaned_lower:
            return row

    raise CreditorCriteria.DoesNotExist(
        f"No criteria row found for: {name!r}"
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


# ---------------------------------------------------------------------------
# Department helpers
# ---------------------------------------------------------------------------

def get_user_department(user):
    """
    Returns the Department linked to the user via UserProfile.
    Falls back to the 'Default' department, or None if that doesn't exist.
    """
    try:
        profile = user.profile
        if profile.department_id:
            return profile.department
    except UserProfile.DoesNotExist:
        pass
    try:
        return Department.objects.get(name='Default')
    except Department.DoesNotExist:
        return None


def filter_by_department(queryset, model, user, visibility_model, fk_field):
    """
    Filter a queryset by department visibility.

    Admin users (is_staff=True) always receive the unfiltered queryset.
    Assessor users see everything EXCEPT records their department has explicitly
    marked is_visible=False (deny-list semantics). If no visibility entries exist
    the full queryset is returned — items are visible by default.

    Parameters
    ----------
    queryset         : base queryset to filter
    model            : the model class of the queryset (unused, kept for signature clarity)
    user             : the request user
    visibility_model : DepartmentRuleVisibility / DepartmentCreditorVisibility / DepartmentCouncilVisibility
    fk_field         : name of the FK field on visibility_model that points to the main model
                       (e.g. 'rule_key', 'creditor', 'council')
    """
    if user.is_staff:
        return queryset

    dept = get_user_department(user)
    if dept is None:
        return queryset

    dept_qs = visibility_model.objects.filter(department=dept)
    if not dept_qs.exists():
        return queryset

    # Determine which field on the target model to filter against.
    # FK with to_field='rule_key' → remote_field.field_name == 'rule_key'
    # FK to default PK          → remote_field.field_name == 'id'
    fk_meta = visibility_model._meta.get_field(fk_field)
    target_field = fk_meta.remote_field.field_name or 'pk'

    hidden_values = list(
        dept_qs.filter(is_visible=False)
        .values_list(fk_field + '_id', flat=True)
    )

    if not hidden_values:
        return queryset

    return queryset.exclude(**{target_field + '__in': hidden_values})
