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

from debt_app.engine.criteria import (
    LEAD_GEN_DRO_DI_THRESHOLD,
    SOLUTION_CHECKLIST_FIELDS,
    _derive_recommended_solution,
)

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
    # Only tests that statements are on file for each credit-report bank account.
    "BANK-STATEMENTS": "12 months of bank statements for each bank account",
}

# ---------------------------------------------------------------------------
# Lead Gen-safe reason text
# ---------------------------------------------------------------------------
# Each reason's headline `text` is the rule's existing GlobalCriteria title
# (rule_name) — generic, no case data — keyed by the same rule ID. Engine-only
# rule IDs have no GlobalCriteria row, so they get a short neutral description
# here. The engine's own plain-English message (with the case figures and, for
# creditor rules, the creditor's name) goes in `detail`, so the advisor can open
# a reason and see why it fired (business decision 2026-10-12).
ENGINE_ONLY_REASON_TEXT = {
    "CREDITOR-BLOCKED": "A creditor on this case is expected to block an IVA",
    "EQUITY-AGE": "Property equity is too high for an IVA",
    "SPECIAL-EMPLOYER-COPPERPOT": "A creditor on this case does not accept IVAs for police employees",
    "DEBT-REPAYABILITY-REJECT": "A creditor considers the debt repayable without an IVA",
    "MAJORITY-IMPOSSIBLE": "The required creditor vote cannot be reached",
    "MAJORITY-INDETERMINATE": "Some creditors' votes are not yet known, so the creditor vote cannot yet be relied on",
    "DIVIDEND-BELOW-MIN": "A creditor's minimum dividend may not be met",
    "CREDITOR-UNIDENTIFIED-MATERIAL": "Some of the debt is owed to creditors whose vote is not yet known",
    "PREVIOUS-IVA-UNCONFIRMED": "Whether the customer has had a previous IVA needs confirming",
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

IVA_CONFLICT_TEXT = "IVA is not currently suitable for this conflict"
IVA_CONFLICT_DETAIL = (
    "A previous-year HMRC VAT debt is an automatic IVA fail. It points to a DMP, "
    "but the Lead Gen DRO threshold also applies, so no solution is chosen until "
    "a caseworker has reviewed the case."
)

FORCED_CONFLICT_TEXT = (
    "A previous-year HMRC VAT debt and the Lead Gen DRO threshold both apply, "
    "so a caseworker needs to decide between a DRO and a DMP"
)

# Open banking: Aryza holds no open banking data, so every rule that needs it
# returns the same "could not be completed, check manually" flag on every case.
# Lead Gen shows those as ONE review line, after the case's real issues. The
# engine messages are recognised by these prefixes (pinned by a test).
_OPEN_BANKING_UNAVAILABLE_PREFIXES = (
    "There is no open banking data loaded",
    "Open banking data was not available",
)
OPEN_BANKING_CODE = "OPEN-BANKING-NOT-AVAILABLE"


def _needs_open_banking(rule):
    return (_message(rule) or "").startswith(_OPEN_BANKING_UNAVAILABLE_PREFIXES)


def _open_banking_reason(rules, rule_titles):
    names = list(dict.fromkeys(
        (rule_titles or {}).get(_rid(r)) or _rid(r) for r in rules
    ))
    n = len(names)
    return _reason(
        OPEN_BANKING_CODE,
        f"{n} check{'s need' if n != 1 else ' needs'} open banking data — check bank statements manually",
        "These checks could not be completed because there is no open banking data for this case. "
        "Check the customer's bank statements for: " + "; ".join(names) + ".",
    )


# Review flags that ask the advisor to check the same thing under another
# criteria set. When both fire, only the first is listed. Hard blocks are
# never merged.
SAME_CHECK_AS = {
    "TIX-02": "TIG-19.1",  # Shop Direct account at least 6 months old
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
        "REVIEW_REQUIRED": "DMP — Caseworker review needed",
        "NOT_SUITABLE": "DMP — Not currently suitable",
        "NOT_ASSESSED": "DMP — Not assessed",
    },
    "overall": {
        "POTENTIALLY_SUITABLE": "Potentially suitable at Lead Gen stage",
        "DRO_REFER": "Debt Relief Order (DRO) — Potentially suitable / Refer for review",
        "DOES_NOT_MEET_CRITERIA": "Does not currently meet criteria",
        "REVIEW_REQUIRED": "Caseworker review needed — DRO or DMP",
    },
}
DRO_LABEL = "Debt Relief Order (DRO) — Potentially suitable / Refer for review"
LABELS["dro"] = {
    "REFER": DRO_LABEL,
    "POTENTIALLY_SUITABLE": "DRO — Potentially suitable",
    "NEEDS_REVIEW": "DRO — Potentially suitable, details to confirm",
    "NOT_SUITABLE": "DRO — Not currently suitable",
    "NOT_ASSESSED": "DRO — Not assessed",
}
LABELS["bankruptcy"] = {
    "POTENTIALLY_SUITABLE": "Bankruptcy — Potentially suitable",
    "NEEDS_REVIEW": "Bankruptcy — Potentially suitable, details to confirm",
    "NOT_SUITABLE": "Bankruptcy — Not currently suitable",
    "NOT_ASSESSED": "Bankruptcy — Not assessed",
}
# Engine solution_eligibility status -> Lead Gen outcome code.
_SOLUTION_CODE = {"ELIGIBLE": "POTENTIALLY_SUITABLE", "NEEDS_REVIEW": "NEEDS_REVIEW", "NOT_ELIGIBLE": "NOT_SUITABLE"}
DMP_NO_SURPLUS_TEXT = "No money left each month for a DMP payment"
# The DRO card's surplus reason (_evaluate_dro_solution). The £399 rule is the
# business's own income test for Lead Gen, so this one reason never stops a
# £399 referral; it is listed as a detail to confirm instead. Pinned by a test.
_DRO_SURPLUS_PREFIX = "Monthly surplus is £"
MAX_DISPLAY_REASONS = 3


