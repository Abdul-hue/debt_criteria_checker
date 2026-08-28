"""
Seed CouncilRule from the Councils.md file in Excel Criteria folder.
This replaces the Excel-based seeder to avoid binary dependencies in deployment.

Usage:
    python manage.py seed_all_councils
    python manage.py seed_all_councils --dry-run
    python manage.py seed_all_councils --overwrite
"""

import re
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from debt_app.models import CouncilRule

# Rows whose council name matches these patterns are not real councils
NON_COUNCIL_PATTERNS = [
    r"credit union",
    r"billing finance",
    r"east end fair finance",
    r"finio loans",
    r"first holiday finance",
    r"kingston university",
    r"metro moneywise",
    r"sefton credit",
    r"west cheshire credit",
    r"croydon / murton",
    r"^hilli$",
    r"^rth$",
    r"hemel hempstead$",
    r"harpenden council$",
    r"huddersfield credit",
    r"huddersfield \(council tax\)",
    r"hilingdon council \(parking",
]

# Map raw status strings -> CouncilRule.status choices
STATUS_MAP = {
    "accept":                          "ACCEPT",
    "reject":                          "REJECT",
    "will consider":                   "WILL_CONSIDER",
    "do not vote":                     "DO_NOT_VOTE",
    "pod only":                        "DO_NOT_VOTE",
    "pod":                             "DO_NOT_VOTE",
    "case by case":                    "WILL_CONSIDER",
    "no voting history":               "DO_NOT_VOTE",
    "not voting history":              "DO_NOT_VOTE",
    "not sure how they vote":          "DO_NOT_VOTE",
    "unsure how vote":                 "DO_NOT_VOTE",
    "unaware how they vote":           "DO_NOT_VOTE",
    "see likely loans":                None,   # skip
}

# Councils whose notes reveal conditional reject flags
CONDITIONAL_FLAGS = {
    "doncaster borough council":               {"reject_if_employed": True},
    "gateshead borough council":               {"reject_if_employed": True, "reject_if_previous_iva": True},
    "huntingdonshire district council":        {"reject_if_any_benefits": True, "reject_if_previous_iva": True, "reject_if_dro_criteria_met": True},
    "mid suffolk district council":            {"reject_if_employed": True},
    "portsmouth city council":                 {"reject_if_dro_criteria_met": True, "reject_if_aoe_in_place": True},
    "reigate & banstead borough council":      {"reject_if_joint_one_party_only": True},
    "shropshire council":                      {"reject_if_sole": True},
    "telford and wrekin borough council":      {"reject_if_aoe_in_place": True, "reject_if_previous_iva": True},
    "uttlesford district council":             {"reject_if_employed": True},
    "wolverhampton city council":              {"reject_if_employed": True},
    "wealden district council":                {"reject_if_dro_criteria_met": True},
    "buckinghamshire distict council":         {"reject_if_employed": True},
    "oldham borough council":                  {"reject_if_previous_iva": True},
    "wycombe district council":                {"reject_if_aoe_in_place": True},
    "east suffolk council":                    {"reject_if_aoe_in_place": True},
    "mid sussex district council":             {"reject_if_any_benefits": True},
}

# Councils with minimum dividend requirements (pence in the pound)
MIN_DIVIDEND = {
    "london borough of richmond upon thames":  40,
    "colchester borough council":              65,
    "reading borough council":                 60,
    "chorley borough council":                 30,
    "medway":                                  25,
    "wandsworth":                              40,
    "wyre forest district council":            50,
    "wycombe district council":                20,
    "worcester city council":                  75,
    "buckinghamshire distict council":         50,
    "doncaster borough council":               50,
    "oldham borough council":                  30,
    "south tyneside borough council":          100,
    "dorset  council direct (now cover east, northa, south and north dorset)": 80,
}

# Councils where chasing converts to REJECT
DO_NOT_CHASE = {
    "slough borough council",
    "southwark (london borough)",
}

# Councils that always include current-year council tax
INCLUDE_CURRENT_YEAR_CT = {
    "cardiff city council",
    "walsall borough council",
    "waltham forest",
    "huntingdonshire district council",
}

