"""
Seed CountyCouncil from Excel Criteria/County_Councils_Criteria.md.

CountyCouncilRouting already links every (county, district) pair to a
CouncilRule; this command only fills in the county-tier record itself —
the parent authority's own notes/criteria, which previously had nowhere
to live (see debt_app.models.CountyCouncil).

Usage:
    python manage.py seed_county_councils
    python manage.py seed_county_councils --dry-run
    python manage.py seed_county_councils --overwrite
"""

import os
import re
from datetime import datetime

from django.core.management.base import BaseCommand
from django.conf import settings

from debt_app.models import CountyCouncil, CountyCouncilRouting

# The source md occasionally has a garbled heading instead of the county
# name, or a typo — resolved by cross-referencing the district list already
# routed in CountyCouncilRouting.
HEADING_OVERRIDES = {
    "Mon 28/07/2025 12:10": "Kent",                # pasted timestamp instead of a name; districts are Kent's
    "Nottingshamshire County Council": "Nottinghamshire",  # typo in source md
}

MIN_DIVIDEND_RE = re.compile(r'(\d{1,3})\s*P\s*/\s*£', re.IGNORECASE)


def _clean(text):
    return re.sub(r'\s+', ' ', text or '').strip(' *')


def _parse_sections(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections = []
    current = None
    for raw in lines:
        line = raw.rstrip('\n')
        heading = re.match(r'^##\s+(.+)$', line)
        if heading:
            if current:
                sections.append(current)
            current = {"heading": heading.group(1).strip(), "body": [], "stop": False}
            continue
        if current is None:
            continue
        if line.strip().startswith('**Districts:**'):
            current["stop"] = True
            continue
        if current["stop"]:
            continue
        current["body"].append(line)
    if current:
        sections.append(current)
    return sections


def _extract_field(body_text, label):
    pattern = re.compile(rf'\*\*{re.escape(label)}:?\*\*\s*(.*)', re.IGNORECASE)
    m = pattern.search(body_text)
    return _clean(m.group(1)) if m else ''


class Command(BaseCommand):
    help = "Seed CountyCouncil table from County_Councils_Criteria.md"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview only")
        parser.add_argument("--overwrite", action="store_true", help="Overwrite existing notes/status")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        md_path = os.path.join(settings.BASE_DIR, "Excel Criteria", "County_Councils_Criteria.md")
        if not os.path.exists(md_path):
            self.stderr.write(f"Source file not found: {md_path}")
            return

        known_counties = set(
            CountyCouncilRouting.objects.values_list('county_name', flat=True).distinct()
        )

        # The source md repeats some counties (e.g. Buckinghamshire appears
        # twice, once with real accept/reject criteria and once with just a
        # generic note). Merge by name first and keep whichever version has
        # actual accept/reject criteria, so a later generic duplicate can't
        # clobber the richer entry.
        by_name = {}

        for section in _parse_sections(md_path):
            heading = section["heading"]
            name = HEADING_OVERRIDES.get(heading, heading)
            name = re.sub(r'\s+County Council\s*$', '', name, flags=re.IGNORECASE).strip()

            if name not in known_counties:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP (not in CountyCouncilRouting): '{name}' (heading '{heading}')"
                ))
                continue

            body_text = "\n".join(section["body"])
            accept_reject = (
                _extract_field(body_text, "Accept / Reject")
                or _extract_field(body_text, "Accept/Reject")
            )
            notes = _extract_field(body_text, "Notes")

            combined = "\n".join(p for p in [
                f"Accept/Reject: {accept_reject}" if accept_reject else '',
                f"Notes: {notes}" if notes else '',
            ] if p)

            status = 'CONDITIONAL_VOTER' if accept_reject else 'NO_CRITERIA'

            min_div = None
            if accept_reject:
                div_match = MIN_DIVIDEND_RE.search(accept_reject)
                if div_match:
                    min_div = int(div_match.group(1))

            last_reviewed = None
            if heading in HEADING_OVERRIDES:
                date_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', heading)
                if date_match:
                    d, m, y = date_match.groups()
                    last_reviewed = datetime(int(y), int(m), int(d)).date()

            defaults = {"status": status, "blocked_reason": combined}
            if min_div is not None:
                defaults["min_dividend_pence"] = min_div
            if last_reviewed:
                defaults["last_reviewed"] = last_reviewed

            existing = by_name.get(name)
            if existing is None or (bool(accept_reject) and not existing["has_accept_reject"]):
                by_name[name] = {"defaults": defaults, "has_accept_reject": bool(accept_reject)}

        created = updated = skipped = 0

        for name, entry in by_name.items():
            defaults = entry["defaults"]

            if dry_run:
                self.stdout.write(f"  DRY-RUN: {name} -> {defaults['status']} ({defaults['blocked_reason'][:60]!r})")
                continue

            obj, was_created = CountyCouncil.objects.get_or_create(
                county_name=name,
                defaults=defaults,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  CREATED: {name}"))
            elif overwrite:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                updated += 1
                self.stdout.write(f"  UPDATED: {name}")
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created: {created}  Updated: {updated}  Skipped: {skipped}"
        ))
