# Phase 2 — Seed Data Complete Rewrite

## Your role

You are a senior Django backend engineer fixing the seed data for a UK debt criteria checker.
This is Phase 2 of a 5-phase plan. Your job is seed data only — no model changes, no engine logic.
Complete every task below in order. After each task, state what you did before moving on.

---

## The problem

The current `seed_criteria_rules.py` has 5 rules, all of which are wrong:

| Current rule_key | Problem |
|---|---|
| `majority_threshold` | PHANTOM RULE — does not exist in any source document. Delete it. |
| `min_debt` | Wrong `criteria_set` (WATCH → should be TIG), wrong severity (flag → hard_block), wrong threshold (5000 → 6000) |
| `watch_single_creditor` | Wrong severity (flag → hard_block) |
| `tix_eligibility` | Too vague — replace with 6 specific TIX rules |
| `evolve_criteria` | Too vague — replace with 3 specific EVOLVE rules |

The file must be completely rewritten to contain all 50 rules below.
The 8 TODO rules are stubs — they are seeded as `is_active=False` with a note in the description.

---

## GlobalCriteria model fields (reference)

```python
criteria_set     CharField  choices: TIG | WATCH | TIX | EVOLVE
rule_key         CharField  unique identifier — use the Rule ID below exactly
rule_name        CharField  human-readable name
severity         CharField  choices: hard_block | flag | info
is_active        BooleanField
threshold_value  DecimalField  nullable
```

---

## The complete rules to seed — 50 active + 8 stubs

### TIG rules — criteria_set = "TIG"

| rule_key | rule_name | severity | threshold_value | notes |
|---|---|---|---|---|
| TIG-01 | Minimum debt | hard_block | 6000 | |
| TIG-02 | Minimum disposable income | hard_block | 100 | |
| TIG-03 | SFS guidelines | flag | None | |
| TIG-04 | DLA/PIP offset | hard_block | None | stub: payload missing disability fields |
| TIG-05 | Wage slip required | hard_block | None | |
| TIG-06 | Benefit income proof | hard_block | None | |
| TIG-07 | UC journal required | hard_block | None | |
| TIG-08 | Self-employed income proof | hard_block | None | |
| TIG-09 | CIS income proof | hard_block | None | |
| TIG-10 | Proof of debt | hard_block | None | |
| TIG-11 | Bank statement verification | hard_block | None | |
| TIG-12 | Third-party contribution evidence | hard_block | None | stub: payload missing field |
| TIG-13 | Previous IVA termination report | hard_block | None | |
| TIG-15.1 | HMRC income deductions | hard_block | None | |
| TIG-15.2 | HMRC previous IVA or bankruptcy | hard_block | None | |
| TIG-15.3 | HMRC late tax submissions | hard_block | None | |
| TIG-15.4 | HMRC equity exceeds debt | hard_block | None | stub: payload missing property_value |
| TIG-15.5 | HMRC bankruptcy return higher | hard_block | None | stub: payload missing bankruptcy_return |
| TIG-15.6 | HMRC full and final from savings | hard_block | None | stub: payload missing field |
| TIG-15.7 | SEISS fraud debt | hard_block | None | stub: payload missing seiss_debt_flag |
| TIG-15.8 | HMRC joint debt | info | None | |
| TIG-15.9 | HMRC debt under 4000 | info | 4000 | |
| TIG-15.10 | Benefits-only income with HMRC | hard_block | None | |
| TIG-16 | Equity exceeds liabilities | flag | None | |
| TIG-17 | Council majority active deduction | flag | None | |
| TIG-18 | Recent spending review | flag | None | |
| TIG-19 | Shop Direct recent spending | flag | None | |
| TIG-19.1 | Shop Direct account age | hard_block | 6 | threshold = months |
| TIG-20 | Creation recent spending | flag | None | |
| TIG-20.1 | Creation Sygma Laser hard block | hard_block | None | |
| TIG-21.1 | Link Financial Mid SFS | flag | None | |
| TIG-21.2 | Link Financial minimum debt | hard_block | 12000 | |
| TIG-21.3 | Link Financial equity | hard_block | None | |
| TIG-21.4 | Link Financial benefits threshold | hard_block | 10 | threshold = percent |
| TIG-21.5 | Link Financial previous IVA arrears | hard_block | None | |

