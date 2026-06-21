"""
Phase 1 — seed CCJ / AOE rejection flags for the two general creditors whose
source-of-truth criteria call for them (Excel Criteria/General_Creditors.md):

  - Admiral Loans:     "running cases: 3 months or older, no CCJ, no AOE"
  - Advantage Finance: "REJECT IF ALREADY HAVE ATTACHMENT OF EARNINGS OR CCJ"

Both stay status=WILL_CONSIDER; the reject_if_ccj / reject_if_aoe flags act as
conditional overrides applied by _check_creditor_individual when the case
actually carries a CCJ (from the credit report) or an AOE in place.
"""

from django.db import migrations


SEEDS = {
    "Admiral Loans": {"reject_if_ccj": True, "reject_if_aoe": True},
    "Advantage Finance": {"reject_if_ccj": True, "reject_if_aoe": True},
}


def forward(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for name, fields in SEEDS.items():
        updated = CreditorCriteria.objects.filter(creditor_name__iexact=name).update(**fields)
        print(f"\n  {name}: set {fields} on {updated} row(s).")


def reverse(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for name in SEEDS:
        CreditorCriteria.objects.filter(creditor_name__iexact=name).update(
            reject_if_ccj=False, reject_if_aoe=False
        )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0052_phase1_creditor_ccj_aoe"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
