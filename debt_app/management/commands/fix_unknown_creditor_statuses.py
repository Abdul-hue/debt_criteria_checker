"""
fix_unknown_creditor_statuses.py
------------------------------------------------------------------------------
Fixes CreditorCriteria rows whose status field equals 'UNKNOWN'.

Note on field naming vs. the spec
----------------------------------
The criteria engine emits the computed key ``effective_status`` at runtime.
When a DB row IS found, ``effective_status = criteria.status``.
When NO DB row is found, ``effective_status = "UNKNOWN"`` (engine sentinel).
Therefore "status='UNKNOWN'" in the DB and "effective_status='UNKNOWN'" at
runtime describe the same underlying problem: a row with a bad/missing status.

The is_watch / is_tix / is_evolve booleans were removed in migration 0003
and replaced by the ``representative`` CharField (WATCH / TIX / EVOLVE / NONE).

Rule mapping
------------
Spec field          -> Actual DB field
effective_status    -> status
is_watch=True       -> representative='WATCH'
is_tix=True         -> representative='TIX'
is_evolve=True      -> representative='EVOLVE'

Rules applied
-------------
Rule 1 - Representative-defaulted rows
  representative='WATCH'  AND status='UNKNOWN' -> status='ACCEPT'
  representative='TIX'    AND status='UNKNOWN' -> status='ACCEPT'
  representative='EVOLVE' AND status='UNKNOWN' -> status='ACCEPT'

Rule 2 - Specific named creditor overrides (always applied regardless of
          current status)

Rule 3 - Remaining status='UNKNOWN' rows with representative='NONE' are
          printed for manual review; their status is NOT changed.

Usage
-----
  python manage.py fix_unknown_creditor_statuses --dry-run
  python manage.py fix_unknown_creditor_statuses
"""

from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria


