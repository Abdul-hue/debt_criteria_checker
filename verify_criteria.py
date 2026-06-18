#!/usr/bin/env python
"""
Verify Creditor Criteria against truth source MD files
"""

import os
import re
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
import django
django.setup()

from debt_app.models import CreditorCriteria


def _parse_pence(s):
    """Extracts integer pence from string like '50p' or '50'."""
    if not s:
        return None
    match = re.search(r"(\d+)", s)
    if match:
        return int(match.group(1))
    return None


def _parse_status(s):
    """Maps General_Creditors.md 'Accept / Reject' column to CreditorCriteria.STATUS_CHOICES."""
    if not s:
        return None
    s_lower = s.lower().strip()
    if any(kw in s_lower for kw in ["do not vote", "pod only", "no voting", "non voter", "not sure how they vote", "unaware how they vote"]):
        return "DO_NOT_VOTE"
    elif "will consider" in s_lower:
        return "WILL_CONSIDER"
    elif "reject" in s_lower:
        return "REJECT"
    elif "accept" in s_lower:
        return "ACCEPT"
    elif "conditional" in s_lower:
        return "CONDITIONAL_VOTER"
    return None


def parse_truth_source():
    """Parses Which_Representative_Criteria.md and General_Creditors.md"""
    criteria_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Excel Criteria")
    
    truth_data = {} # name -> {rep, status, notes, etc}
    
    # 1. Parse Which_Representative_Criteria.md
    rep_md = os.path.join(criteria_dir, "Which_Representative_Criteria.md")
    if os.path.exists(rep_md):
        current_rep = "NONE"
        rep_map = {
            "TIX": "TIX",
            "WATCH": "WATCH",
            "WPM": "WATCH",
            "EVOLVE": "EVOLVE",
            "EVERYDAY LOANS": "EVERYDAY_LOANS"
        }
        with open(rep_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("## "):
                    section = line[3:].strip().upper()
                    found = False
                    for key, val in rep_map.items():
                        if key in section:
                            current_rep = val
                            found = True
                            break
                    if not found: 
                        current_rep = "NONE"
                    continue
                if line.startswith("- "):
                    name = line[2:].strip()
                    if name:
                        truth_data[name] = {
                            "representative": current_rep,
                        }
    
    # 2. Parse General_Creditors.md
    gen_md = os.path.join(criteria_dir, "General_Creditors.md")
    if os.path.exists(gen_md):
        with open(gen_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("|"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) > 1:
                        name = parts[1]
                        if name and name not in ["Creditor", "Group Name", "Entity", "#", "Council"] and not re.match(r"^[- :|]+$", name):
                            # Extract fields
                            status = parts[2] if len(parts) > 2 else None
                            notes = parts[3] if len(parts) > 3 else None
                            
                            parsed_status = _parse_status(status)
                            
                            if name in truth_data:
                                truth_data[name]["status"] = parsed_status
                                truth_data[name]["criteria_notes"] = notes
                            else:
                                truth_data[name] = {
                                    "representative": "NONE",
                                    "status": parsed_status,
                                    "criteria_notes": notes,
                                }
    
    return truth_data


def main():
    print("=" * 80)
    print("DEBT CRITERIA VERIFICATION")
    print("=" * 80)
    
    truth = parse_truth_source()
    print(f"\n[OK] Parsed {len(truth)} creditors from truth source files")
    
    # Get database creditors
    db_creditors = CreditorCriteria.objects.all()
    print(f"[OK] Found {db_creditors.count()} creditors in database")
    
    # Find discrepancies
    discrepancies = []
    
    # Check all creditors in truth
    for name, truth_info in truth.items():
        try:
            db_cred = CreditorCriteria.objects.get(creditor_name=name)
            
            # Check representative
            if truth_info.get("representative") and db_cred.representative != truth_info["representative"]:
                discrepancies.append({
                    "type": "REPRESENTATIVE_MISMATCH",
                    "creditor": name,
                    "db": db_cred.representative,
                    "truth": truth_info["representative"]
                })
            
            # Check status (only if truth has status)
            if truth_info.get("status") and db_cred.status != truth_info["status"]:
                discrepancies.append({
                    "type": "STATUS_MISMATCH",
                    "creditor": name,
                    "db": db_cred.status,
                    "truth": truth_info["status"]
                })
                
        except CreditorCriteria.DoesNotExist:
            discrepancies.append({
                "type": "MISSING_IN_DB",
                "creditor": name,
                "truth": truth_info
            })
    
    # Check for extra creditors in DB not in truth
    for db_cred in db_creditors:
        if db_cred.creditor_name not in truth:
            discrepancies.append({
                "type": "EXTRA_IN_DB",
                "creditor": db_cred.creditor_name,
                "db": db_cred
            })
    
    # Report
    print("\n" + "=" * 80)
    print("DISCREPANCIES FOUND")
    print("=" * 80)
    
    if not discrepancies:
        print("\n[OK] NO DISCREPANCIES FOUND! Database matches truth source perfectly.")
    else:
        print(f"\n[ERROR] Found {len(discrepancies)} discrepancies:\n")
        
        # Group by type
        by_type = {}
        for d in discrepancies:
            by_type.setdefault(d["type"], []).append(d)
        
        for dtype, items in by_type.items():
            print(f"\n--- {dtype} ({len(items)}) ---")
            for item in items:
                if dtype == "MISSING_IN_DB":
                    print(f"  [WARNING] {item['creditor']} is missing from database (should have rep: {item['truth'].get('representative', 'NONE')}, status: {item['truth'].get('status')})")
                elif dtype == "EXTRA_IN_DB":
                    print(f"  [WARNING] {item['creditor']} is in database but not in truth source")
                elif dtype == "STATUS_MISMATCH":
                    print(f"  [ERROR] {item['creditor']}: DB says {item['db']}, Truth says {item['truth']}")
                elif dtype == "REPRESENTATIVE_MISMATCH":
                    print(f"  [ERROR] {item['creditor']}: DB says rep {item['db']}, Truth says {item['truth']}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
