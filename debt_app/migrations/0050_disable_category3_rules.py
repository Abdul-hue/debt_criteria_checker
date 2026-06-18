from django.db import migrations

# Category 3 rules — not related to IVA financial viability or creditor acceptance.
# These cover documentation evidence gathering, client behaviour flags, and client
# profile checks. Disabled so the engine skips them; re-enable individually via
# the Rule Management → Global Rules admin page (is_active toggle).
#
# Kept ACTIVE (excluded from this list):
#   TIG-10 — Proof of debt per creditor (evidence per creditor)
#   TIG-13 — Previous IVA termination report (explicitly kept per product decision)

RULES_TO_DISABLE = [
    # 3a — Documentation / evidence gathering
    "TIG-03",           # SFS expenditure guideline breaches
    "TIG-04",           # DLA/PIP income but no disability expenses
    "TIG-05",           # Wage slip required
    "TIG-06",           # Benefit award letter
    "TIG-07",           # UC journal
    "TIG-08",           # Self-employed tax return + business banking
    "TIG-09",           # CIS invoice
    "TIG-11",           # Bank statement presence / freshness
    "TIG-11-GAMBLING",  # Gambling spend monitor
    "TIG-12",           # Third-party contribution signed letter
    # 3b — Client behaviour / spending patterns
    "TIG-15.6",         # Full & Final funded from savings while debts unpaid
    "TIG-18",           # Total spend >= monthly income
    "WATCH-22.6",       # Luxury/non-essential spend > 50% of income
    "WATCH-22.11",      # Gambling identified as main cause of debt
    "WATCH-22.13",      # Antecedent transactions (non-HMRC)
    "WATCH-22.14",      # Car finance taken in last 3 months
    # 3c — Client profile / I&E completeness
    "WATCH-22.1",       # Vulnerability claimed but no evidence
    "WATCH-22.7",       # Children aged 13+ — sustainability paragraph
    "WATCH-22.8",       # Client aged 80+ (WATCH abstains — info)
    "WATCH-22.9",       # Vehicle value > £9,000
    "WATCH-22.10",      # Car HP payment > £400/month
    "WATCH-22.12",      # Previous IVA — I&E must be consistent
    "TIX-06",           # Vulnerability claimed (TIX version)
    "EVOLVE-03",        # Vulnerability claimed (EVOLVE version)
]


def disable_category3_rules(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    updated = GlobalCriteria.objects.filter(rule_key__in=RULES_TO_DISABLE).update(is_active=False)
    print(f"\n  Disabled {updated} Category 3 GlobalCriteria rules.")


def enable_category3_rules(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key__in=RULES_TO_DISABLE).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0049_seed_sfs_guidelines_data"),
    ]

    operations = [
        migrations.RunPython(disable_category3_rules, reverse_code=enable_category3_rules),
    ]
