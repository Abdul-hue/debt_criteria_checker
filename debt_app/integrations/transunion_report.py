"""
integrations/transunion_report.py

The TransUnion consumer credit report -- its "SHARE" layout, as a Valid8
TransUnion search prints it (2026-11-25, case 438769).

⚠️ BEFORE THIS NO TRANSUNION REPORT HAD ANY ACCOUNT READ. `_detect_agency`
named it "TransUnion" but only Experian had a branch of its own, so the report
fell through to the Aryza Advize reader, which looks for "{Name} {TYPE_CODE}"
headers -- this layout has none. 438769 came out with 0 of its 45 accounts,
and every debt Aryza declared (Abound £13,897, MBNA £8,059, Monzo £6,775,
Payment Assist £106, PayPal £131 -- all on the report, to the pound) read
"Aryza only, needs proof of debt".

Layout (verified on that report, 47 pages, 45 accounts):

    Financial Account Information (SHARE)     <- the accounts' section
    Closed Accounts                            <- a sub-section (also Credit
                                                  Cards, Other Accounts, ...)
    Mr Stephen Gilbert || 4322903 || || 30 Foxdown ... || 12/07/1985 11/10/2024 00:00:00 || ||
    Lender: Rci Financial Services LTD        Opening Balance: £7,995.00
    Balance: £2,998.00                        Regular Pay Amount: £272.00
    ... two columns of "Label: value" ...
    Balance History                           <- a grid; also Payment,
        Jan Feb ... Dec                          Limit, Statement Balance
    2026 £5,452 £5,179 ...                       and Status History
    2025 ...
    Status History
        Jan Feb ... Dec
    2026 Ok Ok ...

Then "Search History" (CAPS), "Address Links", "MODA", "Cifas".

⚠️ READ FROM WORD POSITIONS, NEVER THE TEXT LINE. The grids' columns are of
uneven width, each value centred under its month, so the text layer moves
values between months: on Monzo's grid "Nov" and "Dec" land on the amount
row. A value is placed under the month whose header centre is nearest its
own centre. A status can wrap ("Dormant/inactive" / "account") onto a line
of its own, which joins the cell above it; a long status ("Unclassified or
recently opened account payment delay") spreads over neighbouring columns,
so the words of one cell are joined first and the cell placed by its centre.
A grid can cross a page: its columns and year are carried over.

⚠️ THE SAME LAYOUT COMES AT DIFFERENT SIZES (2026-11-09 report, 76 accounts,
read 2026-11-25): everything 1.27x further right than on 438769. Positions are
therefore the report's own (see `_HEADING_MARGIN_TOLERANCE`). That report also
showed: month names printed with no gap ("AugSep", "OctNovDec" -- split, else
the grid was lost: 4 of its 181), an account line wrapped by a long address
("... || 22/08/2023" then "00:00:00 ||" -- joined, else the account's holder
read "00:00:00"), and an empty sub-section's "No data was retrieved for this
section" (never a cell). "Early arrears" and "Query (account under review)"
are printed month statuses with no code here yet: kept as printed, so never
read as paid.

⚠️ ONLY THE SHARE SECTION. MODA repeats accounts that "will also appear in
the Financial Account Information section" -- read there too, every debt
would be counted twice. Reading stops at the next top-level heading.

⚠️ THE BALANCE IS THE ACCOUNT'S OWN "Balance:" LINE (user, 2026-11-25), the
grid's newest month only when an account prints none -- the order the Valid8
Experian reader keeps (`credit_report._parse_valid8_account`). All 45 accounts
on 438769 print one, and it equals the grid's newest month on every one.

⚠️ STATUS WORDS BECOME THE BUREAU CODES CAT ALREADY READS. "Ok" is "0" (paid
on time), "Dormant/inactive account" "D", a default "8", "1".."6" payments
behind -- Experian's codes, so CAT reads them as Experian's
(`uses_experian_codes`: "D" dormant, "8" default). A word not known here is
kept AS PRINTED: CAT counts only "0" as paid, so an unknown word can never be
read as a payment made. The printed words are kept beside every code.

⚠️ NOTHING PRINTED IS DROPPED. Every "Label: value" an account prints is kept
in `report_fields` as printed, and every grid in full, so a field this reader
does not interpret is still on the extraction.

Public information: a TransUnion report with a judgment or an insolvency has
not been seen, so their layout is unknown. Either section holding anything
but "No data was retrieved" is taken as PRESENT (a CCJ / an insolvency) and
logged -- never read as a clean file.
"""
from __future__ import annotations

