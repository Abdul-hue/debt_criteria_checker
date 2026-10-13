"""
Turn the Excel Criteria markdown (and the sheet owner's recorded decisions)
into DRAFT criteria change requests.

Nothing here changes live criteria. Every proposal becomes an item in a
CriteriaChangeRequest created through the existing service
(debt_app.services.criteria_versioning), so it still needs a trial and a
second manager's approval before anything is applied. The builder only
decides *what to propose* and keeps the drafts idempotent.

Groups (one draft each, independently reviewable):
  1. Creditor statuses and structured criteria  (General Creditor sheet + agreed structured changes + rename aliases)
  2. Council statuses                            (Councils sheet)
  3. Dividends and representatives              (Dividends + Which Representative sheets, Evolve retirement)
  4. Rule switches                               (Watch / Evolve rules retired by the sheet owner)
  5. HMRC equity rule                            (TIG-15.4 on; kept separate because it needs trial evidence)

Idempotency: a draft is identified by its title. Re-running with nothing
changed reports the existing draft and creates nothing. If the proposal now
differs from an open draft (DRAFT or TRIALLED), the old draft is cancelled
through the service and a new one created, and the difference is reported.
"""

import datetime
import json
import re
from pathlib import Path

from django.conf import settings

from debt_app.management.commands.seed_all_councils import _is_non_council, _normalise_status
from debt_app.management.commands.seed_creditor_criteria import _parse_pence, _parse_status
from debt_app.models import CouncilRule, CreditorCriteria, CriteriaChangeRequest, GlobalCriteria
from debt_app.services import criteria_versioning as cv
from debt_app.services.excel_criteria import (
    COUNCIL_COLS,
    DIVIDEND_COLS,
    FILE_COUNCILS,
    FILE_DIVIDENDS,
    FILE_GENERAL,
    FILE_WHICH_REP,
    GENERAL_COLS,
    RENAMED_ROWS,
    existing_rep_sections,
    existing_table_rows,
)

TITLE_PREFIX = "[Excel sync]"

GROUPS = [
    ("creditor_statuses", "Creditor statuses and structured criteria"),
    ("council_statuses", "Council statuses"),
    ("dividends_representatives", "Dividends and representatives"),
    ("rule_switches", "Rule switches"),
    ("hmrc_equity", "HMRC equity rule (TIG-15.4) - needs trial evidence"),
]
GROUP_TITLES = dict(GROUPS)

REP_BODIES = {"WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS"}

# --------------------------------------------------------------------------
# Decisions recorded from the sheet owner, 2026-10-12
# --------------------------------------------------------------------------

OWNER_CONFIRMATION = "confirmed by the sheet owner on 2026-10-12"

RULE_SWITCHES = [
    ("WATCH-22.3", False, "Watch rule 'reject if bankruptcy dividend is higher than IVA' was removed from the workbook; "
                          f"'no longer a thing', {OWNER_CONFIRMATION}."),
    ("WATCH-22.4", False, "Watch rule 'reject if equity is greater than debt' was removed from the workbook; "
                          f"'no longer a thing', {OWNER_CONFIRMATION}. TIG-16 stays non-WPM only, so WATCH cases get no equity check: intended."),
    ("WATCH-22.6", False, "Watch rule 'reject if any spending within 3 months' was removed from the workbook; "
                          f"'no longer a thing', {OWNER_CONFIRMATION}."),
    ("EVOLVE-01", False, f"Evolve Criteria sheet removed; 'Evolve don't exist anymore', {OWNER_CONFIRMATION}."),
    ("EVOLVE-02", False, f"Evolve Criteria sheet removed; 'Evolve don't exist anymore', {OWNER_CONFIRMATION}."),
    ("EVOLVE-03", False, f"Evolve Criteria sheet removed; 'Evolve don't exist anymore', {OWNER_CONFIRMATION}."),
]

