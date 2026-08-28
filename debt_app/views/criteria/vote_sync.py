"""Creditor vote summaries and the Aryza CRM vote sync runs."""

from datetime import timedelta
from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.models import CreditorCriteria
from debt_app.models import CouncilRule
from debt_app.permissions import HasWritePermission
from debt_app.permissions import HasReadPermission
from debt_app.models import CountyCouncil
from debt_app.models import CreditorVoteSummary
from debt_app.models import CrmSyncRun
from debt_app.models import CreditorVoteChangeEvent
from debt_app.models import CreditorMocAlert
from debt_app.models import CreditorNonAcceptMilestone
from debt_app.services.crm_vote_sync import run_crm_vote_sync
from debt_app.services.crm_vote_sync import get_recent_vote_tally
from debt_app.services.crm_vote_sync import get_last_5_tally
import threading

def _vote_summary_to_dict(summary) -> dict:
    if not summary:
        return None
    return {
        "id": summary.id,
        "total_votes": summary.total_votes,
        "accepted_count": summary.accepted_count,
        "rejected_count": summary.rejected_count,
        "modified_count": summary.modified_count,
        "pod_count": summary.pod_count,
        "latest_vote_date": summary.latest_vote_date.isoformat() if summary.latest_vote_date else None,
        "latest_vote_outcome": summary.latest_vote_outcome,
        "crm_rows_covered": summary.crm_rows_covered,
        "last_synced_at": summary.last_synced_at.isoformat(),
        "recent_tally": get_recent_vote_tally(summary),
        "last_5_tally": get_last_5_tally(summary),
    }


class CreditorVoteSummaryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasReadPermission]

    def get_permissions(self):
        # Determine required feature based on creditor type
        creditor_type = self.kwargs.get('type', '')
        if creditor_type == 'councils':
            self.required_feature = 'councils'
        elif creditor_type == 'county-councils':
            self.required_feature = 'councils'
        else:  # general creditors, which representative, etc.
            self.required_feature = 'general_creditors'
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request, type, id):
        creditor_obj = None
        if type == 'creditors':
            creditor_obj = CreditorCriteria.objects.filter(id=id).first()
            if not creditor_obj:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            summary = creditor_obj.vote_summaries.first()
        elif type == 'councils':
            creditor_obj = CouncilRule.objects.filter(id=id).first()
            if not creditor_obj:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            summary = creditor_obj.vote_summaries.first()
        elif type == 'county-councils':
            creditor_obj = CountyCouncil.objects.filter(id=id).first()
            if not creditor_obj:
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            summary = creditor_obj.vote_summaries.first()
        else:
            return Response({"detail": "Invalid creditor type."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(_vote_summary_to_dict(summary))


def _crm_sync_run_to_dict(run) -> dict:
    duration_seconds = None
    if run.finished_at:
        duration_seconds = (run.finished_at - run.started_at).total_seconds()
    return {
        "id": run.id,
        "status": run.status,
        "stage": run.stage,
        "trigger_source": run.trigger_source,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": duration_seconds,
        "dry_run": run.dry_run,
        "crm_rows_fetched": run.crm_rows_fetched,
        "records_created": run.records_created,
        "records_updated": run.records_updated,
        "creditor_criteria_count": run.creditor_criteria_count,
        "council_rule_count": run.council_rule_count,
        "county_council_count": run.county_council_count,
        "error_message": run.error_message,
        "triggered_by": run.triggered_by.username if run.triggered_by else None,
    }


def _run_crm_sync_in_background(run_id):
    """
    Thread target: runs the CRM vote sync for the given CrmSyncRun id and updates
    its status on completion/failure. Runs in its own thread, so it must close its
    own DB connections when done (this isn't a request-response cycle).
    """
    from django.db import connections
    try:
        run = CrmSyncRun.objects.get(pk=run_id)
        try:
            run_crm_vote_sync(run=run, dry_run=run.dry_run)
            run.status = "SUCCESS"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at"])
        except Exception as e:
            run.status = "FAILED"
            run.finished_at = timezone.now()
            run.error_message = str(e)
            run.save(update_fields=["status", "finished_at", "error_message"])
    finally:
        connections.close_all()


# A real sync (background thread or CLI) finishes in well under a minute in
# practice (see CrmSyncRun history), and the CRM query itself is capped at
# MAX_EXECUTION_TIME=600000ms (10 min) in crm_vote_sync.py. A RUNNING row
# older than this is not a slow sync - it's one whose process was killed
# (Ctrl+C, dev-server reload, crash) before it could mark itself FAILED, and
# would otherwise block every future trigger with a 409 forever.
STALE_RUN_THRESHOLD = timedelta(minutes=30)


class CrmSyncTriggerView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasWritePermission()]

    def post(self, request):
        CrmSyncRun.objects.filter(
            status='RUNNING', started_at__lt=timezone.now() - STALE_RUN_THRESHOLD,
        ).update(
            status='FAILED',
            error_message='Orphaned - process terminated before completion (auto-detected as stale)',
            finished_at=timezone.now(),
        )

        existing = CrmSyncRun.objects.filter(status='RUNNING').first()
        if existing:
            return Response(
                {"detail": "A sync is already running.", "id": existing.id, "status": existing.status},
                status=status.HTTP_409_CONFLICT,
            )

        run = CrmSyncRun.objects.create(trigger_source='MANUAL', triggered_by=request.user)

        thread = threading.Thread(target=_run_crm_sync_in_background, args=(run.id,), daemon=True)
        thread.start()

        return Response({"id": run.id, "status": "RUNNING"}, status=status.HTTP_202_ACCEPTED)


class CrmSyncStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request, pk):
        run = CrmSyncRun.objects.filter(pk=pk).first()
        if not run:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_crm_sync_run_to_dict(run))


class CrmSyncHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)

        queryset = CrmSyncRun.objects.all()

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_crm_sync_run_to_dict(r) for r in page_obj],
        }, status=status.HTTP_200_OK)


class CrmSyncRunCreditorBreakdownView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request, run_id):
        if not CrmSyncRun.objects.filter(pk=run_id).exists():
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Single aggregate query: counts per (vote_summary, status) for this run.
        # Avoids the N+1 that calling get_recent_vote_tally() per creditor would cause.
        counts_by_summary_and_status = (
            CreditorVoteChangeEvent.objects
            .filter(sync_run_id=run_id)
            .values('vote_summary_id', 'status')
            .annotate(count=Count('id'))
        )

        summary_ids = {row['vote_summary_id'] for row in counts_by_summary_and_status}
        summaries = CreditorVoteSummary.objects.filter(id__in=summary_ids).select_related(
            'creditor_criteria', 'council_rule', 'county_council'
        )

        creditor_info_by_summary_id = {}
        for summary in summaries:
            if summary.creditor_criteria:
                creditor_info_by_summary_id[summary.id] = {
                    "creditor_id": summary.creditor_criteria_id,
                    "creditor_name": summary.creditor_criteria.creditor_name,
                    "creditor_type": "creditors",
                }
            elif summary.council_rule:
                creditor_info_by_summary_id[summary.id] = {
                    "creditor_id": summary.council_rule_id,
                    "creditor_name": summary.council_rule.council_name,
                    "creditor_type": "councils",
                }
            elif summary.county_council:
                creditor_info_by_summary_id[summary.id] = {
                    "creditor_id": summary.county_council_id,
                    "creditor_name": summary.county_council.county_name,
                    "creditor_type": "county-councils",
                }

        results_by_summary_id = {}
        for row in counts_by_summary_and_status:
            summary_id = row['vote_summary_id']
            info = creditor_info_by_summary_id.get(summary_id)
            if not info:
                continue
            entry = results_by_summary_id.setdefault(summary_id, {
                "vote_summary_id": summary_id,
                **info,
                "accepted": 0,
                "rejected": 0,
                "modified": 0,
                "pod": 0,
            })
            entry[row['status']] = row['count']

        return Response({
            "run_id": run_id,
            "creditors": list(results_by_summary_id.values()),
        })