import logging
import re

from debt_app.integrations.account_categories import SOURCE_TRANSUNION_PDF, type_source

logger = logging.getLogger(__name__)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTH_NUMBER = {name.lower(): i + 1 for i, name in enumerate(_MONTHS)}

#: The accounts' section heading -- TransUnion's own name for its shared
#: account data. Its presence is what marks this layout.
_SHARE_HEADING_RE = re.compile(r"^\s*Financial Account Information \(SHARE\)\s*$", re.M)

#: Top-level headings that END the accounts' section (the report's table of
#: contents, plus "Search History", which is how CAPS is titled in the body).
_TOP_LEVEL_RE = re.compile(
    r"^(Summary|Notices of Correction|Electoral Roll|Aliases and Associations|"
    r"Public Information|Search History|CAPS\b.*|Address Links|MODA|Cifas)"
    r"(\s+\d+\s+Records?)?$",
    re.IGNORECASE,
)

#: Words of one line closer than this (points) belong to one phrase.
#: Measured on 438769's every grid row: words of one cell at most 1.5pt
#: apart ("Unclassified or recently ..."), neighbouring cells at least
#: 4.96pt ("Dormant/inactive" side by side, the tightest columns).
_PHRASE_GAP = 3.0
#: Parts of one line further apart than this are separate "Label: value"
#: fields -- the two field columns sit ~100pt apart.
_FIELD_GAP = 12.0
#: Words this close in height share a line. Status badges ("Up to date",
#: "Good") sit ~1pt below their label.
_LINE_TOLERANCE = 2.5
#: ⚠️ NO FIXED POSITIONS ACROSS THE PAGE (2026-11-25, the 2026-11-09 report).
#: The same layout is printed at different sizes: one report has everything
#: 1.27x further right than 438769's (sub-section headings at x0 20.1 against
#: 15.8, field labels 26.4 against 20.7, year labels' right edge 51.5 against
#: 40.4). A fixed "heading left of 19pt" read no heading at all on it -- no
#: account marked closed -- so positions are taken from the report itself:
#:   * a sub-section heading starts at the section's left margin, where the
#:     introduction line under the SHARE heading starts (or left of the field
#:     labels by this much, before that is known);
#:   * a grid's continuation line (a wrapped status) starts right of the year
#:     label above it.
_HEADING_MARGIN_TOLERANCE = 2.0
_HEADING_LEFT_OF_LABELS = 3.0
#: An account line has six "||" ("Name || id || || address || dates || end ||").
#: One with fewer that is followed by another "||" line before any field has
#: wrapped (a long address: "... || 22/08/2023" then "00:00:00 ||").
_ACCOUNT_LINE_BARS = 6
#: Printed under a heading or grid that holds nothing -- never a cell. One
#: constant for the accounts and the public information (lowercase).
_NO_DATA = "no data was retrieved for this section"

#: The report's account types (`Account Type Name`) where it words them
#: differently from Experian -- the Experian map
#: (`credit_report._EXPERIAN_CATEGORY_TO_TYPE`) is read for the rest, so the
#: same wording types alike on every report. EXACT WORDINGS ONLY: anything
#: else is "OT" and marked `type_unmapped`.
#:   * "Deferred Payment Credit" (PayPal Pay in 3) is "DP", as the Valid8
#:     map's "BNPL/Deferred Payment" and an Aryza Advize "DP".
#:   * "Telecommunications Supplier" is "TM" -- CAT already reads that
#:     wording as telecom (`ledger/credit_report.py :: _TELECOM_SOURCE_TYPES`).
#: "Loan (unspecified type)" is left "OT": whether secured is not said.
_TU_TYPE_TO_CODE: dict[str, str] = {
    "deferred payment credit": "DP",
    "telecommunications supplier": "TM",
}

