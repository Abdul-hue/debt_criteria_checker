"""
Lead Generation pre-screen: a PRESENTATION layer over the existing criteria
engine. Nothing here decides eligibility — it interprets what assess_case()
already returned:

  * engine solution code (_derive_recommended_solution)  -> IVA outcome / DRO
  * hard_blocks / flags (RuleResult, engine order)       -> reasons
  * dmp_eligibility.status / reasons                     -> DMP outcome

The only Lead Gen-specific judgement is WHICH rules are "evidence-stage"
(EVIDENCE_STAGE_RULES): rules that only check whether a supporting document
has been supplied. At pre-screen no documents exist yet, so those rules are
shown as "evidence required later" instead of making an otherwise suitable
case look unsuitable. The full CAT assessment is unchanged — they remain
hard blocks there.
"""

import logging
from collections import defaultdict

from django.utils import timezone

from debt_app.engine.criteria import _derive_recommended_solution

logger = logging.getLogger(__name__)

LEAD_GEN_DEPARTMENT = "Lead Generation"

# ---------------------------------------------------------------------------
# Evidence-stage rules
# ---------------------------------------------------------------------------
# Classification source (verified against the repository, not assumed):
#   * debt_app/migrations/0050_disable_category3_rules.py groups exactly these
#     rules as "3a — Documentation / evidence gathering ... not related to IVA
#     financial viability or creditor acceptance".
#   * Excel Criteria/TIG_Criteria.md lists them as documents "we require"
#     (wage slip, benefit letters, UC journal, tax return / banking, CIS
#     invoice, bank statements, signed third-party letters).
#   * Each rule's code only tests whether that document is present in the
#     payload's `documents` (or its date/holder) — never the client's finances.
# NOT included:
#   * TIG-13 (previous-IVA termination report) — 0050 records it as
#     "explicitly kept per product decision"; awaiting a business decision, so
#     it stays a Lead Gen blocker (the conservative, unchanged treatment).
#   * TIG-11-GAMBLING (gambling must be under £1,000) and TIG-10 (unidentified
#     debts / debt-level issue) — substantive eligibility, not paperwork.
EVIDENCE_STAGE_RULES = {
    "TIG-05": "Wage slip",
    "TIG-06": "Benefit award letter (or a current-year bank statement)",
    "TIG-07": "Universal Credit journal",
    "TIG-08": "Tax return or business bank statement",
    "TIG-09": "CIS invoice",
    "TIG-11": "Bank statement",
    "TIG-12": "Signed third-party contribution letter",
}

# ---------------------------------------------------------------------------
# Lead Gen-safe reason text
# ---------------------------------------------------------------------------
# Engine rule messages carry case figures (income, balances, dividends) and
# creditor names, so they are NOT shown to Lead Gen. Reasons use the rule's
# existing GlobalCriteria title (rule_name) — generic, no case data — keyed by
# the same rule ID. Engine-only rule IDs have no GlobalCriteria row, so they
# get a short neutral description here.
ENGINE_ONLY_REASON_TEXT = {
    "CREDITOR-BLOCKED": "A creditor on this case is expected to block an IVA",
    "EQUITY-AGE": "Property equity is too high for an IVA",
    "SPECIAL-EMPLOYER-COPPERPOT": "A creditor on this case does not accept IVAs for police employees",
    "DEBT-REPAYABILITY-REJECT": "A creditor considers the debt repayable without an IVA",
    "MAJORITY-IMPOSSIBLE": "The required creditor vote may not be achievable",
    "MAJORITY-INDETERMINATE": "Unidentified creditors mean the creditor vote cannot yet be relied on",
    "DIVIDEND-BELOW-MIN": "A creditor's minimum dividend may not be met",
    "CREDITOR-UNIDENTIFIED-MATERIAL": "Some of the debt is owed to creditors that could not be identified",
    "CREDIT-REPORT-REQUIRED": "A credit report is needed to complete some checks",
    "GUARANTOR-NOT-CALLED-UP": "A guaranteed debt needs checking",
    "IE-MATCH-FAIL": "A creditor requires the income and expenditure to match the original application",
    "PROPERTY-DATA-CONFLICT": "Property details need checking against the credit report",
    "PROPERTY-DATA-FROM-CREDIT-REPORT": "Property details need checking against the credit report",
    "CONDITIONAL-VOTER-REQUIRED": "A creditor's vote depends on conditions that need checking",
    "CONDITIONAL-VOTER-CONTACT-REQUIRED": "A creditor needs to be contacted before proposing",
    "COUNTY-COUNCIL-OWN-CRITERIA": "A council creditor applies its own criteria, which need checking",
    # Engine solution codes surfaced as reasons
    "REVIEW_REQUIRED": "A creditor on this case does not vote, so a caseworker needs to review it",
    "FORCED_DMP_VAT": "A previous-year HMRC VAT debt is an automatic IVA fail",
    "FORCED_DRO_LG": "Disposable income is below the Lead Gen DRO threshold",
}

