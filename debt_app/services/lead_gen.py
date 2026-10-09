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

import json
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
#   * TIG-13 (previous-IVA termination report): approved business decision
#     (2026-10-10) to show it as evidence required later at Lead Gen. The rule
#     only fires for a previous IVA, and only tests that the report is on file;
#     CAT / the full assessment still hard-block without it.
# NOT included:
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
    "TIG-13": "Termination report",
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
    income_missing=False,
):
    """Pure interpretation of assess_case() outputs into Lead Gen outcomes.

    engine_solution: assess_case()'s recommended_solution code.
    hard_blocks / flags: in engine order (RuleResult objects or enriched dicts).
    documents_supplied: whether the assessed payload carried any `documents`.
        Evidence-stage treatment applies only when none were supplied, so a
        document that WAS supplied and failed a check is never hidden.
    income_missing: no income is recorded in the fact find (see
        lead_gen_income_missing). The engine's £399 forced DRO then rests on an
        unknown income, so it is not shown as a DRO referral; a warning tells
        staff to check the fact find instead. Recorded income (including an
        entered £0) keeps the existing DRO rule.
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

    dro_forced = engine_solution == "FORCED_DRO_LG" and not income_missing
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
        "warnings": [dict(INCOME_NOT_RECORDED_WARNING)] if income_missing else [],
    }


INCOME_NOT_RECORDED_WARNING = {
    "code": "INCOME-NOT-RECORDED",
    "text": "Income not recorded — check the fact find",
}


def lead_gen_income_missing(case_obj):
    """True when the case has no usable income: a £0 total that is not an
    entered figure (no income row, a blank one, or a failed read). An income
    row with amounts entered — even £0 — is recorded income."""
    total = (getattr(case_obj, "income", None) or {}).get("total") or 0
    return total <= 0 and getattr(case_obj, "income_recorded", None) is not True


def to_lead_gen_result(outcome, income_missing=False):
    """Interpret a StandaloneAssessmentResult (views.criteria_views)."""
    return interpret_engine_result(
        engine_solution=outcome.engine_recommended_solution,
        hard_blocks=outcome.hard_blocks,
        flags=outcome.flags,
        creditor_positions=outcome.engine_creditor_positions,
        dmp_eligibility=outcome.dmp_eligibility,
        documents_supplied=bool(outcome.case_data.get("documents")),
        income_missing=income_missing,
    )


# ---------------------------------------------------------------------------
# DMP checklist answers (council tax)
# ---------------------------------------------------------------------------
# The engine's only answer-driven DMP rejection is council tax: arrears for
# BOTH the current and previous year AND the right to pay by instalments lost
# (_evaluate_dmp_eligibility). Lead Gen asks exactly those three questions and
# feeds them through the same inputs the CAT screen uses: the two year answers
# as council-tax creditor-row selections, the instalment answer as the
# case-level checkbox (criteria_views.build_dmp_checklist).

LEAD_GEN_DMP_QUESTIONS = (
    "council_tax_current_year",
    "council_tax_previous_year",
    "lost_right_to_pay_instalments",
)


def _is_yes(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return value == 1


def lead_gen_dmp_inputs(raw):
    """Lead Gen DMP answers -> (creditor_rows, dmp_checklist_raw) for
    run_standalone_assessment. Unknown keys are ignored; a missing or
    unticked answer means "no". `raw` may be a dict or a JSON string (the
    multipart request sent when a credit report is uploaded)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except ValueError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    answers = {q: _is_yes(raw.get(q)) for q in LEAD_GEN_DMP_QUESTIONS}
    creditor_rows = []
    if answers["council_tax_current_year"]:
        creditor_rows.append({"debt_type_normalised": "council_tax", "value": "current"})
    if answers["council_tax_previous_year"]:
        creditor_rows.append({"debt_type_normalised": "council_tax", "value": "previous"})
    checklist_raw = {"lost_right_to_pay_instalments": answers["lost_right_to_pay_instalments"]}
    return creditor_rows, checklist_raw