#: A month's status, as printed, to the bureau code CAT reads (see module
#: docstring). Keys are lowercase, single-spaced.
_STATUS_CODES: dict[str, str] = {
    "ok": "0",
    "up to date": "0",
    "dormant/inactive account": "D",
    "dormant": "D",
    "inactive": "D",
    "default": "8",
    "defaulted": "8",
    "settled/closed": "S",
    "settled": "S",
    "closed": "S",
    "unclassified or recently opened account payment delay": "U",
    "unclassified": "U",
}
#: "2 payments late", "1 month in arrears", "3 missed payments" ...
_ARREARS_RE = re.compile(r"^(\d)\b.*\b(late|missed|behind|arrears)\b")


def is_transunion_share_report(full_text: str) -> bool:
    """True when the text carries TransUnion's "Financial Account Information
    (SHARE)" section heading. Holds for a SHARE report with no accounts too,
    so it is never handed to another reader."""
    return bool(_SHARE_HEADING_RE.search(full_text or ""))


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

def _lines(page) -> list[list[dict]]:
    """The page's words as lines (top to bottom), each left to right."""
    lines: list[tuple[float, list[dict]]] = []
    for word in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0] - word["top"]) <= _LINE_TOLERANCE:
            lines[-1][1].append(word)
        else:
            lines.append((word["top"], [word]))
    return [sorted(words, key=lambda w: w["x0"]) for _top, words in lines]


def _groups(words: list[dict], gap: float) -> list[list[dict]]:
    """Consecutive words split wherever the space between two exceeds `gap`."""
    out: list[list[dict]] = []
    for word in words:
        if out and word["x0"] - out[-1][-1]["x1"] <= gap:
            out[-1].append(word)
        else:
            out.append([word])
    return out


def _text(words: list[dict]) -> str:
    return " ".join(w["text"] for w in words)


def _centre(words: list[dict]) -> float:
    return (words[0]["x0"] + words[-1]["x1"]) / 2


_RUN_TOGETHER_MONTHS_RE = re.compile(
    r"(?:" + "|".join(m.lower() for m in _MONTHS) + r"){2,12}")


def _split_months(word: dict) -> list[dict]:
    """A word of month names printed with no gap ("AugSep", "JanFebMar" --
    narrow columns over wide cells) as one word per month, each a share of
    the width (every name is three letters); any other word unchanged."""
    text = word["text"]
    if not _RUN_TOGETHER_MONTHS_RE.fullmatch(text.lower()):
        return [word]
    count = len(text) // 3
    width = (word["x1"] - word["x0"]) / count
    return [{**word, "text": text[i * 3:i * 3 + 3],
             "x0": word["x0"] + i * width, "x1": word["x0"] + (i + 1) * width}
            for i in range(count)]


def _month_header(words: list[dict]) -> list[tuple[int, float]] | None:
    """[(month 1-12, column centre)] for a "Jan Feb ... Dec" line -- a leading
    year allowed, names printed together ("OctNovDec") split -- else None."""
    names = words[1:] if words and re.fullmatch(r"\d{4}", words[0]["text"]) else words
    names = [part for w in names for part in _split_months(w)]
    if not names or any(w["text"].lower() not in _MONTH_NUMBER for w in names):
        return None
    months = [_MONTH_NUMBER[w["text"].lower()] for w in names]
    if months != sorted(set(months)):
        return None
    return [(m, (w["x0"] + w["x1"]) / 2) for m, w in zip(months, names)]