HMRC_SWITCH = (
    "TIG-15.4", True,
    "TIG sheet now reads 'HMRC - WILL REJECT if more equity than their debt (100% HOUSE VALUATION)'; "
    f"100% is for HMRC only, {OWNER_CONFIRMATION}. The rule already values the property at 100% "
    "(available_equity = property value - mortgage). It has been a switched-off stub because the case "
    "payload did not carry a property value; the Aryza client now reads slam_property_details, but no "
    "stored decision on this environment involves a homeowner, so the trial must confirm the rule "
    "behaves on real cases before approval.",
)

# (group, creditor name, field, value, source, rationale)
STRUCTURED_CHANGES = [
    ("creditor_statuses", "Admiral Loans", "account_age_months", 6,
     "General Creditor notes", "'running cases: 6 months or older' (was 3 months), updated 24.08.26."),
    ("creditor_statuses", "Admiral Loans", "reject_if_second_iva", True,
     "General Creditor notes", "'REJECT IF PREVIOUS IVA CONFIRMED THIS 24.08.26'. The engine's reject_if_second_iva fires on any previous IVA."),
    ("creditor_statuses", "Loans by Mal", "young_account_months", 6,
     "General Creditor notes", "'if under 6 months but older than 3 months - has to 40p/£' (new field; under 3 months is still a reject)."),
    ("creditor_statuses", "Loans by Mal", "young_account_min_dividend_pence", 40,
     "General Creditor notes", "'if under 6 months but older than 3 months - has to 40p/£'."),
    # Match the Cash t/a Guarantor My Loan keeps its own 50p: its row says
    # "will consider 50p/£ min div ... they are only on there at the minute as
    # 50p div" (updated 25.08.26). The Dividends sheet's 'Guarantor My Loan:
    # 100P/£' names the separate Guarantor My Loan row only; nothing in the
    # workbook applies it to Match the Cash (decision confirmed 2026-10-13).
    # Ratesetter: two tiers, decision confirmed 2026-10-13. Standard 25p; 50p
    # while the loan is under six months old (exactly six months = standard).
    # The row has carried 50p plus a 6-month account-age REJECT as a stand-in
    # ("Engine enforces 50p threshold; caseworker must manually verify age");
    # the reject contradicts the sheet (a young loan needs 50p, it is not a
    # reject) and is cleared alongside.
    ("dividends_representatives", "Ratesetter", "min_dividend_pence", 25,
     "Dividends sheet", "'25p' standard minimum; confirmed 2026-10-13."),
    ("dividends_representatives", "Ratesetter", "young_account_months", 6,
     "Dividends sheet", "'if under 6 months old it 50p': the higher minimum applies while the loan is under 6 months old; at exactly 6 months the standard 25p applies."),
    ("dividends_representatives", "Ratesetter", "young_account_min_dividend_pence", 50,
     "Dividends sheet", "'if under 6 months old it 50p'; confirmed 2026-10-13."),
    ("dividends_representatives", "Ratesetter", "account_age_months", None,
     "General Creditor notes", "The 6-month account-age reject was a stand-in for the 50p tier (its note says the caseworker had to verify age by hand). "
                               "The sheet says a loan under 6 months needs 50p, not that it is rejected, so the reject is cleared now the tier is encoded."),
    # Sheet-owner answers, 2026-10-13 (stances themselves are exporter fixes;
    # see OWNER_ANSWERS_2026_10_13 in services/excel_criteria.py).
    ("creditor_statuses", "Reward Rate", "reject_if_debt_repayable_within_months", 84,
     "General Creditor notes", "'TRADING STYLE OF AMIGO'; the sheet owner confirmed on 2026-10-13 it is treated "
                               "the same as Amigo, so it carries Amigo's 84-month repayment reject as well as Do Not Vote."),
    ("creditor_statuses", "Likely Loan", "trading_names", ["Finio Loans", "Finio"],
     "Councils sheet row 'Finio Loans: See Likely Loans'", "The sheet owner confirmed on 2026-10-13 that Finio "
                                                           "Loans follows the Likely Loan row, so cases naming Finio resolve to it."),
    # HMRC equity: the sheet's rule is TIG-15.4 (equity at 100% of the property
    # value against the HMRC balance). The per-creditor flag was a stand-in that
    # checks equity at 85% against TOTAL unsecured debt; the owner decided
    # (2026-10-13) it is superseded and must not run alongside TIG-15.4.
    ("hmrc_equity", "HM Revenue & Customs", "reject_if_equity_exceeds_debt", False,
     "TIG Criteria sheet", "Superseded by TIG-15.4 (100% of property value vs the HMRC balance). This per-creditor "
                           "check (85% of value vs total unsecured debt) is not what the sheet describes and must not "
                           "operate alongside TIG-15.4; switched off in the same draft that switches TIG-15.4 on."),
]

