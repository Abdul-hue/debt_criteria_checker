"""Compare models.py field defs vs migrations 0009, 0011, 0012."""
import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

MODELS_PATH = BASE / "debt_app" / "models.py"
MIG_009 = (BASE / "debt_app" / "migrations" / "0009_phase2_schema.py").read_text(encoding="utf-8")
MIG_011 = (BASE / "debt_app" / "migrations" / "0011_phase3_voter_fields.py").read_text(encoding="utf-8")
MIG_012 = (BASE / "debt_app" / "migrations" / "0012_phase3_client_flags.py").read_text(encoding="utf-8")

SCOPE = {
    "CreditorCriteria": [
        "status", "reject_if_in_dmp", "reject_if_never_made_payment",
        "reject_if_ie_doesnt_match_application", "reject_if_debt_repayable_within_months",
        "reject_if_client_still_has_asset", "reject_if_majority_share_exceeds_pct",
        "reject_if_second_iva", "reject_if_police_employed", "reject_if_equity_exceeds_debt",
        "requires_pg_called_up", "requires_arrangement_call_before_proposing",
        "requires_grant_overpayment_only", "vehicle_arrears_repossession_months",
        "fees_cap_percentage", "termination_risk_if_vehicle_on_finance",
        "conditional_voter", "conditional_voter_min_dividend_pence",
        "open_banking_access", "min_di_for_fees_pence", "fraud_claim_risk",
        "blocked_until_cleared", "blocked_reason", "last_reviewed",
    ],
    "CouncilRule": [
        "council_name", "status", "min_dividend_pence", "reject_if_employed",
        "reject_if_unemployed_and_homeowner", "reject_if_benefits_only",
        "reject_if_any_benefits", "reject_if_previous_iva", "reject_if_dro_criteria_met",
        "reject_if_aoe_in_place", "reject_if_joint_one_party_only",
        "reject_if_joint_both_parties", "do_not_chase", "blocked_reason",
        "source_priority", "last_reviewed",
    ],
    "CountyCouncilRouting": ["county_name", "district_name", "council_rule"],
    "DebtTypeCouncilVote": ["council", "debt_type", "status"],
    "ConditionalVoterRule": [
        "creditor", "min_dividend_pence", "contact_required",
        "contact_name", "contact_email",
    ],
    "CreditorOpenBankingRule": ["creditor", "review_period_months", "ie_must_match_exactly"],
    "ClientFlags": [
        "application", "is_currently_in_dmp", "is_royal_mail_employee",
        "is_police_officer", "previous_iva_failed",
    ],
    "Voter": [
        "is_joint", "last_payment_date", "first_payment_made",
        "vehicle_arrears_months", "ie_matches_loan_application",
        "arrangement_confirmed_before_proposing", "client_still_has_asset_in_possession",
        "is_grant_overpayment", "guarantee_called_up",
    ],
}


def parse_models_fields():
    tree = ast.parse(MODELS_PATH.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name):
                        fields[t.id] = ast.get_source_segment(
                            MODELS_PATH.read_text(encoding="utf-8"), item
                        ) or ""
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields[item.target.id] = ast.get_source_segment(
                    MODELS_PATH.read_text(encoding="utf-8"), item
                ) or ""
        out[node.name] = fields
    return out


def mig_snippet(field_name, mig_text):
    # Find AddField or CreateModel block for field
    patterns = [
        rf"name='{field_name}'[^)]*\)",
        rf"'{field_name}',\s*models\.([^)]+(?:\([^)]*\))?[^)]*)\)",
        rf"\('{field_name}',\s*models\.([\s\S]*?)\),\s*\n",
    ]
    for pat in patterns:
        m = re.search(pat, mig_text)
        if m:
            return m.group(0).replace("\n", " ")[:200]
    if f"'{field_name}'" in mig_text:
        idx = mig_text.index(f"'{field_name}'")
        return mig_text[idx : idx + 180].replace("\n", " ")
    return "(not in 0009/0011/0012 — check 0010 seeds or earlier)"


def norm(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    s = s.replace("models.", "")
    return s


def compare(model, field, model_src, mig_src):
    ms = norm(model_src)
    mg = norm(mig_src)
    if not model_src and not mig_src:
        return "match", ms, mg
    if "not in 0009" in mig_src:
        return "match", ms, mg
    # runtime checks
    runtime_keys = ["default=", "null=", "blank=", "choices=", "on_delete=", "related_name="]
    for k in runtime_keys:
        mv = re.search(k + r"([^,\)]+)", ms)
        gv = re.search(k + r"([^,\)]+)", mg)
        if (mv or gv) and (not mv or not gv or mv.group(1) != gv.group(1)):
            if k == "help_text=":
                continue
            return "drift_runtime", ms[:120], mg[:120]
    if ms != mg and ("help_text" in ms or "help_text" in mg):
        if re.sub(r"help_text=[^,]+,?", "", ms) == re.sub(r"help_text=[^,]+,?", "", mg):
            return "drift_cosmetic", ms[:120], mg[:120]
    if ms == mg or ms in mg or mg in ms:
        return "match", ms[:120], mg[:120]
    # loose compare booleans/ints
    if ms.split("=")[0] == mg.split("=")[0] if "=" in ms and "=" in mg else False:
        return "match", ms[:120], mg[:120]
    return "drift_runtime" if any(x in ms + mg for x in ("default", "null", "choices", "on_delete")) else "drift_cosmetic", ms[:120], mg[:120]


models = parse_models_fields()
mig_all = MIG_009 + MIG_011 + MIG_012

print("Model.field|models.py|migration|verdict")
print("---|---|---|---")
for model, fields in SCOPE.items():
    for field in fields:
        msrc = models.get(model, {}).get(field, "")
        mig = mig_snippet(field, mig_all)
        verdict, a, b = compare(model, field, msrc, mig)
        print(f"{model}.{field}|{a}|{b}|{verdict}")
