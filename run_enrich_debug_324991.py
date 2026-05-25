#!/usr/bin/env python
"""
Run assess_case for 324991 with DEBUG logging, then print only lines
containing [ENRICH], [CREDIT REPORT MATCH], or [TIG-10].
"""
import io
import logging
import os
import sys

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")

# Configure logging BEFORE django.setup() so Django doesn't override it
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

import django
django.setup()

# Capture log output into a buffer by adding handler to the engine logger directly
buffer = io.StringIO()
handler = logging.StreamHandler(buffer)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

engine_logger = logging.getLogger("debt_app.criteria_engine")
engine_logger.setLevel(logging.DEBUG)
engine_logger.addHandler(handler)
engine_logger.propagate = False  # prevent double output to console

try:
    from debt_app.views.criteria_views import AssessCaseView
    from debt_app.aryza_client import fetch_case_by_reference
    from debt_app.criteria_engine import assess_case

    obj = fetch_case_by_reference("324991")
    view = AssessCaseView()
    payload, prepared_creditors = view._prepare_engine_payload(obj)
    result = assess_case(payload)
finally:
    engine_logger.removeHandler(handler)
    engine_logger.propagate = True

# ── Filter and print relevant lines ──────────────────────────────────────────
KEYWORDS = ("[ENRICH]", "[CREDIT REPORT MATCH]", "[TIG-10]", "[ENRICH FALLBACK]", "[CREDIT REPORT]")
lines = buffer.getvalue().splitlines()
filtered = [l for l in lines if any(k in l for k in KEYWORDS)]

print(f"\n{'='*70}")
print(f"  FILTERED LOG — case 324991 ({len(filtered)} matching lines)")
print(f"{'='*70}\n")
for line in filtered:
    print(line)

# ── Summary checks ────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("VERIFICATION CHECKS")
print(f"{'='*70}")

# 1. No account skipped due to empty name
skipped_no_name = [l for l in filtered if "account skipped" in l]
print(f"\n1. Accounts skipped (empty name): {len(skipped_no_name)}")
for l in skipped_no_name:
    print(f"   {l}")
if not skipped_no_name:
    print("   OK — no accounts skipped")

# 2. Both Lloyds accounts show distinct best_creditor lines
lloyds_lines = [l for l in filtered if "best_creditor" in l and "lloyd" in l.lower()]
print(f"\n2. Lloyds best_creditor log lines: {len(lloyds_lines)}")
for l in lloyds_lines:
    print(f"   {l}")
if len(lloyds_lines) >= 2:
    print("   OK — both Lloyds accounts logged")
elif len(lloyds_lines) == 1:
    print("   WARNING — only one Lloyds account logged")
else:
    print("   FAIL — no Lloyds best_creditor lines found")

# 3. Link Financial — no fallback needed
link_lines = [l for l in filtered if "link" in l.lower()]
link_fallback = [l for l in link_lines if "FALLBACK" in l]
print(f"\n3. Link Financial lines: {len(link_lines)}, fallback used: {len(link_fallback)}")
for l in link_lines:
    print(f"   {l}")
if link_lines and not link_fallback:
    print("   OK — Link Financial resolved without fallback")
elif link_fallback:
    print("   NOTE — Link Financial required linked_creditor fallback")
else:
    print("   INFO — no Link Financial lines found")

# 4. TIG-10 pass/fail
passed_rules = [r for r in result.get("passed", []) if getattr(r, "rule_id", "") == "TIG-10"]
blocked_rules = [r for r in result.get("hard_blocks", []) if getattr(r, "rule_id", "") == "TIG-10"]
flag_rules = [r for r in result.get("flags", []) if getattr(r, "rule_id", "") == "TIG-10"]
tig10_status = "PASS" if passed_rules else ("HARD BLOCK" if blocked_rules else ("FLAG" if flag_rules else "UNKNOWN"))
print(f"\n4. TIG-10 result: {tig10_status}")
if passed_rules:
    print(f"   {passed_rules[0]}")
if blocked_rules:
    print(f"   {blocked_rules[0]}")
if flag_rules:
    print(f"   {flag_rules[0]}")

# Overall
print(f"\n{'='*70}")
overall = result.get("overall_status", "unknown")
print(f"Overall case status: {overall}")
