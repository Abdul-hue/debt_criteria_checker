from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria

# ---------------------------------------------------------------------------
# Representative mappings
# ---------------------------------------------------------------------------

WATCH_CREDITORS = [
    "Barclays", "Barclaycard", "Barclays Direct", "Woolwich",
    "MBNA", "Virgin Money", "Tesco Bank", "Capital One",
    "Aqua", "Marbles", "Fluid", "Opus",
]

TIX_CREDITORS = [
    "Shop Direct", "Very", "Littlewoods", "Littlewoods.com",
    "Creation", "Creation Consumer Finance", "Sygma", "Laser",
    "NewDay", "Aquis", "Blemain",
]

EVOLVE_CREDITORS = [
    "NatWest", "Royal Bank of Scotland", "Ulster Bank",
    "Coutts", "Think Banking", "Lombard",
]

# ---------------------------------------------------------------------------
# Trading names — real-world variations that match each seeded creditor
# ---------------------------------------------------------------------------

TRADING_NAMES = {
    "Barclays": [
        "Barclays Bank", "Barclays PLC", "Barclays Personal Loan",
        "Barclays Bank PLC",
    ],
    "Barclaycard": [
        "Barclaycard Credit Card", "Barclaycard Services",
        "Barclaycard Visa",
    ],
    "MBNA": [
        "MBNA Limited", "MBNA Europe", "MBNA Credit Card",
        "MBNA Bank",
    ],
    "Virgin Money": [
        "Virgin Money Credit Card", "Virgin Money Personal Loan",
        "Virgin Money UK",
    ],
    "NatWest": [
        "NatWest Bank", "NatWest Personal Loan",
        "National Westminster Bank", "Natwest",
    ],
    "Royal Bank of Scotland": [
        "RBS", "RBS Group", "Royal Bank", "RBS PLC",
    ],
    "Shop Direct": [
        "Shop Direct Finance", "Shop Direct Group",
        "Shop Direct Home Shopping",
    ],
    "Littlewoods": [
        "Littlewoods Catalogue", "Littlewoods Online",
        "Littlewoods Home Shopping",
    ],
    "Capital One": [
        "Capital One Credit Card", "Capital One (Europe)",
        "Capital One Bank",
    ],
    "Tesco Bank": [
        "Tesco Personal Finance", "Tesco Credit Card",
        "Tesco Bank PLC",
    ],
    "HSBC": [
        "HSBC Bank", "HSBC PLC", "HSBC UK", "HSBC Holdings",
    ],
    "Halifax": [
        "Halifax Bank", "Halifax PLC", "Halifax Credit Card",
        "Bank of Halifax",
    ],
    "Santander": [
        "Santander UK", "Santander Bank", "Santander PLC",
        "Santander Personal Loan",
    ],
    "NewDay": [
        "NewDay Ltd", "NewDay Cards", "NewDay Group",
        "Aquis Credit Card by NewDay",
    ],
    "Aqua": [
        "Aqua Credit Card", "Aqua Card", "aqua",
    ],
    "Creation": [
        "Creation Consumer Finance Ltd", "Creation Financial Services",
        "Creation Credit Card",
    ],
}

# ---------------------------------------------------------------------------
# Banking group mappings
# ---------------------------------------------------------------------------

PARENT_GROUPS = {
    "RBS Group": [
        "Royal Bank of Scotland", "NatWest", "Ulster Bank",
        "Coutts", "Think Banking",
    ],
    "Lloyds Group": [
        "Lloyds", "Bank of Scotland", "Halifax", "Blackhorse",
        "Birmingham Midshires", "AA", "Intelligent Finance",
        "Cheltenham and Gloucester", "Saga",
    ],
    "Barclays Group": [
        "Barclays", "Barclays Direct", "Barclaycard", "Woolwich",
        "Standard Life",
    ],
    "HSBC Group": [
        "HSBC", "First Direct", "Midland Bank",
    ],
    "Santander Group": [
        "Santander", "Cahoot", "Alliance and Leicester", "Abbey National",
    ],
    "Co-op Group": [
        "Co-operative Bank", "Smile", "Britannia Building Society",
    ],
    "BoI Group": [
        "Bank of Ireland", "Post Office",
    ],
    "Nationwide Group": [
        "Nationwide", "Cheshire BS", "Derbyshire BS", "Dunfermline BS",
    ],
    "Yorkshire Group": [
        "Yorkshire BS", "Barnsley BS", "Chelsea BS",
        "Norwich and Peterborough BS",
    ],
    "Clydesdale Group": [
        "Clydesdale Bank", "Yorkshire Bank", "National Australia",
    ],
    "Skipton Group": [
        "Skipton BS", "Chesham BS", "Scarborough BS",
    ],
    "Coventry Group": [
        "Coventry BS", "Stroud and Swindon BS",
    ],
    "Shop Direct Group": [
        "Shop Direct", "Very", "Littlewoods", "Littlewoods.com",
    ],
}

# ---------------------------------------------------------------------------
# Build lookup: creditor_name → parent_group
# ---------------------------------------------------------------------------

_CREDITOR_TO_GROUP: dict[str, str] = {}
for group_name, members in PARENT_GROUPS.items():
    for member in members:
        _CREDITOR_TO_GROUP[member] = group_name

# ---------------------------------------------------------------------------
# Build full seed list: creditor_name → {representative, parent_group}
# ---------------------------------------------------------------------------

_REP_MAP: dict[str, str] = {}
for name in WATCH_CREDITORS:
    _REP_MAP[name] = "WATCH"
for name in TIX_CREDITORS:
    _REP_MAP[name] = "TIX"
for name in EVOLVE_CREDITORS:
    _REP_MAP[name] = "EVOLVE"

# Collect every creditor that appears in either representatives or groups
_ALL_CREDITORS: set[str] = set(_REP_MAP.keys()) | set(_CREDITOR_TO_GROUP.keys())


class Command(BaseCommand):
    help = "Seed CreditorCriteria with representative (WATCH/TIX/EVOLVE) and parent_group data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be seeded without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created_count = 0
        updated_count = 0

        for creditor_name in sorted(_ALL_CREDITORS):
            representative = _REP_MAP.get(creditor_name, "NONE")
            parent_group = _CREDITOR_TO_GROUP.get(creditor_name)
            trading_names = TRADING_NAMES.get(creditor_name, [])

            defaults = {
                "representative": representative,
                "is_active": True,
                "trading_names": trading_names,
            }
            if parent_group:
                defaults["parent_group"] = parent_group

            if dry_run:
                self.stdout.write(
                    f"  {creditor_name!r:40s} rep={representative:6s}  "
                    f"group={parent_group or '-'}  "
                    f"trading_names={trading_names or []}"
                )
                continue

            _, created = CreditorCriteria.objects.update_or_create(
                creditor_name=creditor_name,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(_ALL_CREDITORS)} rows would be written."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created_count}  Updated: {updated_count}  "
            f"Total: {created_count + updated_count}"
        ))

        # Summary by representative
        from debt_app.models import CreditorCriteria as CC
        for rep in ("WATCH", "TIX", "EVOLVE"):
            count = CC.objects.filter(representative=rep).count()
            self.stdout.write(f"  {rep}: {count} creditors")
