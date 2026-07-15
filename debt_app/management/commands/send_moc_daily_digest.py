"""
send_moc_daily_digest.py
------------------------------------------------------------------------------
Sends ONE combined email per day to MOC_ALERT_RECIPIENTS, covering every
CreditorMocAlert and CreditorNonAcceptMilestone row created that hasn't been
emailed yet (emailed=False).

Background
----------
Previously, check_and_send_moc_alerts() / check_and_send_non_accept_milestones()
(debt_app/services/crm_vote_sync.py) sent an email inline at the end of every
CRM sync run. Since a sync can be triggered any number of times a day (the
frontend "sync" button, or the sync_creditor_vote_summaries CLI command),
MOC_ALERT_RECIPIENTS could receive up to two emails per run - i.e. as many
emails a day as there were sync runs.

Those two functions now only create CreditorMocAlert / CreditorNonAcceptMilestone
rows (emailed defaults to False) - they no longer send anything. This command
is the only thing that sends MOC email, and is meant to be run once a day
(e.g. at 23:30 Europe/London via Windows Task Scheduler, since this project
has no Celery/cron infrastructure):

    python manage.py send_moc_daily_digest

It queries today's un-emailed rows, sends a single email if there's anything
to report, and marks every row it just emailed as emailed=True so re-running
the command the same day (or a stray double-schedule) never re-sends the same
rows. If send_mail() raises, rows are NOT marked emailed - they'll go out on
the next run instead of being silently lost.

Usage
-----
  python manage.py send_moc_daily_digest --dry-run
  python manage.py send_moc_daily_digest
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from debt_app.models import CreditorMocAlert, CreditorNonAcceptMilestone, CreditorVoteSummary
from debt_app.services.crm_vote_sync import get_creditor_tags, resolve_vote_summary_creditor


def _build_alert_section(alerts):
    if not alerts:
        return None

    vote_summary_ids = [a.vote_summary_id for a in alerts]
    summaries_by_id = {
        s.id: s
        for s in CreditorVoteSummary.objects.filter(id__in=vote_summary_ids).select_related(
            "creditor_criteria", "council_rule", "county_council"
        )
    }

    lines = []
    for alert in alerts:
        summary = summaries_by_id.get(alert.vote_summary_id)
        if summary is None:
            continue
        creditor_name, creditor_criteria = resolve_vote_summary_creditor(summary)
        line = f"- {creditor_name}: {alert.triggered_by_status} (alert date: {alert.alert_date.isoformat()})"
        if creditor_criteria:
            tags = get_creditor_tags(creditor_criteria)
            if tags:
                line += f" [{', '.join(tags)}]"
        lines.append(line)

    header = f"MOC Alerts: {len(lines)} creditor(s) with new vote activity"
    return header + "\n" + "\n".join(lines)


def _build_milestone_section(milestones):
    if not milestones:
        return None

    vote_summary_ids = [m.vote_summary_id for m in milestones]
    summaries_by_id = {
        s.id: s
        for s in CreditorVoteSummary.objects.filter(id__in=vote_summary_ids).select_related(
            "creditor_criteria", "council_rule", "county_council"
        )
    }

    lines = []
    for milestone in milestones:
        summary = summaries_by_id.get(milestone.vote_summary_id)
        if summary is None:
            continue
        creditor_name, creditor_criteria = resolve_vote_summary_creditor(summary)
        line = f"- {creditor_name}"
        if creditor_criteria:
            tags = get_creditor_tags(creditor_criteria)
            if tags:
                line += f" [{', '.join(tags)}]"

        first_event_str = timezone.localtime(milestone.first_event_at).strftime("%d/%m/%Y %H:%M:%S")
        third_event_str = timezone.localtime(milestone.third_event_at).strftime("%d/%m/%Y %H:%M:%S")
        line += f"\n  Achieved 3 {milestone.status} between {first_event_str} and {third_event_str}"
        lines.append(line)

    header = f"MOC Milestones: {len(lines)} creditor(s) reached non-accept thresholds"
    return header + "\n" + "\n\n".join(lines)


class Command(BaseCommand):
    help = "Send one combined MOC digest email for today's un-emailed alerts/milestones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be emailed without sending or marking rows as emailed.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        w = self.stdout.write
        style = self.style

        if dry_run:
            w(style.WARNING("DRY RUN - no email will be sent, no rows will be marked emailed\n"))

        today = timezone.localtime(timezone.now()).date()

        alerts = list(
            CreditorMocAlert.objects.filter(alert_date=today, emailed=False).order_by("id")
        )
        milestones = list(
            CreditorNonAcceptMilestone.objects.filter(milestone_date=today, emailed=False).order_by("id")
        )

        if not alerts and not milestones:
            w(style.SUCCESS("Nothing new to report today - no email sent.\n"))
            return

        sections = [
            s for s in (_build_alert_section(alerts), _build_milestone_section(milestones)) if s
        ]

        subject = f"MOC Daily Digest {today.isoformat()}: {len(alerts)} alert(s), {len(milestones)} milestone(s)"
        body = "\n\n".join(sections)

        w(f"Alerts to email: {len(alerts)}")
        w(f"Milestones to email: {len(milestones)}")
        w("")
        w(body)

        if dry_run:
            w(style.WARNING("\n[DRY RUN] Email not sent, rows not marked emailed."))
            return

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.MOC_ALERT_FROM_EMAIL,
            recipient_list=settings.MOC_ALERT_RECIPIENTS,
        )

        with transaction.atomic():
            CreditorMocAlert.objects.filter(id__in=[a.id for a in alerts]).update(emailed=True)
            CreditorNonAcceptMilestone.objects.filter(id__in=[m.id for m in milestones]).update(emailed=True)

        w(style.SUCCESS(f"\nSent digest email and marked {len(alerts) + len(milestones)} row(s) as emailed."))
