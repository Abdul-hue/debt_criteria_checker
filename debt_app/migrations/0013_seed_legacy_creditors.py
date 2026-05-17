"""
Seed legacy creditors (Phase 1 initial seed — idempotent get_or_create).

NOTE: Migrations must be self-contained and must NOT import from management
commands (those files change over time and break migration replay). All data
that was originally sourced from seed_creditor_criteria.py is inlined here.
"""

from django.db import migrations


# ---------------------------------------------------------------------------
# Data inlined from original seed_creditor_criteria.py (Phase 1 snapshot)
# This data is frozen at migration time and must never be changed.
# ---------------------------------------------------------------------------

_DIVIDEND_MINIMUMS = {
    "Asset Link":                {"min_dividend_pence": 50},
    "Believe Housing":           {"min_dividend_pence": 40},
    "Beyond Housing":            {"min_dividend_pence": 30},
    "Buckinghamshire Council":   {"min_dividend_pence": 50, "dividend_notes": "If joint council tax debt, they don't vote — DI not applicable."},
    "Cardiff Credit Union":      {"min_dividend_pence": 45},
    "Chorley Council":           {"min_dividend_pence": 30},
    "Clockwise Credit Union":    {"min_dividend_pence": 50, "dividend_notes": "Loan must be at least 2 months old."},
    "Colchester Council":        {"min_dividend_pence": 45},
    "East Suffolk Council":      {"min_dividend_pence": 50},
    "FCE Bank":                  {"min_dividend_pence": 75},
    "Funding Circle":            {"min_dividend_pence": 30, "dividend_notes": "Will reject if equity in property — prefers charging order."},
    "Funding Corporation":       {"min_dividend_pence": 50},
    "Glenside Finance":          {"min_dividend_pence": 25},
    "Guarantor My Loan":         {"min_dividend_pence": 50},
    "Hull and East Yorkshire CU":{"min_dividend_pence": 60},
    "Medway Council":            {"min_dividend_pence": 25, "dividend_notes": "Must be higher than 25p — propose 26p minimum."},
    "Ratesetter":                {"min_dividend_pence": 25, "dividend_notes": "50p required if loan under 6 months old."},
    "Reading Council":           {"min_dividend_pence": 60},
    "Shell Energy":              {"min_dividend_pence": None, "dividend_notes": "Follow EVOLVE criteria."},
    "South East Water":          {"min_dividend_pence": 40, "dividend_notes": "Get dividend as high as possible."},
    "Specialist Motor Finance":  {"min_dividend_pence": 50},
    "Transave Credit Union":     {"min_dividend_pence": 60, "dividend_notes": "Loan must be at least 3 months old."},
    "Wandsworth Council":        {"min_dividend_pence": 40},
    "Worcester Council":         {"min_dividend_pence": 75},
    "Wyre Forest Council":       {"min_dividend_pence": 50, "dividend_notes": "Will REJECT if AOE in place — do not propose if AOE active."},
}

_TRADING_NAMES = {
    "Barclays":      ["Barclays Bank", "Barclays PLC", "Barclays Personal Loan", "Barclays Bank PLC"],
    "Barclaycard":   ["Barclaycard Credit Card", "Barclaycard Services", "Barclaycard Visa"],
    "MBNA":          ["MBNA Limited", "MBNA Europe", "MBNA Credit Card", "MBNA Bank"],
    "Virgin Money":  ["Virgin Money Credit Card", "Virgin Money Personal Loan", "Virgin Money UK"],
    "NatWest":       ["NatWest Bank", "NatWest Personal Loan", "National Westminster Bank", "Natwest"],
    "Royal Bank of Scotland": ["RBS", "RBS Group", "Royal Bank", "RBS PLC"],
    "Shop Direct":   ["Shop Direct Finance", "Shop Direct Group", "Shop Direct Home Shopping"],
    "Littlewoods":   ["Littlewoods Catalogue", "Littlewoods Online", "Littlewoods Home Shopping"],
    "Capital One":   ["Capital One Credit Card", "Capital One (Europe)", "Capital One Bank"],
    "Tesco Bank":    ["Tesco Personal Finance", "Tesco Credit Card", "Tesco Bank PLC"],
    "HSBC":          ["HSBC Bank", "HSBC PLC", "HSBC UK", "HSBC Holdings"],
    "Halifax":       ["Halifax Bank", "Halifax PLC", "Halifax Credit Card", "Bank of Halifax"],
    "Santander":     ["Santander UK", "Santander Bank", "Santander PLC", "Santander Personal Loan"],
    "NewDay":        ["NewDay Ltd", "NewDay Cards", "NewDay Group", "Aquis Credit Card by NewDay"],
    "Aqua":          ["Aqua Credit Card", "Aqua Card", "aqua"],
    "Creation":      ["Creation Consumer Finance Ltd", "Creation Financial Services", "Creation Credit Card"],
}

