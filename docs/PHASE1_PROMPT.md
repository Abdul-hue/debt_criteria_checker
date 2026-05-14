# Phase 1 — Models Cleanup, RuleResult, Migration

## Your role

You are a senior Django backend engineer fixing the data model layer of a UK debt criteria checker.
This is Phase 1 of a 5-phase plan. Your job is model cleanup only — no rule logic, no seed data.
Complete every task below in order. After each task, state what you did before moving on.

---

## The problem

The current `models.py` has structural issues that block all subsequent work:

1. `CreditorCriteria` has `is_watch`, `is_tix`, `is_evolve` BooleanFields that conflict with the
   existing `representative` CharField. The booleans must be removed — `representative` is the
   single source of truth.

2. `CreditorCriteria` is missing `account_age_months` IntegerField — needed for Shop Direct
   account age rules (TIG-19.1, TIX-02).

3. `CreditorCriteria` is missing `parent_group` CharField — needed for banking group conflict
   detection. If it already exists, confirm and leave it.

4. `criteria_engine.py` has no `RuleResult` dataclass — every rule method must return one.

5. No migration exists for the above changes.

---

## Task list — complete in this exact order

### T1 — Remove redundant BooleanFields from CreditorCriteria

In `models.py`, find `CreditorCriteria` and remove these three fields if they exist:
```python
is_watch = models.BooleanField(...)
is_tix   = models.BooleanField(...)
is_evolve = models.BooleanField(...)
```

The `representative` CharField replaces all three. After removal, confirm `representative` is
defined and accepts these values: `"WATCH"`, `"TIX"`, `"EVOLVE"`, or blank/null.

If `representative` is not already on the model, add it:
```python
representative = models.CharField(
    max_length=20,
    blank=True,
    null=True,
    choices=[
        ("WATCH", "WATCH"),
        ("TIX", "TIX"),
        ("EVOLVE", "EVOLVE"),
    ],
    help_text="Which creditor representative this creditor belongs to, if any."
)
```

### T2 — Add account_age_months to CreditorCriteria

Add this field if it does not already exist:
```python
account_age_months = models.IntegerField(
    null=True,
    blank=True,
    help_text="Age of the account in months. Used for Shop Direct account age rules."
)
```

### T3 — Confirm or add parent_group to CreditorCriteria

Check if `parent_group` CharField exists. If yes, leave it exactly as is.
If no, add:
```python
parent_group = models.CharField(
    max_length=100,
    blank=True,
    null=True,
    help_text="Banking group this creditor belongs to, e.g. 'Lloyds Group'."
)
```

### T4 — Remove parent_group_conflict from GlobalCriteria rules

`parent_group_conflict` is not a rule — it is a data attribute on creditors.
Find and remove any `GlobalCriteria` or seed entry with `rule_key="parent_group_conflict"`.
Do not delete the `parent_group` field on `CreditorCriteria` — that stays.
Only remove the rule entry from the criteria rules table.

### T5 — Add RuleResult dataclass to criteria_engine.py

At the top of `criteria_engine.py` (after imports, before any class definition), add:

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RuleResult:
    rule_id: str
    severity: str          # "hard_block" | "flag" | "info" | "pass"
    triggered: bool        # True if the rule fired (i.e. a problem was found)
    message: str           # Human-readable explanation for the caseworker
    threshold: Optional[float] = None    # The threshold compared against, if numeric
    actual_value: Optional[float] = None # The actual value from the case, if numeric
```

Rules that pass (no problem found) should return:
```python
RuleResult(rule_id="TIG-01", severity="pass", triggered=False, message="Passed.")
```

Rules that fire should return:
```python
RuleResult(
    rule_id="TIG-01",
    severity="hard_block",
    triggered=True,
    message="Total debt £5,500 is below the £6,000 minimum.",
    threshold=6000.0,
    actual_value=5500.0
)
```

### T6 — Write the migration

Run (or write manually if you cannot run commands):
```bash
python manage.py makemigrations --name="remove_watch_tix_evolve_booleans_add_account_age"
```

The migration must:
- Remove `is_watch`, `is_tix`, `is_evolve` from `CreditorCriteria`
- Add `account_age_months` to `CreditorCriteria`
- Add `parent_group` to `CreditorCriteria` (if it was missing)
- Add `representative` to `CreditorCriteria` (if it was missing)

If you are writing the migration manually, follow this structure:
```python
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "XXXX_previous_migration"),  # replace with actual last migration
    ]

    operations = [
        migrations.RemoveField(model_name="creditorcriteria", name="is_watch"),
        migrations.RemoveField(model_name="creditorcriteria", name="is_tix"),
        migrations.RemoveField(model_name="creditorcriteria", name="is_evolve"),
        migrations.AddField(
            model_name="creditorcriteria",
            name="account_age_months",
            field=models.IntegerField(null=True, blank=True),
        ),
        # Add representative and parent_group only if they were missing
    ]
```

### T7 — Verify

After completing T1–T6, run through this checklist and confirm each point:

- [ ] `CreditorCriteria` has NO `is_watch`, `is_tix`, `is_evolve` fields
- [ ] `CreditorCriteria` has `representative` CharField with WATCH/TIX/EVOLVE choices
- [ ] `CreditorCriteria` has `account_age_months` IntegerField (nullable)
- [ ] `CreditorCriteria` has `parent_group` CharField (nullable)
- [ ] `GlobalCriteria` has NO `parent_group_conflict` rule entry
- [ ] `criteria_engine.py` has `RuleResult` dataclass with all 6 fields
- [ ] Migration file exists and covers all changes
- [ ] `python manage.py check` returns zero errors

---

## What NOT to do in this phase

- Do not touch any rule logic in `criteria_engine.py` beyond adding `RuleResult`
- Do not modify seed data files
- Do not add or remove any other models
- Do not rename any existing fields other than the three removals listed above
- Do not change `GlobalCriteria` except to remove the `parent_group_conflict` rule entry

---

## Output format

For each task, respond with:
```
T1 — DONE
  Removed: is_watch, is_tix, is_evolve from CreditorCriteria
  Confirmed: representative CharField present with choices WATCH/TIX/EVOLVE
```

Then paste the full updated file content for:
1. `models.py` (complete file)
2. The new migration file (complete file)
3. The top section of `criteria_engine.py` showing the RuleResult dataclass in place

---

## Paste your models.py and criteria_engine.py below this line