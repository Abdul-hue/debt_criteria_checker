"""
Phase 5 — retire the duplicate TIG-14 GlobalCriteria row.

TIG-14 ("Verbal debt proof", info, £1000) has no engine function: its behaviour
(debts under £1,000 may be verbal if no POD is available) is implemented inside
TIG-10, which also now enforces the Excel "unless it is a debt level issue"
caveat (a sub-£1,000 debt cannot be verbal when it is load-bearing for the
£6,000 minimum — TIG-10 then hard-blocks). A standalone TIG-14 rule would
double-report, so the row is deactivated (kept for history, not deleted).

Mirrors the seed_rule_meta.py source-of-truth entry (also set is_active=False),
so a reseed won't reactivate it.
"""

from django.db import migrations


RETIRED_DESC = (
    "RETIRED (2026-06-21): duplicate of TIG-10. The verbal-debt exception (debts "
    "under £1,000 may be verbal if no POD is available) is implemented inside "
    "TIG-10, including the Excel \"unless it is a debt level issue\" caveat — a "
    "sub-£1,000 debt cannot be verbal when it is load-bearing for the £6,000 "
    "minimum (TIG-01), in which case TIG-10 hard-blocks. No separate TIG-14 "
    "engine rule exists; this row is kept inactive for history."
)


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    n = GlobalCriteria.objects.filter(rule_key="TIG-14").update(
        is_active=False, description=RETIRED_DESC
    )
    print(f"\n  Retired {n} TIG-14 GlobalCriteria row(s) (duplicate of TIG-10).")


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="TIG-14").update(
        is_active=True,
        description="Debts under £1,000 can be verbal if written proof unavailable.",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0055_phase4_alias_pin_districts"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