def _rid(rule):
    return rule.rule_id if hasattr(rule, "rule_id") else (rule or {}).get("rule_id")


def _message(rule):
    """The engine's plain-English message for a rule, or None."""
    msg = rule.message if hasattr(rule, "message") else (rule or {}).get("message")
    return (msg or "").strip() or None


def _reason(code, text, detail=None):
    return {"code": code, "text": text, "detail": detail}


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
    detail = (text or "").strip() or None
    if text.startswith(_DMP_MIN_DEBT_PREFIX):
        return _reason("DMP-MIN-DEBT", "Total debt is below the minimum needed for a debt management plan", detail)
    if text.startswith(_DMP_COUNCIL_TAX_PREFIX):
        return _reason(
            "DMP-COUNCIL-TAX",
            "Council tax instalment rights lost with arrears for both the current and previous year",
            detail,
        )
    return _reason("DMP-REJECTED", "DMP criteria not met", detail)


_HOUSING_SOURCE_TEXT = {
    "rent": "rent (£{amount:,.2f} a month on the SFS)",
    "mortgage": "mortgage payments (£{amount:,.2f} a month on the credit report)",
}


def _forced_dro_detail(lead_gen_disposable_income, housing=None):
    if lead_gen_disposable_income is None:
        return None
    template = _HOUSING_SOURCE_TEXT.get((housing or {}).get("source"))
    if template:
        income = f"household income after {template.format(amount=housing['amount'])}"
    else:
        income = "household income (no rent or mortgage payment is recorded)"
    return (
        f"The customer's {income} is £{lead_gen_disposable_income:,.2f} "
        f"per month, which is below the £{LEAD_GEN_DRO_DI_THRESHOLD:,.2f} Lead Gen threshold. "
        "The case should be referred for a Debt Relief Order (DRO) review instead of an IVA."
    )


def _solution_card(solution_eligibility, code):
    return next((s for s in (solution_eligibility or []) if s.get("code") == code), None)