class Command(BaseCommand):
    help = (
        "Fix CreditorCriteria rows whose status='UNKNOWN' using representative "
        "defaults (Rule 1) and known named-creditor overrides (Rule 2). "
        "Rows that cannot be auto-fixed are listed for manual review (Rule 3)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be changed without making any changes.",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Named-creditor fix definitions (Rule 2)
    # Each entry is:  (filter_kwargs, exclude_kwargs, update_kwargs, label)
    # ─────────────────────────────────────────────────────────────────────────
    _NAMED_FIXES = [
        # Lloyds Bank - WATCH managed, votes to accept
        # Exclude "Lloyds Bank Personal Loan" rows (different policy)
        (
            {"creditor_name__icontains": "lloyds"},
            {"creditor_name__icontains": "personal loan"},
            {"status": "ACCEPT", "representative": "WATCH"},
            "Lloyds Bank (excl. Personal Loan) -> ACCEPT / WATCH",
        ),
        (
            {"creditor_name__in": ["Lloyds", "Lloyds Bank"]},
            {},
            {"status": "ACCEPT", "representative": "WATCH"},
            "Lloyds / Lloyds Bank exact names -> ACCEPT / WATCH",
        ),
        # Monzo Bank - WATCH from 30/04/2024
        (
            {"creditor_name__icontains": "monzo"},
            {},
            {"status": "ACCEPT", "representative": "WATCH"},
            "Monzo Bank -> ACCEPT / WATCH",
        ),
        # British Gas - TIX managed
        (
            {"creditor_name__icontains": "british gas"},
            {},
            {"status": "ACCEPT", "representative": "TIX"},
            "British Gas -> ACCEPT / TIX",
        ),
        # Thames Water - WATCH managed
        (
            {"creditor_name__icontains": "thames water"},
            {},
            {"status": "ACCEPT", "representative": "WATCH"},
            "Thames Water -> ACCEPT / WATCH",
        ),
        # Tesco Bank - WATCH managed
        (
            {"creditor_name__icontains": "tesco bank"},
            {},
            {"status": "ACCEPT", "representative": "WATCH"},
            "Tesco Bank -> ACCEPT / WATCH",
        ),
        # CapQuest - WATCH managed
        (
            {"creditor_name__icontains": "capquest"},
            {},
            {"status": "ACCEPT", "representative": "WATCH"},
            "CapQuest -> ACCEPT / WATCH",
        ),
    ]

    # ─────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        w = self.stdout.write
        style = self.style

        if dry_run:
            w(style.WARNING("DRY RUN - no changes will be made\n"))

        # ── Step 1: before-state snapshot ─────────────────────────────────────
        unknown_qs = CreditorCriteria.objects.filter(status="UNKNOWN")
        total_before = unknown_qs.count()

        w(style.HTTP_INFO("\n" + "=" * 60))
        w(style.HTTP_INFO("BEFORE STATE"))
        w(style.HTTP_INFO("=" * 60))
        w(f"Total rows with status='UNKNOWN': {total_before}\n")

        if total_before == 0:
            w(style.SUCCESS(
                "No rows with status='UNKNOWN' found in the database.\n"
                "The database is already clean.\n"
            ))
        else:
            from django.db.models import Count
            breakdown = (
                unknown_qs
                .values("representative")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            w("Breakdown by representative:")
            for row in breakdown:
                w(f"  representative={row['representative']!r}  count={row['count']}")
            w("")

        # ── Step 2: Rule 1 — auto-fix representative-defaulted rows ──────────
        w(style.HTTP_INFO("\n" + "=" * 60))
        w(style.HTTP_INFO("RULE 1 - Representative-defaulted UNKNOWN rows"))
        w(style.HTTP_INFO("=" * 60))

        rule1_total_fixed = 0
        for rep_value in ("WATCH", "TIX", "EVOLVE"):
            qs = CreditorCriteria.objects.filter(
                status="UNKNOWN", representative=rep_value
            )
            count = qs.count()
            if count == 0:
                w(f"  representative={rep_value!r}: no UNKNOWN rows - nothing to fix")
                continue

            names = list(qs.values_list("creditor_name", flat=True))
            w(f"  representative={rep_value!r}: {count} row(s) -> status='ACCEPT'")
            for name in names:
                w(f"    - {name}")

            if not dry_run:
                updated = qs.update(status="ACCEPT")
                w(style.SUCCESS(f"    [OK] Updated {updated} row(s)"))
            else:
                w(style.WARNING(f"    [DRY RUN] Would update {count} row(s)"))

            rule1_total_fixed += count

        if rule1_total_fixed == 0:
            w("  No Rule 1 fixes needed.\n")

        # ── Step 3: Rule 2 — specific named creditor fixes ────────────────────
        w(style.HTTP_INFO("\n" + "=" * 60))
        w(style.HTTP_INFO("RULE 2 - Named creditor overrides"))
        w(style.HTTP_INFO("=" * 60))

        rule2_total_fixed = 0
        for filter_kw, exclude_kw, update_kw, label in self._NAMED_FIXES:
            qs = CreditorCriteria.objects.filter(**filter_kw)
            if exclude_kw:
                qs = qs.exclude(**exclude_kw)

            count = qs.count()
            if count == 0:
                w(f"  {label}: no matching rows - SKIPPED")
                continue

            # Identify rows whose values differ from the target (real changes)
            changed_rows = []
            for obj in qs:
                diffs = {
                    field: (getattr(obj, field), new_val)
                    for field, new_val in update_kw.items()
                    if getattr(obj, field) != new_val
                }
                if diffs:
                    changed_rows.append((obj.creditor_name, diffs))

            if not changed_rows:
                w(f"  {label}: {count} row(s) already correct - nothing to change")
                continue

            w(f"  {label}: {len(changed_rows)} row(s) need updating")
            for cname, diffs in changed_rows:
                diff_str = ", ".join(
                    f"{f}: {old!r} -> {new!r}" for f, (old, new) in diffs.items()
                )
                w(f"    - {cname!r}  ({diff_str})")

            if not dry_run:
                updated = qs.update(**update_kw)
                w(style.SUCCESS(f"    [OK] Updated {updated} row(s)"))
                rule2_total_fixed += updated
            else:
                w(style.WARNING(f"    [DRY RUN] Would update {len(changed_rows)} row(s)"))
                rule2_total_fixed += len(changed_rows)

        if rule2_total_fixed == 0 and not dry_run:
            w("  No Rule 2 fixes needed.\n")

        # ── Step 4: Rule 3 — remaining UNKNOWN, no representative (manual) ────
        w(style.HTTP_INFO("\n" + "=" * 60))
        w(style.HTTP_INFO("RULE 3 - Remaining UNKNOWN rows (manual review required)"))
        w(style.HTTP_INFO("=" * 60))

        remaining_qs = CreditorCriteria.objects.filter(
            status="UNKNOWN", representative="NONE"
        )
        remaining_count = remaining_qs.count()

        if remaining_count == 0:
            w(style.SUCCESS("  No unresolvable UNKNOWN rows - all clear.\n"))
        else:
            w(style.ERROR(
                f"  {remaining_count} row(s) with status='UNKNOWN' and no "
                "representative - cannot be auto-fixed:"
            ))
            for obj in remaining_qs.order_by("creditor_name"):
                w(
                    f"    - {obj.creditor_name!r}"
                    f"  (status={obj.status!r}, representative={obj.representative!r})"
                )
            w("")
            w(style.WARNING(
                "  ACTION REQUIRED: Manually set status and/or representative "
                "for the rows listed above."
            ))

        # ── Step 5: final summary ─────────────────────────────────────────────
        w(style.HTTP_INFO("\n" + "=" * 60))
        w(style.HTTP_INFO("FINAL SUMMARY"))
        w(style.HTTP_INFO("=" * 60))

        if dry_run:
            w(style.WARNING(
                f"  [DRY RUN] Would fix: {rule1_total_fixed + rule2_total_fixed} row(s)"
            ))
            w(style.WARNING(
                f"  [DRY RUN] Remaining unresolvable: {remaining_count} row(s)"
            ))
            w(style.WARNING(
                "\n  Re-run without --dry-run to apply changes.\n"
            ))
        else:
            total_fixed = rule1_total_fixed + rule2_total_fixed
            final_unknown = CreditorCriteria.objects.filter(status="UNKNOWN").count()
            w(style.SUCCESS(f"  Rows fixed (Rule 1 + Rule 2): {total_fixed}"))
            w(
                style.ERROR(f"  Rows still UNKNOWN: {final_unknown}")
                if final_unknown
                else style.SUCCESS(f"  Rows still UNKNOWN: {final_unknown}")
            )
            w("")
