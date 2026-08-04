"""
Recommendation Engine for Phase 1.
Provides a recommended debt solution based on criteria engine output and case data.
"""

from typing import Dict, Any, Optional


def get_recommendation(
    decision: str,
    engine_output: Dict[str, Any],
    case_data: Dict[str, Any],
    vat_forced: bool = False,
    dro_forced: bool = False,
) -> Dict[str, Any]:
    """
    Determines the recommended debt solution and alternative solutions.

    Args:
        decision: The high-level decision (ELIGIBLE, INELIGIBLE, REFERRED, INCOMPLETE)
        engine_output: The raw output from the criteria engine
        case_data: The normalized case data used for the assessment
        vat_forced: True when the criteria engine's _derive_recommended_solution
            already determined the case must be forced to DMP due to a confirmed
            previous-year HMRC VAT debt (engine_output["recommended_solution"] ==
            "FORCED_DMP_VAT"). Checked BEFORE `decision` is used for anything —
            this mirrors _derive_recommended_solution's own precedence (the VAT
            check sits above hard_blocks there too) so the override cannot be
            diluted into "one more elif" alongside ELIGIBLE/REFERRED/INELIGIBLE.
        dro_forced: True when _derive_recommended_solution already determined a
            Lead Generation case must be forced to DRO because
            lead_gen_disposable_income < £399
            (engine_output["recommended_solution"] == "FORCED_DRO_LG"). Same
            precedence tier as vat_forced — the two are mutually exclusive by
            construction, since the engine routes their simultaneous case to
            REVIEW_REQUIRED before returning here.

    Returns:
        A dictionary containing recommended_solution and alternative_solutions
    """
    if vat_forced:
        return {
            "recommended_solution": {
                "code": "DMP",
                "label": "Debt Management Plan",
                "rationale": (
                    "A previous-year HMRC VAT debt is confirmed — this is an "
                    "automatic IVA fail, so a Debt Management Plan is required "
                    "regardless of all other criteria."
                ),
                "confidence": "HIGH",
            },
            "alternative_solutions": [],
        }

    if dro_forced:
        return {
            "recommended_solution": {
                "code": "DRO",
                "label": "Debt Relief Order",
                "rationale": (
                    "This is a Lead Generation case with disposable income "
                    "below £399 (Total Household Income minus rent-or-mortgage "
                    "payment) — a Debt Relief Order is required regardless of "
                    "all other criteria."
                ),
                "confidence": "HIGH",
            },
            "alternative_solutions": [],
        }

    recommended = None
    alternatives = []

    if decision == "INCOMPLETE":
        return {
            "recommended_solution": None,
            "alternative_solutions": []
        }

    if decision == "ELIGIBLE":
        recommended = {
            "code": "IVA",
            "label": "Individual Voluntary Arrangement",
            "rationale": "Case meets all TIG and creditor-specific criteria for an IVA.",
            "confidence": "HIGH"
        }
        alternatives = [
            {"code": "DMP", "label": "Debt Management Plan", "rationale": "Suitable if the client prefers informal repayment over a 5-6 year period."}
        ]

    elif decision == "REFERRED":
        recommended = {
            "code": "IVA",
            "label": "Individual Voluntary Arrangement",
            "rationale": "Case is potentially suitable for an IVA, but requires manual review of flagged criteria.",
            "confidence": "MEDIUM"
        }
        alternatives = [
            {"code": "DMP", "label": "Debt Management Plan", "rationale": "Alternative if flagged items cannot be resolved for an IVA."}
        ]

    elif decision == "INELIGIBLE":
        # Extract hard block messages for rationale
        hard_blocks = engine_output.get("hard_blocks", [])
        if isinstance(hard_blocks, list):
            reasons = []
            for hb in hard_blocks:
                if hasattr(hb, 'message'):
                    reasons.append(hb.message)
                elif isinstance(hb, dict):
                    reasons.append(hb.get('message', ''))
                else:
                    reasons.append(str(hb))
        else:
            reasons = []
        rationale_prefix = "IVA is not suitable due to hard blocks: "
        rationale = rationale_prefix + "; ".join(reasons) if reasons else "IVA is not suitable for this case."

        # Simple logic for DMP vs BREATHING_SPACE fallback
        # If disposable income is very low or zero, Breathing Space might be better.
        # Otherwise, DMP.
        di = case_data.get("disposable_income", 0)
        
        if di <= 0:
            recommended = {
                "code": "BREATHING_SPACE",
                "label": "Debt Respite Scheme (Breathing Space)",
                "rationale": f"{rationale} With zero or negative disposable income, a temporary stay of action is recommended.",
                "confidence": "MEDIUM"
            }
            alternatives = [
                {"code": "DMP", "label": "Debt Management Plan", "rationale": "Only viable if disposable income can be increased."}
            ]
        else:
            recommended = {
                "code": "DMP",
                "label": "Debt Management Plan",
                "rationale": f"{rationale} A DMP is the recommended fallback for debt repayment.",
                "confidence": "MEDIUM"
            }
            alternatives = [
                {"code": "BREATHING_SPACE", "label": "Breathing Space", "rationale": "Can provide temporary relief if the client is in a crisis situation."}
            ]

    return {
        "recommended_solution": recommended,
        "alternative_solutions": alternatives
    }