def _nearest_month(columns: list[tuple[int, float]], x: float) -> int:
    return min(columns, key=lambda c: abs(c[1] - x))[0]


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _amount_pence(text: str | None) -> int | None:
    """"£6,775.00", "-£30.00", a mojibake pound sign alike, in pence."""
    from debt_app.integrations.credit_report import _parse_amount
    text = (text or "").strip()
    negative = text.startswith("-")
    pence = _parse_amount(text[1:] if negative else text)
    return -pence if negative and pence is not None else pence


def status_code(printed: str) -> str:
    """The bureau code for a month's printed status, or the printed words
    themselves when they are not known (never read as paid)."""
    words = " ".join(str(printed or "").lower().split())
    if words in _STATUS_CODES:
        return _STATUS_CODES[words]
    match = _ARREARS_RE.match(words)
    if match and 1 <= int(match.group(1)) <= 6:
        return match.group(1)
    if words:
        logger.warning("[TRANSUNION] unknown month status %r kept as printed", printed)
    return " ".join(str(printed or "").split())


def _iso(date_text: str | None) -> str | None:
    from debt_app.integrations.credit_report import normalise_start_date_iso
    return normalise_start_date_iso((date_text or "").split()[0] if (date_text or "").split() else None)


def _history(cells: dict, value_of) -> list[dict]:
    """A grid as [{"month": "YYYY-MM", "value": ...}], oldest first."""
    out = []
    for (year, month), text in sorted(cells.items()):
        out.append({"month": f"{year:04d}-{month:02d}", "value": value_of(text), "printed": text})
    return out


def _amount_history(cells: dict | None) -> list[dict]:
    return [{"month": e["month"], "amount": e["value"]}
            for e in _history(cells or {}, _amount_pence) if e["value"] is not None]


def _newest_amount(history: list[dict]) -> int | None:
    return history[-1]["amount"] if history else None


# ---------------------------------------------------------------------------
# One account
# ---------------------------------------------------------------------------

def _parse_header(text: str) -> dict:
    """The account line: "Name || id || || address || dob start || end || ||".
    The applicant as the LENDER holds them -- name spelling and address may
    differ from the report's subject ("Steven Gilbert" at Payment Assist)."""
    parts = [p.strip() for p in text.split("||")]
    dates = re.findall(r"\d{2}/\d{2}/\d{4}", parts[4] if len(parts) > 4 else "")
    return {
        "account_holder": parts[0] if parts else "",
        "address": parts[3] if len(parts) > 3 else "",
        "date_of_birth": _iso(dates[0]) if dates else None,
    }


def _missed_last_3(codes: list[str]) -> int:
    """Payments missed in the newest three reported months -- the measure the
    Aryza Advize reader gives (`_parse_missed_payments_last_3_months`): each
    month's arrears count, a default counting one."""
    missed = 0
    for code in codes[-3:]:
        if code.isdigit() and 1 <= int(code) <= 6:
            missed += int(code)
        elif code == "8":
            missed += 1
    return missed


def _worst_status(codes: list[str]) -> str | None:
    """The worst month on record, in the words the other readers give
    ("Default", "N Months Delinquent", "Satisfactory"), or None with no
    paid / behind / default month to judge by."""
    if "8" in codes:
        return "Default"
    behind = [int(c) for c in codes if c.isdigit() and 1 <= int(c) <= 6]
    if behind:
        worst = max(behind)
        return f"{worst} Month{'s' if worst != 1 else ''} Delinquent"
    return "Satisfactory" if "0" in codes else None


