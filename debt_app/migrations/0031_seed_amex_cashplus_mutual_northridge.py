from django.db import migrations


def seed_amex_cashplus_mutual_northridge(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    # Task 1 — Create 3 new creditor rows
    new_creditors = [
        {
            "creditor_name": "American Express",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": True,
            "trading_names": ["Amex", "American Express Service"],
        },
        {
            "creditor_name": "Cashplus",
            "status": "DO_NOT_VOTE",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": ["Cashplus Bank"],
        },
        {
            "creditor_name": "Mutual (Home Credit)",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": ["Mutual Home Credit", "Mutual Clothing"],
        },
    ]

    for entry in new_creditors:
        CreditorCriteria.objects.update_or_create(
            creditor_name=entry["creditor_name"],
            defaults={
                "status": entry["status"],
                "representative": entry["representative"],
                "min_dividend_pence": entry["min_dividend_pence"],
                "conditional_voter": entry["conditional_voter"],
                "conditional_voter_min_dividend_pence": entry["conditional_voter_min_dividend_pence"],
                "reject_if_equity_exceeds_debt": entry["reject_if_equity_exceeds_debt"],
                "trading_names": entry["trading_names"],
            },
        )

    # Task 2 — Add Northridge Finance aliases to Santander Consumer Finance
    try:
        obj = CreditorCriteria.objects.get(creditor_name="Santander Consumer Finance")
        names = obj.trading_names or []
        for alias in ["Northridge Finance", "Northridge Finance Ltd"]:
            if alias not in names:
                names.append(alias)
        obj.trading_names = names
        obj.save()
    except CreditorCriteria.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0030_seed_unknown_creditors"),
    ]
    operations = [
        migrations.RunPython(
            seed_amex_cashplus_mutual_northridge,
            migrations.RunPython.noop,
        ),
    ]