class CrmSyncTodayView(APIView):
    """
    Rolled-up totals for "today" (Europe/London calendar day), across ALL
    CrmSyncRun runs that occurred today - not a single run.
    """
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        return [IsAuthenticated(), HasReadPermission()]

    def get(self, request):
        from debt_app.services.daily_digest import compute_daily_stats

        # Same computation as crm_vote_sync.py's _create_moc_alerts_for_run
        # (Prompt 10a): timezone.now().date() would give the UTC calendar
        # date, which disagrees with the Europe/London calendar date for part
        # of every day during BST. localtime() converts to the active
        # Europe/London time first, so this always matches the calendar day
        # site users actually experience. compute_daily_stats() does the same
        # local-day-bounds computation (shared with send_moc_daily_digest) so
        # this tile and the emailed digest can never show different numbers.
        stats = compute_daily_stats()
        today = stats["date"]

        return Response({
            "date": today.isoformat(),
            "vote_change_events": stats["vote_change_events"],
            "moc_alerts_today": stats["moc_alerts_today"],
            "sync_runs_today": stats["sync_runs_today"],
            "distinct_creditors_affected": stats["distinct_creditors_affected"],
            # Alerts/milestones are only emailed once a day by the
            # send_moc_daily_digest management command, which flips
            # emailed=True on every row it just sent. So "email_sent_today"
            # reflects whether that digest has actually gone out today, not
            # just whether alert rows exist yet.
            "email_sent_today": (
                CreditorMocAlert.objects.filter(alert_date=today, emailed=True).exists()
                or CreditorNonAcceptMilestone.objects.filter(milestone_date=today, emailed=True).exists()
            ),
        })


NON_ACCEPT_STATUSES = ('rejected', 'modified', 'pod')


def check_non_accept_milestone(vote_summary, sync_run):
    """
    Check each non-accepted status (rejected, modified, pod) independently for
    this creditor. Any status that reaches 3+ events within a single UK
    calendar day - and hasn't already triggered a milestone today for that
    status - gets its own CreditorNonAcceptMilestone row.

    Returns a list of newly created milestones (may be empty, or contain more
    than one if several statuses cross the threshold in the same check).
    """
    from django.db import IntegrityError, transaction
    from debt_app.helpers import get_london_day_boundary

    # Get London calendar day boundaries
    day_start, day_end, today_date = get_london_day_boundary()

    created_milestones = []

    for status in NON_ACCEPT_STATUSES:
        # Query this vote_summary's CreditorVoteChangeEvent rows for this exact
        # status, within today's London day, ordered by detected_at ascending.
        events = list(
            CreditorVoteChangeEvent.objects.filter(
                vote_summary=vote_summary,
                status=status,
                detected_at__gte=day_start,
                detected_at__lt=day_end
            )
            .order_by('detected_at')
        )

        if len(events) < 3:
            continue

        first_event_at = events[0].detected_at
        third_event_at = events[2].detected_at

        try:
            # Wrapped in its own savepoint so a duplicate-today IntegrityError
            # only rolls back this insert, not any outer transaction the
            # caller may be running inside (e.g. a test harness).
            with transaction.atomic():
                milestone = CreditorNonAcceptMilestone.objects.create(
                    vote_summary=vote_summary,
                    milestone_date=today_date,
                    status=status,
                    first_event_at=first_event_at,
                    third_event_at=third_event_at,
                    count=len(events),
                )
            created_milestones.append(milestone)
        except IntegrityError:
            # Already triggered today for this status - expected/normal, not an error.
            continue

    return created_milestones