def _build_account(raw: dict) -> dict | None:
    """One account's dict, in the shape the other readers give
    (`credit_report._parse_valid8_account`), or None with no lender."""
    from debt_app.integrations.credit_report import (
        CREDITOR_ALIAS_MAP, RECONCILIATION_ONLY_TYPE_CODES,
        _EXPERIAN_CATEGORY_TO_TYPE, _months_since, _status_history_fields,
    )

    fields: dict[str, str] = raw["fields"]
    raw_name = " ".join(fields.get("Lender", "").split())
    if not raw_name:
        logger.warning("[TRANSUNION] an account with no Lender line was skipped: %r", fields)
        return None

    account_type = " ".join(fields.get("Account Type Name", "").split())
    type_key = account_type.lower()
    type_code = _TU_TYPE_TO_CODE.get(type_key) or _EXPERIAN_CATEGORY_TO_TYPE.get(type_key) or "OT"
    type_unmapped = type_key not in _TU_TYPE_TO_CODE and type_key not in _EXPERIAN_CATEGORY_TO_TYPE

    grids: dict[str, dict] = raw["grids"]
    balance_history = _amount_history(grids.get("Balance"))
    payment_history = _amount_history(grids.get("Payment"))
    limit_history = _amount_history(grids.get("Limit"))
    statement_history = _amount_history(grids.get("Statement Balance"))

    # The balance: its own "Balance:" line ("Settled" is £0), else the
    # grid's newest month -- see the module docstring.
    own = fields.get("Balance", "").strip()
    current_balance = 0 if own.lower() == "settled" else _amount_pence(own)
    if current_balance is None:
        current_balance = _newest_amount(balance_history)

    credit_limit = _amount_pence(fields.get("Credit Limit")) or _newest_amount(limit_history)
    utilisation_pct = (round(current_balance / credit_limit * 100, 1)
                       if current_balance is not None and credit_limit else None)

    # The newest year's latest non-zero payment, as the Aryza Advize reader
    # takes it from its Payment Amount grid (`_extract_monthly_payment_pence`).
    monthly_payment = None
    if payment_history:
        newest_year = payment_history[-1]["month"][:4]
        monthly_payment = next((e["amount"] for e in reversed(payment_history)
                                if e["month"][:4] == newest_year and e["amount"] > 0), None)
    recent_spending = any(e["amount"] > 0 for e in payment_history[-3:])

    balances_by_month = {e["month"]: e["amount"] for e in balance_history}
    status_history = [
        {"month": e["month"], "status": status_code(e["printed"]),
         "status_printed": " ".join(e["printed"].split()),
         "balance": balances_by_month.get(e["month"])}
        for e in _history(grids.get("Status") or {}, str)
    ]
    codes = [e["status"] for e in status_history]

    frequency = " ".join(fields.get("Repayment Frequency", "").split())
    regular = _amount_pence(fields.get("Regular Pay Amount"))

    # "100227757920 0", "609468744 2": every account number on the report
    # ends in a separate single digit -- TransUnion's suffix field, not part
    # of the number a letter quotes. Kept as printed in `report_fields`.
    account_number = " ".join(fields.get("Acc Number", "").split())
    number_parts = account_number.rsplit(" ", 1)
    if len(number_parts) == 2 and re.fullmatch(r"\d", number_parts[1]):
        account_number = number_parts[0]

    start_date = _iso(fields.get("Start Date")) or _iso(fields.get("Payment Start Date"))
    section = raw.get("section") or ""
    normalised = raw_name.lower().strip()
    reconciliation_only = type_code in RECONCILIATION_ONLY_TYPE_CODES
    header = raw.get("header") or {}

    logger.debug("[TRANSUNION INCLUDE] '%s' type=%s balance=%s status=%r",
                 raw_name, type_code, current_balance, fields.get("Status"))

    return {
        "raw_name": raw_name,
        "type_code": type_code,
        **type_source(source_system=SOURCE_TRANSUNION_PDF, type_code=type_code,
                      source_account_type=account_type, type_unmapped=type_unmapped),
        "normalised_name": normalised,
        "matched_creditor": CREDITOR_ALIAS_MAP.get(normalised, raw_name),
        "account_age_months": _months_since(start_date or ""),
        "missed_payments_last_3_months": _missed_last_3(codes),
        "recent_spending": recent_spending,
        "current_balance": current_balance,
        "default_balance": _amount_pence(fields.get("Default Balance")),
        "start_balance": _amount_pence(fields.get("Opening Balance")),
        "credit_limit": credit_limit,
        "utilisation_pct": utilisation_pct,
        # As printed: "Up to date", "Settled" -- CAT reads "Settled" as a
        # settled account (`ledger/credit_report.py :: account_is_settled`).
        "account_status": " ".join(fields.get("Status", "").split()),
        # As printed. ⚠️ TransUnion prints "Default" here on settled accounts
        # whose every month was paid (Raylo, Lendable): a rating level, not a
        # defaulted debt -- nothing reads it as one.
        "account_status_subjective": " ".join(fields.get("Status Subjective Lvl", "").split()) or None,
        "worst_status": _worst_status(codes),
        "payment_history_months": len(status_history),
        "monthly_payment": monthly_payment,
        # "Regular Pay Amount", only when the frequency is Monthly -- nothing
        # is converted (the rule the other readers keep).
        "agreed_monthly_payment": regular if frequency.lower() == "monthly" else None,
        "repayment_frequency": frequency or None,
        "account_number": account_number or None,
        "start_date": start_date,
        "end_date": _iso(fields.get("End Date")),
        "last_update": _iso(fields.get("Update Date")),
        "cais_last_updated": None,
        "reconciliation_only": reconciliation_only,
        "address": header.get("address") or None,
        "account_holder": header.get("account_holder") or None,
        "date_of_birth": header.get("date_of_birth"),
        # The report's sub-section ("Closed Accounts", "Credit Cards", ...).
        "report_section": section or None,
        "closed": section.lower().startswith("closed"),
        **_status_history_fields(status_history),
        "balance_history": balance_history,
        "payment_history": payment_history,
        "limit_history": limit_history,
        "statement_balance_history": statement_history,
        # Every "Label: value" the account printed, as printed.
        "report_fields": dict(fields),
        # Any grid this reader has no name for, kept whole.
        "other_histories": {kind: _history(cells, str) for kind, cells in grids.items()
                            if kind not in ("Balance", "Payment", "Limit", "Statement Balance", "Status")},
    }


