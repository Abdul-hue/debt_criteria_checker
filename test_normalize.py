
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.helpers import normalise_creditor_name

name = "Zilch Technology Limited"
print(f"Original: {name!r}")

# Step by step
name_step1 = name.lower().strip()
print(f"Step1 (lower/strip): {name_step1!r}")

# Handle t/a/trading as
import re
name_step2 = re.split(r"\s+t/a\s+|\s+trading as\s+", name_step1, flags=re.IGNORECASE)[-1].strip()
print(f"Step2 (split t/a): {name_step2!r}")

# Strip double spaces
name_step3 = re.sub(r"\s+", " ", name_step2).strip()
print(f"Step3 (strip doubles): {name_step3!r}")

# Now remove suffixes
suffixes = [
    "group limited", "group plc", "group ltd",
    "uk limited", "uk ltd", "limited uk",
    "limited", "ltd.", "ltd", "plc.", "plc", "llp", "llc",
    "(uk)", "uk", "(europe) plc", "(europe)"
]

current = name_step3
changed = True
print("\nRemoving suffixes:")
while changed:
    changed = False
    original = current
    print(f"  Current: {original!r}")
    
    # Remove parenthetical suffixes
    current = re.sub(r"\s*\([^)]+\)$", "", current).strip()
    
    # Remove suffixes
    for suffix in suffixes:
        pattern = rf"(?:\s+|^){re.escape(suffix)}$"
        new_current = re.sub(pattern, "", current).strip()
        if new_current != current:
            print(f"    Removed suffix {suffix!r} -> {new_current!r}")
            current = new_current
            changed = True
    
    if current != original:
        changed = True
        current = re.sub(r"\s+", " ", current).strip()

print(f"\nFinal: {current!r}")
print(f"normalise_creditor_name result: {normalise_creditor_name(name)!r}")