# DMP reasons come from _evaluate_dmp_eligibility as free text with no code.
# Map the known ones to a stable code + figure-free text; the prefixes are
# pinned by a test so a wording change in the engine is caught.
_DMP_MIN_DEBT_PREFIX = "The customer's total debt is £"
_DMP_COUNCIL_TAX_PREFIX = "The customer has lost the right to pay their council tax by instalments"

LABELS = {
    "iva": {
        "POTENTIALLY_SUITABLE": "IVA — Potentially suitable",
        "NEEDS_REVIEW": "IVA — Potentially suitable, needs review",
        "NOT_SUITABLE": "IVA — Not currently suitable",
    },
    "dmp": {
        "POTENTIALLY_SUITABLE": "DMP — Potentially suitable",
        "NOT_SUITABLE": "DMP — Not currently suitable",
        "NOT_ASSESSED": "DMP — Not assessed",
    },
    "overall": {
        "POTENTIALLY_SUITABLE": "Potentially suitable at Lead Gen stage",
        "DRO_REFER": "Debt Relief Order (DRO) — Potentially suitable / Refer for review",
        "DOES_NOT_MEET_CRITERIA": "Does not currently meet criteria",
    },
}
DRO_LABEL = "Debt Relief Order (DRO) — Potentially suitable / Refer for review"
MAX_DISPLAY_REASONS = 3


def _rid(rule):
    return rule.rule_id if hasattr(rule, "rule_id") else (rule or {}).get("rule_id")


def _reason_text(rule_id, rule, rule_titles, review=False):
    if rule_id in ENGINE_ONLY_REASON_TEXT:
        return ENGINE_ONLY_REASON_TEXT[rule_id]
    title = None
    if isinstance(rule, dict):
        title = rule.get("rule_name") or rule.get("title")
    if not title or title == rule_id:
        title = (rule_titles or {}).get(rule_id)
    if title and title != rule_id:
        return f"{title} — needs checking" if review else f"{title} — criteria not met"
    if review:
        return f"Criteria check {rule_id} needs checking by a caseworker"
    return f"Criteria check {rule_id} not met — a caseworker can explain the detail"


def _dmp_reason(text):
    if text.startswith(_DMP_MIN_DEBT_PREFIX):
        return {
            "code": "DMP-MIN-DEBT",
            "text": "Total debt is below the minimum needed for a debt management plan",
        }
    if text.startswith(_DMP_COUNCIL_TAX_PREFIX):
        return {
            "code": "DMP-COUNCIL-TAX",
            "text": "Council tax instalment rights lost with arrears for both the current and previous year",
        }
    return {"code": "DMP-REJECTED", "text": "DMP criteria not met — a caseworker can explain the detail"}


