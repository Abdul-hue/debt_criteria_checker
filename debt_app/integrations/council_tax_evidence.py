"""
integrations/council_tax_evidence.py

Extracts structured council-tax debt evidence (balance, liability order,
account reference, council name, client salutation name) from an uploaded
image or PDF — built for correspondence (a liability-order letter, an
email/portal notification) rather than a formal periodic bill, which is
why the field extraction works off free-text keyword anchors instead of a
fixed layout.

Ground truth: built and verified against a real screenshot of a council
liability-order email (a phone photo of an email client), OCR'd with
pytesseract + Tesseract 5.4. OCR output for that reference file (kept for
anyone re-verifying this module):

    14:53 8 Fea
    < Council Tax Account - 801302683

    From: Local Taxation
    <local.taxation@flintshire.gov.uk>
    Sent: Thursday, June 25, 2026 9:40 am
    To: Karen Wylie <Karen@kicare,co,uk>
    Subject: RE: Council Tax Account -
    801302683

    Dear MISS WYLIE,

    1am contacting you with regards to
    outstanding balance on your 2025/26
    Council Tax account.

    A Liability Order was granted at Mold
    Magistrates Court on 17th February 2026
    for non-payment of your Council Tax. The
    remaining balance on your account is
    currently £2,047.00.

    Please contact the Council Tax section
    before 5pm Monday 29th June 2026 on

    ev Repy.. SW & em

Note the OCR noise this module has to tolerate: "1am" for "I am" and a
mangled email address ("Karen@kicare,co,uk" for "Karen@klcare.co.uk").
Tesseract read the £ glyph correctly for this reference file, but the
amount parser still tolerates a mojibake replacement character too
(matching integrations/credit_report.py's _parse_amount /
_ccj_amount_to_pence pattern) in case a different scan/font doesn't.

Never raises. Every extractor function returns best-effort None/False
values on a field it can't find rather than raising, so a partially
readable scan still yields whatever it could find.
"""

import io
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


def _get_tesseract_cmd() -> str:
    """
    Resolve the tesseract binary path from Django settings when available,
    falling back to pytesseract's own default ("tesseract" on PATH). Kept
    as its own function (rather than a module-level Django import) so this
    module's pure text-extraction functions can be unit tested without
    Django settings configured — same pattern as integrations/credit_report.py.
    """
    try:
        from django.conf import settings
        return getattr(settings, "TESSERACT_CMD", "") or ""
    except Exception:
        return ""