# Dividend rows whose note describes a tier the sheet owner has not yet agreed
# how to encode. Nothing is proposed for them; they are reported instead.
DIVIDEND_NEEDS_DECISION = {
    # (empty: Ratesetter's tier was agreed on 2026-10-13 and is in STRUCTURED_CHANGES)
}

# Councils listed more than once in the sheet, and which row wins.
COUNCIL_DUPLICATE_RESOLUTIONS = {
    "suffolk coastal district council": (
        "last",
        "The sheet has two rows: the older 'Will Consider' row and a newer 'Reject' row dated 31.07.26 "
        "('will not consider any IVA ... DO NOT PUT FORWARD'). The newer row is taken. The existing council "
        "record is kept; only its status changes.",
    ),
}

EVOLVE_RETIREMENT = (
    f"Evolve no longer exists ({OWNER_CONFIRMATION}) and the EVOLVE section is no longer exported, so this "
    "creditor is no longer represented."
)

# Creditors that lost the Evolve representative and have no stance of their own
# in the workbook. The criteria owner has confirmed (2026-10-13) that falling
# back to the row's default ACCEPT is wrong, so their stance is recorded as
# UNKNOWN: the engine flags the case for confirmation and never counts it as
# an acceptance.
EVOLVE_STANCE_UNCONFIRMED = (
    "This creditor appeared only on the retired Evolve list and has no stance of its own in the workbook. "
    "Its row carries the model default ACCEPT, which the criteria owner has confirmed is wrong, so the stance "
    "is set to UNKNOWN: the engine flags it as unconfirmed (CREDITOR-STANCE-UNCONFIRMED) and never treats it "
    "as an acceptance. Replace with the real stance once the sheet owner confirms it."
)

# Ex-Evolve creditors with authoritative evidence elsewhere in the workbook:
# name -> (representative to propose, keep the existing status, rationale)
EX_EVOLVE_DECISIONS = {
    "Barclaycard": (
        "WATCH", True,
        "The Which Representative sheet lists 'Barclaycard (including cards below) - IVA' (and Barclaycard Motor "
        "Loans / Amazon) under WATCH, so Barclaycard is WATCH-represented and its vote follows the WATCH rules; "
        "the row's own status is not used.",
    ),
    "Shell Energy": (
        "NONE", True,
        "General Creditor sheet row 174 'Shell Energy Retail Limited (NOW OCTOPUS) | Accept'; the user confirmed on "
        "2026-10-13 that the 'Shell Energy' row is that same creditor, so its ACCEPT stance is kept. See also the "
        "SHELL_ENERGY_CONSOLIDATION items in this draft.",
    ),
}

# Workbook rows that MAY describe an ex-Evolve creditor under another name.
# Reported for the reviewer; never used to set a stance. (Empty since the
# Shell Energy match was confirmed on 2026-10-13.)
EX_EVOLVE_POSSIBLE_MATCHES = {}