def _solution_outcome(card, kind, prefix):
    """An engine solution card as a Lead Gen outcome with its reasons, the
    details the advisor still has to confirm, and the engine's notes."""
    if card is None:
        return {"code": "NOT_ASSESSED", "label": LABELS[kind]["NOT_ASSESSED"],
                "reasons": [], "to_confirm": [], "notes": []}
    code = _SOLUTION_CODE.get(card.get("status"), "NOT_ASSESSED")
    return {
        "code": code,
        "label": LABELS[kind][code],
        "reasons": [_reason(f"{prefix}-{i}", text) for i, text in enumerate(card.get("reasons") or [], 1)],
        "to_confirm": list(card.get("to_confirm") or []),
        "notes": list(card.get("notes") or []),
    }


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
    lead_gen_disposable_income=None,
    previous_year_vat=False,
    solution_eligibility=None,
    lead_gen_housing=None,
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
    lead_gen_disposable_income: the engine's figure behind the forced DRO,
        quoted in that reason's detail.
    previous_year_vat: the assessed checklist's hmrc_previous_year_vat tick.
        When the engine's forced DMP (VAT) and forced DRO both fire it returns
        REVIEW_REQUIRED instead of either (_derive_recommended_solution). Lead
        Gen keeps that decision: the overall outcome is REVIEW_REQUIRED, no
        DRO referral is made and no route is chosen; a review reason says a
        caseworker must decide between a DRO and a DMP. IVA is not suitable
        (both rules rule it out). With no income recorded the DRO side is not
        shown (see income_missing), so the VAT outcome stands.

    solution_eligibility: the engine's per-solution cards (DMP / DRO /
        Bankruptcy). The DRO and Bankruptcy cards are shown as their own
        outcomes. The £399 rule only refers to a DRO when the DRO card is not
        "not eligible" (debt, surplus, property, vehicle, and the advisor's
        answers); otherwise the IVA stays ruled out but no referral is made.
        The DMP card's own checks (disposable income above £0) can make the
        DMP not suitable (business decision 2026-10-13). None (e.g. an old
        saved snapshot) keeps the previous behaviour.
    lead_gen_housing: what the engine deducted for the £399 figure, quoted in
        the forced-DRO detail.

    Every reason is {code, text, detail}: `text` is the short, figure-free
    headline; `detail` is the engine's plain-English explanation (or None).
    """
    def is_evidence(rule):
        return (not documents_supplied) and _rid(rule) in EVIDENCE_STAGE_RULES

    eligibility_blocks = [r for r in hard_blocks if not is_evidence(r)]
    review_flags = [r for r in flags if not is_evidence(r)]
    # The engine keeps an unreachable majority as a review flag, so a
    # caseworker in CAT can still overrule it. At Lead Gen it makes the IVA
    # not currently suitable: even if every undecided creditor voted yes the
    # vote fails (business decision 2026-10-13).
    majority_impossible = [r for r in review_flags if _rid(r) == "MAJORITY-IMPOSSIBLE"]
    review_flags = [r for r in review_flags if _rid(r) != "MAJORITY-IMPOSSIBLE"]

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
    dro = _solution_outcome(_solution_card(solution_eligibility, "DRO"), "dro", "DRO")
    bankruptcy = _solution_outcome(_solution_card(solution_eligibility, "BANKRUPTCY"), "bankruptcy", "BANKRUPTCY")
    # The £399 rule refers to a DRO only when the DRO limits allow one
    # (debt, property, vehicle, and the advisor's answers). Its own surplus
    # test replaces the card's £75 surplus limit.
    dro_blockers = [r for r in dro["reasons"] if not r["text"].startswith(_DRO_SURPLUS_PREFIX)]
    dro_referred = dro_forced and dro["code"] != "NOT_ASSESSED" and not dro_blockers
    if dro_forced and dro["code"] == "NOT_ASSESSED":
        dro_referred = True  # no card (e.g. an old snapshot): the previous behaviour
    if dro_referred:
        surplus = [r["text"] for r in dro["reasons"] if r not in dro_blockers]
        dro.update(code="REFER", label=LABELS["dro"]["REFER"], reasons=[],
                   to_confirm=surplus + dro["to_confirm"])
    # The engine only returns REVIEW_REQUIRED with the VAT tick set when the
    # VAT and DRO overrides collide.
    forced_conflict = engine_solution == "REVIEW_REQUIRED" and previous_year_vat and not income_missing
    vat_forced = engine_solution == "FORCED_DMP_VAT" or (
        engine_solution == "REVIEW_REQUIRED" and previous_year_vat and income_missing
    )

    # ---- IVA -----------------------------------------------------------
    iva_reasons = []
    if forced_conflict:
        iva_code = "NOT_SUITABLE"
        iva_reasons.append(_reason("FORCED-SOLUTION-CONFLICT", IVA_CONFLICT_TEXT, IVA_CONFLICT_DETAIL))
    elif dro_forced or vat_forced:
        iva_code = "NOT_SUITABLE"
        detail = _forced_dro_detail(lead_gen_disposable_income, lead_gen_housing) if dro_forced else None
        if dro_forced and not dro_referred and detail:
            detail += " However, a DRO is not possible on this case: see the DRO reasons."
        code = "FORCED_DMP_VAT" if engine_solution == "REVIEW_REQUIRED" else engine_solution
        iva_reasons.append(_reason(code, ENGINE_ONLY_REASON_TEXT[code], detail))
    elif eligibility_blocks or majority_impossible:
        iva_code = "NOT_SUITABLE"
    else:
        # The engine's own derivation, re-run without the evidence-stage
        # rules (case=None: the forced-solution overrides were handled above).
        lead_gen_solution = _derive_recommended_solution([], review_flags, creditor_positions or [], None)
        iva_code = "POTENTIALLY_SUITABLE" if lead_gen_solution == "IVA_VIABLE" else "NEEDS_REVIEW"
    for r in eligibility_blocks:
        iva_reasons.append(_reason(_rid(r), _reason_text(_rid(r), r, rule_titles), _message(r)))
    for r in majority_impossible:
        iva_reasons.append(_reason(_rid(r), _reason_text(_rid(r), r, rule_titles), _message(r)))

    # Engine flags are listed whatever the IVA outcome: some still matter when
    # the IVA is not suitable (e.g. a debt listed under a debt collector, which
    # needs correcting in Aryza for a DMP too). They never change an outcome.
    open_banking_flags = [r for r in review_flags if _needs_open_banking(r)]
    other_flags = [r for r in review_flags if not _needs_open_banking(r)]
    listed = {_rid(r) for r in other_flags}
    review_reasons = [
        _reason(_rid(r), _reason_text(_rid(r), r, rule_titles, review=True), _message(r))
        for r in other_flags if SAME_CHECK_AS.get(_rid(r)) not in listed
    ]
    if open_banking_flags:
        review_reasons.append(_open_banking_reason(open_banking_flags, rule_titles))
    if iva_code == "NEEDS_REVIEW" and not review_flags:
        review_reasons.append(_reason("REVIEW_REQUIRED", ENGINE_ONLY_REASON_TEXT["REVIEW_REQUIRED"]))
    review_reasons = list({r["code"]: r for r in review_reasons}.values())
    if forced_conflict:
        review_reasons.append(_reason(
            "FORCED-SOLUTION-CONFLICT", FORCED_CONFLICT_TEXT,
            _forced_dro_detail(lead_gen_disposable_income, lead_gen_housing),
        ))

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
    # The DMP card adds the affordability check (disposable income above £0):
    # any card reason that is not one of dmp_eligibility's own reasons.
    dmp_card = _solution_card(solution_eligibility, "DMP")
    if dmp_code != "NOT_ASSESSED" and dmp_card and not income_missing:
        own = set((dmp_eligibility or {}).get("reasons") or [])
        extra = [t for t in (dmp_card.get("reasons") or []) if t not in own]
        if extra:
            dmp_code = "NOT_SUITABLE"
            dmp_reasons += [_reason("DMP-NO-SURPLUS", DMP_NO_SURPLUS_TEXT, t) for t in extra]
    # In the VAT-vs-DRO conflict a DMP that passes its own checks is still not
    # the chosen route: it waits on the caseworker like the DRO does. A DMP
    # that fails its own checks stays NOT_SUITABLE with its reasons.
    if forced_conflict and dmp_code == "POTENTIALLY_SUITABLE":
        dmp_code = "REVIEW_REQUIRED"

    # ---- Overall -------------------------------------------------------
    if forced_conflict:
        overall = "REVIEW_REQUIRED"
    elif dro_referred:
        overall = "DRO_REFER"
    elif (iva_code in ("POTENTIALLY_SUITABLE", "NEEDS_REVIEW") or dmp_code == "POTENTIALLY_SUITABLE"
          # A DRO counts once its limits pass; not on an unrecorded income.
          or (dro["code"] in ("POTENTIALLY_SUITABLE", "NEEDS_REVIEW") and not income_missing)):
        overall = "POTENTIALLY_SUITABLE"
    else:
        overall = "DOES_NOT_MEET_CRITERIA"

    # Reasons: IVA blockers in engine (execution) order, then DMP reasons.
    all_reasons = list({r["code"]: r for r in (iva_reasons + dmp_reasons)}.values())

    return {
        "overall": {"code": overall, "label": LABELS["overall"][overall]},
        "iva": {"code": iva_code, "label": LABELS["iva"][iva_code]},
        "dmp": {"code": dmp_code, "label": LABELS["dmp"][dmp_code]},
        "dro": dro,
        "bankruptcy": bankruptcy,
        "reasons": all_reasons[:MAX_DISPLAY_REASONS],
        "reason_codes": [r["code"] for r in all_reasons],
        # Every IVA / DMP reason, uncapped, so the screen can group them by
        # solution and never drop one silently.
        "iva_reasons": iva_reasons,
        "dmp_reasons": dmp_reasons,
        # Engine DMP notes (which debts go in / stay out of the DMP). Never
        # affect any outcome above.
        "dmp_notes": list((dmp_eligibility or {}).get("notes") or []) if dmp_code != "NOT_ASSESSED" else [],
        "review_reasons": review_reasons,
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


def to_lead_gen_result(outcome, income_missing=False, rule_titles=None):
    """Interpret a StandaloneAssessmentResult (views.criteria_views).

    rule_titles: {rule_key: rule_name} from GlobalCriteria. The engine's
    RuleResults carry no title, so without this every headline falls back to
    the bare rule ID.
    """
    return interpret_engine_result(
        rule_titles=rule_titles,
        engine_solution=outcome.engine_recommended_solution,
        hard_blocks=outcome.hard_blocks,
        flags=outcome.flags,
        creditor_positions=outcome.engine_creditor_positions,
        dmp_eligibility=outcome.dmp_eligibility,
        documents_supplied=bool(outcome.case_data.get("documents")),
        income_missing=income_missing,
        lead_gen_disposable_income=(outcome.response_body or {}).get("lead_gen_disposable_income"),
        previous_year_vat=bool((outcome.case_data.get("dmp_checklist") or {}).get("hmrc_previous_year_vat")),
        solution_eligibility=(outcome.response_body or {}).get("solution_eligibility"),
        lead_gen_housing=getattr(outcome, "lead_gen_housing", None),
    )


def _pounds(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def case_figures(case_data, income_missing=False):
    """The figures the criteria were run on, for the advisor (pounds/month).

    case_data: the engine payload (StandaloneAssessmentResult.case_data).
    A figure that was not recorded is None ("Not recorded"), never £0:
      * income when lead_gen_income_missing() says it is missing;
      * expenditure when the SFS has no expenses (total 0), the same reading
        _prepare_engine_payload uses ("income present but no SFS expenses yet").
    disposable_income is exactly what the checks used (TIG-02, DRO surplus,
    DMP): the estimated disposable income when one was available (basis
    "ESTIMATE", with the full I&E figure alongside), otherwise the full I&E
    figure, including Aryza's own DI fallback when no income rows exist.
    """
    case_data = case_data or {}
    expenditure = _pounds((case_data.get("expenditure") or {}).get("total"))
    estimate_used = "full_ie_disposable_income" in case_data
    return {
        "total_unsecured_debt": _pounds(case_data.get("total_unsecured_debt")),
        "monthly_income": None if income_missing else _pounds((case_data.get("income") or {}).get("total")),
        "monthly_expenditure": expenditure if expenditure else None,
        "disposable_income": _pounds(case_data.get("disposable_income")),
        "disposable_income_basis": "ESTIMATE" if estimate_used else "FULL_IE",
        "full_ie_disposable_income": _pounds(case_data.get("full_ie_disposable_income")) if estimate_used else None,
    }


# ---------------------------------------------------------------------------
# DMP checklist answers
# ---------------------------------------------------------------------------
# The engine's only answer-driven DMP rejection is council tax: arrears for
# BOTH the current and previous year AND the right to pay by instalments lost
# (_evaluate_dmp_eligibility). Lead Gen asks those three questions and feeds
# them through the same inputs the CAT screen uses: the two year answers as
# council-tax creditor-row selections, the instalment answer as the
# case-level checkbox (criteria_views.build_dmp_checklist).
#
# The utility / phone answers are the CAT screen's case-level checkboxes. They
# never change the DMP outcome; they only produce the engine's DMP notes
# (included in / left out of the DMP), returned as `dmp_notes`.

LEAD_GEN_DMP_CASE_LEVEL_QUESTIONS = (
    "current_gas_bill",
    "current_electric_bill",
    "previous_gas_provider_debt",
    "previous_electric_provider_debt",
    "current_phone_contract",
    "lost_right_to_pay_instalments",
)

# HMRC VAT: the CAT screen's two VAT ticks, asked only once a check has shown
# the case has an HMRC creditor (the engine's hmrc_is_creditor). A
# previous-year VAT debt forces the engine's FORCED_DMP_VAT; the parent tick
# alone changes nothing (_derive_recommended_solution, _sanitize_dmp_checklist).
LEAD_GEN_VAT_QUESTIONS = (
    "hmrc_debt_has_vat",
    "hmrc_previous_year_vat",
)

LEAD_GEN_DMP_QUESTIONS = (
    "council_tax_current_year",
    "council_tax_previous_year",
) + LEAD_GEN_DMP_CASE_LEVEL_QUESTIONS + LEAD_GEN_VAT_QUESTIONS


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
    checklist_raw = {q: answers[q] for q in LEAD_GEN_DMP_CASE_LEVEL_QUESTIONS}
    for q in LEAD_GEN_VAT_QUESTIONS:
        if answers[q]:
            checklist_raw[q] = True
    return creditor_rows, checklist_raw


# DRO / Bankruptcy questions: the engine's SOLUTION_CHECKLIST_FIELDS, each
# Yes / No / not answered. Not answered stays None, which the engine shows as
# a detail to confirm, never as a pass.
def _tri_state(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "1"):
            return True
        if v in ("false", "no", "0"):
            return False
    return None


def lead_gen_solution_inputs(raw):
    """Lead Gen DRO / Bankruptcy answers -> solution_checklist for
    run_standalone_assessment. `raw` may be a dict or a JSON string (the
    multipart request sent when a credit report is uploaded)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except ValueError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {f: _tri_state(raw.get(f)) for f in SOLUTION_CHECKLIST_FIELDS}