# ---------------------------------------------------------------------------
# The accounts' section, page by page
# ---------------------------------------------------------------------------

def _new_account(section: str) -> dict:
    return {"fields": {}, "grids": {}, "header": None, "section": section}


def read_accounts(pdf) -> list[dict]:
    """Every account in the "Financial Account Information (SHARE)" section,
    in report order. Never raises past the caller's guard; an account that
    cannot be built is logged and skipped, the rest kept."""
    raws: list[dict] = []
    in_share = False
    section = ""
    account: dict | None = None
    grid: str | None = None
    columns: list[tuple[int, float]] | None = None
    year: int | None = None
    # The right edge of the year label of the grid row being read.
    year_x1: float | None = None
    # Where the section's own lines start (see `_HEADING_MARGIN_TOLERANCE`).
    margin: float | None = None
    expect_intro = False
    label_x0: float | None = None

    def finish():
        nonlocal account, grid, columns, year, year_x1
        if account is not None and (account["fields"] or account["header"]):
            raws.append(account)
        account, grid, columns, year, year_x1 = None, None, None, None, None

    def is_heading(first: dict, text: str) -> bool:
        """A sub-section heading: short, no colon, at the section's margin."""
        if ":" in text or not re.fullmatch(r"[A-Za-z&/ \-]{3,50}", text):
            return False
        if margin is not None:
            return abs(first["x0"] - margin) <= _HEADING_MARGIN_TOLERANCE
        if label_x0 is not None:
            return first["x0"] < label_x0 - _HEADING_LEFT_OF_LABELS
        # No introduction and no account yet: before the first account a
        # short line of words can only be a heading.
        return account is None

    for page in pdf.pages:
        for words in _lines(page):
            text = _text(words)

            if _SHARE_HEADING_RE.match(text):
                in_share = True
                expect_intro = True
                continue
            if not in_share:
                continue
            if _TOP_LEVEL_RE.match(text.strip()):
                finish()
                in_share = False
                continue

            first = words[0]

            # The introduction under the SHARE heading ("This section shows
            # you the information provided to us by credit providers ...")
            # starts at the section's margin, where its headings start.
            if expect_intro:
                expect_intro = False
                if "||" not in text and ":" not in text and len(text) > 50:
                    margin = first["x0"]
                    continue

            if " ".join(text.lower().split()) == _NO_DATA:
                # Under an empty heading or grid; never a cell of the grid above.
                grid, columns, year, year_x1 = None, None, None, None
                continue

            # The account line ("Name || id || || address || dates || end ||"),
            # possibly sharing its line with the right-hand column's first
            # field ("Opening Balance: £14,958.00").
            if "||" in text:
                # At most the one field that can share the account line
                # ("Opening Balance: ..." beside it on 438769).
                wrapped = (account is not None and account.get("_header_text")
                           and len(account["fields"]) <= 1 and not account["grids"]
                           and account["_header_text"].count("||") < _ACCOUNT_LINE_BARS)
                if not wrapped:
                    finish()
                    account = _new_account(section)
                for part in _groups(words, _FIELD_GAP):
                    part_text = _text(part)
                    if "||" in part_text:
                        # A long account line can run up to the field beside
                        # it with no gap: what follows its last "||" is a field.
                        head, _bars, tail = part_text.rpartition("||")
                        header_text = (f"{account['_header_text']} {head}||" if wrapped
                                       else f"{head}||")
                        account["_header_text"] = header_text
                        account["header"] = _parse_header(header_text)
                        if tail.strip():
                            _put_field(account, tail.strip())
                    else:
                        _put_field(account, part_text)
                continue

            if is_heading(first, text):
                finish()
                section = text.strip()
                continue

            if account is None:
                # Introductory text before the first account.
                if text.startswith("Lender:"):
                    account = _new_account(section)
                else:
                    continue

            # A grid title: "Balance History", "Status History", ...
            if text.endswith(" History") and ":" not in text and len(words) <= 4:
                grid, columns, year = text[: -len(" History")].strip(), None, None
                account["grids"].setdefault(grid, {})
                continue

            if grid is not None:
                header = _month_header(words)
                if header:
                    columns, year = header, None
                    continue
                if columns and re.fullmatch(r"\d{4}", first["text"]) \
                        and 1900 < int(first["text"]) < 2200 and first["x1"] < columns[0][1]:
                    year, year_x1 = int(first["text"]), first["x1"]
                    for cell in _groups(words[1:], _PHRASE_GAP):
                        month = _nearest_month(columns, _centre(cell))
                        account["grids"][grid][(year, month)] = _text(cell)
                    continue
                if columns and year is not None and year_x1 is not None \
                        and first["x0"] > year_x1 and ":" not in text:
                    # A wrapped cell's second line joins the cell above it.
                    for cell in _groups(words, _PHRASE_GAP):
                        month = _nearest_month(columns, _centre(cell))
                        key = (year, month)
                        cells = account["grids"][grid]
                        cells[key] = f"{cells[key]} {_text(cell)}" if key in cells else _text(cell)
                    continue

            # "Label: value" fields, one or two per line.
            if ":" in text:
                if re.match(r"[A-Za-z][A-Za-z ()/&]{0,40}:", text):
                    label_x0 = first["x0"] if label_x0 is None else min(label_x0, first["x0"])
                if text.startswith("Lender:") and "Lender" in account["fields"]:
                    # A second account with no account line of its own.
                    finish()
                    account = _new_account(section)
                grid = None
                for part in _groups(words, _FIELD_GAP):
                    _put_field(account, _text(part))
                continue

            logger.debug("[TRANSUNION] line not read: %r", text)

    finish()

    accounts = []
    for raw in raws:
        try:
            built = _build_account(raw)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[TRANSUNION] account could not be built (%s): %r",
                           exc, raw.get("fields"), exc_info=True)
            continue
        if built is not None:
            accounts.append(built)
    return accounts


