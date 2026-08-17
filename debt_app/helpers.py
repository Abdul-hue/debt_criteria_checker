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
    'halifax personal loan': 'HBOS - Halifax - IVA',
    'halifax bank': 'HBOS - Halifax - IVA',
    'halifax plc': 'HBOS - Halifax - IVA',
    'bank of scotland': 'HBOS - Bank of Scotland - IVA',
    'bank of scotland credit card': 'HBOS - Bank of Scotland - IVA',
    'bank of scotland plc': 'HBOS - Bank of Scotland - IVA',
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
    'pulse': 'Pulse - IVA',
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
    'klarna bank ab': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'klarna uk': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'klarna uk ltd': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'klarna pay later and pay in 3': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'klarna bank ab pay later and pay in 3': 'Ikano Bank AB - IVA or TD or BKY or DAS or SEQ or DRO',
    'zilch': 'Zilch',
    'zilch technology limited': 'Zilch',
    # Zable is a trading name of Lendable — not its own CreditorCriteria row.
    # (Previously 'zable' pointed to the unrelated 'NewDay' and was silently
    # shadowed by 'lendable limited t/a zable' pointing to a non-existent
    # 'Zable' row — both normalise to the same key "zable", so only the last
    # one written ever took effect. Fixed to the one real target for both.)
    'zable': 'Lendable',
    'lendable limited t/a zable': 'Lendable',
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
    # Councils never go through CREDITOR_ALIAS_MAP / CreditorCriteria — they're
    # matched entirely via _match_council_rule() against CouncilRule, which has
    # its own name normalisation and fuzzy fallback. These 3 entries pointed at
    # CreditorCriteria rows that were never meant to exist and were dead code:
    # removed rather than "fixed", since there's nothing here for them to do.
    'west sussex & surrey credit union limited t/a boom community bank': 'Boom Credit Union ALSO known as East Sussex Credit Union Ltd t/a Wave Community Bank:',
    'department for work & pensions (dwp)': 'DWP',
    'hm revenue & customs': 'HM Revenue & Customs',
    # Northridge Finance is Santander Consumer Finance's motor-finance brand,
    # not its own CreditorCriteria row (a migration once added it as a
    # trading_name on that row, but trading_names is reset to [] by every
    # `seed_creditor_criteria` run — pointing the alias straight at the real
    # row is what actually survives).
    'northridge finance ltd': 'Santander Consumer Finance',
    'northridge finance': 'Santander Consumer Finance',
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

    # Found via a sweep of real Aryza creditor names that were silently failing
    # to match any CreditorCriteria row (verified against the DB, not guessed —
    # see conversation re: case 394638 WATCH detection investigation).
    'jaja finance': 'Jaja Finance Ltd',
    'marks and spencer': 'Marks & Spencer',
    "sainsbury's bank": 'Sainsburys Bank',
    'sainsbury bank': 'Sainsburys Bank',
    'vanquis loans': 'Vanquis Bank',
    'co-operative bank': 'The Co-operative Bank',
    'the cooperative': 'The Co-operative Bank',
    'grattans': 'Grattan',
    'bank of ireland': 'AA Bank of Ireland',
    'monozo bank': 'Monzo Bank',  # typo seen in live data
    'bank of scotland personal loan': 'HBOS - Bank of Scotland - IVA',
    # PayPal's legal-entity name has "(Europe)" in the MIDDLE of the string, so
    # normalise_creditor_name's end-anchored parenthetical strip never reaches
    # it — explicit aliases needed for the real Aryza/credit-report renderings.
    'paypal': 'Paypal Europe Ltd',
    'paypal (europe) sarl et cie sca': 'Paypal Europe Ltd',
    'paypal (europe) sarl & cia, sca': 'Paypal Europe Ltd',
    'paypal credit': 'Paypal Europe Ltd',
    'redcats catalogue': 'Redcats UK',
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


