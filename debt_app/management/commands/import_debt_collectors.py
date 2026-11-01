"""
Load debt collectors (BPO) into the DebtCollector list used by the BPO-DEBT rule.

    python manage.py import_debt_collectors collectors.csv [--dry-run] [--reactivate]

Accepts .csv, .txt or .xlsx (first sheet). Column 1 is the collector name;
optional column 2 holds other trading names separated by ";". A header row
whose first cell is "name" is skipped.

Additive only: new names are created, existing names get any new aliases.
Nothing is deleted or deactivated — do that in the admin.

⚠️ AN INACTIVE COLLECTOR STAYS INACTIVE (2026-11-01). Switching one off in the
admin is a decision; a list that still names it is not a reason to undo it, and
the record holds no "why" to tell the two apart. It is reported as
[INACTIVE — kept] (its new aliases still merge — an inactive record is never
loaded, so they match nothing until it is switched back on). `--reactivate`
switches back on the inactive collectors the file names, each reported as
[REACTIVATED].

⚠️ ONE ORGANISATION PER MATCH KEY (2026-11-01). BPO-DEBT matches a creditor
name to a collector by its normalised key (`engine/criteria.py ::
_collector_key`: case, punctuation, "&"/"and", trailing Ltd/plc/LLP ignored).
A row whose name or alias reduces to a key another collector already owns
("Marston Ltd" beside "Marston", an alias already on someone else) would make
two records answer for the same name, so it is reported as [CONFLICT] and
skipped — fix the file or the admin, then re-run. A name repeated in the file
is reported as [DUPLICATE ROW]; its aliases still merge.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from debt_app.engine.criteria import _collector_key
from debt_app.models import DebtCollector


def _read_rows(path: Path) -> list:
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        # A read-only workbook holds the file open until closed (locked on Windows).
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return [[("" if v is None else str(v)) for v in row]
                    for row in workbook.worksheets[0].iter_rows(values_only=True)]
        finally:
            workbook.close()
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


class Command(BaseCommand):
    help = "Import debt collectors (BPO) from a .csv/.txt/.xlsx file into the DebtCollector list."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving.")
        parser.add_argument("--reactivate", action="store_true",
                            help="Switch back on inactive collectors the file names (kept inactive otherwise).")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        created, updated, unchanged, conflicts, duplicates = [], [], [], [], []
        reactivated, kept_inactive = [], []
        with transaction.atomic():
            # Match key -> the collector (lower-cased name) that owns it.
            owner = {}
            for dc in DebtCollector.objects.all():
                for n in [dc.name, *(dc.aliases or [])]:
                    if _collector_key(n):
                        owner.setdefault(_collector_key(n), dc.name.lower())
            seen = set()
            for row in _read_rows(path):
                name = (row[0] if row else "").strip()
                if not name or name.lower() == "name":
                    continue
                aliases = [a.strip() for a in (row[1] if len(row) > 1 else "").split(";") if a.strip()]
                if name.lower() in seen:
                    duplicates.append(name)
                seen.add(name.lower())

                obj = DebtCollector.objects.filter(name__iexact=name).first()
                me = (obj.name if obj else name).lower()
                clash = sorted({f"{n!r} = {owner[_collector_key(n)]!r}" for n in [name, *aliases]
                                if owner.get(_collector_key(n), me) != me})
                if clash:
                    conflicts.append(f"{name}: {', '.join(clash)}")
                    continue
                for n in [name, *aliases]:
                    if _collector_key(n):
                        owner.setdefault(_collector_key(n), me)
                if obj is None:
                    DebtCollector.objects.create(name=name, aliases=aliases)
                    created.append(name)
                    continue
                merged = list(obj.aliases or [])
                merged += [a for a in aliases if a.lower() not in {m.lower() for m in merged}]
                new_aliases = merged != (obj.aliases or [])
                reactivate = not obj.is_active and options["reactivate"]
                if not obj.is_active and not reactivate and obj.name not in kept_inactive:
                    kept_inactive.append(obj.name)
                if new_aliases or reactivate:
                    obj.aliases = merged
                    if reactivate:
                        obj.is_active = True
                        reactivated.append(obj.name)
                    obj.save()
                    if new_aliases:
                        updated.append(name)
                elif obj.is_active:
                    unchanged.append(name)

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[DRY RUN] " if options["dry_run"] else ""
        for name in created:
            self.stdout.write(f"  {prefix}[CREATED] {name}")
        for name in updated:
            self.stdout.write(f"  {prefix}[UPDATED] {name}")
        for name in reactivated:
            self.stdout.write(self.style.WARNING(f"  {prefix}[REACTIVATED] {name}"))
        for name in kept_inactive:
            self.stdout.write(self.style.WARNING(
                f"  {prefix}[INACTIVE — kept] {name} -- switched off in the admin; --reactivate to switch it on"))
        for name in duplicates:
            self.stdout.write(self.style.WARNING(f"  {prefix}[DUPLICATE ROW] {name}"))
        for detail in conflicts:
            self.stdout.write(self.style.ERROR(
                f"  {prefix}[CONFLICT] skipped {detail} -- already another collector's name or alias"))
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}{len(created)} created, {len(updated)} updated, {len(unchanged)} unchanged, "
            f"{len(reactivated)} reactivated, {len(kept_inactive)} inactive kept, "
            f"{len(conflicts)} conflicts skipped, {len(duplicates)} duplicate rows."
        ))