def ocr_image_to_text(file_path: str) -> str:
    """
    Run OCR over an image file (PNG/JPEG/etc.) and return the extracted
    text. Returns "" on any failure (missing Tesseract binary, unreadable
    image) rather than raising — the caller treats empty text the same as
    "nothing could be read".
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        logger.error("[COUNCIL TAX OCR] pytesseract/Pillow not installed: %s", e)
        return ""

    cmd = _get_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    try:
        with Image.open(file_path) as img:
            return pytesseract.image_to_string(img) or ""
    except Exception as e:
        logger.error("[COUNCIL TAX OCR] OCR failed for %s: %s", file_path, e)
        return ""


# ---------------------------------------------------------------------------
# Chrome-stripping — screenshots of a phone email client carry UI text
# (clock, battery, nav bar icons) that OCR reads as garbage lines mixed
# into the real content. This is defensive cleanup only: every field
# extractor below anchors on a distinctive keyword phrase from the actual
# letter/email body, so it does not depend on chrome having been stripped
# to find the right field — this just keeps the returned raw text tidier
# for anything that logs or displays it.
# ---------------------------------------------------------------------------

_UI_CHROME_LINE_RE = re.compile(
    r"^\s*(\d{1,2}:\d{2}\b.*|.*\b(reply|forward|delete|apps|calendar|email)\b.*)\s*$",
    re.IGNORECASE,
)


def _strip_ui_chrome(text: str) -> str:
    lines = [ln for ln in text.split("\n") if not _UI_CHROME_LINE_RE.match(ln.strip())]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


def _amount_to_pence(text: str) -> int | None:
    """
    Parse a sterling amount, tolerant of whatever the currency symbol OCR'd
    or rendered as (£, mojibake replacement char, or nothing at all) —
    same tolerance principle as credit_report._parse_amount.
    """
    if not text:
        return None
    m = re.search(r"(\d[\d,]*\.\d{2}|\d[\d,]*)", text)
    if not m:
        return None
    try:
        return int(round(float(m.group(1).replace(",", "")) * 100))
    except ValueError:
        return None


def _flatten(text: str) -> str:
    """
    Collapse all whitespace (including line breaks) to single spaces.

    A screenshotted email/letter line-wraps mid-phrase wherever the phone's
    render width happens to break — e.g. "...granted at Mold\nMagistrates
    Court on..." — so anchoring these regexes on the raw newline-preserving
    text would miss any phrase OCR split across a wrap. All the keyword
    anchors below search this flattened form instead.
    """
    return re.sub(r"\s+", " ", text or "").strip()


def extract_account_reference(text: str) -> str | None:
    m = re.search(r"Council Tax Account\s*-?\s*(\d{4,})", _flatten(text), re.IGNORECASE)
    return m.group(1) if m else None


def extract_balance_pence(text: str) -> int | None:
    """Balance owed — anchored on "...is currently <amount>" wording."""
    flat = _flatten(text)
    m = re.search(r"currently\s*[^\d]{0,3}([\d,]+\.\d{2})", flat, re.IGNORECASE)
    if m:
        return _amount_to_pence(m.group(1))
    # Fallback: any "balance ... £X.XX" nearby.
    m = re.search(r"balance[^£�\d]{0,40}([\d,]+\.\d{2})", flat, re.IGNORECASE)
    return _amount_to_pence(m.group(1)) if m else None


_MONTH_RE = r"January|February|March|April|May|June|July|August|September|October|November|December"


def extract_liability_order(text: str) -> dict:
    """
    Returns {"court": str|None, "date_raw": str|None, "date_iso": str|None}.
    """
    result = {"court": None, "date_raw": None, "date_iso": None}
    m = re.search(
        rf"Liability Order was granted at\s+(.+?)\s+on\s+"
        rf"(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_RE})\s+\d{{4}})",
        _flatten(text), re.IGNORECASE,
    )
    if not m:
        return result
    result["court"] = m.group(1).strip()
    date_raw = m.group(2).strip()
    result["date_raw"] = date_raw
    cleaned = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", date_raw, flags=re.IGNORECASE)
    try:
        result["date_iso"] = datetime.strptime(cleaned, "%d %B %Y").date().isoformat()
    except ValueError:
        logger.debug("[COUNCIL TAX] unparseable liability order date %r", date_raw)
    return result


def extract_client_salutation_name(text: str) -> str | None:
    m = re.search(r"Dear\s+([A-Za-z][A-Za-z .]{1,40}?)[,\n]", _flatten(text) + "\n")
    return m.group(1).strip() if m else None


def extract_council_name(text: str) -> str | None:
    """
    Best-effort council name from the sender's @....gov.uk domain (e.g.
    "local.taxation@flintshire.gov.uk" -> "Flintshire"). This is a
    heuristic label, not a lookup against the authoritative CouncilRule
    table — a caller matching this evidence to a real council row should
    still run it through the engine's own _match_council_rule() resolver,
    the same as any other Aryza-sourced council name.
    """
    m = re.search(r"@([\w-]+)\.[\w.-]*gov\.uk", _flatten(text), re.IGNORECASE)
    if not m:
        return None
    return m.group(1).replace("-", " ").replace(".", " ").strip().title() or None


def _pdf_text(file_path: str) -> str:
    """Text-layer extraction for a digital PDF (e.g. a liability-order
    letter saved straight to PDF rather than screenshotted)."""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        logger.error("[COUNCIL TAX] PDF text extraction failed for %s: %s", file_path, e)
        return ""


def extract_council_tax_evidence(file_path: str, *, is_image: bool = True) -> dict:
    """
    Main entry point. OCRs images (PNG/JPEG/etc. — the ctax1.png use case
    this module was built for); reads the text layer directly for a
    digital PDF instead (no OCR needed). Returns:

        {
            "raw_text": str,
            "account_reference": str | None,
            "balance_pence": int | None,
            "liability_order": {"court", "date_raw", "date_iso"},
            "client_salutation_name": str | None,
            "council_name": str | None,
            "extraction_error": str,   # only present on failure
        }

    Never raises.
    """
    try:
        raw_text = ocr_image_to_text(file_path) if is_image else _pdf_text(file_path)
        cleaned = _strip_ui_chrome(raw_text)

        return {
            "raw_text": cleaned,
            "account_reference": extract_account_reference(raw_text),
            "balance_pence": extract_balance_pence(raw_text),
            "liability_order": extract_liability_order(raw_text),
            "client_salutation_name": extract_client_salutation_name(raw_text),
            "council_name": extract_council_name(raw_text),
        }
    except Exception as e:
        logger.error("Council tax evidence extraction failed for %s: %s", file_path, e, exc_info=True)
        return {
            "raw_text": "",
            "account_reference": None,
            "balance_pence": None,
            "liability_order": {"court": None, "date_raw": None, "date_iso": None},
            "client_salutation_name": None,
            "council_name": None,
            "extraction_error": str(e),
        }
