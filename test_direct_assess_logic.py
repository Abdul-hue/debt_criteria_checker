
import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CriteriaDecision
from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name
from debt_app.models import CreditReport
from debt_app.criteria_engine import assess_case, detect_representatives, reconcile_creditor_positions, _apply_representative_outcomes
from debt_app.recommendation_engine import get_recommendation
from debt_app.views.criteria_views import enrich_positions_with_tallies

# Get case data
cd = CriteriaDecision.objects.filter(application_id="324901").first()
case_json = cd.input_snapshot.copy()

print("--- Original creditors (before DirectAssessView processing):")
for c in case_json.get("creditors", []):
    print(f"  {c.get('name', c.get('creditor_name'))}:")
    print(f"    cr_* fields: {[k for k in c.keys() if k.startswith('cr_') or k == 'type_code']}")

# --- Run DirectAssessView's code ---
# Step 1: Apply alias map
for c in case_json.get("creditors") or []:
    raw_name = c.get("name") or c.get("creditor_name") or ""
    normalized = normalise_creditor_name(raw_name)
    resolved = CREDITOR_ALIAS_MAP.get(normalized, raw_name)
    
    c["creditor_name"] = resolved
    if "name" not in c:
        c["name"] = raw_name

# Step 2: Enrich with CR data
aryza_reference = case_json.get("application_id") or case_json.get("aryza_reference")
if aryza_reference:
    recent_reports = CreditReport.objects.filter(
        aryza_reference=aryza_reference,
        extraction_status="extracted",
    ).order_by("-created_at")
    cr_obj = next(
        (r for r in recent_reports if (r.extracted_data or {}).get('accounts')),
        None,
    )
    if cr_obj and cr_obj.extracted_data:
        cr_accounts = (
            (cr_obj.extracted_data.get('accounts', []) or []) +
            (cr_obj.extracted_data.get('mortgage_accounts', []) or [])
        )
        cr_list = []
        for acc in cr_accounts:
            mc = (acc.get('matched_creditor') or acc.get('raw_name') or '').lower().strip()
            bal = acc.get('current_balance')
            cr_list.append((mc, bal, acc))
        used_indices = set()
        def _cr_match_tolerance_pence(aryza_bal_pence):
            return max(5000, round(aryza_bal_pence * 0.20))
        for c in case_json.get("creditors") or []:
            key_name = (c.get("creditor_name") or '').lower().strip()
            orig_name = (c.get("name") or c.get("original_name") or '').lower().strip()
            aryza_bal_pence = int(round((float(c.get("balance") or 0) or 0) * 100))
            tolerance_pence = _cr_match_tolerance_pence(aryza_bal_pence)
            best_idx = None
            best_diff = None
            for i, (mc, bal, acc) in enumerate(cr_list):
                if i in used_indices:
                    continue
                name_match = (
                    mc == key_name or mc == orig_name or
                    (len(mc) >= 5 and (
                        mc in key_name or key_name in mc or
                        mc in orig_name or orig_name in mc
                    ))
                )
                if not name_match:
                    continue
                cr_bal = bal if bal is not None else 0
                diff = abs(cr_bal - aryza_bal_pence)
                if bal is not None and diff > tolerance_pence:
                    continue
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = i
            if best_idx is not None:
                used_indices.add(best_idx)
                acc = cr_list[best_idx][2]
                c['type_code'] = acc.get('type_code') or ''
                c['cr_raw_name'] = acc.get('raw_name') or ''
                c['cr_balance'] = acc.get('current_balance')
                c['cr_account_status'] = acc.get('account_status') or ''
                c['cr_account_status_subjective'] = acc.get('account_status_subjective') or ''
                c['cr_credit_limit'] = acc.get('credit_limit')
                c['cr_account_age_months'] = acc.get('account_age_months')
                c['cr_missed_payments_3m'] = acc.get('missed_payments_last_3_months')

print("\n--- Creditors after CR enrichment:")
for c in case_json.get("creditors", []):
    print(f"  {c.get('creditor_name')}:")
    print(f"    cr_raw_name: {c.get('cr_raw_name')}")
    print(f"    type_code: {c.get('type_code')}")
    print(f"    cr_balance: {c.get('cr_balance')}")

# Step 3: Run the engine
_ev = case_json.get("evidence_ledger", [])
if isinstance(_ev, dict):
    case_json["evidence_ledger"] = [
        {"category": k, "is_verified": bool(v), "ref": k}
        for k, v in _ev.items()
    ]
elif not isinstance(_ev, list):
    case_json["evidence_ledger"] = []
creditors = case_json.get("creditors") or []
detected_reps = detect_representatives(creditors)
result = assess_case(case_json, detected_reps)

# Step 4: Reconcile creditor positions
result["creditor_positions"] = reconcile_creditor_positions(result, creditors)

# Step 5: Stamp CR fields
_pc_enriched = [pc for pc in creditors if pc.get('type_code') or pc.get('cr_raw_name')]
_used_pc = set()
for pos in result["creditor_positions"]:
    pos_name = (pos.get('original_aryza_name') or pos.get('creditor_name') or '').lower().strip()
    pos_bal_pence = int(round((pos.get('balance') or 0) * 100))
    best_idx = None
    best_diff = None
    for i, pc in enumerate(_pc_enriched):
        if i in _used_pc:
            continue
        pc_name = (pc.get('creditor_name') or pc.get('name') or '').lower().strip()
        pos_canonical = (pos.get('creditor_name') or '').lower().strip()
        name_match = (
            pc_name == pos_name or
            pc_name == pos_canonical or
            (len(pc_name) >= 5 and (pc_name in pos_name or pos_name in pc_name)) or
            (len(pc_name) >= 5 and (pc_name in pos_canonical or pos_canonical in pc_name))
        )
        if not name_match:
            continue
        pc_bal_pence = int(round((pc.get('balance') or pc.get('crm_balance') or 0) * 100))
        diff = abs(pc_bal_pence - pos_bal_pence)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = i
    if best_idx is not None:
        _used_pc.add(best_idx)
        pc = _pc_enriched[best_idx]
        pos['type_code'] = pc.get('type_code') or ''
        pos['cr_raw_name'] = pc.get('cr_raw_name') or ''
        pos['cr_balance'] = pc.get('cr_balance')
        pos['cr_account_status'] = pc.get('cr_account_status') or ''
        pos['cr_account_status_subjective'] = pc.get('cr_account_status_subjective') or ''
        pos['cr_credit_limit'] = pc.get('cr_credit_limit')
        pos['cr_account_age_months'] = pc.get('cr_account_age_months')
        pos['cr_missed_payments_3m'] = pc.get('cr_missed_payments_3m')

_apply_representative_outcomes(
    result["creditor_positions"],
    result.get("representative_outcomes") or {},
)
enrich_positions_with_tallies(result["creditor_positions"])

print("\n--- Final creditor positions with CR fields:")
for pos in result["creditor_positions"]:
    print(f"  {pos.get('creditor_name')}:")
    print(f"    cr_raw_name: {pos.get('cr_raw_name')}")
    print(f"    type_code: {pos.get('type_code')}")
    print(f"    cr_balance: {pos.get('cr_balance')}")