### WATCH rules — criteria_set = "WATCH"

| rule_key | rule_name | severity | threshold_value | notes |
|---|---|---|---|---|
| WATCH-22.1 | WATCH vulnerability evidence | flag | None | |
| WATCH-22.2 | WATCH debt repayable in 6 years | hard_block | 72 | threshold = months |
| WATCH-22.3 | WATCH bankruptcy dividend higher | hard_block | None | stub: payload missing bankruptcy_return |
| WATCH-22.4 | WATCH equity greater than debt | hard_block | None | |
| WATCH-22.5 | WATCH single creditor | hard_block | 500 | threshold = min second creditor balance |
| WATCH-22.6 | WATCH recent spending 3 months | hard_block | None | |
| WATCH-22.7 | WATCH children over 13 | flag | 13 | stub: payload missing children field |
| WATCH-22.8 | WATCH client age 80 plus | info | 80 | |
| WATCH-22.9 | WATCH vehicle value | flag | 9000 | |
| WATCH-22.10 | WATCH vehicle HP payment | flag | 400 | threshold = monthly £ |
| WATCH-22.11 | WATCH gambling main cause | flag | None | |
| WATCH-22.12 | WATCH previously proposed IVA | flag | None | |
| WATCH-22.13 | WATCH antecedent transactions | hard_block | None | stub: payload missing antecedent_transactions |
| WATCH-22.14 | WATCH car finance in last 3 months | hard_block | None | |

### TIX rules — criteria_set = "TIX"

| rule_key | rule_name | severity | threshold_value | notes |
|---|---|---|---|---|
| TIX-01 | TIX Shop Direct recent spend | hard_block | None | |
| TIX-02 | TIX Shop Direct account age | hard_block | 6 | threshold = months |
| TIX-03 | TIX Creation Sygma Laser | hard_block | None | |
| TIX-04 | TIX vehicle HP payment | flag | 250 | threshold = monthly £ — NOTE: 250 not 400 |
| TIX-05 | TIX deregistered creditors | info | None | |
| TIX-06 | TIX vulnerability evidence | flag | None | |

### EVOLVE rules — criteria_set = "EVOLVE"

| rule_key | rule_name | severity | threshold_value | notes |
|---|---|---|---|---|
| EVOLVE-01 | EVOLVE equity greater than debt | hard_block | None | uses 85% LTV |
| EVOLVE-02 | EVOLVE single creditor | hard_block | 500 | threshold = min second creditor balance |
| EVOLVE-03 | EVOLVE vulnerability evidence | flag | None | |

---

## Task list — complete in this exact order

### T1 — Delete the 5 wrong existing rules

The `get_or_create` pattern in the current file means wrong rules already in the database
will NOT be updated — they will just be skipped. You must handle existing wrong data.

Add a cleanup block at the start of the `handle` method that runs BEFORE the seeding loop:

```python
# Delete phantom and wrong rules before seeding
rules_to_delete = [
    'majority_threshold',   # phantom rule — never existed in source documents
    'min_debt',             # wrong criteria_set and threshold — replaced by TIG-01
    'watch_single_creditor',# wrong severity — replaced by WATCH-22.5
    'tix_eligibility',      # too vague — replaced by TIX-01 through TIX-06
    'evolve_criteria',      # too vague — replaced by EVOLVE-01 through EVOLVE-03
]
deleted, _ = GlobalCriteria.objects.filter(rule_key__in=rules_to_delete).delete()
self.stdout.write(self.style.WARNING(f'Deleted {deleted} old/wrong rules'))
```

### T2 — Rewrite the rules list

Replace the entire `rules = [...]` list with all 50 active rules from the table above.

Use this exact structure for each entry:
```python
{
    'criteria_set': 'TIG',
    'rule_key': 'TIG-01',
    'rule_name': 'Minimum debt',
    'severity': 'hard_block',
    'is_active': True,
    'threshold_value': Decimal('6000.00'),
    'description': 'Total unsecured debt must be at least £6,000. Below this threshold the case cannot proceed.'
},
```

For rules with `threshold_value = None`:
```python
'threshold_value': None,
```

### T3 — Handle the 8 stub rules correctly

The following rules cannot be fully implemented until the upstream JSON payload adds missing fields.
Seed them as `is_active=False` so the engine skips them but they exist in the database as placeholders.