def interpret_engine_result(
    *,
    engine_solution,
    hard_blocks,
    flags,
    creditor_positions,
    dmp_eligibility,
    documents_supplied,
    rule_titles=None,
):
    """Pure interpretation of assess_case() outputs into Lead Gen outcomes.

    engine_solution: assess_case()'s recommended_solution code.
    hard_blocks / flags: in engine order (RuleResult objects or enriched dicts).
    documents_supplied: whether the assessed payload carried any `documents`.
        Evidence-stage treatment applies only when none were supplied, so a
        document that WAS supplied and failed a check is never hidden.
    """
    def is_evidence(rule):
        return (not documents_supplied) and _rid(rule) in EVIDENCE_STAGE_RULES

    eligibility_blocks = [r for r in hard_blocks if not is_evidence(r)]
    review_flags = [r for r in flags if not is_evidence(r)]

    evidence = []
    for r in list(hard_blocks) + list(flags):
        if is_evidence(r):
            label = EVIDENCE_STAGE_RULES[_rid(r)]
            if label not in evidence:
                evidence.append(label)
    evidence_codes = [
        rid for rid in dict.fromkeys(_rid(r) for r in list(hard_blocks) + list(flags) if is_evidence(r))
    ]

    dro_forced = engine_solution == "FORCED_DRO_LG"
    vat_forced = engine_solution == "FORCED_DMP_VAT"

    # ---- IVA -----------------------------------------------------------
    iva_reasons = []
    if dro_forced or vat_forced:
        iva_code = "NOT_SUITABLE"
        iva_reasons.append({"code": engine_solution, "text": ENGINE_ONLY_REASON_TEXT[engine_solution]})
    elif eligibility_blocks:
        iva_code = "NOT_SUITABLE"
    else:
        # The engine's own derivation, re-run without the evidence-stage
        # rules (case=None: the forced-solution overrides were handled above).
        lead_gen_solution = _derive_recommended_solution([], review_flags, creditor_positions or [], None)
        iva_code = "POTENTIALLY_SUITABLE" if lead_gen_solution == "IVA_VIABLE" else "NEEDS_REVIEW"
    for r in eligibility_blocks:
        iva_reasons.append({"code": _rid(r), "text": _reason_text(_rid(r), r, rule_titles)})

    review_reasons = []
    if iva_code == "NEEDS_REVIEW":
        for r in review_flags:
            review_reasons.append({"code": _rid(r), "text": _reason_text(_rid(r), r, rule_titles, review=True)})
        if not review_flags:
            review_reasons.append({"code": "REVIEW_REQUIRED", "text": ENGINE_ONLY_REASON_TEXT["REVIEW_REQUIRED"]})
        review_reasons = list({r["code"]: r for r in review_reasons}.values())

    # ---- DMP -----------------------------------------------------------
    dmp_status = (dmp_eligibility or {}).get("status")
    dmp_reasons = []
    if dmp_status == "DMP_ELIGIBLE":
        dmp_code = "POTENTIALLY_SUITABLE"
    elif dmp_status == "DMP_REJECTED":
        dmp_code = "NOT_SUITABLE"
        dmp_reasons = [_dmp_reason(t) for t in (dmp_eligibility or {}).get("reasons", [])]
    else:
        dmp_code = "NOT_ASSESSED"

    # ---- Overall -------------------------------------------------------
    if dro_forced:
        overall = "DRO_REFER"
    elif iva_code in ("POTENTIALLY_SUITABLE", "NEEDS_REVIEW") or dmp_code == "POTENTIALLY_SUITABLE":
        overall = "POTENTIALLY_SUITABLE"
    else:
        overall = "DOES_NOT_MEET_CRITERIA"

    # Reasons: IVA blockers in engine (execution) order, then DMP reasons.
    all_reasons = list({r["code"]: r for r in (iva_reasons + dmp_reasons)}.values())

    return {
        "overall": {"code": overall, "label": LABELS["overall"][overall]},
        "iva": {"code": iva_code, "label": LABELS["iva"][iva_code]},
        "dmp": {"code": dmp_code, "label": LABELS["dmp"][dmp_code]},
        "dro": {"code": "REFER", "label": DRO_LABEL} if dro_forced else None,
        "reasons": all_reasons[:MAX_DISPLAY_REASONS],
        "reason_codes": [r["code"] for r in all_reasons],
        "iva_reasons": iva_reasons[:MAX_DISPLAY_REASONS],
        "dmp_reasons": dmp_reasons[:MAX_DISPLAY_REASONS],
        "review_reasons": review_reasons[:MAX_DISPLAY_REASONS],
        "evidence_required_later": evidence,
        "evidence_codes": evidence_codes,
    }


