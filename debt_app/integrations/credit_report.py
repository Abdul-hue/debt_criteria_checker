"""
integrations/credit_report.py

Extracts structured per-creditor data from Aryza Advize credit report PDFs.

PDF structure (confirmed from real report):
  - Account header:  "{Creditor Name} {TYPE_CODE}"
    TYPE_CODE suffixes: CC, UL, MG, MO, CA, UT
  - Account Status line (after pdfplumber): "Account Status: {status} {subjective}"
  - Start Date: "Start Date: YYYY-MM-DD"  → compute account_age_months
  - Current Balance: "Current Balance: £{amount}" or "N/A"
  - Credit Limit: "Credit Limit: £{amount}" or "N/A"
  - Default Balance: "Default Balance: £{amount}" or "N/A"
  - Payment history grid: year row followed by 12 integers/D values
    Each integer = missed payments that month. D = defaulted.
  - Missed payments last 3 months: sum of last 3 values in most recent year row.

Type code handling (as actually implemented — see _parse_account_block):
  MG              → returned in `mortgage_accounts` (secured; not unsecured debt)
  MI/MU/BK        → returned in `other_accounts` (reconciliation only, never debt)
  everything else → returned in `accounts` (counted as unsecured IVA debt)

No status- or balance-conditional filtering is applied. An earlier version of
this module skipped BD on zero balance and CA/UT unless derogatory; that logic
was removed, so all non-mortgage, non-reconciliation codes are included and the
caller decides. Do not re-document the old rules here without restoring them.

Known type codes are listed in _TYPE_CODE_RE. That regex is the ONLY thing that
marks where one account block ends and the next begins, so an unlisted code used
to make the whole account vanish — its body, balance included, was appended to
the previous account's block where _extract_field() only ever returns the first
match. _ARYZA_FALLBACK_HEADER_RE now catches unlisted codes so new ones degrade
to a logged warning instead of silent data loss.
"""

import re
import logging
from datetime import date, datetime

import pdfplumber

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type code classification
# ---------------------------------------------------------------------------

# These suffix codes appear at the end of every account header line.
# NOTE: SKIP_TYPE_CODES and DEBT_TYPE_CODES are retained for callers that import
# them, but neither parser reads them any more — MG is routed by an explicit
# type_code check and there is no allow-list gate. See the module docstring.
SKIP_TYPE_CODES = {"MG"}                              # secured mortgage
DEBT_TYPE_CODES = {"CC", "UL", "MO", "PL", "HP", "TM", "BD", "CA", "UT", "DP", "IL", "EW", "EE"}
# Non-debt tradelines. Never counted as unsecured IVA debt, but still extracted
# and returned separately so the case assessment app can show their
# credit-report balance in the reconciliation table (same pattern as mortgages).
#   MI = motor insurance, MU = multi-comms, BK = basic bank account
# BK belongs here rather than in `accounts`: it is a bank account, not borrowing,
# and every BK seen in the corpus reports "Current Balance: N/A".
RECONCILIATION_ONLY_TYPE_CODES = {"MI", "MU", "BK"}

# ---------------------------------------------------------------------------
# Creditor alias map
# Keys: lowercase stripped name from PDF (without type code suffix)
# Values: canonical name as it appears in Aryza / CreditorCriteria
# ---------------------------------------------------------------------------

CREDITOR_ALIAS_MAP = {
    # NatWest variants
    "national westminster credit cards": "Natwest Group Plc",
    "national westminster": "Natwest Group Plc",
    "natwest": "Natwest Group Plc",
    "natwest group": "Natwest Group Plc",
    "rbs": "Natwest Group Plc",
    # Lloyds variants — all map to same canonical
    "lloyds bank": "Lloyds Bank",
    "lloyds bank personal loans": "Lloyds Bank",
    "lloyds bank mortgages ltd": "Lloyds Bank",
    "lloyds banking group": "Lloyds Bank",
    "lloyds": "Lloyds Bank",
    "halifax": "Halifax",
    "bank of scotland": "Bank of Scotland",
    # MBNA
    "mbna ltd": "MBNA - IVA",
    "mbna limited": "MBNA - IVA",
    "mbna": "MBNA - IVA",
    # Link Financial
    "link financial outsourcing limited": "Link Financial Outsourcing Limited",
    "link financial": "Link Financial Outsourcing Limited",
    "link": "Link Financial Outsourcing Limited",
    # JD Williams / N Brown
    "jd williams ta jacamo": "JD WIlliams (N Brown Group)",
    "jd williams": "JD WIlliams (N Brown Group)",
    "jacamo": "JD WIlliams (N Brown Group)",
    "simply be": "JD WIlliams (N Brown Group)",
    "ambrose wilson": "JD WIlliams (N Brown Group)",
    # Barclays
    "barclaycard": "Barclaycard",
    "barclays": "Barclays",
    # HSBC
    "hsbc": "HSBC",
    "hsbc bank": "HSBC",
    # NatWest/RBS cards
    "tesco bank": "Tesco Bank",
    # Santander
    "santander": "Santander",
    "santander uk": "Santander",
    # Capital One
    "capital one": "Capital One",
    # Virgin
    "virgin money": "Virgin Money",
    "virgin credit card": "Virgin Money",
    # Vanquis
    "vanquis bank": "Vanquis Bank",
    "vanquis": "Vanquis Bank",
    # Aqua / NewDay
    "aqua": "Aqua",
    "marbles": "Marbles",
    "newday": "NewDay",
    # Shop Direct / Very
    "shop direct": "Shop Direct",
    "very": "Very",
    "littlewoods": "Littlewoods",
    # Debt purchasers
    "lowell financial": "Lowell",
    "lowell portfolio": "Lowell",
    "lowell": "Lowell",
    "pra group": "PRA Group",
    "pra": "PRA Group",
    "intrum": "Intrum",
    "cabot financial": "Cabot Financial",
    "cabot": "Cabot Financial",
    # Lending
    "ratesetter": "RateSetter",
    "zopa": "Zopa",
    "funding circle": "Funding Circle",
    "amigo loans": "Amigo Loans",
    "amigo": "Amigo Loans",
    "brighthouse": "BrightHouse",
    # ---------------------------------------------------------------------------
    # Experian CAIS format — full legal names as they appear in Experian reports
    # ---------------------------------------------------------------------------
    # Water / utilities
    "anglian water": "Anglian Water",
    "anglian water services": "Anglian Water",
    "severn trent water": "Severn Trent Water",
    "severn trent": "Severn Trent Water",
    "thames water": "Thames Water",
    "united utilities": "United Utilities",
    "yorkshire water": "Yorkshire Water",
    "southern water": "Southern Water",
    "wessex water": "Wessex Water",
    "south west water": "South West Water",
    "affinity water": "Affinity Water",
    # Telecoms / communications
    "ee": "EE",
    "ee limited": "EE",
    "bt": "BT",
    "bt group": "BT",
    "sky": "Sky",
    "sky uk limited": "Sky",
    "virgin media": "Virgin Media",
    "vodafone": "Vodafone",
    "vodafone limited": "Vodafone",
    "o2": "O2",
    "telefonica uk limited": "O2",
    "three": "Three",
    "hutchison 3g uk limited": "Three",
    # Insurance / financial
    "premium credit limited": "Premium Credit Limited",
    "premium credit": "Premium Credit Limited",
    # Debt purchasers / other
    "lowell portfolio i ltd": "Lowell",
    "lowell portfolio 1 ltd": "Lowell",
    "lowell portfolio ltd": "Lowell",
    "monzo bank ltd": "Monzo Bank",
    "monzo bank": "Monzo Bank",
    "ovo energy": "OVO Energy",
    "jc international acquisition llc": "JC International Acquisition LLC",
    "mutual": "Mutual",
    "novuna personal finance": "Novuna",
    "novuna consumer finance": "Novuna",
    "barclays bank uk plc": "Barclays",
    "hsbc uk bank plc": "HSBC",
    "lloyds bank plc": "Lloyds Bank",
    "nationwide building society": "Nationwide",
    # ⚠️ Key must be lowercase: `match_creditor` (and every inline
    # `CREDITOR_ALIAS_MAP.get(...)` call) lowercases the NAME but not the
    # key, so the old "Yorkshire bank" spelling could never match.
    "yorkshire bank": "Yorkshire Bank",
    # Government -- the Department for Work and Pensions, whose
    # CreditorCriteria row is "DWP" (migration 0030, trading name "Department
    # for Work and Pensions"; `helpers.py` already maps "department for work &
    # pensions (dwp)" to it). "of" is Aryza's own spelling of the same
    # department. Mirrored by CAT's `common/creditor_identity.py`. "dwp" itself
    # is keyed the way "ee" / "bt" / "o2" are, so any casing lands on "DWP".
    "dwp": "DWP",
    "department for work and pensions": "DWP",
    "department of work and pensions": "DWP",
}

