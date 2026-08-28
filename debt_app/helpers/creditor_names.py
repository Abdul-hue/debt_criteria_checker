"""Creditor name normalisation, alias resolution and fuzzy lookup."""

import re
from debt_app.models import CreditorCriteria
from debt_app.helpers.creditor_aliases import _RAW_CREDITOR_ALIAS_MAP

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


# Alias keys are normalised on import so lookups can compare like with like.
CREDITOR_ALIAS_MAP = {
    normalise_creditor_name(k): v for k, v in _RAW_CREDITOR_ALIAS_MAP.items()
}


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