def to_lead_gen_result(outcome):
    """Interpret a StandaloneAssessmentResult (views.criteria_views)."""
    return interpret_engine_result(
        engine_solution=outcome.engine_recommended_solution,
        hard_blocks=outcome.hard_blocks,
        flags=outcome.flags,
        creditor_positions=outcome.engine_creditor_positions,
        dmp_eligibility=outcome.dmp_eligibility,
        documents_supplied=bool(outcome.case_data.get("documents")),
    )


def display_client_name(full_name):
    """'Jane Mary Smith' -> 'J. Smith' (enough to confirm the right case)."""
    parts = (full_name or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0][0]}. {parts[-1]}"


# ---------------------------------------------------------------------------
# Activity reporting
# ---------------------------------------------------------------------------

def _london_date(dt):
    return timezone.localtime(dt).date()  # TIME_ZONE = Europe/London


def summarise_activity(checks):
    """Aggregate LeadGenCheck rows into per-user daily "cases checked".

    A case checked = one distinct (user, aryza_reference, Europe/London day)
    with status OK. Repeat checks of the same case by the same user on the same
    day count once; the outcome counted is that day's LATEST successful check.
    Failed attempts are reported separately and never counted as checked.
    """
    latest = {}      # (user_key, ref, day) -> check
    failed = defaultdict(int)
    names = {}
    for c in checks:
        user_key = c.user_id if c.user_id is not None else f"deleted:{c.username}"
        names[user_key] = (c.username, c.department_name)
        if c.status != "OK":
            failed[user_key] += 1
            continue
        key = (user_key, c.aryza_reference, _london_date(c.checked_at))
        if key not in latest or c.checked_at > latest[key].checked_at:
            latest[key] = c

    rows = {}
    for (user_key, _ref, _day), c in latest.items():
        row = rows.setdefault(user_key, {
            "cases_checked": 0, "iva_potential": 0, "iva_needs_review": 0,
            "dmp_potential": 0, "dro_referral": 0, "no_solution": 0,
        })
        row["cases_checked"] += 1
        if c.iva_outcome in ("POTENTIALLY_SUITABLE", "NEEDS_REVIEW"):
            row["iva_potential"] += 1
        if c.iva_outcome == "NEEDS_REVIEW":
            row["iva_needs_review"] += 1
        if c.dmp_outcome == "POTENTIALLY_SUITABLE":
            row["dmp_potential"] += 1
        if c.overall_outcome == "DRO_REFER":
            row["dro_referral"] += 1
        if c.overall_outcome == "DOES_NOT_MEET_CRITERIA":
            row["no_solution"] += 1

    result = []
    for user_key in set(rows) | set(failed):
        username, department = names[user_key]
        result.append({
            "user_id": user_key if isinstance(user_key, int) else None,
            "username": username,
            "department": department,
            **rows.get(user_key, {
                "cases_checked": 0, "iva_potential": 0, "iva_needs_review": 0,
                "dmp_potential": 0, "dro_referral": 0, "no_solution": 0,
            }),
            "failed_attempts": failed.get(user_key, 0),
        })
    result.sort(key=lambda r: (-r["cases_checked"], r["username"]))
    return result