def _normalise_status(raw):
    if not raw:
        return "DO_NOT_VOTE"
    key = raw.strip().lower()
    if key in STATUS_MAP:
        return STATUS_MAP[key]
    for pattern, mapped in STATUS_MAP.items():
        if key.startswith(pattern):
            return mapped
    if "reject" in key:
        return "REJECT"
    if "accept" in key:
        return "ACCEPT"
    if "consider" in key:
        return "WILL_CONSIDER"
    return "DO_NOT_VOTE"

def _is_non_council(name):
    lower = name.lower()
    for pat in NON_COUNCIL_PATTERNS:
        if re.search(pat, lower):
            return True
    return False

def _parse_date(val):
    if not val:
        return None
    s = str(val).strip()
    # Handle the common 2021-01-12 00:00:00 format found in the MD
    if "00:00:00" in s:
        s = s.split(" ")[0]
    
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

class Command(BaseCommand):
    help = "Seed CouncilRule table from Councils.md"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview only")
        parser.add_argument("--overwrite", action="store_true", help="Overwrite existing")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        md_path = os.path.join(settings.BASE_DIR, "Excel Criteria", "Councils.md")
        if not os.path.exists(md_path):
            self.stderr.write(f"Source file not found: {md_path}")
            return

        with open(md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        created = updated = skipped = non_council = 0
        
        # Table starts after header and separator
        in_table = False
        for line in lines:
            line = line.strip()
            if line.startswith("| # | Council |"):
                in_table = True
                continue
            if in_table and line.startswith("|---|"):
                continue
            if not in_table or not line.startswith("|"):
                continue

            # Parse MD table row
            parts = [p.strip() for p in line.split("|")]
            # Format: | # | Council | Status | Notes | Updated Criteria | Criteria Changed From Rej Date | Contact Name | Contact Number |
            if len(parts) < 9:
                continue

            raw_name    = parts[2]
            raw_status  = parts[3]
            raw_notes   = parts[4]
            raw_date    = parts[5]
            raw_changed = parts[6]
            raw_cname   = parts[7]
            raw_cnumber = parts[8]

            if not raw_name or raw_name == "Council":
                continue

            if _is_non_council(raw_name):
                non_council += 1
                continue

            status = _normalise_status(raw_status)
            if status is None:
                non_council += 1
                continue

            last_rev = _parse_date(raw_date)
            name_key = raw_name.lower()
            flags = CONDITIONAL_FLAGS.get(name_key, {})
            min_div = MIN_DIVIDEND.get(name_key)
            do_not_chase = name_key in DO_NOT_CHASE
            inc_ct = name_key in INCLUDE_CURRENT_YEAR_CT

            defaults = {
                "status": status,
                "source_priority": 1,
                "blocked_reason": raw_notes[:1000] if raw_notes else "",
                "criteria_changed_from_rej_date": raw_changed[:100],
                "contact_name": raw_cname[:255],
                "contact_number": raw_cnumber[:255],
                "do_not_chase": do_not_chase,
                "include_current_year_ct": inc_ct,
                **flags,
            }
            if min_div is not None:
                defaults["min_dividend_pence"] = min_div
            if last_rev:
                defaults["last_reviewed"] = last_rev

            if dry_run:
                self.stdout.write(f"  DRY-RUN: {raw_name} -> {status}")
                created += 1
                continue

            obj, was_created = CouncilRule.objects.get_or_create(
                council_name=raw_name,
                defaults=defaults,
            )

            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  CREATED: {raw_name} ({status})"))
            elif overwrite:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                updated += 1
                self.stdout.write(f"  UPDATED: {raw_name} ({status})")
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created: {created}  Updated: {updated}  "
            f"Skipped: {skipped}  Non-council: {non_council}"
        ))

        # Phase 4: pin the 4 missing counties' routing now that CouncilRule rows
        # exist. Idempotent and strict (raises on a missing/ambiguous/drifted
        # pin) — councils were just seeded above, so a 0-match is a real error.
        if not dry_run:
            from debt_app.county_routing_seed import seed_county_routing, apply_alias_pins
            from debt_app.models import CountyCouncilRouting
            _log = lambda m: self.stdout.write(self.style.SUCCESS("  " + m))
            seed_county_routing(CouncilRule, CountyCouncilRouting, strict=True, log=_log)
            apply_alias_pins(CouncilRule, CountyCouncilRouting, strict=True, log=_log)
