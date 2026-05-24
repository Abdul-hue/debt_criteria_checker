"""
Seed CouncilRule from the Councils sheet of TIP CRITERIA & VOTING HISTORY.xlsx.

Reads directly from the Excel file. Creates or updates one CouncilRule per council.
Non-council rows (credit unions, finance companies, etc.) are skipped automatically.

Run with:
    python manage.py seed_all_councils
    python manage.py seed_all_councils --dry-run
    python manage.py seed_all_councils --overwrite   # overwrite existing records too
"""

import re
from datetime import datetime

from django.core.management.base import BaseCommand

from debt_app.models import CouncilRule

try:
    import openpyxl
except ImportError:
    openpyxl = None

EXCEL_PATH = "C:/Users/Canton Computers/Desktop/TIP CRITERIA & VOTING HISTORY.xlsx"

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

# Map raw Excel status strings -> CouncilRule.status choices
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

# Councils whose notes reveal conditional reject flags (manually coded)
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
    # exact match first
    if key in STATUS_MAP:
        return STATUS_MAP[key]
    # prefix match for longer variants like "reject sole accounts..."
    for pattern, mapped in STATUS_MAP.items():
        if key.startswith(pattern):
            return mapped
    # fallback
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
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y",
                "%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt[:len(fmt)]).date()
        except ValueError:
            pass
    return None


class Command(BaseCommand):
    help = "Seed CouncilRule table from Excel Councils sheet"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
        parser.add_argument("--overwrite", action="store_true", help="Overwrite existing records")

    def handle(self, *args, **options):
        if openpyxl is None:
            self.stderr.write("openpyxl not installed. Run: pip install openpyxl")
            return

        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
        ws = wb["Councils"]
        rows = list(ws.iter_rows(values_only=True))

        created = updated = skipped = non_council = 0

        for row in rows[1:]:
            # skip blank rows
            if not any(c is not None and str(c).strip() for c in row[:7]):
                continue

            raw_name = str(row[0]).strip() if row[0] else ""
            if not raw_name:
                skipped += 1
                continue

            if _is_non_council(raw_name):
                non_council += 1
                self.stdout.write(f"  SKIP (non-council): {raw_name}")
                continue

            raw_status = str(row[1]).strip() if row[1] else ""
            status = _normalise_status(raw_status)

            if status is None:
                non_council += 1
                self.stdout.write(f"  SKIP (See Likely Loans): {raw_name}")
                continue

            raw_notes  = str(row[2]).strip() if row[2] else ""
            raw_date   = row[3]
            last_rev   = _parse_date(raw_date)

            name_key = raw_name.lower()
            flags = CONDITIONAL_FLAGS.get(name_key, {})
            min_div = MIN_DIVIDEND.get(name_key)
            do_not_chase = name_key in DO_NOT_CHASE
            inc_ct = name_key in INCLUDE_CURRENT_YEAR_CT

            raw_changed = str(row[4]).strip() if row[4] else ""
            raw_cname   = str(row[5]).strip() if row[5] else ""
            raw_cnumber = str(row[6]).strip() if row[6] else ""

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

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created}  Updated: {updated}  "
            f"Skipped (existing): {skipped}  Non-council: {non_council}"
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("(dry-run — no changes written)"))
