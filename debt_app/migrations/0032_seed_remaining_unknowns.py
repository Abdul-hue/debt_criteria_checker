from django.db import migrations


def seed_remaining_unknowns(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    new_creditors = [
        {
            "creditor_name": "HMRC",
            "status": "DO_NOT_VOTE",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": [
                "HM Revenue & Customs",
                "HM Revenue and Customs",
                "HMRC - benefits overpayments",
            ],
        },
        {
            "creditor_name": "Anderson Brookes",
            "status": "DO_NOT_VOTE",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": ["Anderson Brookes Solicitors"],
        },
        {
            "creditor_name": "Huws Gray",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": [],
        },
        {
            "creditor_name": "Tyrell Carpentry",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": [],
        },
        {
            "creditor_name": "Credit4",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": ["Credit 4"],
        },
        {
            "creditor_name": "CCC Debt Management",
            "status": "DO_NOT_VOTE",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": ["CCC", "Complete Credit Control"],
        },
        {
            "creditor_name": "The Money Platform",
            "status": "WILL_CONSIDER",
            "representative": "NONE",
            "min_dividend_pence": None,
            "conditional_voter": False,
            "conditional_voter_min_dividend_pence": None,
            "reject_if_equity_exceeds_debt": False,
            "trading_names": ["Money Platform"],
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


class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0031_seed_amex_cashplus_mutual_northridge"),
    ]

    operations = [
        migrations.RunPython(
            seed_remaining_unknowns,
            migrations.RunPython.noop,
        ),
    ]