def _cosmetic_normalise(s: str) -> str:
    """
    Lightweight, symmetric cleanup applied to BOTH sides of a comparison
    (unlike normalise_creditor_name, which is asymmetric and aggressively
    strips legal suffixes — only meant for generating alias-map keys).

    Only touches cosmetic noise that never changes brand identity:
    apostrophes, '&' vs 'and', bracketed asides anywhere in the string
    (not just at the end), and punctuation/whitespace. Never strips
    suffix words like "Ltd"/"Bank" — that's normalise_creditor_name's job
    and doing both here would risk collapsing genuinely different names.
    """
    if not s:
        return ""
    s = s.lower()
    s = s.replace("’", "'").replace("‘", "'").replace("'", "")
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"\([^)]*\)", " ", s)   # strip bracketed asides anywhere, not just at the end
    s = re.sub(r"[.,]", " ", s)        # "S.A.R.L." / "Cia," style punctuation noise
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Words that are pure suffix/connector noise in split "BRAND - SUFFIX" style
# CreditorCriteria names (e.g. "Pulse - IVA", "Zopa - IVA or BKY") — a segment
# composed ENTIRELY of these words (e.g. "IVA or BKY", "TD or SEQ") carries no
# brand identity and must never be used as a standalone match target.
_DB_NAME_SUFFIX_WORDS = frozenset({
    "iva", "td", "bky", "seq", "das", "dro", "or", "and", "bankruptcy",
    "ltd", "limited", "plc",
})

# Generic business-descriptor words that carry no brand identity on their
# own — a segment consisting of exactly ONE of these (e.g. "Bank", "Finance"
# split out of "Somelender - Bank - IVA") must never be used as a standalone
# match target, or it would match almost any unrelated creditor whose name
# happens to contain that common word. Multi-word segments (e.g. "Bank of
# Scotland") are unaffected — this only excludes single bare generic nouns.
_GENERIC_SINGLE_WORD_SEGMENTS = frozenset({
    "bank", "banking", "bancorp", "card", "cards", "finance", "financial",
    "loan", "loans", "group", "services", "service", "credit", "capital",
    "company", "co", "insurance", "recovery", "recoveries", "holdings",
    "holding", "consumer", "personal", "retail", "direct", "solutions",
})


