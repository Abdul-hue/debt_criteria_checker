"""
Seed CreditorCriteria with representative and parent_group data.

Source of truth: TIP CRITERIA & VOTING HISTORY.xlsx — "Which Representative" sheet.
Run with: python manage.py seed_creditor_criteria [--dry-run]
"""

from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria

# ---------------------------------------------------------------------------
# WATCH creditors  (col B — "WATCH")
# ---------------------------------------------------------------------------

WATCH_SEED = [
    {
        "creditor_name": "Lloyds Bank",
        "trading_names": [
            "Lloyds", "Lloyds Banking Group", "Lloyds TSB", "Lloyds TSB Bank",
        ],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "MBNA",
        "trading_names": [
            "MBNA Limited", "MBNA Europe", "MBNA Credit Card", "MBNA Bank",
            "MBNA America",
        ],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "Halifax",
        "trading_names": [
            "Halifax Bank", "Halifax PLC", "Halifax Credit Card", "Bank of Halifax",
            "Halifax Personal Loan",
        ],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "Bank of Scotland",
        "trading_names": ["Bank of Scotland PLC"],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "Blackhorse",
        "trading_names": ["Black Horse", "Black Horse Finance", "Blackhorse Finance"],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "Birmingham Midshires",
        "trading_names": [],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "Virgin Money",
        "trading_names": [
            "Virgin Money Credit Card", "Virgin Money Personal Loan", "Virgin Money UK",
            "Virgin Money Investments",
        ],
        "parent_group": "Lloyds Group",
    },
    {
        "creditor_name": "Clydesdale Bank",
        "trading_names": [],
        "parent_group": "Virgin Money Group",
    },
    {
        "creditor_name": "Yorkshire Bank",
        "trading_names": [],
        "parent_group": "Virgin Money Group",
    },
    {
        "creditor_name": "Monzo Bank",
        "trading_names": ["Monzo"],
        # Date-gated: only WATCH from 30/04/2024 — engine enforces this
        "parent_group": None,
    },
    {
        "creditor_name": "La Redoute",
        "trading_names": [
            "LR UK (Retail) Limited", "LR UK", "Redcats UK",
            "Droyds", "Droyds Debt & Collection Services",
        ],
        # Date-gated: only WATCH from 16/07/2025 — engine enforces this
        "parent_group": None,
    },
    {
        "creditor_name": "New Day",
        "trading_names": [
            "NewDay", "NewDay Ltd", "NewDay Cards", "NewDay Group",
            "Aqua", "Aqua Credit Card", "Aqua Card",
            "Marbles", "Marbles Credit Card",
            "Fluid", "Fluid Credit Card",
            "Opus", "Opus Credit Card",
            "Aquis", "Aquis Credit Card by NewDay",
        ],
        "parent_group": None,
    },
    {
        "creditor_name": "Tesco Bank",
        "trading_names": [
            "Tesco Personal Finance", "Tesco Credit Card", "Tesco Bank PLC",
        ],
        "parent_group": None,
    },
    {
        "creditor_name": "Thames Water",
        "trading_names": [],
        "parent_group": None,
    },
    {
        "creditor_name": "Asset Link Capital",
        "trading_names": ["Asset Link", "Asset Link Capital Ltd"],
        "parent_group": None,
    },
    {
        "creditor_name": "Link Financial",
        "trading_names": [
            "Link Financial Outsourcing", "Link Financial Limited",
        ],
        "parent_group": None,
    },
]

# ---------------------------------------------------------------------------
# TIX creditors  (col C — "TIX")
# ---------------------------------------------------------------------------

