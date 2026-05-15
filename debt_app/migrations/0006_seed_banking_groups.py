"""Seed Banking Groups parent_group mappings.

Source: TIP_CRITERIA_VOTING_HISTORY.xlsx, "Banking Groups" sheet.

Why: WATCH-22.5 and EVOLVE-02 require >1 separate lender group with the
second group > £500. Without these mappings, a case with Halifax +
Bank of Scotland + Lloyds reads as 3 separate lenders rather than the
Lloyds Banking Group, and the rule silently passes.

Scope: only sets creditor_name and parent_group. Does not touch
representative, min_dividend_pence, or trading_names — those come from
the Which Representative seed (separate migration).
"""

from django.db import migrations

BANKING_GROUPS = {
    "RBS Group": [
        "Royal Bank of Scotland",
        "NatWest",
        "Ulster Bank",
        "Coutts",
        "Think Banking",
    ],
    "Barclays Group": [
        "Barclays",
        "Barclays Bank",
        "Barclays Direct",
        "Barclaycard",
        "Woolwich",
        "Standard Life",
    ],
    "Co-op Group": [
        "Co-operative Bank",
        "The Co-operative Bank",
        "Smile",
        "Britannia Building Society",
    ],
    "Lloyds Group": [
        "Lloyds",
        "Lloyds Bank",
        "Bank of Scotland",
        "Halifax",
        "Black Horse",
        "Blackhorse",
        "Birmingham Midshires",
        "AA",
        "Intelligent Finance",
        "Cheltenham and Gloucester",
        "Saga",
    ],
    "HSBC Group": [
        "HSBC",
        "First Direct",
        "Midland Bank",
    ],
    "Nationwide Group": [
        "Nationwide Building Society",
        "Cheshire Building Society",
        "Derbyshire Building Society",
        "Dunfermline Building Society",
        "Norwich & Peterborough Building Society",
    ],
    "Santander Group": [
        "Santander",
        "Cahoot",
        "Alliance & Leicester",
        "Abbey National",
    ],
    "Yorkshire Group": [
        "Yorkshire Building Society",
        "Barnsley Building Society",
        "Chelsea Building Society",
    ],
    "Clydesdale Group": [
        "Clydesdale Bank",
        "Clydesdale Bank plc",
        "Yorkshire Bank",
        "National Australia",
        "CYBG",
    ],
    "Skipton Group": [
        "Skipton Building Society",
        "Chesham Building Society",
        "Scarborough Building Society",
    ],
    "Coventry Group": [
        "Coventry Building Society",
        "Stroud & Swindon Building Society",
    ],
    "BoI Group": [
        "Bank of Ireland",
        "Post Office",
    ],
}


def seed_banking_groups(apps, schema_editor):
    """For each (group, creditor_name) pair:
      - if row exists with matching creditor_name (case-insensitive),
        update only parent_group (preserves representative, dividend, etc.)
      - if no row exists, create with creditor_name + parent_group + is_active=True
    """
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    created = 0
    updated = 0
    untouched = 0
    for group_name, creditor_names in BANKING_GROUPS.items():
        for name in creditor_names:
            existing = CreditorCriteria.objects.filter(
                creditor_name__iexact=name
            ).first()
            if existing:
                if existing.parent_group != group_name:
                    existing.parent_group = group_name
                    existing.save(update_fields=["parent_group"])
                    updated += 1
                else:
                    untouched += 1
            else:
                CreditorCriteria.objects.create(
                    creditor_name=name,
                    parent_group=group_name,
                    is_active=True,
                )
                created += 1

    print(
        f"  Banking Groups seed: {created} created, "
        f"{updated} updated, {untouched} already correct"
    )


def reverse_banking_groups(apps, schema_editor):
    """Clear parent_group on rows whose name matches our seed list.
    Does NOT delete rows — they may be referenced by assessment records
    or have other fields populated (representative, dividend, etc).
    """
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    all_names = [n for names in BANKING_GROUPS.values() for n in names]
    CreditorCriteria.objects.filter(
        creditor_name__in=all_names
    ).update(parent_group=None)


class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0005_creditor_criteria_dividend_notes"),
    ]

    operations = [
        migrations.RunPython(
            seed_banking_groups,
            reverse_banking_groups,
        ),
    ]