Stub rules (seed with `is_active=False`):
- TIG-04 — needs `disability_income`, `disability_expenses` fields in payload
- TIG-12 — needs `third_party_contribution` object in payload
- TIG-15.4 — needs `property_value` field in payload
- TIG-15.5 — needs `bankruptcy_return` field in payload
- TIG-15.6 — needs `full_and_final_from_savings` flag in payload
- TIG-15.7 — needs `seiss_debt_flag` in payload
- WATCH-22.3 — needs `bankruptcy_return` field in payload
- WATCH-22.7 — needs `children` array in payload
- WATCH-22.13 — needs `antecedent_transactions` boolean in payload

Add a note in the description for each:
```python
'description': 'STUB: requires antecedent_transactions boolean field in case payload. Set is_active=True once payload is updated.'
```

### T4 — Switch get_or_create to update_or_create

The current `get_or_create` pattern will skip rules that already exist with wrong values.
Replace it with `update_or_create` so re-running the command always fixes wrong data:

```python
obj, created = GlobalCriteria.objects.update_or_create(
    rule_key=rule_data['rule_key'],
    defaults={k: v for k, v in rule_data.items() if k != 'rule_key'}
)
if created:
    self.stdout.write(self.style.SUCCESS(f'  ✓ Created: {obj.rule_key}'))
else:
    self.stdout.write(self.style.WARNING(f'  ~ Updated: {obj.rule_key}'))
```

### T5 — Add a final summary count

At the end of `handle`, after the loop, add:

```python
total = GlobalCriteria.objects.count()
active = GlobalCriteria.objects.filter(is_active=True).count()
stubs = GlobalCriteria.objects.filter(is_active=False).count()
self.stdout.write(self.style.SUCCESS(
    f'\n✓ Seeding complete.\n'
    f'  Total rules in database: {total}\n'
    f'  Active rules: {active}\n'
    f'  Stub rules (awaiting payload fields): {stubs}\n'
))
```

### T6 — Verify

After writing the file, check these points before returning output:

- [ ] `majority_threshold` does NOT appear anywhere in the rules list
- [ ] `min_debt` does NOT appear anywhere in the rules list
- [ ] `TIG-01` exists with `criteria_set=TIG`, `severity=hard_block`, `threshold_value=6000`
- [ ] `TIG-02` exists with `criteria_set=TIG`, `severity=hard_block`, `threshold_value=100`
- [ ] `TIG-20` exists with `severity=flag` (NOT hard_block)
- [ ] `TIG-20.1` exists with `severity=hard_block`
- [ ] `WATCH-22.5` exists with `severity=hard_block` (NOT flag)
- [ ] `WATCH-22.10` exists with `threshold_value=400`
- [ ] `TIX-04` exists with `threshold_value=250` (NOT 400 — TIX and WATCH have different HP thresholds)
- [ ] `WATCH-22.8` exists with `severity=info`
- [ ] `TIG-15.8` exists with `severity=info`
- [ ] `TIG-15.9` exists with `severity=info`
- [ ] Stub rules have `is_active=False`
- [ ] Total rule count in the list = 50 active + 9 stubs = 59 entries

---

## Critical rules — do not break these

1. `majority_threshold` must not exist anywhere. It is a phantom rule invented in the original
   implementation. It has no basis in any source document.

2. TIG-20 severity is `flag`. TIG-20.1 severity is `hard_block`. They are different rules.
   Do not merge them. Do not make TIG-20 a hard_block.

3. TIX-04 threshold is `250`. WATCH-22.10 threshold is `400`. They are intentionally different.
   TIX is stricter on HP payments than WATCH.

4. WATCH-22.5 severity is `hard_block`. The original seed had it as `flag`. This is a confirmed
   error that caused wrong live decisions.

5. Do not add any rules not listed in the table above. If you are unsure whether something
   is a rule, it is not — do not add it.

---

## Output format

Respond with:
```
T1 — DONE: deleted 5 old rules
T2 — DONE: 50 active rules written
T3 — DONE: 9 stubs written with is_active=False
T4 — DONE: switched to update_or_create
T5 — DONE: summary block added
T6 — DONE: all checklist items verified
```

Then paste the complete rewritten `seed_criteria_rules.py` file.

---

## Paste your current seed_criteria_rules.py below this line