TIX_SEED = [
    {
        "creditor_name": "Barclays Bank",
        "trading_names": [
            "Barclays", "Barclays PLC", "Barclays Personal Loan",
            "Barclays Bank PLC", "Barclays Direct",
        ],
        "parent_group": "Barclays Group",
    },
    {
        "creditor_name": "Woolwich",
        "trading_names": ["Woolwich Building Society"],
        "parent_group": "Barclays Group",
    },
    {
        "creditor_name": "Capital One",
        "trading_names": [
            "Capital One Credit Card", "Capital One (Europe)", "Capital One Bank",
        ],
        "parent_group": None,
    },
    {
        "creditor_name": "HSBC",
        "trading_names": ["HSBC Bank", "HSBC PLC", "HSBC UK", "HSBC Holdings"],
        "parent_group": "HSBC Group",
    },
    {
        "creditor_name": "First Direct",
        "trading_names": [],
        "parent_group": "HSBC Group",
    },
    {
        "creditor_name": "Marks and Spencer Financial Services",
        "trading_names": ["M&S Bank", "M&S Credit Card", "Marks and Spencer Bank"],
        "parent_group": "HSBC Group",
    },
    {
        "creditor_name": "Santander",
        "trading_names": [
            "Santander UK", "Santander Bank", "Santander PLC",
            "Santander Personal Loan", "Cahoot", "Alliance and Leicester",
            "Abbey National",
        ],
        "parent_group": "Santander Group",
    },
    {
        "creditor_name": "Nationwide",
        "trading_names": ["Nationwide Building Society"],
        "parent_group": "Nationwide Group",
    },
    {
        "creditor_name": "Shop Direct",
        "trading_names": [
            "Shop Direct Finance", "Shop Direct Group", "Shop Direct Home Shopping",
        ],
        "parent_group": "Shop Direct Group",
    },
    {
        "creditor_name": "Very",
        "trading_names": ["Very.co.uk", "The Very Group"],
        "parent_group": "Shop Direct Group",
    },
    {
        "creditor_name": "Littlewoods",
        "trading_names": [
            "Littlewoods.com", "Littlewoods Catalogue",
            "Littlewoods Online", "Littlewoods Home Shopping",
        ],
        "parent_group": "Shop Direct Group",
    },
    # EXCEL_CRITERIA_REFERENCE.md — Which Representative: TIX
    {
        "creditor_name": "JD Williams",
        "trading_names": [
            "J D Williams", "JD Williams & Company", "Simply Be",
            "Jacamo", "Fashion World", "Marisota",
        ],
        "parent_group": "Shop Direct Group",
    },
    {
        "creditor_name": "Creation Consumer Finance",
        "trading_names": [
            "Creation", "Creation Financial Services", "Creation Credit Card",
            "Sygma", "Sygma Bank", "Laser", "Laser UK",
        ],
        "parent_group": None,
    },
    {
        "creditor_name": "Moneybarn",
        "trading_names": ["Moneybarn No.1 Ltd"],
        "parent_group": None,
    },
    {
        "creditor_name": "Lombard",
        "trading_names": ["Lombard North Central", "Lombard Finance"],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "Blemain Finance",
        "trading_names": ["Blemain", "Together Financial Services"],
        "parent_group": None,
    },
    {
        "creditor_name": "Paragon",
        "trading_names": ["Paragon Finance", "Paragon Bank"],
        "parent_group": None,
    },
]

# ---------------------------------------------------------------------------
# EVOLVE creditors  (col D — "EVOLVE")
# ---------------------------------------------------------------------------

EVOLVE_SEED = [
    # EXCEL_CRITERIA_REFERENCE.md — Which Representative sheet
    {
        "creditor_name": "Barclaycard",
        "trading_names": [
            "Barclaycard Credit Card", "Barclaycard Services", "Barclaycard Visa",
            "Barclaycard Business", "Barclaycard Platinum",
        ],
        "parent_group": "Barclays Group",
    },
    {
        "creditor_name": "NatWest Bank",
        "trading_names": [
            "NatWest", "NatWest Personal Loan", "National Westminster Bank", "Natwest",
        ],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "The Royal Bank of Scotland Plc",
        "trading_names": [
            "Royal Bank of Scotland", "RBS", "RBS Group", "Royal Bank", "RBS PLC",
        ],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "Ulster Bank",
        "trading_names": [],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "Coutts",
        "trading_names": ["Coutts & Co"],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "Think Banking",
        "trading_names": [],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "Mint",
        "trading_names": ["Mint Credit Card"],
        "parent_group": "RBS Group",
    },
    {
        "creditor_name": "TSB Bank",
        "trading_names": ["TSB", "TSB PLC"],
        "parent_group": None,
    },
]

# ---------------------------------------------------------------------------
# EVERYDAY LOANS creditors  (col G — "EVERYDAY LOANS")
# ---------------------------------------------------------------------------

EVERYDAY_LOANS_SEED = [
    {
        "creditor_name": "George Banco",
        "trading_names": ["George Banco Ltd"],
        "parent_group": "Everyday Loans Group",
    },
    {
        "creditor_name": "Trust Two",
        "trading_names": ["Trust II", "Trust 2"],
        "parent_group": "Everyday Loans Group",
    },
]

# ---------------------------------------------------------------------------
# Deregistered from TIX on 30/06/2023 — seeded as NONE so engine excludes them
# ---------------------------------------------------------------------------