# ---------------------------------------------------------------------------
# Estimated disposable income (informational guideline only)
# ---------------------------------------------------------------------------
# Manager's formula: minimum expenditure = £799 (first adult) + £579 per
# additional adult + £331 per child; estimate = monthly income - rent - that.
# Nothing here feeds the IVA / DMP / DRO outcomes above or the engine's
# lead_gen_disposable_income (£399 forced-DRO rule).
EDI_FIRST_ADULT_PENCE = 79_900
EDI_ADDITIONAL_ADULT_PENCE = 57_900
EDI_CHILD_PENCE = 33_100

_EDI_UNAVAILABLE = "Estimated disposable income unavailable — "
EDI_UNAVAILABLE_TEXT = {
    "NO_SFS": "SFS information is not available.",
    "EMPTY_SFS": "SFS information is not available.",
    "SFS_UNREADABLE": "SFS information could not be read. Please try again.",
    "INVALID_HOUSEHOLD": "the number of adults and children on the SFS is not valid.",
    "RENT_NOT_RECORDED": "current rent is not recorded.",
    "INCOME_NOT_RECORDED": "monthly income is not recorded.",
}


def _money(pence):
    """-900 -> '-£9.00', 170900 -> '£1,709.00'."""
    sign = "-" if pence < 0 else ""
    return f"{sign}£{abs(pence) / 100:,.2f}"


def _count(value):
    """A household count from the SFS: a whole number >= 0, else None."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def estimate_disposable_income(household, monthly_income_pence):
    """Estimated DI from the active SFS household and the existing monthly income.

    household: AryzaClient.fetch_sfs_household() output (or None).
    monthly_income_pence: CaseData.income["total"] — the same figure the engine
        uses as total_income. 0 means income was not captured (see
        _prepare_engine_payload), so it is unavailable, never a £0 estimate.

    Missing or invalid data makes the estimate unavailable rather than being
    treated as 0. Household values are not capped.
    """
    household = household or {"status": "NO_SFS"}
    status = household.get("status")
    if status != "OK":
        code = status if status in ("NO_SFS", "EMPTY_SFS") else "SFS_UNREADABLE"
        return _edi_unavailable([code])

    reasons = []
    adults = _count(household.get("adults"))
    under_16 = _count(household.get("under_16"))
    under_18 = _count(household.get("under_18"))
    if adults is None or adults < 1 or under_16 is None or under_18 is None:
        reasons.append("INVALID_HOUSEHOLD")
    rent = household.get("rent_monthly_pence")
    if rent is None or rent < 0:
        reasons.append("RENT_NOT_RECORDED")
    if not monthly_income_pence or monthly_income_pence <= 0:
        reasons.append("INCOME_NOT_RECORDED")
    if reasons:
        return _edi_unavailable(reasons)

    children = under_16 + under_18  # under_18 = ages 16-17
    minimum = (EDI_FIRST_ADULT_PENCE
               + EDI_ADDITIONAL_ADULT_PENCE * (adults - 1)
               + EDI_CHILD_PENCE * children)
    estimate = monthly_income_pence - rent - minimum
    return {
        "available": True,
        "adults": adults,
        "children": children,
        "monthly_income": monthly_income_pence / 100,
        "monthly_rent": rent / 100,
        "minimum_expenditure": minimum / 100,
        "estimated_disposable_income": estimate / 100,
        "message": (
            f"For {adults} adult(s) and {children} child(ren), the estimated disposable income is "
            f"{_money(estimate)} per month. Please use this estimate as a guideline only when making "
            "your decision. A full I&E assessment is still required to confirm affordability and suitability."
        ),
    }


def _edi_unavailable(codes):
    codes = list(dict.fromkeys(codes))
    return {
        "available": False,
        "reasons": [{"code": c, "text": _EDI_UNAVAILABLE + EDI_UNAVAILABLE_TEXT[c]} for c in codes],
    }


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