def _put_field(account: dict, part_text: str) -> None:
    """One "Label: value" part. A part with no label continues the last field
    (a value wrapped onto the next line)."""
    label, sep, value = part_text.partition(":")
    if sep and re.fullmatch(r"[A-Za-z][A-Za-z ()/&]{0,40}", label.strip()):
        label = label.strip()
        if label in account["fields"]:
            # Never overwrite: the first is the account's own.
            label = f"{label} ({len([k for k in account['fields'] if k.startswith(label)]) + 1})"
        account["fields"][label] = value.strip()
        account["_last"] = label
    elif account.get("_last"):
        last = account["_last"]
        account["fields"][last] = f"{account['fields'][last]} {part_text.strip()}".strip()


# ---------------------------------------------------------------------------
# Report-level facts
# ---------------------------------------------------------------------------

def _section_text(full_text: str, heading: str) -> str:
    """The text from a top-level heading to the next top-level heading."""
    lines = (full_text or "").split("\n")
    out, inside = [], False
    for line in lines:
        stripped = line.strip()
        if re.match(rf"^{re.escape(heading)}(\s+\d+\s+Records?)?$", stripped, re.IGNORECASE):
            inside = True
            continue
        if inside and (_TOP_LEVEL_RE.match(stripped) or _SHARE_HEADING_RE.match(stripped)):
            break
        if inside:
            out.append(stripped)
    return "\n".join(out)