# Shell Energy exists twice in the database: 'Shell Energy' (the row a case
# named "Shell Energy" resolves to by exact match; formerly Evolve) and 'Shell
# Energy Retail Limited (NOW OCTOPUS)' (created from the General sheet row).
# Confirmed the same creditor on 2026-10-13. The duplicate is deactivated
# (kept, primary key preserved; its notes still sync). No trading names are
# added to 'Shell Energy': migration 0030 already made "Shell Energy Retail
# Limited" a trading name of Octopus Energy (the sheet says "NOW OCTOPUS"), so
# that variant resolves to Octopus Energy by design; adding it here too would
# make the match depend on row order. Both records say Accept.
SHELL_ENERGY_CANONICAL = "Shell Energy"
SHELL_ENERGY_DUPLICATE = "Shell Energy Retail Limited (NOW OCTOPUS)"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _criteria_dir(override=None):
    if override:
        return Path(override)
    return Path(settings.BASE_DIR) / "Excel Criteria"


def _rep_value_for(heading):
    h = heading.upper()
    if "WATCH" in h or "WPM" in h:
        return "WATCH"
    if "TIX" in h:
        return "TIX"
    if "EVERYDAY" in h:
        return "EVERYDAY_LOANS"
    if "EVOLVE" in h:
        return "EVOLVE"
    return None