# ---------------------------------------------------------------------------
# Public name-matching helper (also used by engine/criteria.py)
# ---------------------------------------------------------------------------

def match_creditor(raw_name: str) -> str:
    """
    Look up raw_name in CREDITOR_ALIAS_MAP (case-insensitive, stripped).
    Returns the canonical creditor name, or raw_name if no match found.
    Never raises.
    """
    if not raw_name:
        return raw_name or ""
    try:
        return CREDITOR_ALIAS_MAP.get(raw_name.lower().strip(), raw_name)
    except Exception:
        return raw_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Known Aryza Advize account type codes.
#   DP = deferred payment (Klarna "Pay Later"/"Pay in 3" BNPL)
#   IL = advance against income (payday / short-term instalment)
#   EW = water, EE = electricity  (utilities, same treatment as UT)
#   BK = basic bank account       (reconciliation only, see above)
# Codes are ordered longest-alternatives-first only for readability; all are
# two characters and the trailing $ anchor makes ordering irrelevant here.
_TYPE_CODE_RE = re.compile(
    r"^(.+?)\s+(CC|UL|MG|MO|CA|UT|PL|HP|ST|OT|TM|BD|MI|MU|DP|IL|EW|EE|BK)$"
)

# Fallback for any Aryza header whose type code is not in the list above.
# Without this, an unlisted code silently deletes the account (see module
# docstring). The Experian path has had an equivalent fallback for a while;
# this brings the Aryza path to parity.
#
# False-positive safety: this is only ever applied to a line that is IMMEDIATELY
# followed by an "Account Details" line (see _split_into_account_blocks), which
# is what actually distinguishes a real header from a payment-grid row. Verified
# against 200 production reports: all 1,949 known-code headers have that
# follower, and the pattern matched zero non-header lines even before the
# follower check was applied.
_ARYZA_FALLBACK_HEADER_RE = re.compile(
    r"^([A-Za-z0-9][^:]{1,79}?)\s+([A-Z]{2})$"
)

def _parse_amount(text: str) -> int | None:
    """
    Parse a sterling amount string → pence integer.
    Handles: "£8,039", "£8039", "8039", "-£30"
    Also handles inline fields like "£106098 Last Update: 2025-12-31" by
    taking only the first whitespace-delimited token.
    Returns None for "N/A", "-", empty, or unparseable.

    Currency-symbol tolerant: some PDF font encodings render "£" as a
    mojibake replacement glyph (e.g. the Valid8IP-format Experian search —
    see _split_valid8_accounts) rather than the literal "£" character.
    Stripping any leading non-numeric character (instead of only "£")
    keeps this working regardless of which glyph a given exporter used —
    the same tolerance _ccj_amount_to_pence already applies via regex.
    """
    if not text:
        return None
    first_token = text.strip().split()[0] if text.strip() else ""
    if first_token.upper() in ("N/A", "-", ""):
        return None
    # Strip a single leading currency-symbol-shaped character (anything
    # that isn't a digit, minus sign, or comma) before the numeric parse —
    # covers "£", "$", and mojibake replacements alike.
    t = re.sub(r"^[^\d\-,]+", "", first_token).replace(",", "")
    if t.upper() in ("N/A", "-", ""):
        return None
    try:
        return int(round(float(t) * 100))
    except (ValueError, TypeError):
        return None


def _months_since(date_str: str) -> int | None:
    """
    Compute months between a date string (YYYY-MM-DD) and today.
    Returns None if date_str is unparseable.
    """
    if not date_str:
        return None
    try:
        start = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        today = date.today()
        return (today.year - start.year) * 12 + (today.month - start.month)
    except ValueError:
        return None


def _extract_field(lines: list[str], label: str) -> str:
    """
    Find the first line containing `label:` and return everything after the colon.
    Returns empty string if not found.
    """
    prefix = label.lower() + ":"
    for line in lines:
        low = line.lower()
        idx = low.find(prefix)
        if idx != -1:
            return line[idx + len(prefix):].strip()
    return ""


def _detect_agency(text: str) -> str:
    """
    Detect credit agency from report text.
    This report format is Aryza Advize — an internal aggregator.
    Falls back to bureau detection if Aryza branding absent.
    """
    sample = text[:800].lower()
    if "aryza" in sample or "advize" in sample:
        return "Aryza Advize"
    if "experian" in sample or "credit expert" in sample:
        return "Experian"
    # ⚠️ ARYZA ADVIZE PRINTS NO BRANDING. Its page one opens "Credit Report /
    # Client Details / ... / Debt Overview", with "CCJs and Insolvencies" in
    # the overview -- all 163 Aryza-layout reports in media/credit_reports
    # came back "Unknown" on the branding check above, so the view's
    # "recognised format but 0 accounts" warning never fired for any of them.
    # Checked AFTER Experian so a branded Experian report is never taken.
    if "debt overview" in sample and "ccjs and insolvencies" in sample:
        return "Aryza Advize"
    if "equifax" in sample or "clearscore" in sample:
        return "Equifax"
    if "transunion" in sample or "credit karma" in sample:
        return "TransUnion"
    return "Unknown"