def record_count(full_text: str, heading: str) -> int | None:
    """The "N Records" a top-level section prints beside its heading."""
    lines = (full_text or "").split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = re.match(rf"^{re.escape(heading)}(?:\s+(\d+)\s+Records?)?$", stripped, re.IGNORECASE)
        if not m:
            continue
        if m.group(1):
            return int(m.group(1))
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        m2 = re.match(r"^(\d+)\s+Records?$", nxt, re.IGNORECASE)
        if m2:
            return int(m2.group(1))
    return None


def public_information(full_text: str, base: dict) -> dict:
    """`base` (the shared reader's result) with TransUnion's own Public
    Information section read: "Insolvencies" and "Judgments", each either
    "No data was retrieved for this section" or records -- whose layout is
    unknown, so any record is taken as PRESENT and logged (module docstring)."""
    info = dict(base or {})
    section = _section_text(full_text, "Public Information")
    found = {}
    for name in ("Insolvencies", "Judgments"):
        m = re.search(rf"^{name}\b(.*?)(?=^(?:Insolvencies|Judgments)\b|\Z)", section,
                      re.IGNORECASE | re.MULTILINE | re.DOTALL)
        body = " ".join((m.group(1) if m else "").split())
        found[name] = bool(body) and _NO_DATA not in body.lower()
        if found[name]:
            logger.warning("[TRANSUNION] %s present on the report -- layout not seen before, "
                           "taken as present: %r", name, body[:300])
    if found["Judgments"]:
        info["has_ccj"] = True
        info["ccj_count"] = max(int(info.get("ccj_count") or 0), 1)
    if found["Insolvencies"]:
        info["iva_or_bankruptcy"] = True
    info["transunion_unread_records"] = [n for n, present in found.items() if present]
    return info


def credit_score(full_text: str) -> int | None:
    """The "Credit Score: 620" the report's summary prints, or None."""
    m = re.search(r"Credit Score:\s*(\d{1,4})\b", full_text or "")
    return int(m.group(1)) if m else None


def report_date(accounts: list[dict], printed: str) -> str:
    """The printed search date, else the newest account update -- the
    fallback the Aryza Advize reader gives (`_extract_report_date`)."""
    if printed:
        return printed
    updates = sorted(a["last_update"] for a in accounts if a.get("last_update"))
    return updates[-1] if updates else ""