def without_vat_answers(checklist_raw):
    """The same case-level answers with the HMRC VAT ticks removed."""
    return {k: v for k, v in (checklist_raw or {}).items() if k not in LEAD_GEN_VAT_QUESTIONS}


# ---------------------------------------------------------------------------
# Estimated disposable income (the disposable income the Lead Gen checks use)
# ---------------------------------------------------------------------------
# Manager's formula: minimum expenditure = £799 (first adult) + £579 per
# additional adult + £331 per child; estimate = monthly income - rent - that.
# Since 2026-10-13 the Lead Gen check uses it (floored at £0) as the case's
# disposable income for the IVA / DMP / DRO checks; it never feeds the engine's
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
            f"{_money(estimate)} per month. The Lead Gen checks use this estimate. "
            "A full I&E assessment is still required to confirm affordability and suitability."
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


_EMPTY_ACTIVITY_ROW = {
    "cases_checked": 0, "iva_potential": 0, "iva_needs_review": 0,
    "dmp_potential": 0, "dro_referral": 0, "no_solution": 0,
    # Overall "caseworker review needed" (the VAT / DRO conflict).
    "caseworker_review": 0,
    # Checks that warned income is not recorded in the fact find.
    "income_not_recorded": 0,
}
ACTIVITY_COUNT_KEYS = tuple(_EMPTY_ACTIVITY_ROW) + ("failed_attempts",)


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
        row = rows.setdefault(user_key, dict(_EMPTY_ACTIVITY_ROW))
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
        if c.overall_outcome == "REVIEW_REQUIRED":
            row["caseworker_review"] += 1
        if INCOME_NOT_RECORDED_WARNING["code"] in (c.reason_codes or []):
            row["income_not_recorded"] += 1

    result = []
    for user_key in set(rows) | set(failed):
        username, department = names[user_key]
        result.append({
            "user_id": user_key if isinstance(user_key, int) else None,
            "username": username,
            "department": department,
            **rows.get(user_key, _EMPTY_ACTIVITY_ROW),
            "failed_attempts": failed.get(user_key, 0),
        })
    result.sort(key=lambda r: (-r["cases_checked"], r["username"]))
    return result