def _source_label(criteria_dir):
    """Workbook name from the generated file's source line, for the reason text."""
    path = criteria_dir / FILE_GENERAL
    if path.exists():
        m = re.search(r"Source: `([^`]+)`", path.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return "Excel Criteria markdown"


class ProposalSet:
    """Collects proposals per group, de-duplicated on (model, pk, field)."""

    def __init__(self):
        self.groups = {key: [] for key, _ in GROUPS}
        self.notes = []       # skipped items, conflicts, warnings (strings)
        self._seen = {}       # (model, pk, field) -> proposal
        self.sheet_statuses = {}   # creditor name (lower) -> stance parsed from the General sheet

    def note(self, text):
        self.notes.append(text)

    def propose(self, group, model_name, obj, field, new_value, source, rationale):
        """Add a proposal if the value actually changes. Returns the proposal or None."""
        label = str(getattr(obj, cv.LABEL_FIELD[model_name]))
        if field not in cv.MANAGED_FIELDS[model_name]:
            self.note(f"SKIP {model_name} {label!r} {field}: not a managed field; use the notes-only sync or admin.")
            return None
        old_value = cv._json_value(getattr(obj, field))
        try:
            coerced = cv._coerce(model_name, field, new_value)
        except cv.CriteriaChangeError as exc:
            self.note(f"SKIP {model_name} {label!r} {field}: {exc.message}")
            return None
        if old_value == coerced:
            return None
        key = (model_name, obj.pk, field)
        if key in self._seen:
            prev = self._seen[key]
            if prev["new_value"] != coerced:
                self.note(
                    f"CONFLICT {model_name} {label!r} {field}: {prev['source']} proposes {prev['new_value']!r}, "
                    f"{source} proposes {coerced!r}; keeping the first."
                )
            return None
        flags = []
        if getattr(obj, "updated_by_id", None):
            # Set by an admin edit or by an approved change; either way a
            # person chose the current value, so say so.
            flags.append(f"last edited by {obj.updated_by}; review carefully")
        proposal = {
            "model": model_name, "object_id": obj.pk, "object_label": label, "field": field,
            "old_value": old_value, "new_value": coerced,
            "source": source, "rationale": rationale, "flags": flags,
        }
        self._seen[key] = proposal
        self.groups[group].append(proposal)
        return proposal


def _ws_key(name):
    """Whitespace-insensitive key: some council rows were created straight
    from the workbook with line breaks inside the name."""
    return re.sub(r"\s+", " ", (name or "").replace("\xa0", " ")).strip().lower()


def find_council(name):
    obj = CouncilRule.objects.filter(council_name=name).first()
    if obj is None:
        obj = CouncilRule.objects.filter(council_name__iexact=name).order_by("pk").first()
    if obj is None:
        key = _ws_key(name)
        for c in CouncilRule.objects.only("pk", "council_name"):
            if _ws_key(c.council_name) == key:
                obj = CouncilRule.objects.get(pk=c.pk)
                break
    return obj


def find_creditor(name):
    """Exact, then case-insensitive, then through the agreed renames (either direction)."""
    if not name:
        return None
    row = CreditorCriteria.objects.filter(creditor_name=name).first()
    if row is None:
        row = CreditorCriteria.objects.filter(creditor_name__iexact=name).order_by("pk").first()
    if row is None:
        for old, new in RENAMED_ROWS.items():
            if name.lower() == new.lower():
                row = CreditorCriteria.objects.filter(creditor_name__iexact=old).order_by("pk").first()
            elif name.lower() == old.lower():
                row = CreditorCriteria.objects.filter(creditor_name__iexact=new).order_by("pk").first()
            if row is not None:
                break
    return row


# --------------------------------------------------------------------------
# Building proposals (read-only)
# --------------------------------------------------------------------------

def build_proposals(criteria_dir=None):
    d = _criteria_dir(criteria_dir)
    ps = ProposalSet()
    _creditor_statuses(d, ps)
    _structured_changes(ps)
    _rename_aliases(ps)
    _council_statuses(d, ps)
    _dividends(d, ps)
    _representatives(d, ps)
    _rule_switches(ps)
    return ps


def _creditor_statuses(d, ps):
    source = "General Creditor sheet, 'Accept / Reject' column"
    for row in existing_table_rows(d / FILE_GENERAL, GENERAL_COLS):
        name, raw_status = row[0], row[1]
        if not name:
            continue
        parsed = _parse_status(raw_status)
        obj = find_creditor(name)
        if obj is None:
            ps.note(f"NEW creditor {name!r} is not in the database: created by the notes-only sync (seed_creditor_criteria), with status {parsed or 'default'}.")
            continue
        if parsed is None:
            if raw_status:
                ps.note(f"SKIP creditor {obj.creditor_name!r}: status {raw_status!r} is not a recognised stance; database keeps {obj.status}.")
            continue
        ps.sheet_statuses[obj.creditor_name.lower()] = parsed
        if obj.representative in REP_BODIES and obj.representative != "EVOLVE" and obj.status != parsed:
            ps.note(
                f"SKIP creditor {obj.creditor_name!r} status {obj.status} -> {parsed}: represented by "
                f"{obj.representative}, whose body rules decide the vote; the row's own status is not used."
            )
            continue
        ps.propose("creditor_statuses", "CreditorCriteria", obj, "status", parsed, source,
                   f"Sheet says {raw_status!r}.")


def _structured_changes(ps):
    for group, name, field, value, source, rationale in STRUCTURED_CHANGES:
        obj = find_creditor(name)
        if obj is None:
            ps.note(f"SKIP structured change for {name!r} ({field}): creditor not in the database.")
            continue
        ps.propose(group, "CreditorCriteria", obj, field, value, source, rationale)


def _rename_aliases(ps):
    """After a rename the old name must still resolve, so propose it as a trading name."""
    for old, new in RENAMED_ROWS.items():
        obj = find_creditor(new) or find_creditor(old)
        if obj is None:
            ps.note(f"SKIP rename alias {old!r} -> {new!r}: creditor not in the database.")
            continue
        current = list(obj.trading_names or [])
        if any(t.lower() == old.lower() for t in current):
            continue
        ps.propose(
            "creditor_statuses", "CreditorCriteria", obj, "trading_names", current + [old],
            "Workbook rename",
            f"Renamed {old!r} -> {new!r} in the workbook (the row keeps its id; seed_creditor_criteria renames it). "
            "Keeping the old name as a trading name so cases that still use it resolve to this row.",
        )


def _council_statuses(d, ps):
    source = "Councils sheet, 'Accept / Reject' column"
    by_name = {}
    for row in existing_table_rows(d / FILE_COUNCILS, COUNCIL_COLS, numbered=True):
        name = row[0]
        if not name or _is_non_council(name):
            continue
        by_name.setdefault(name.lower(), []).append(row)

    for key, rows in by_name.items():
        statuses = [(r[1], _normalise_status(r[1]) if r[1] else None) for r in rows]
        obj = find_council(rows[0][0])
        if obj is None:
            ps.note(f"NEW council {rows[0][0]!r} is not in the database: created by seed_all_councils (which never overwrites existing rows).")
            continue

        if len(rows) > 1:
            resolution = COUNCIL_DUPLICATE_RESOLUTIONS.get(key)
            if resolution:
                which, rationale = resolution
                raw, parsed = statuses[-1] if which == "last" else statuses[0]
                if parsed is None:
                    ps.note(f"SKIP council {obj.council_name!r}: resolved duplicate row has no usable status.")
                    continue
                ps.propose("council_statuses", "CouncilRule", obj, "status", parsed, source,
                           f"Sheet says {raw!r} (duplicate rows; agreed resolution: take the {which} row). {rationale}")
                continue
            parsed_set = {p for _, p in statuses if p}
            if obj.status in parsed_set:
                ps.note(
                    f"SKIP council {obj.council_name!r}: listed {len(rows)} times in the sheet "
                    f"({', '.join(repr(r) for r, _ in statuses)}); database ({obj.status}) matches one of them; left as it is."
                )
            else:
                ps.note(
                    f"CONFLICT council {obj.council_name!r}: listed {len(rows)} times in the sheet "
                    f"({', '.join(repr(r) for r, _ in statuses)}) and database is {obj.status}; nothing proposed — ask the sheet owner."
                )
            continue

        raw, parsed = statuses[0]
        if not raw:
            ps.note(f"SKIP council {obj.council_name!r}: no status in the sheet; database keeps {obj.status}.")
            continue
        if parsed is None:
            ps.note(f"SKIP council {obj.council_name!r}: status {raw!r} is not a recognised stance; database keeps {obj.status}.")
            continue
        ps.propose("council_statuses", "CouncilRule", obj, "status", parsed, source, f"Sheet says {raw!r}.")


def _dividends(d, ps):
    source = "Dividends sheet"
    for row in existing_table_rows(d / FILE_DIVIDENDS, DIVIDEND_COLS):
        name, div_raw = row[0], row[1]
        if not name:
            continue
        pence = _parse_pence(div_raw)
        if pence is None:
            continue  # "DO NOT REQUIRE A DIV NOW" etc.: never clear a minimum from here
        obj = find_creditor(name)
        if obj is None:
            ps.note(f"SKIP dividend for {name!r}: creditor not in the database.")
            continue
        if name.lower() in DIVIDEND_NEEDS_DECISION and obj.min_dividend_pence != pence:
            ps.note(f"NEEDS DECISION dividend for {obj.creditor_name!r} (database {obj.min_dividend_pence}p, sheet {div_raw!r}): "
                    f"{DIVIDEND_NEEDS_DECISION[name.lower()]}")
            continue
        ps.propose("dividends_representatives", "CreditorCriteria", obj, "min_dividend_pence", pence, source,
                   f"Sheet says {div_raw!r}.")


def _representatives(d, ps):
    source = "Which Representative sheet"
    listed = set()
    for heading, items in existing_rep_sections(d / FILE_WHICH_REP).items():
        value = _rep_value_for(heading)
        if value is None:
            ps.note(f"SKIP representative section {heading!r}: not a known body.")
            continue
        for item in items:
            obj = find_creditor(item)
            if obj is None:
                ps.note(f"NEW representative entry {item!r} ({value}) is not in the database: created by the notes-only sync.")
                continue
            listed.add(obj.pk)
            ps.propose("dividends_representatives", "CreditorCriteria", obj, "representative", value, source,
                       f"Listed under '{heading}'.")

    for obj in CreditorCriteria.objects.filter(representative="EVOLVE").order_by("creditor_name"):
        if obj.pk in listed:
            continue
        rep, keep_status, rationale = EX_EVOLVE_DECISIONS.get(obj.creditor_name, ("NONE", False, EVOLVE_RETIREMENT))
        ps.propose("dividends_representatives", "CreditorCriteria", obj, "representative", rep,
                   "Evolve retirement", rationale)
        if rep in REP_BODIES or keep_status:
            continue
        if obj.creditor_name.lower() in ps.sheet_statuses:
            continue   # the General sheet gives this creditor an explicit stance of its own (e.g. Octopus Energy: Accept)
        rationale = EVOLVE_STANCE_UNCONFIRMED
        if obj.creditor_name in EX_EVOLVE_POSSIBLE_MATCHES:
            rationale += " POSSIBLE MATCH: " + EX_EVOLVE_POSSIBLE_MATCHES[obj.creditor_name]
            ps.note(f"CONFIRM {obj.creditor_name!r}: {EX_EVOLVE_POSSIBLE_MATCHES[obj.creditor_name]}")
        ps.propose("dividends_representatives", "CreditorCriteria", obj, "status", "UNKNOWN",
                   "Evolve retirement", rationale)

    _shell_energy_consolidation(ps)


def _shell_energy_consolidation(ps):
    """The confirmed duplicate row is deactivated (not deleted)."""
    canonical = CreditorCriteria.objects.filter(creditor_name=SHELL_ENERGY_CANONICAL).first()
    duplicate = CreditorCriteria.objects.filter(creditor_name=SHELL_ENERGY_DUPLICATE).first()
    if canonical is None:
        ps.note(f"SKIP Shell Energy consolidation: {SHELL_ENERGY_CANONICAL!r} not in the database.")
        return
    if duplicate is not None and duplicate.pk != canonical.pk and duplicate.is_active:
        ps.propose("dividends_representatives", "CreditorCriteria", duplicate, "is_active", False,
                   "User confirmation 2026-10-13",
                   f"Duplicate of {SHELL_ENERGY_CANONICAL!r} (confirmed the same creditor). Deactivated, not deleted: "
                   "the row and its history are kept, and cases resolve to the one active record.")


def _rule_switches(ps):
    for rule_key, value, rationale in RULE_SWITCHES:
        obj = GlobalCriteria.objects.filter(rule_key=rule_key).first()
        if obj is None:
            ps.note(f"SKIP rule {rule_key}: not in the database.")
            continue
        if obj.is_active == value:
            ps.note(f"Rule {rule_key} is already {'on' if value else 'off'}; nothing to propose.")
            continue
        ps.propose("rule_switches", "GlobalCriteria", obj, "is_active", value, "Workbook criteria sheets", rationale)

    rule_key, value, rationale = HMRC_SWITCH
    obj = GlobalCriteria.objects.filter(rule_key=rule_key).first()
    if obj is None:
        ps.note(f"SKIP rule {rule_key}: not in the database.")
    elif obj.is_active == value:
        ps.note(f"Rule {rule_key} is already {'on' if value else 'off'}; nothing to propose.")
    else:
        ps.propose("hmrc_equity", "GlobalCriteria", obj, "is_active", value, "TIG Criteria sheet", rationale)


# --------------------------------------------------------------------------
# Drafts (the only writes, and only through the service)
# --------------------------------------------------------------------------

def draft_title(group_key):
    return f"{TITLE_PREFIX} {GROUP_TITLES[group_key]}"


def _signature(items):
    return sorted(
        (i["model"], int(i["object_id"]), i["field"], json.dumps(i["new_value"], sort_keys=True, default=str))
        for i in items
    )


def _reason_text(group_key, proposals, source_label):
    lines = [
        f"Generated by manage.py build_criteria_change_from_excel from {source_label} on "
        f"{datetime.date.today():%Y-%m-%d}. Each line: record, field, before -> after, source, why.",
        "",
    ]
    for p in proposals:
        line = (f"- {p['model']} #{p['object_id']} {p['object_label']!r} {p['field']}: "
                f"{p['old_value']!r} -> {p['new_value']!r} | source: {p['source']} | {p['rationale']}")
        if p["flags"]:
            line += " | " + "; ".join(p["flags"])
        lines.append(line)
    return "\n".join(lines)


def _open_drafts(title):
    return list(CriteriaChangeRequest.objects.filter(
        title=title,
        status__in=(CriteriaChangeRequest.STATUS_DRAFT, CriteriaChangeRequest.STATUS_TRIALLED),
    ).order_by("pk"))


def _describe_diff(old_items, new_items):
    old = {(i["model"], int(i["object_id"]), i["field"]): i["new_value"] for i in old_items}
    new = {(i["model"], int(i["object_id"]), i["field"]): i["new_value"] for i in new_items}
    out = []
    for k in sorted(set(old) | set(new)):
        if k not in new:
            out.append(f"removed {k[0]} #{k[1]} {k[2]} (was -> {old[k]!r})")
        elif k not in old:
            out.append(f"added {k[0]} #{k[1]} {k[2]} -> {new[k]!r}")
        elif old[k] != new[k]:
            out.append(f"changed {k[0]} #{k[1]} {k[2]}: -> {old[k]!r} becomes -> {new[k]!r}")
    return out


def sync_drafts(ps, user=None, dry_run=True, criteria_dir=None):
    """Create / refresh one draft per non-empty group. Returns a list of
    per-group result dicts. With dry_run nothing is written."""
    source_label = _source_label(_criteria_dir(criteria_dir))
    results = []
    for key, title_text in GROUPS:
        proposals = ps.groups[key]
        title = draft_title(key)
        result = {"key": key, "title": title, "proposals": proposals, "action": None,
                  "request_id": None, "previous_ids": [], "diff": [], "error": None}
        results.append(result)
        if not proposals:
            result["action"] = "nothing-to-propose"
            continue

        raw_items = [{"model": p["model"], "object_id": p["object_id"], "field": p["field"], "new_value": p["new_value"]}
                     for p in proposals]
        open_drafts = _open_drafts(title)
        current = [d for d in open_drafts if _signature(d.items) == _signature(raw_items)]
        if current:
            result["action"] = "unchanged"
            result["request_id"] = current[0].pk
            result["previous_ids"] = [d.pk for d in open_drafts if d.pk != current[0].pk]
            continue

        if open_drafts:
            result["previous_ids"] = [d.pk for d in open_drafts]
            for d in open_drafts:
                result["diff"].extend(_describe_diff(d.items, raw_items))
            result["action"] = "would-replace" if dry_run else "replaced"
        else:
            result["action"] = "would-create" if dry_run else "created"

        if dry_run:
            continue

        try:
            for d in open_drafts:
                cv.cancel_change_request(d, user)
            change = cv.create_change_request(
                user, title, _reason_text(key, proposals, source_label), raw_items,
            )
            result["request_id"] = change.pk
        except cv.CriteriaChangeError as exc:
            result["action"] = "error"
            result["error"] = exc.message
    return results


def render_report(ps, results):
    """Plain-text report: every proposal with before/after, then skips and warnings."""
    out = []
    for r in results:
        out.append(f"== {r['title']} ==")
        if r["action"] == "nothing-to-propose":
            out.append("  (nothing to propose)")
        else:
            out.append(f"  {len(r['proposals'])} change(s) - {r['action']}"
                       + (f" - request #{r['request_id']}" if r["request_id"] else "")
                       + (f" - replaces #{', #'.join(map(str, r['previous_ids']))}" if r["previous_ids"] and r["action"] != "unchanged" else "")
                       + (f" - other open drafts with this title: #{', #'.join(map(str, r['previous_ids']))}" if r["previous_ids"] and r["action"] == "unchanged" else ""))
            if r["error"]:
                out.append(f"  ERROR: {r['error']}")
            for p in r["proposals"]:
                flag = f"  [{'; '.join(p['flags'])}]" if p["flags"] else ""
                out.append(f"  {p['model']} #{p['object_id']} {p['object_label']!r}")
                out.append(f"      {p['field']}: {p['old_value']!r} -> {p['new_value']!r}{flag}")
                out.append(f"      source: {p['source']} | {p['rationale']}")
            for line in r["diff"]:
                out.append(f"  DIFF vs open draft: {line}")
        out.append("")
    if ps.notes:
        out.append("== Skipped / conflicts / warnings ==")
        for n in ps.notes:
            out.append(f"  {n}")
    return "\n".join(out)
