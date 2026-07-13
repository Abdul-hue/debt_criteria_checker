import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from django.db import transaction, connection, reset_queries
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from datetime import timedelta

from debt_app.models import CreditorCriteria, CreditorVoteSummary, CreditorVoteChangeEvent, CrmSyncRun
from debt_app.services.crm_vote_sync import get_last_5_tally
from debt_app.views.criteria_views import enrich_positions_with_tallies

N_CREDITORS = 75  # realistic case size per Prompt 17 (50-200 range)


def main():
    print(f"Verifying enrich_positions_with_tallies() with N={N_CREDITORS} creditors...")

    with transaction.atomic():
        try:
            sync_run = CrmSyncRun.objects.create(
                status="SUCCESS",
                stage="Done — TEST VERIFICATION RUN, SAFE TO DELETE",
            )

            now = timezone.now()
            positions = []
            expected_by_cid = {}

            for i in range(N_CREDITORS):
                creditor, _ = CreditorCriteria.objects.get_or_create(
                    creditor_name=f"Perf Test Creditor {i}"
                )
                summary, _ = CreditorVoteSummary.objects.get_or_create(creditor_criteria=creditor)
                CreditorVoteChangeEvent.objects.filter(vote_summary=summary).delete()

                # Give every creditor 5+ events so last_5_tally is non-trivial
                # for all of them (worst case for the N+1 concern).
                statuses = ["modified", "accepted", "rejected", "rejected", "pod", "accepted"]
                for j, status in enumerate(statuses):
                    e = CreditorVoteChangeEvent.objects.create(
                        vote_summary=summary, sync_run=sync_run, status=status
                    )
                    e.detected_at = now - timedelta(minutes=(len(statuses) - j) * 10)
                    e.save()

                positions.append({"criteria_id": creditor.id})
                expected_by_cid[creditor.id] = get_last_5_tally(summary)

            # ---- Query count check ----
            reset_queries()
            with CaptureQueriesContext(connection) as ctx:
                enrich_positions_with_tallies(positions)
            query_count = len(ctx.captured_queries)

            print(f"\nTotal queries for enrich_positions_with_tallies() over {N_CREDITORS} creditors: {query_count}")
            print(f"  Expected: 2 bulk queries + {N_CREDITORS} get_last_5_tally() queries = {2 + N_CREDITORS}")

            # ---- Correctness check: pos["last_5_tally"] matches direct call ----
            mismatches = 0
            for pos in positions:
                cid = pos["criteria_id"]
                if pos.get("last_5_tally") != expected_by_cid[cid]:
                    mismatches += 1
                    print(f"MISMATCH for criteria_id={cid}: {pos.get('last_5_tally')} != {expected_by_cid[cid]}")

            assert mismatches == 0, f"{mismatches} creditor(s) had incorrect last_5_tally"
            assert all(pos.get("last_5_tally") is not None for pos in positions)
            assert all(pos["last_5_tally"]["total"] == 5 for pos in positions), (
                "Expected every creditor to be capped at the 5 most recent events"
            )
            sample = positions[0]["last_5_tally"]
            print(f"\nSample last_5_tally output (creditor 0): {sample}")

            print(f"\nAll {N_CREDITORS} creditors matched get_last_5_tally() output exactly. PASSED.")

        finally:
            transaction.set_rollback(True)
            print("Rolled back all test data.")


if __name__ == "__main__":
    main()