_REP_MAP = {
    # WATCH creditors (Phase 1 snapshot — these assignments were in the original seed)
    "Barclays": "WATCH",
    # EXCEL_CRITERIA_REFERENCE.md — Which Representative sheet
    "Barclaycard": "EVOLVE",
    "Barclays Direct": "WATCH",
    "Woolwich": "WATCH",
    "MBNA": "WATCH",
    "Virgin Money": "WATCH",
    "Tesco Bank": "WATCH",
    "Capital One": "WATCH",
    "Aqua": "WATCH",
    "Marbles": "WATCH",
    "Fluid": "WATCH",
    "Opus": "WATCH",
    # TIX creditors (Phase 1 snapshot)
    "Shop Direct": "TIX",
    "Very": "TIX",
    "Littlewoods": "TIX",
    "Littlewoods.com": "TIX",
    "Creation": "TIX",
    "Creation Consumer Finance": "TIX",
    "Sygma": "TIX",
    "Laser": "TIX",
    "NewDay": "TIX",
    "Aquis": "TIX",
    "Blemain": "TIX",
    # EVOLVE creditors (Phase 1 snapshot)
    "NatWest": "EVOLVE",
    "Royal Bank of Scotland": "EVOLVE",
    "Ulster Bank": "EVOLVE",
    "Coutts": "EVOLVE",
    "Think Banking": "EVOLVE",
    "Lombard": "EVOLVE",
}

_PARENT_GROUPS = {
    "RBS Group": ["Royal Bank of Scotland", "NatWest", "Ulster Bank", "Coutts", "Think Banking"],
    "Lloyds Group": ["Lloyds", "Bank of Scotland", "Halifax", "Blackhorse", "Birmingham Midshires", "AA", "Intelligent Finance", "Cheltenham and Gloucester", "Saga"],
    "Barclays Group": ["Barclays", "Barclays Direct", "Barclaycard", "Woolwich", "Standard Life"],
    "HSBC Group": ["HSBC", "First Direct", "Midland Bank"],
    "Santander Group": ["Santander", "Cahoot", "Alliance and Leicester", "Abbey National"],
    "Co-op Group": ["Co-operative Bank", "Smile", "Britannia Building Society"],
    "BoI Group": ["Bank of Ireland", "Post Office"],
    "Nationwide Group": ["Nationwide", "Cheshire BS", "Derbyshire BS", "Dunfermline BS"],
    "Yorkshire Group": ["Yorkshire BS", "Barnsley BS", "Chelsea BS", "Norwich and Peterborough BS"],
    "Clydesdale Group": ["Clydesdale Bank", "Yorkshire Bank", "National Australia"],
    "Skipton Group": ["Skipton BS", "Chesham BS", "Scarborough BS"],
    "Coventry Group": ["Coventry BS", "Stroud and Swindon BS"],
    "Shop Direct Group": ["Shop Direct", "Very", "Littlewoods", "Littlewoods.com"],
}

_CREDITOR_TO_GROUP = {}
for _group, _members in _PARENT_GROUPS.items():
    for _member in _members:
        _CREDITOR_TO_GROUP[_member] = _group

_ALL_CREDITORS = set(_REP_MAP.keys()) | set(_CREDITOR_TO_GROUP.keys())


def seed_legacy_creditors(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    all_creditors = _ALL_CREDITORS | set(_DIVIDEND_MINIMUMS.keys())

    for creditor_name in sorted(all_creditors):
        representative = _REP_MAP.get(creditor_name, "NONE")
        parent_group = _CREDITOR_TO_GROUP.get(creditor_name)
        trading_names = _TRADING_NAMES.get(creditor_name, [])
        dividend_data = _DIVIDEND_MINIMUMS.get(creditor_name, {})

        defaults = {
            "representative": representative,
            "is_active": True,
            "trading_names": trading_names or [],
        }
        if parent_group:
            defaults["parent_group"] = parent_group
        if "min_dividend_pence" in dividend_data:
            defaults["min_dividend_pence"] = dividend_data["min_dividend_pence"]
        if "dividend_notes" in dividend_data:
            defaults["dividend_notes"] = dividend_data["dividend_notes"]

        CreditorCriteria.objects.update_or_create(
            creditor_name=creditor_name,
            defaults=defaults,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0012_phase3_client_flags"),
    ]

    operations = [
        migrations.RunPython(seed_legacy_creditors, migrations.RunPython.noop),
    ]