DEREGISTERED_FROM_TIX_SEED = [
    {
        "creditor_name": "UKAR",
        "trading_names": ["UK Asset Resolution", "UK Asset Resolution Ltd"],
        "parent_group": None,
    },
    {
        "creditor_name": "Whistletree",
        "trading_names": ["Whistletree Mortgages"],
        "parent_group": None,
    },
    {
        "creditor_name": "Computershare",
        "trading_names": ["Computershare Loan Services"],
        "parent_group": None,
    },
    {
        "creditor_name": "Landmark",
        "trading_names": ["Landmark Mortgages"],
        "parent_group": None,
    },
]

# ---------------------------------------------------------------------------
# Banking group mappings (for non-representative creditors)
# ---------------------------------------------------------------------------

PARENT_GROUPS = {
    "RBS Group": [
        "The Royal Bank of Scotland Plc", "NatWest Bank", "Ulster Bank",
        "Coutts", "Think Banking", "Lombard", "Mint",
    ],
    "Lloyds Group": [
        "Lloyds Bank", "Bank of Scotland", "Halifax", "Blackhorse",
        "Birmingham Midshires", "MBNA", "Virgin Money",
        "Cheltenham and Gloucester", "Intelligent Finance", "AA", "Saga",
    ],
    "Barclays Group": [
        "Barclays Bank", "Barclaycard", "Woolwich", "Standard Life Bank",
    ],
    "HSBC Group": [
        "HSBC", "First Direct", "Marks and Spencer Financial Services",
    ],
    "Santander Group": [
        "Santander", "Cahoot", "Alliance and Leicester", "Abbey National",
    ],
    "Nationwide Group": [
        "Nationwide",
    ],
    "Shop Direct Group": [
        "Shop Direct", "Very", "Littlewoods", "JD Williams",
    ],
    "Virgin Money Group": [
        "Clydesdale Bank", "Yorkshire Bank",
    ],
    "Everyday Loans Group": [
        "George Banco", "Trust Two",
    ],
    "Co-op Group": [
        "Co-operative Bank", "Smile", "Britannia Building Society",
    ],
    "BoI Group": [
        "Bank of Ireland", "Post Office",
    ],
    "Yorkshire Group": [
        "Yorkshire BS", "Barnsley BS", "Chelsea BS", "Norwich and Peterborough BS",
    ],
    "Skipton Group": [
        "Skipton BS", "Chesham BS", "Scarborough BS",
    ],
    "Coventry Group": [
        "Coventry BS", "Stroud and Swindon BS",
    ],
}


def _build_seed_rows():
    rows = []
    for entry in WATCH_SEED:
        rows.append({**entry, "representative": "WATCH"})
    for entry in TIX_SEED:
        rows.append({**entry, "representative": "TIX"})
    for entry in EVOLVE_SEED:
        rows.append({**entry, "representative": "EVOLVE"})
    for entry in EVERYDAY_LOANS_SEED:
        rows.append({**entry, "representative": "EVERYDAY_LOANS"})
    for entry in DEREGISTERED_FROM_TIX_SEED:
        rows.append({**entry, "representative": "NONE"})

    # Add any creditors referenced in PARENT_GROUPS but not already in a rep list
    seeded_names = {r["creditor_name"] for r in rows}
    for group_name, members in PARENT_GROUPS.items():
        for member in members:
            if member not in seeded_names:
                rows.append({
                    "creditor_name": member,
                    "trading_names": [],
                    "parent_group": group_name,
                    "representative": "NONE",
                })
                seeded_names.add(member)
    return rows


class Command(BaseCommand):
    help = "Seed CreditorCriteria with representative and parent_group data from the Which Representative sheet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be seeded without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        rows = _build_seed_rows()
        created_count = 0
        updated_count = 0

        for row in sorted(rows, key=lambda r: r["creditor_name"]):
            defaults = {
                "representative": row["representative"],
                "is_active": True,
                "trading_names": row.get("trading_names") or [],
            }
            if row.get("parent_group"):
                defaults["parent_group"] = row["parent_group"]

            if dry_run:
                self.stdout.write(
                    f"  {row['creditor_name']!r:50s} rep={row['representative']:15s} "
                    f"group={row.get('parent_group') or '-'}"
                )
                continue

            _, created = CreditorCriteria.objects.update_or_create(
                creditor_name=row["creditor_name"],
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(rows)} rows would be written."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created_count}  Updated: {updated_count}  "
            f"Total: {created_count + updated_count}"
        ))

        for rep in ("WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS"):
            count = CreditorCriteria.objects.filter(representative=rep).count()
            self.stdout.write(f"  {rep}: {count} creditors")
