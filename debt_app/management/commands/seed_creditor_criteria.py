"""
Seed CreditorCriteria with representative and parent_group data.

Source of truth: Which_Representative_Criteria.md
Run with: python manage.py seed_creditor_criteria [--dry-run]
"""

import os
import re
from django.conf import settings
from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria

# ---------------------------------------------------------------------------
# Banking group mappings (manual enrichment not in the MD file)
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


def _parse_pence(s):
    """Extracts integer pence from string like '50p' or '50'."""
    if not s:
        return None
    match = re.search(r"(\d+)", s)
    if match:
        return int(match.group(1))
    return None


def _parse_strict_sources():
    """Parses Which_Representative_Criteria.md, General_Creditors.md, and Dividends_Criteria.md."""
    criteria_dir = os.path.join(settings.BASE_DIR, "Excel Criteria")
    if not os.path.exists(criteria_dir):
        criteria_dir = os.path.join(os.path.dirname(settings.BASE_DIR), "Excel Criteria")

    valid_creditors = {} # name -> {rep, source, group, trading_names, min_dividend_pence, dividend_notes}
    
    # 1. Parse Which_Representative_Criteria.md (Source: REPRESENTATIVE)
    rep_md = os.path.join(criteria_dir, "Which_Representative_Criteria.md")
    if os.path.exists(rep_md):
        current_rep = "NONE"
        rep_map = {
            "TIX": "TIX",
            "WATCH": "WATCH",
            "WPM": "WATCH",
            "EVOLVE": "EVOLVE",
            "EVERYDAY LOANS": "EVERYDAY_LOANS"
        }
        with open(rep_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("## "):
                    section = line[3:].strip().upper()
                    found = False
                    for key, val in rep_map.items():
                        if key in section:
                            current_rep = val
                            found = True
                            break
                    if not found: current_rep = "NONE"
                    continue
                if line.startswith("- "):
                    name = line[2:].strip()
                    if name:
                        valid_creditors[name] = {
                            "representative": current_rep,
                            "source": "REPRESENTATIVE",
                            "trading_names": [],
                            "parent_group": None,
                            "min_dividend_pence": None,
                            "dividend_notes": None
                        }

    # 2. Parse General_Creditors.md (Source: GENERAL_CREDITOR)
    gen_md = os.path.join(criteria_dir, "General_Creditors.md")
    if os.path.exists(gen_md):
        with open(gen_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("|"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) > 1:
                        name = parts[1]
                        if name and name not in ["Creditor", "Group Name", "Entity", "#", "Council"] and not re.match(r"^[- :|]+$", name):
                            if name in valid_creditors:
                                valid_creditors[name]["source"] = "GENERAL_CREDITOR"
                            else:
                                valid_creditors[name] = {
                                    "representative": "NONE",
                                    "source": "GENERAL_CREDITOR",
                                    "trading_names": [],
                                    "parent_group": None,
                                    "min_dividend_pence": None,
                                    "dividend_notes": None
                                }

    # 3. Parse Dividends_Criteria.md
    div_md = os.path.join(criteria_dir, "Dividends_Criteria.md")
    if os.path.exists(div_md):
        with open(div_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("|"):
                    parts = [p.strip() for p in line.split("|")]
                    # Format: | Creditor | Div Required | Notes |
                    if len(parts) >= 4:
                        name = parts[1]
                        div_req = parts[2]
                        notes = parts[3]
                        if name and name not in ["Creditor", "Div Required"] and not re.match(r"^[- :|]+$", name):
                            pence = _parse_pence(div_req)
                            if name in valid_creditors:
                                valid_creditors[name]["min_dividend_pence"] = pence
                                valid_creditors[name]["dividend_notes"] = notes
                            else:
                                valid_creditors[name] = {
                                    "representative": "NONE",
                                    "source": "DIVIDEND",
                                    "trading_names": [],
                                    "parent_group": None,
                                    "min_dividend_pence": pence,
                                    "dividend_notes": notes
                                }

    # 4. Apply parent groups
    for group_name, members in PARENT_GROUPS.items():
        for member in members:
            for name, data in valid_creditors.items():
                if member.lower() in name.lower() or name.lower() in member.lower():
                    data["parent_group"] = group_name

    return valid_creditors


class Command(BaseCommand):
    help = "Strict sync CreditorCriteria with General and Representative Excel sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be changed without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            valid_map = _parse_strict_sources()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error parsing sources: {e}"))
            return

        # 1. Remove non-creditors (orphans not in General or Rep files)
        db_creditors = CreditorCriteria.objects.all()
        deleted_count = 0
        for c in db_creditors:
            if c.creditor_name not in valid_map:
                if dry_run:
                    self.stdout.write(self.style.WARNING(f"  [DELETE] {c.creditor_name}"))
                else:
                    c.delete()
                deleted_count += 1

        # 2. Upsert valid ones
        created_count = 0
        updated_count = 0

        for name, data in sorted(valid_map.items()):
            defaults = {
                "representative": data["representative"],
                "source_sheet": data["source"],
                "is_active": True,
                "trading_names": data["trading_names"],
                "min_dividend_pence": data["min_dividend_pence"],
                "dividend_notes": data["dividend_notes"],
            }
            if data["parent_group"]:
                defaults["parent_group"] = data["parent_group"]

            if dry_run:
                continue

            _, created = CreditorCriteria.objects.update_or_create(
                creditor_name=name,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nDry run complete. Would delete {deleted_count} and sync {len(valid_map)} creditors."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Strict Sync complete. Deleted: {deleted_count}  Created: {created_count}  Updated: {updated_count}"
        ))

        for rep in ("WATCH", "TIX", "EVOLVE", "EVERYDAY_LOANS", "NONE"):
            count = CreditorCriteria.objects.filter(representative=rep).count()
            self.stdout.write(f"  {rep}: {count} creditors")
        
        for source in ("GENERAL_CREDITOR", "REPRESENTATIVE", "DIVIDEND"):
            count = CreditorCriteria.objects.filter(source_sheet=source).count()
            self.stdout.write(f"  Source {source}: {count} creditors")
