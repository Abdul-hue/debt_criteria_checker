from django.db import migrations


def seed_unknown_creditors(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    # Task 1 — Create 7 new creditor rows
    new_creditors = [
        {
            "creditor_name": "Octopus Energy",
            "status": "ACCEPT",
            "representative": "EVOLVE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "trading_names": ["Bulb Energy", "Shell Energy Retail Limited"],
        },
        {
            "creditor_name": "Updraft",
            "status": "ACCEPT",
            "representative": "EVOLVE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "trading_names": [],
        },
        {
            "creditor_name": "DWP",
            "status": "DO_NOT_VOTE",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "trading_names": ["Department for Work and Pensions"],
        },
        {
            "creditor_name": "O2 UK Ltd",
            "status": "DO_NOT_VOTE",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "trading_names": ["O2 (UK) Ltd", "O2 UK"],
        },
        {
            "creditor_name": "Castle Community Bank",
            "status": "ACCEPT",
            "representative": "NONE",
            "min_dividend_pence": 30,
            "conditional_voter": True,
            "conditional_voter_min_dividend_pence": 30,
            "trading_names": [],
        },
        {
            "creditor_name": "Boom Credit Union",
            "status": "REJECT",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "trading_names": [
                "East Sussex Credit Union",
                "East Sussex Credit Union Ltd",
                "Wave Community Bank",
                "West Sussex and Surrey Credit Union",
            ],
        },
        {
            "creditor_name": "Travis Perkins",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": 50,
            "conditional_voter": True,
            "conditional_voter_min_dividend_pence": 50,
            "trading_names": [],
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
                "trading_names": entry["trading_names"],
            },
        )

    # Task 2 — Add trading names to both Intrum rows
    for intrum_name in [
        "Intrum UK Ltd (previously 1st Credit) - IVA or BKY",
        "Intrum UK Ltd (previously 1st Credit) - TD or DAS or SEQ",
    ]:
        try:
            obj = CreditorCriteria.objects.get(creditor_name=intrum_name)
            names = obj.trading_names or []
            for alias in ["Tesco C/O WPM (Intrum)", "Tesco C/O WPM Intrum", "Tesco Bank"]:
                if alias not in names:
                    names.append(alias)
            obj.trading_names = names
            obj.save()
        except CreditorCriteria.DoesNotExist:
            pass

    # Task 3 — Add Shell Energy Retail Limited alias to Shell Energy row
    try:
        obj = CreditorCriteria.objects.get(creditor_name="Shell Energy")
        names = obj.trading_names or []
        for alias in ["Shell Energy Retail Limited"]:
            if alias not in names:
                names.append(alias)
        obj.trading_names = names
        obj.save()
    except CreditorCriteria.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0029_trading_name_aliases"),
    ]
    operations = [
        migrations.RunPython(seed_unknown_creditors, migrations.RunPython.noop),
    ]