def _extract_client_name(text: str) -> str:
    """
    Extract client name from "Name: Mrs Theresa Topp" style header.
    Strips titles (Mr/Mrs/Ms/Miss/Dr).
    """
    m = re.search(
        r"Name:\s*(Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+(.+?)(?:\n|$)",
        text, re.IGNORECASE
    )
    if m:
        return m.group(2).strip()
    m = re.search(r"Name:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""



# Matches a UK postcode whose two halves got glued together by PDF text
# extraction (e.g. "DT102FW" instead of "DT10 2FW") at the end of an address
# string. Deliberately requires the full contiguous run to sit at the very
# end ($) so a postcode that already has its normal space is never touched —
# the space breaks the contiguous match this pattern needs.
_POSTCODE_GLUED_RE = re.compile(r"([A-Za-z]{1,2}\d[A-Za-z\d]?)(\d[A-Za-z]{2})$")

# Matches a COMPLETE UK postcode (outward + inward code) at the end of a
# string, with the space between them optional — so it recognises both the
# normal "BN2 4EU" form and the glued "DT102FW" form _POSTCODE_GLUED_RE
# fixes up. Used to tell "this line already has the whole address" apart
# from "this line got cut off mid-postcode" — see _extract_client_address.
_FULL_POSTCODE_END_RE = re.compile(r"[A-Za-z]{1,2}\d[A-Za-z\d]?\s?\d[A-Za-z]{2}$")


def _clean_address(raw: str | None) -> str:
    """
    Normalise a raw address string pulled from a credit report PDF into the
    single-line, comma-separated form callers (e.g. the case-assessment
    tool) can display or store directly:
      - collapses whitespace runs introduced by PDF text extraction
      - normalises comma spacing and drops stray leading/trailing commas
      - collapses an empty field between two commas (e.g. a blank county:
        "LIVERPOOL, , L32 0RP" -> "LIVERPOOL, L32 0RP" — seen verbatim in a
        real report, so this is source data, not a PDF-extraction artefact,
        but it's still noise worth dropping from what callers display)
      - splits a UK postcode PDF-extraction glued into one token
        ("DT102FW" -> "DT10 2FW")
    Does NOT change letter case — reports mix ALL CAPS (Experian) and Title
    Case (Aryza) and title-casing risks mangling postcodes/initialisms.
    Never raises; returns "" for falsy input.
    """
    if not raw:
        return ""
    addr = re.sub(r"\s+", " ", raw.strip())
    addr = re.sub(r"\s*,\s*", ", ", addr)
    addr = addr.strip(", ").strip()
    addr = re.sub(r"(,\s*)+,", ",", addr)
    addr = _POSTCODE_GLUED_RE.sub(lambda m: f"{m.group(1)} {m.group(2)}", addr)
    return addr


def _extract_client_address(text: str) -> str:
    """
    Extract the client's own current address from an Aryza Advize report.

    Aryza prints this once, near the top of the report, as a
    "Current Address: {address}" line (confirmed against real production
    reports — see test_credit_report_address_extraction.py). It is the
    client/debtor's address, not any creditor's — credit reports never carry
    a creditor's own postal address, only the applicant's.

    A long address routinely wraps onto a second (or third) line of the PDF
    with no label of its own — verified against 3 real reports where the
    trailing town/county and the ENTIRE postcode landed on the next line,
    e.g.:
        "Current Address: 42 Rowleys Green Lane, Longford, Coventry CV6"
        "6AH"
    A naive single-line regex silently drops that continuation, truncating
    the postcode. Bare continuation lines (no ':' of their own — every real
    field label has one) are pulled in until the next labelled field/section
    or a blank line, capped at 2 lines so a parsing miss elsewhere can't run
    away and swallow unrelated report content — but ONLY when the line
    doesn't already end in a complete postcode: an address that's whole on
    one line must never reach past it and swallow the next unrelated line
    (e.g. a "Report generated ..." footer) just because that line also has
    no ':' of its own.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        low = line.lower()
        idx = low.find("current address:")
        if idx == -1:
            continue
        value = line[idx + len("current address:"):].strip()
        appended = 0
        j = i + 1
        while j < len(lines) and appended < 2 and not _FULL_POSTCODE_END_RE.search(value):
            nxt = lines[j].strip()
            if not nxt or ":" in nxt:
                break
            value += " " + nxt
            j += 1
            appended += 1
        return _clean_address(value)
    return ""


def _extract_report_date(text: str) -> str:
    """
    Extract the most recent "Last Update" date from the report.
    Returns ISO string or empty string.
    """
    dates = re.findall(r"Last Update:\s*(\d{4}-\d{2}-\d{2})", text)
    if dates:
        # Return the most recent one
        return sorted(dates)[-1]
    return ""


def _parse_missed_payments_last_3_months(lines: list[str]) -> int:
    """
    Parse the payment history grid and return missed payment count
    for the most recent 3 months.

    Grid structure after pdfplumber extraction:
      Balance line:  "£8,039 £7,496 ..."  (12 values)
      Missed line:   "3 0 0 0 ..."        (12 integers or D)
      Year label:    "2026" or "2025"

    The year label can appear before or after the value rows.
    We want the most recent 3 non-empty values from the missed row
    of the most recent year that has data.

    Strategy: find lines that are purely space-separated integers/D/-
    and are associated with the most recent year.
    """
    payment_row_re = re.compile(
        r"^[\s\d D\-]+$"
    )
    year_re = re.compile(r"^\d{4}$")

    current_year = None
    year_data: dict[int, list[str]] = {}

    for line in lines:
        stripped = line.strip()
        if year_re.match(stripped):
            current_year = int(stripped)
        elif current_year and payment_row_re.match(stripped):
            tokens = stripped.split()
            clean = [t for t in tokens if t == "D" or (t.isdigit() and int(t) <= 6)]
            if 1 <= len(clean) <= 12:
                if current_year not in year_data:
                    year_data[current_year] = clean

    if not year_data:
        return 0

    best_year = max(year_data.keys())
    values = year_data[best_year]

    # Most recent 3 months = last 3 values in the row
    recent = values[-3:]

    missed = 0
    for v in recent:
        if v == "D":
            missed += 1
        elif int(v) <= 6:
            missed += int(v)
        # else: discard — value above valid CAIS range, extraction artifact
    return missed


def _parse_worst_status_from_grid(lines: list[str]) -> str | None:
    """
    Aryza Advize has no labelled "Worst Status:" field like Experian does —
    it only reports the current "Account Status:". This scans the FULL
    payment-history grid (every year found, not just the most recent 3
    months used by _parse_missed_payments_last_3_months) to derive the same
    kind of worst-ever-recorded signal, so an account that is "Up to date"
    today but defaulted or ran up arrears earlier isn't waved through as
    clean just because its current status looks fine.

    Returns a string in the same vocabulary as Experian's Worst Status
    ("Default", "N Months Delinquent", "Satisfactory"), or None if no grid
    data was found at all.
    """
    payment_row_re = re.compile(r"^[\s\d D\-]+$")
    year_re = re.compile(r"^\d{4}$")

    current_year = None
    year_data: dict[int, list[str]] = {}

    for line in lines:
        stripped = line.strip()
        if year_re.match(stripped):
            current_year = int(stripped)
        elif current_year and payment_row_re.match(stripped):
            tokens = stripped.split()
            clean = [t for t in tokens if t == "D" or (t.isdigit() and int(t) <= 6)]
            if 1 <= len(clean) <= 12:
                if current_year not in year_data:
                    year_data[current_year] = clean

    all_values = [v for values in year_data.values() for v in values]
    if not all_values:
        return None

    if "D" in all_values:
        return "Default"

    worst = max(int(v) for v in all_values)
    if worst == 0:
        return "Satisfactory"
    return f"{worst} Month{'s' if worst != 1 else ''} Delinquent"


_KNOWN_SUBJECTIVE_LEVELS = {"Good", "Bad", "Fair", "Poor", "Satisfactory", "Excellent", "Unrated"}


def _determine_account_status(lines: list[str]) -> tuple[str, str]:
    """
    Extract raw account_status and account_status_subjective from Aryza Advize lines.
    Preserves raw labels with original capitalisation (e.g. 'Default', 'Up to date', 'Late payment').
    """
    account_status = ""
    account_status_subjective = ""

    # First pass: look for 'Account Status Subjective Level' in lines
    for line in lines:
        if "account status subjective level" in line.lower():
            low = line.lower()
            idx = low.find("account status subjective level")
            parts = line[idx:].split(":", 1)
            if len(parts) > 1:
                account_status_subjective = parts[1].strip()
                break

    # Second pass: extract 'Account Status' line
    for line in lines:
        low = line.lower()
        if "account status:" in low:
            idx = low.find("account status:")
            val = line[idx + len("account status:"):].strip()

            if "account status subjective level" in val.lower():
                subj_idx = val.lower().find("account status subjective level")
                status_part = val[:subj_idx].strip()
                account_status = status_part.rstrip(":").strip()
                if not account_status_subjective:
                    subj_part = val[subj_idx:]
                    if ":" in subj_part:
                        account_status_subjective = subj_part.split(":", 1)[1].strip()
            else:
                words = val.split()
                if len(words) > 1 and words[-1] in _KNOWN_SUBJECTIVE_LEVELS:
                    if not account_status_subjective:
                        account_status_subjective = words[-1]
                    account_status = " ".join(words[:-1])
                else:
                    account_status = val
            break

    return account_status, account_status_subjective



def _extract_monthly_payment_pence(lines: list[str]) -> int | None:
    """
    Extract the most recent monthly payment from the Payment Amount section (in pence).
    Returns None if the section is absent or all values are dashes.
    """
    in_payment_section = False
    year_re = re.compile(r"^(\d{4})\s+(.+)$")
    most_recent_payments: list[str] = []
    best_year = 0

    for line in lines:
        if "Payment Amount" in line:
            in_payment_section = True
            continue
        if not in_payment_section:
            continue
        if re.match(r"^[A-Z][a-z]+ [A-Z]", line) and "£" not in line:
            break
        m = year_re.match(line.strip())
        if m:
            yr = int(m.group(1))
            if yr > best_year:
                best_year = yr
                most_recent_payments = m.group(2).split()

    for val in reversed(most_recent_payments):
        if val == "-":
            continue
        amt = _parse_amount(val)
        if amt and amt > 0:
            return amt
    return None


def _has_recent_spending(lines: list[str]) -> bool:
    """
    Detect recent spending (last 3 months) from the Payment Amount grid.
    Look for the Payment Amount section and check the last 3 non-zero values
    in the most recent year.
    """
    in_payment_section = False
    year_re = re.compile(r"^(\d{4})\s+(.+)$")

    most_recent_payments: list[str] = []
    best_year = 0

    for line in lines:
        if "Payment Amount" in line:
            in_payment_section = True
            continue
        if not in_payment_section:
            continue
        # Stop at next section header
        if re.match(r"^[A-Z][a-z]+ [A-Z]", line) and "£" not in line:
            break

        m = year_re.match(line.strip())
        if m:
            yr = int(m.group(1))
            if yr > best_year:
                best_year = yr
                tokens = m.group(2).split()
                most_recent_payments = tokens

    if not most_recent_payments:
        return False

    # Check last 3 non-dash values
    non_dash = [t for t in most_recent_payments if t != "-"][-3:]
    for val in non_dash:
        amt = _parse_amount(val)
        if amt and amt > 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Experian CAIS format — constants and helpers
# ---------------------------------------------------------------------------

# Maps Experian account category text → internal Aryza-style type codes.
# These type codes feed into the same SKIP / CONDITIONAL filtering logic
# already used for Aryza Advize reports.
_EXPERIAN_CATEGORY_TO_TYPE: dict[str, str] = {
    "water": "UT",
    "electricity": "UT",
    "gas": "UT",
    "communications": "UT",
    "telecoms": "UT",
    "telecommunications": "UT",
    "current accounts": "CA",
    "current account": "CA",
    "savings accounts": "CA",
    "savings account": "CA",
    "credit cards": "CC",
    "credit card": "CC",
    "store cards": "CC",
    "store card": "CC",
    "personal loans": "PL",
    "personal loan": "PL",
    "unsecured loan (personal loan)": "PL",
    "unsecured loans (personal loan)": "PL",
    "unsecured loan": "UL",
    "unsecured loans": "UL",
    "secured loan": "MG",
    "secured loans": "MG",
    "running account credit": "CC",
    "revolving credit": "CC",
    "charge card": "CC",
    "hire purchase / conditional sale": "HP",
    "hire purchase": "HP",
    "conditional sale": "HP",
    "mortgages": "MG",
    "mortgage": "MG",
    "home credit": "UL",
    "mail order": "MO",
    "student loans": "UL",
    "student loan": "UL",
    "motor insurance": "OT",
    "insurance": "OT",
    "credit card / store card": "CC",
    "car insurance": "OT",
    "public utility": "UT",
    "utility": "UT",
}

# Matches Experian CAIS account header lines: "{CREDITOR NAME} - {Category}"
# The " - " separator (space-dash-space) distinguishes headers from inline dashes.
_EXPERIAN_HEADER_RE = re.compile(
    r"^(.+?)\s+-\s+("
    # Utilities
    r"Water|Electricity|Gas|Public Utility|Utility|"
    # Telecoms
    r"Communications?|Telecoms?|Telecommunications|"
    # Bank accounts
    r"Current Accounts?|Savings Accounts?|"
    # Credit / revolving
    r"Credit Cards?|Store Cards?|Credit Card / Store Card|Charge Cards?|Running Account Credit|Revolving Credit|"
    # Loans — includes Experian's "Unsecured Loan (Personal Loan)" parenthetical form
    r"Personal Loans?|Unsecured Loans?\s*(?:\([^)]*\))?|Secured Loans?|"
    # HP / conditional sale
    r"Hire Purchase.*?|Conditional Sale|"
    # Property
    r"Mortgages?|"
    # Other consumer
    r"Home Credit|Mail Order|Student Loans?|Motor Insurance|Car Insurance|Insurance"
    r")$",
    re.IGNORECASE,
)

# Fallback for any Experian CAIS header whose category isn't in the strict list above.
# Catches lines of the form "{CREDITOR NAME} - {Title Case Category}" that the
# primary regex missed. Safety constraints that prevent false positives on inner
# account-block lines:
#   - Group 1 starts with [A-Z0-9] (excludes bullet chars like •, allows numbers)
#   - Group 1 must NOT contain ':' (excludes field labels like "Status: Active - Default")
#   - Group 2 starts with [A-Z] and is 2–40 chars
# Accounts matched only by this fallback receive type_code "OT" (Other) because
# their category won't be in _EXPERIAN_CATEGORY_TO_TYPE — they pass all existing
# inclusion/exclusion filters unchanged, so they always surface for caseworker review.
_EXPERIAN_HEADER_FALLBACK_RE = re.compile(
    r"^([A-Z0-9][^:\n]{1,59}?)\s+-\s+([A-Z][A-Za-z0-9 /()\-]{1,39})$"
)



# ---------------------------------------------------------------------------
# Experian "bureau search" format (e.g. a Valid8IP-branded consumer credit
# report) — a second, structurally different Experian-sourced layout.
#
# Ground truth confirmed against a real report (pdfplumber text extraction):
# each CAIS record's block opens with the APPLICANT's own name (not the
# creditor), then an "Address:" line, then a bare status word on its own
# line (Active / Settled / Default), then labelled fields including
# "Company:" — which holds the actual creditor name several lines in.
# _EXPERIAN_HEADER_RE only matches "{Creditor} - {Category}" headers, which
# never occur in this layout at all, so _split_experian_accounts() returns
# zero blocks and the whole report's accounts are silently dropped (the
# extraction still reports "success" with accounts_found=0 — see
# CreditReportUploadView). This splitter recognises the real anchor
# instead: a status-word line immediately following an "Address:" line.
#
# The monthly grid in this format is also laid out differently to Aryza's:
# for each year, a status-code row is printed, THEN the year label, THEN
# the £-amount row (mojibake-encoded currency symbol) — status row and
# year label are reversed relative to what the existing Aryza grid parsers
# assume, so those are not reused here; balance is read directly off the
# "Current Balance:"/"Balance:" fields when present, falling back to the
# grid only for the handful of accounts (seen for Utility/Bank company
# types) that carry no balance field at all.
_VALID8_STATUS_WORDS = {"Active", "Settled", "Default"}

_VALID8_CATEGORY_TO_TYPE: dict[str, str] = {
    "credit card/store card": "CC",
    "current accounts": "CA",
    "public utility": "UT",
    "electricity": "UT",
    "gas": "UT",
    "water": "UT",
    "multi communications": "UT",
    "communications": "UT",
    "unsecured loan (personal loans etc)": "UL",
    "budget (revolving account)": "CC",
}


def _split_valid8_accounts(full_text: str) -> list[tuple[str, str]]:
    """
    Split the report into (address, block_text) pairs for the Valid8-style
    layout. A block starts at a bare status-word line that immediately
    follows an "Address:" line, and runs until the next such line.

    The "Address:" line itself is captured (not just used as an anchor) —
    it's the applicant's own address as recorded against that tradeline,
    not the creditor's. Multiple accounts usually repeat the same current
    address; a handful may differ if the client moved between accounts.
    """
    lines = full_text.split("\n")
    blocks: list[tuple[str, str]] = []
    current: list[str] | None = None
    current_address = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_anchor = (
            stripped in _VALID8_STATUS_WORDS
            and i > 0
            and lines[i - 1].strip().lower().startswith("address:")
        )
        if is_anchor:
            if current is not None:
                blocks.append((current_address, "\n".join(current)))
            current = [stripped]
            current_address = _clean_address(lines[i - 1].strip()[len("address:"):])
        elif current is not None:
            current.append(line)

    if current is not None:
        blocks.append((current_address, "\n".join(current)))

    return blocks


def _valid8_latest_grid_balance_pence(lines: list[str]) -> int | None:
    """
    Fallback balance source for accounts with no explicit "Current Balance:"
    or "Balance:" field: take the last (most recent) token of the most
    recent year's £-amount row.

    Grid order in this format is [status-code row, year label, amount row]
    — the amount row is the line immediately AFTER the year label.
    """
    year_re = re.compile(r"^\d{4}$")
    best_year = -1
    best_amount_line = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if year_re.match(stripped):
            year = int(stripped)
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if year > best_year and nxt:
                best_year = year
                best_amount_line = nxt

    if not best_amount_line:
        return None
    tokens = best_amount_line.split()
    return _parse_amount(tokens[-1]) if tokens else None


def _parse_valid8_account(address: str, block_text: str) -> dict | None:
    """
    Parse one Valid8-style account block into the same structured dict
    shape _parse_account_block()/_parse_experian_account() produce.
    Returns None only when the block carries no "Company:" field — the
    one field every real record in this format has (verified: 28/28 in
    the reference report) — since without it there is no creditor name
    to report against.

    `address` is the applicant's own address recorded against this
    tradeline (see _split_valid8_accounts) — not the creditor's.
    """
    lines = block_text.split("\n")

    raw_name = _extract_field(lines, "Company")
    if not raw_name:
        return None

    # _split_valid8_accounts() anchors each block on the bare status word
    # itself (Active/Settled/Default), so it is always line 0 — reading it
    # straight from there is exact, unlike re-deriving it from other fields.
    account_status = lines[0].strip() if lines else "Active"

    account_type = _extract_field(lines, "Account Type")
    type_code = _VALID8_CATEGORY_TO_TYPE.get(account_type.lower().strip(), "OT")

    start_date_str = _extract_field(lines, "Start Date")
    account_age_months = _months_since(start_date_str)

    # Balance precedence: explicit "Current Balance:" (Default-status
    # accounts always carry this) > explicit "Balance:" (either a £ amount
    # or the literal word "Settled", which _parse_amount safely returns
    # None for) > last grid value (the handful of accounts with no
    # balance field printed at all).
    current_balance = _parse_amount(_extract_field(lines, "Current Balance"))
    if current_balance is None:
        current_balance = _parse_amount(_extract_field(lines, "Balance"))
    if current_balance is None:
        current_balance = _valid8_latest_grid_balance_pence(lines)

    default_balance = _parse_amount(_extract_field(lines, "Default Balance"))
    credit_limit = _parse_amount(_extract_field(lines, "Credit Limit"))

    worst_status_raw = _extract_field(lines, "Worst Status")
    # e.g. "8 (Default)" / "2 (2 Month Delinquent)" / "0 (Satisfactory)" —
    # the parenthesised wording is the same vocabulary the rest of this
    # module already uses for worst_status, so keep only that part.
    m = re.search(r"\(([^)]+)\)", worst_status_raw)
    worst_status = m.group(1).strip() if m else (worst_status_raw or None)

    account_number_raw = _extract_field(lines, "Account No")
    account_number = account_number_raw if account_number_raw else None

    cais_updated_raw = _extract_field(lines, "CAIS Last Updated")
    cais_last_updated = cais_updated_raw if cais_updated_raw else None

    normalised = raw_name.lower().strip()
    matched = CREDITOR_ALIAS_MAP.get(normalised, raw_name)

    reconciliation_only = type_code in RECONCILIATION_ONLY_TYPE_CODES

    balance_display = round(current_balance / 100) if current_balance else 0
    logger.debug(
        f"[VALID8 INCLUDE] '{raw_name}' type={type_code} balance=£{balance_display} "
        f"status='{account_status}'"
    )

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": normalised,
        "matched_creditor": matched,
        "account_age_months": account_age_months,
        "missed_payments_last_3_months": 0,
        "recent_spending": False,
        "current_balance": current_balance,
        "default_balance": default_balance,
        "start_balance": None,
        "credit_limit": credit_limit,
        "utilisation_pct": None,
        "account_status": account_status,
        "account_status_subjective": None,
        "worst_status": worst_status,
        "payment_history_months": 0,
        "monthly_payment": None,
        "account_number": account_number,
        "start_date": normalise_start_date_iso(start_date_str),
        "cais_last_updated": cais_last_updated,
        "reconciliation_only": reconciliation_only,
        "address": address or None,
    }


def _months_since_dmy(date_str: str) -> int | None:
    """Parse a DD-MM-YYYY date string (Experian format) and return months since today."""
    if not date_str:
        return None
    try:
        start = datetime.strptime(date_str.strip(), "%d-%m-%Y").date()
        today = date.today()
        return (today.year - start.year) * 12 + (today.month - start.month)
    except ValueError:
        return None


def normalise_start_date_iso(date_str: str | None) -> str | None:
    """
    Normalise a credit-report account Start Date to ISO YYYY-MM-DD.

    Aryza Advize prints Start Date as YYYY-MM-DD; Experian CAIS prints it as
    DD-MM-YYYY. Both are emitted on the same `start_date` key, and downstream
    consumers (the CA Tool verification table) parse the value with JS
    `new Date()`, which reads "16-09-2021" as an Invalid Date. Normalising at
    the single point that produces the field keeps every consumer format-agnostic.

    Returns None when the value is missing or in no recognised format — better a
    blank cell than a date rendered with the day and month transposed.
    """
    if not date_str:
        return None
    raw = str(date_str).strip()
    # ISO first: a 4-digit leading year is unambiguous, so it can never be
    # mistaken for the day-first Experian layout.
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    logger.debug("[START DATE] unrecognised format %r — emitting None", raw)
    return None


#: The labels a report PRINTS its own date under, each with its dd/mm/yyyy
#: capture. ⚠️ ONLY PRINTED LABELS. `report_date` falls back to the latest
#: tradeline update ("Last Update" / "CAIS Last Updated"), which is when a
#: LENDER last reported, not when the search was run -- an Aryza Advize report
#: prints no date of its own at all (all 161 in media/credit_reports, checked
#: 2026-09-30). That derived value must never be passed off as the search date.
_PRINTED_REPORT_DATE_RES = (
    # Experian "Consumer Credit Report": "Issue Date and Time 04/03/2026 17:26:04"
    re.compile(r"Issue Date and Time\s+(\d{2}/\d{2}/\d{4})"),
    # Experian Valid8IP bureau search: "Search Date: 23/08/2026"
    re.compile(r"Search Date:\s*(\d{2}/\d{2}/\d{4})"),
)


def _extract_printed_report_date(page_one_text: str) -> str:
    """
    The date the report prints as its own issue / search date, ISO, or "".

    ⚠️ PAGE ONE ONLY. Both labels sit in the report header; a Valid8 report's
    CAPS section lists OTHER lenders' searches further in, and one of those
    must never be read as this report's date. Both bureaus print UK
    dd/mm/yyyy, so the format is fixed rather than guessed; an impossible
    date ("31/02/2026") returns "" rather than a coerced one.
    """
    for pattern in _PRINTED_REPORT_DATE_RES:
        m = pattern.search(page_one_text or "")
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                return ""
    return ""


def _extract_experian_report_date(text: str) -> str:
    """
    Extract the report date from an Experian consumer credit report.
    Looks for "Issue Date and Time DD/MM/YYYY" on page 1.
    Falls back to the most recent "CAIS Last Updated: DD-MM-YYYY" date.
    Returns ISO YYYY-MM-DD string, or empty string if not found.
    """
    m = re.search(r"Issue Date and Time\s+(\d{2}/\d{2}/\d{4})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    dates = re.findall(r"CAIS Last Updated:\s*(\d{2}-\d{2}-\d{4})", text)
    if dates:
        parsed = []
        for d in dates:
            try:
                parsed.append(datetime.strptime(d, "%d-%m-%Y"))
            except ValueError:
                pass
        if parsed:
            return max(parsed).strftime("%Y-%m-%d")
    return ""


def _parse_experian_status(lines: list[str]) -> str:
    """
    Derive raw capitalised status string from Experian fields ("Account Status:", "Status:", "Worst Status:").
    Preserves raw Experian wording (e.g. Default, Open, Late, Satisfied).
    """
    status_raw = _extract_field(lines, "Account Status") or _extract_field(lines, "Status")
    if status_raw:
        return status_raw.strip().capitalize()
    worst = _extract_field(lines, "Worst Status")
    if "default" in worst.lower():
        return "Default"
    return "Open"


# Keyword substrings (not an exact-value set) so real-world wording variants
# all match: "Month Delinquent" (missing its digit), "1 Month Delinquent",
# "2 Months Delinquent", "Late Payment", "Arrangement to Pay", etc.
_DEROGATORY_KEYWORDS = ("default", "delinquent", "late", "arrangement", "arrears", "collections")


def _is_derogatory_status(text: str) -> bool:
    """True if any derogatory/arrears keyword appears in the status text."""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in _DEROGATORY_KEYWORDS)


def _split_experian_accounts(full_text: str) -> list[tuple[str, str]]:
    """
    Split Experian CAIS report text into (header_line, block_text) tuples.
    Headers match the pattern "{CREDITOR NAME} - {Category}".
    """
    lines = full_text.split("\n")
    blocks: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _EXPERIAN_HEADER_RE.match(stripped) or _EXPERIAN_HEADER_FALLBACK_RE.match(stripped):
            if current_header is not None:
                blocks.append((current_header, "\n".join(current_lines)))
            current_header = stripped
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)

    if current_header is not None:
        blocks.append((current_header, "\n".join(current_lines)))

    return blocks


def _parse_experian_account(header: str, block_text: str) -> dict | None:
    """
    Parse one Experian CAIS account block into the same structured dict shape
    that _parse_account_block() produces for Aryza Advize reports.
    Returns None when the account should be excluded by type/status rules.
    """
    m = _EXPERIAN_HEADER_RE.match(header)
    if not m:
        m = _EXPERIAN_HEADER_FALLBACK_RE.match(header)
    if not m:
        return None

    raw_name = m.group(1).strip()
    category = m.group(2).strip()
    type_code = _EXPERIAN_CATEGORY_TO_TYPE.get(category.lower(), "OT")

    if "application type" in raw_name.lower():
        return None

    lines = block_text.split("\n")

    # Start date is DD-MM-YYYY in Experian (not YYYY-MM-DD like Aryza)
    start_date_str = _extract_field(lines, "Start Date")
    account_age_months = _months_since_dmy(start_date_str)

    raw_balance = _extract_field(lines, "Current Balance")
    current_balance = _parse_amount(raw_balance)

    # Experian does not provide a credit limit field; utilisation not applicable
    credit_limit = None
    utilisation_pct = None

    account_status = _parse_experian_status(lines)
    account_status_subjective = _extract_field(lines, "Account Status Subjective Level")
    worst_status = _extract_field(lines, "Worst Status")

    # Apply the same exclusion rules as the Aryza path

    reconciliation_only = False
    if type_code in RECONCILIATION_ONLY_TYPE_CODES:
        reconciliation_only = True

    # Name resolution via shared alias map
    normalised = raw_name.lower().strip()
    matched = CREDITOR_ALIAS_MAP.get(normalised, raw_name)

    # Reuse the existing missed-payments parser — grid format is the same
    missed_payments_last_3_months = _parse_missed_payments_last_3_months(lines)

    account_number_raw = _extract_field(lines, "Account Number")
    account_number = account_number_raw if account_number_raw else None

    start_balance_raw = _extract_field(lines, "Start Balance")
    start_balance = _parse_amount(start_balance_raw)

    cais_updated_raw = _extract_field(lines, "CAIS Last Updated")
    cais_last_updated = cais_updated_raw if cais_updated_raw else None

    balance_display = round(current_balance / 100) if current_balance else 0
    logger.debug(
        f"[EXPERIAN INCLUDE] '{raw_name}' type={type_code} balance=£{balance_display} status='{account_status}'"
    )

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": normalised,
        "matched_creditor": matched,
        "account_age_months": account_age_months,
        "missed_payments_last_3_months": missed_payments_last_3_months,
        "recent_spending": False,
        "current_balance": current_balance,
        "start_balance": start_balance,
        "credit_limit": credit_limit,
        "utilisation_pct": utilisation_pct,
        "account_status": account_status,
        "account_status_subjective": account_status_subjective,
        "worst_status": worst_status or None,
        "payment_history_months": 0,
        "monthly_payment": None,
        "account_number": account_number,
        "start_date": normalise_start_date_iso(start_date_str),
        "cais_last_updated": cais_last_updated,
        "reconciliation_only": reconciliation_only,
    }


# ---------------------------------------------------------------------------
# Public Information — CCJ / judgment extraction (both Aryza & Experian formats)
# ---------------------------------------------------------------------------

def _ccj_amount_to_pence(text: str) -> int | None:
    """Parse a CCJ amount string into pence. Tolerant of the '£' mojibake
    that pdfplumber sometimes produces (e.g. '�557.0')."""
    if not text:
        return None
    m = re.search(r"(\d[\d,]*\.?\d*)", text)
    if not m:
        return None
    try:
        return int(round(float(m.group(1).replace(",", "")) * 100))
    except ValueError:
        return None


def extract_public_information(full_text: str) -> dict:
    """
    Extract Public Information (CCJ / judgment, insolvency, debt-management)
    signals from a credit report, supporting both report formats:

      - Experian: a "Public Information" summary block plus per-record detail
        lines ("Type: Judgement - Judgement", "Amount: £…", "Settled: N",
        "Date: DD-MM-YYYY", then "Source:", "Court Name:", "Court Order
        Number:"). The detail records are CCJ-specific and are the primary
        signal.
      - Aryza Advize: an inline "CCJs and Insolvencies: N" combined count in
        the Debt Overview, AND a per-judgment block after the tradelines:

            CCJ County Court Judgment
            Court Details: Info:
            Case Number: L7KQ4M25 Satisfied Date: N/A
            Value: 2146
            Court Name: Civil National Business Centre
            Court Date: 2024-08-19 00:00:00

        ⚠️ THIS DOCSTRING USED TO SAY ARYZA HAS NO PER-RECORD BREAKDOWN. It
        does (verified against a production Aryza Advize report), and reading
        only the count meant every Aryza CCJ reached the case-assessment tool
        with no amount -- so it could never become evidence against a debt.

    ⚠️ NEITHER FORMAT NAMES THE CLAIMANT. Experian's "Source" is the register
    (Registry Trust), its "Court Name"/"Court Plaintif Number" are court
    codes, and Aryza's "Court Name" is the court. None is the creditor, so
    none is returned as one -- callers must not invent a creditor name.

    Returns:
        {
            "has_ccj": bool,
            "ccj_count": int,
            "ccj_total_pence": int | None,
            "ccjs": [ {"amount_pence", "settled", "date",
                       "case_number", "court_name"}, ... ],
            "iva_or_bankruptcy": bool,
            "debt_management": bool,
        }
    Never raises.
    """
    info = {
        "has_ccj": False,
        "ccj_count": 0,
        "ccj_total_pence": None,
        "ccjs": [],
        "iva_or_bankruptcy": False,
        "debt_management": False,
        "aoe_in_place": False,
    }
    if not full_text:
        return info

    lines = full_text.split("\n")

    def _field_in(window: list[str], label: str) -> str:
        prefix = label.lower() + ":"
        for ln in window:
            low = ln.lower()
            idx = low.find(prefix)
            if idx != -1:
                return ln[idx + len(prefix):].strip()
        return ""

    # --- Experian: per-record judgment detail blocks ---
    # Each record is anchored on a "Type: Judgement …" line; the Date/Amount/
    # Settled fields sit within a few lines either side of it.
    records = []
    for i, ln in enumerate(lines):
        if re.search(r"type:\s*judg", ln, re.IGNORECASE):
            window = lines[max(0, i - 4): i + 6]
            settled_raw = _field_in(window, "Settled")
            # The court fields sit AFTER the Type line (Source, Court Name,
            # Plaintif Number, Order Number), past the end of `window`. Read
            # forwards only, so a neighbouring record's fields are never taken.
            after = lines[i + 1: i + 9]
            records.append({
                "amount_pence": _ccj_amount_to_pence(_field_in(window, "Amount")),
                "settled": settled_raw.upper().startswith("Y") if settled_raw else None,
                "date": _field_in(window, "Date") or None,
                "case_number": _field_in(after, "Court Order Number") or None,
                "court_name": _field_in(after, "Court Name") or None,
            })

    # --- Aryza Advize: per-judgment "CCJ County Court Judgment" blocks ---
    # Anchored on the block's own header line; its fields follow within a few
    # lines, several sharing one line ("Case Number: X Satisfied Date: N/A"),
    # so each is read with a pattern that stops at the next label.
    if not records:
        for i, ln in enumerate(lines):
            if not re.match(r"^\s*CCJ\s+County\s+Court\s+Judg", ln, re.IGNORECASE):
                continue
            block = []
            for nxt in lines[i + 1: i + 9]:
                if re.match(r"^\s*CCJ\s+County\s+Court\s+Judg", nxt, re.IGNORECASE):
                    break
                block.append(nxt)
            text = "\n".join(block)

            def _grab(pattern):
                m = re.search(pattern, text, re.IGNORECASE)
                return m.group(1).strip() if m else ""

            satisfied = _grab(r"Satisfied Date:\s*(\S+)")
            records.append({
                "amount_pence": _ccj_amount_to_pence(_grab(r"Value:\s*(\S+)")),
                # "N/A" = not satisfied; a date = satisfied; absent = unknown.
                "settled": (None if not satisfied
                            else satisfied.upper() not in ("N/A", "-", "NONE")),
                "date": _grab(r"Court Date:\s*(\d{4}-\d{2}-\d{2})") or None,
                "case_number": _grab(r"Case Number:\s*(\S+)") or None,
                "court_name": _grab(r"Court Name:\s*(.+)") or None,
            })

    # --- Aryza Advize: combined "CCJs and Insolvencies: N" summary ---
    aryza_m = re.search(r"CCJ['s]*\s+and\s+Insolvencies:\s*(\d+)", full_text, re.IGNORECASE)
    aryza_count = int(aryza_m.group(1)) if aryza_m else None

    # --- Experian summary fallback: "Public Information … Number: N" ---
    exp_num_m = re.search(
        r"Public Information\b[\s\S]{0,80}?Number:\s*(\d+)", full_text, re.IGNORECASE
    )
    exp_num = int(exp_num_m.group(1)) if exp_num_m else None

    if records:
        info["ccjs"] = records
        info["ccj_count"] = len(records)
        info["has_ccj"] = True
        amounts = [r["amount_pence"] for r in records if r["amount_pence"]]
        info["ccj_total_pence"] = sum(amounts) if amounts else None
    elif aryza_count is not None and aryza_count > 0:
        # Aryza exposes only a combined CCJ+insolvency count with no detail.
        info["ccj_count"] = aryza_count
        info["has_ccj"] = True
    elif exp_num is not None and exp_num > 0:
        info["ccj_count"] = exp_num
        info["has_ccj"] = True

    iva_m = re.search(r"IVA or Bankruptcy Detected:\s*(\w)", full_text, re.IGNORECASE)
    info["iva_or_bankruptcy"] = bool(iva_m and iva_m.group(1).upper() == "Y")
    dm_m = re.search(r"Debt Management:\s*(\w)", full_text, re.IGNORECASE)
    info["debt_management"] = bool(dm_m and dm_m.group(1).upper() == "Y")

    # Attachment of Earnings detection — Experian and Aryza Advize formats
    _aoe_patterns = [
        r"type:\s*attachment",
        r"attachment\s+of\s+earnings",
        r"\bAoE\s+Order\b",
        r"\bAttachment\s+Order\b",
        r"earnings\s+arrestment",   # Scottish equivalent
    ]
    info["aoe_in_place"] = any(
        re.search(p, full_text, re.IGNORECASE)
        for p in _aoe_patterns
    )

    return info


# ---------------------------------------------------------------------------
# Account block splitter
# ---------------------------------------------------------------------------

def _split_into_account_blocks(full_text: str) -> list[tuple[str, str]]:
    """
    Split the full PDF text into (header_line, block_text) tuples.

    Account headers match "{Name} {TYPE_CODE}" at the start of a line, where
    TYPE_CODE is a known code from _TYPE_CODE_RE. Headers carrying an UNKNOWN
    two-letter code are also recognised, via _ARYZA_FALLBACK_HEADER_RE, provided
    the next line is the "Account Details" line that always follows a real
    header. Those are logged as warnings so a newly-introduced Aryza code shows
    up as a signal instead of silently swallowing an account's balance.
    """
    lines = full_text.split("\n")
    blocks: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        is_header = bool(_TYPE_CODE_RE.match(stripped))

        if not is_header:
            fallback = _ARYZA_FALLBACK_HEADER_RE.match(stripped)
            # Only trust the loose pattern when the following line is the
            # "Account Details" line that every real account header precedes.
            # Guarding on that is what keeps payment-grid rows and address
            # lines from being mistaken for headers.
            if fallback and "Account Details" in " ".join(lines[idx + 1:idx + 3]):
                is_header = True
                logger.warning(
                    "[EXTRACTOR] unknown Aryza account type code %r on header %r "
                    "— account included via fallback; add the code to "
                    "_TYPE_CODE_RE (and RECONCILIATION_ONLY_TYPE_CODES if it is "
                    "not unsecured debt)",
                    fallback.group(2), stripped,
                )

        if is_header:
            # Save previous block
            if current_header is not None:
                blocks.append((current_header, "\n".join(current_lines)))
            current_header = stripped
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)

    # Last block
    if current_header is not None:
        blocks.append((current_header, "\n".join(current_lines)))

    return blocks


# ---------------------------------------------------------------------------
# Single account parser
# ---------------------------------------------------------------------------

def _parse_account_block(header: str, block_text: str) -> dict | None:
    """
    Parse one account block into structured data.
    Returns None only if the header is unparseable.
    """
    m = _TYPE_CODE_RE.match(header)
    if not m:
        # Must accept the same fallback headers _split_into_account_blocks
        # accepted, or an unknown-code account would be split into its own
        # block and then dropped here — the exact silent data loss the
        # fallback exists to prevent.
        m = _ARYZA_FALLBACK_HEADER_RE.match(header)
    if not m:
        return None

    raw_name = m.group(1).strip()
    type_code = m.group(2).strip()

    lines = block_text.split("\n")

    # --- Core fields ---
    start_date_str = _extract_field(lines, "Start Date")
    account_age_months = _months_since(start_date_str)

    raw_balance = _extract_field(lines, "Current Balance")
    current_balance = _parse_amount(raw_balance)

    raw_limit = _extract_field(lines, "Credit Limit")
    credit_limit = _parse_amount(raw_limit)

    raw_default = _extract_field(lines, "Default Balance")
    default_balance = _parse_amount(raw_default)

    # --- Utilisation ---
    utilisation_pct: float | None = None
    if current_balance is not None and credit_limit and credit_limit > 0:
        utilisation_pct = round((current_balance / credit_limit) * 100, 1)

    # --- Status ---
    account_status, account_status_subjective = _determine_account_status(lines)
    worst_status = _parse_worst_status_from_grid(lines)

    # --- Payment history depth ---
    year_rows = re.findall(r"^\d{4}\b", block_text, re.MULTILINE)
    payment_history_months = len(set(year_rows)) * 12  # approximate

    # --- Missed payments last 3 months ---
    missed_payments_last_3_months = _parse_missed_payments_last_3_months(lines)

    # --- Recent spending ---
    recent_spending = _has_recent_spending(lines)

    # --- Monthly payment (from Payment Amount section) ---
    monthly_payment = _extract_monthly_payment_pence(lines)

    # --- Name resolution ---
    normalised = raw_name.lower().strip()
    matched = CREDITOR_ALIAS_MAP.get(normalised, raw_name)

    # --- Conditional type code filtering ---

    # MG: mortgage accounts are always included for asset reconciliation
    # (not counted as unsecured IVA debt — separated by caller)



    # Decide whether this account is unsecured IVA debt or "reconciliation
    # only" (extracted for the assessment table, but never counted as debt).
    #
    #  - MI / MU (motor insurance, multi-comms): never debt.
    reconciliation_only = False
    if type_code in RECONCILIATION_ONLY_TYPE_CODES:
        reconciliation_only = True

    balance_display = round(current_balance / 100) if current_balance else 0
    logger.debug(
        f"[EXTRACTOR INCLUDE] '{raw_name}' type={type_code} balance=£{balance_display} "
        f"reconciliation_only={reconciliation_only}"
    )

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        "normalised_name": normalised,
        "matched_creditor": matched,
        "start_date": normalise_start_date_iso(start_date_str),
        "account_age_months": account_age_months,
        "missed_payments_last_3_months": missed_payments_last_3_months,
        "recent_spending": recent_spending,
        "current_balance": current_balance,
        # Parsed above but never returned, so no caller could see a default
        # balance on an Aryza report (the Valid8 layout already returns it).
        "default_balance": default_balance,
        "credit_limit": credit_limit,
        "utilisation_pct": utilisation_pct,
        "account_status": account_status,
        "account_status_subjective": account_status_subjective,
        "worst_status": worst_status,
        "payment_history_months": payment_history_months,
        "monthly_payment": monthly_payment,
        "reconciliation_only": reconciliation_only,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_credit_report(pdf_path: str) -> dict:
    """
    Extract structured per-creditor data from an Aryza Advize credit report PDF.

    Returns:
        {
            "agency": str,
            "client_name": str,
            "report_date": str,
            "printed_report_date": str,   # ISO; "" when none is printed
            "accounts": [list of parsed account dicts],
            "unmatched_accounts": [raw names with no alias map hit]
        }

    Never raises. On any exception returns dict with "extraction_error" key.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_texts = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(page_texts)

        printed_report_date = _extract_printed_report_date(page_texts[0] if page_texts else "")
        agency = _detect_agency(full_text)
        client_name = _extract_client_name(full_text)
        public_info = extract_public_information(full_text)

        accounts: list[dict] = []
        mortgage_accounts: list[dict] = []
        other_accounts: list[dict] = []
        unmatched: list[str] = []

        if agency == "Experian":
            # ----------------------------------------------------------------
            # Experian Consumer Credit Report (CAIS format)
            # Headers: "{CREDITOR NAME} - {Category}"
            # Date format: DD-MM-YYYY
            # ----------------------------------------------------------------
            report_date = printed_report_date or _extract_experian_report_date(full_text)

            # Try the Valid8IP-style bureau-search layout FIRST. Its anchor
            # (a status word right after "Address:", with a "Company:"
            # field for the real creditor name) only ever matches genuine
            # CAIS account records. The standard "{Creditor} - {Category}"
            # header's fallback regex is looser and produces false
            # positives on OTHER sections of this same report shape (e.g.
            # the Voters Roll's "Main Applicant - Current Address" /
            # "Undisclosed - Undisclosed Address" lines match its "{X} -
            # {Y}" pattern) — so checking "did the standard path find
            # anything" is not a safe gate for whether to try this one;
            # a report is one layout or the other, never both, so Valid8
            # blocks (when present) always take precedence.
            parsed_accounts = []
            client_address = ""
            valid8_blocks = _split_valid8_accounts(full_text)
            for address, block_text in valid8_blocks:
                parsed = _parse_valid8_account(address, block_text)
                if parsed is not None:
                    parsed_accounts.append(parsed)
                    if not client_address and parsed.get("address"):
                        # Every account normally repeats the client's current
                        # address; take the first non-empty one seen.
                        client_address = parsed["address"]

            if parsed_accounts:
                logger.info(
                    "[EXTRACTOR] Experian report matched via Valid8-style "
                    "layout: %d accounts", len(parsed_accounts),
                )
            else:
                blocks = _split_experian_accounts(full_text)
                for header, block_text in blocks:
                    parsed = _parse_experian_account(header, block_text)
                    if parsed is not None:
                        parsed_accounts.append(parsed)

            for parsed in parsed_accounts:
                if parsed.get("reconciliation_only"):
                    other_accounts.append(parsed)
                elif parsed["type_code"] == "MG":
                    mortgage_accounts.append(parsed)
                else:
                    accounts.append(parsed)
                    if parsed["matched_creditor"] == parsed["raw_name"]:
                        unmatched.append(parsed["raw_name"])

            if not client_address:
                # Neither Experian sub-layout above carries a per-record
                # address to fall back on here (classic CAIS has none at
                # all; Valid8 would already have set client_address if it
                # matched). But a third, genuine-Experian "Consumer Credit
                # Report" layout exists (verified against a real production
                # report) that isn't anchored by either splitter — it uses
                # the exact same bullet-prefixed "Current Address: {addr}"
                # summary field as Aryza Advize (bullet: "Applicant:",
                # "Current Address:", "Voters Roll:", ...). Reusing the
                # Aryza extractor here (it already tolerates the bullet
                # prefix and the line-wrap this format also exhibits) covers
                # that layout without a fourth parser.
                client_address = _extract_client_address(full_text)
        else:
            # ----------------------------------------------------------------
            # Aryza Advize format (original path — unchanged)
            # Headers: "{Creditor Name} {TYPE_CODE}"
            # Date format: YYYY-MM-DD
            # ----------------------------------------------------------------
            report_date = _extract_report_date(full_text)
            client_address = _extract_client_address(full_text)
            blocks = _split_into_account_blocks(full_text)
            for header, block_text in blocks:
                parsed = _parse_account_block(header, block_text)
                if parsed is None:
                    continue  # header did not parse
                if parsed.get("reconciliation_only"):
                    # Non-debt tradelines (insurance, multi-comms). Not IVA
                    # debt, but returned separately so the assessment app can
                    # show their credit-report balance in the reconciliation
                    # table.
                    other_accounts.append(parsed)
                elif parsed["type_code"] == "MG":
                    # Mortgages are secured — excluded from IVA criteria but
                    # included separately so the case assessment app can compare
                    # them against CRM property data in the Assets & Property section.
                    mortgage_accounts.append(parsed)
                else:
                    accounts.append(parsed)
                    if parsed["matched_creditor"] == parsed["raw_name"]:
                        unmatched.append(parsed["raw_name"])

        return {
            "agency": agency,
            "client_name": client_name,
            "client_address": client_address,
            "report_date": report_date,
            # The printed issue / search date only, "" when the report
            # prints none -- see `_PRINTED_REPORT_DATE_RES`.
            "printed_report_date": printed_report_date,
            "accounts": accounts,
            "mortgage_accounts": mortgage_accounts,
            "other_accounts": other_accounts,
            "unmatched_accounts": unmatched,
            "public_information": public_info,
            "has_ccj": public_info["has_ccj"],
            "aoe_in_place": public_info.get("aoe_in_place", False),
        }

    except Exception as e:
        logger.error(f"Credit report extraction failed for {pdf_path}: {e}", exc_info=True)
        return {
            "agency": "Unknown",
            "client_name": "",
            "report_date": "",
            "printed_report_date": "",
            "accounts": [],
            "unmatched_accounts": [],
            "extraction_error": str(e),
        }