def _db_name_segments(creditor_name: str) -> list:
    """
    Split a CreditorCriteria.creditor_name on ' - ' into candidate brand
    segments, dropping segments that are pure suffix/connector noise (every
    word in the segment is a suffix word), a single bare generic business
    word (e.g. "Bank" alone), or too short to be a safe standalone target.

    e.g. "HBOS - Halifax - IVA"       -> ["hbos", "halifax"]
         "Pulse - IVA"                -> ["pulse"]
         "Zopa - IVA or BKY"          -> ["zopa"]     ("iva or bky" dropped)
         "Somelender - Bank - IVA"    -> ["somelender"]  ("bank" alone dropped)
    """
    segments = []
    for part in re.split(r"\s*-\s*", creditor_name.lower()):
        part = part.strip()
        if len(part) < 4:
            continue
        words = [w for w in re.split(r"[\s/]+", part) if w]
        if all(w in _DB_NAME_SUFFIX_WORDS for w in words):
            continue  # pure suffix segment, e.g. "iva or bky", "td or seq"
        if len(words) == 1 and words[0] in _GENERIC_SINGLE_WORD_SEGMENTS:
            continue  # bare generic noun, e.g. "bank", "finance", "group"
        segments.append(part)
    return segments


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
    5. Cosmetic-normalised exact match (apostrophes/&/brackets ignored on both
       sides) — catches punctuation-only variants with no alias needed,
       e.g. "Sainsbury's Bank" == "Sainsburys Bank".
    6. Segment substring — DB names shaped "BRAND - IVA" or "PREFIX - BRAND -
       SUFFIX" (the WATCH/TIX seed convention) are unreachable by whole-string
       substring matching in either direction. Splitting on " - " and trying
       each brand segment generalises the Pulse/Halifax/Bank-of-Scotland
       pattern to every similarly-shaped row without a hand-written alias.
    7. Raise DoesNotExist
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

    # 4-6. Single pass over active rows, checking (in priority order) whole-name
    # substring, cosmetic-normalised exact match, and segment substring. One
    # query + one Python pass instead of three, since this runs on every
    # creditor in every case assessment.
    #
    # 4. Substring: DB name contained in Aryza name, matched on a word boundary.
    # e.g. "NatWest" in "Natwest Group Plc" → match.
    # A plain `in` check on short names caused false positives (e.g. "AO" inside
    # "MBNA"), so this used to require the DB name be >= 5 chars — but that
    # silently broke real short official names ("DWP", "EE", "O2", "BT"...)
    # whenever Aryza sent them with any extra noise appended (e.g. a stray
    # "DWP.docx" filename entered as the creditor name). Word-boundary matching
    # rejects "AO" inside "MBNA" (no boundary before/after "ao") while still
    # matching "dwp" inside "dwp.docx" (the "." is a non-word character), so
    # the length floor is no longer needed for correctness.
    #
    # 5. Cosmetic-normalised exact match — apostrophes, &/and, brackets anywhere
    #    ignored on both sides. e.g. "Sainsbury's Bank" == "Sainsburys Bank".
    #
    # 6. Segment substring for "BRAND - SUFFIX" shaped DB names (the WATCH/TIX
    #    seed convention, e.g. "Pulse - IVA", "HBOS - Halifax - IVA"). Whole-
    #    string substring matching can never reach these since the DB name has
    #    extra text ("- IVA", "HBOS - ") the input doesn't. Splitting on " - "
    #    and matching brand segments generalises the fix to every similarly
    #    shaped row instead of needing a hand-written alias per creditor.
    all_active = list(CreditorCriteria.objects.filter(is_active=True))
    cosmetic_input = _cosmetic_normalise(cleaned)

    # Precompute each row's comparison values once (avoids re-normalising the
    # same DB name 3 times across the 3 passes below), but keep the 3 passes
    # STRICTLY SEQUENTIAL — each must finish scanning every row before the
    # next begins, exactly preserving the original step-4-before-5-before-6
    # priority. Interleaving them into one combined loop would let a lower-
    # priority match (e.g. step 6, found early in iteration order) win over a
    # higher-priority one (step 4, found later) purely by list position.
    _precomputed = [
        (row, row.creditor_name.strip().lower(),
         _cosmetic_normalise(row.creditor_name) if cosmetic_input else None,
         _db_name_segments(row.creditor_name) if cosmetic_input else ())
        for row in all_active
    ]

    for row, db_lower, _cosmetic_db, _segments in _precomputed:
        if db_lower and re.search(rf"\b{re.escape(db_lower)}\b", cleaned_lower):
            return row

    if cosmetic_input:
        for row, _db_lower, cosmetic_db, _segments in _precomputed:
            if cosmetic_db == cosmetic_input:
                return row

        for row, _db_lower, _cosmetic_db, segments in _precomputed:
            for segment in segments:
                if re.search(rf"\b{re.escape(segment)}\b", cosmetic_input):
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
    except (UserProfile.DoesNotExist, AttributeError):
        # AttributeError covers AnonymousUser/None, which have no `.profile`.
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


def get_london_day_boundary(dt=None):
    """
    Given a datetime (defaulting to now), return the Europe/London calendar-day
    boundaries as timezone-aware datetime instants (day_start, day_end) and
    the London date object itself.
    """
    from datetime import datetime, time, timedelta
    if dt is None:
        dt = timezone.now()
    london_date = timezone.localtime(dt).date()
    current_tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(london_date, time.min), current_tz)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end, london_date
