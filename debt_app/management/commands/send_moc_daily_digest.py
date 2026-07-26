"""
send_moc_daily_digest.py
------------------------------------------------------------------------------
Sends ONE combined HTML+text email per calendar day to MOC_ALERT_RECIPIENTS,
covering the full CRM vote-sync report for today: sync run count, creditors
affected, the vote-change breakdown (accepted/rejected/modified/POD), every
un-emailed CreditorMocAlert, and every un-emailed CreditorNonAcceptMilestone.

Background
----------
Previously, check_and_send_moc_alerts() / check_and_send_non_accept_milestones()
(debt_app/services/crm_vote_sync.py) sent an email inline at the end of every
CRM sync run. Since a sync can be triggered any number of times a day (the
frontend "sync" button, or the sync_creditor_vote_summaries CLI command),
MOC_ALERT_RECIPIENTS could receive as many emails a day as there were sync
runs. Those two functions now only create CreditorMocAlert /
CreditorNonAcceptMilestone rows (emailed defaults to False) - they no longer
send anything. This command is the only thing that sends MOC email, and is
meant to be run once a day (e.g. at 23:30 Europe/London) via cron / Windows
Task Scheduler - see scripts/send_moc_digest_cron.sh and
scripts/send_moc_digest.bat.

Exactly-once-per-day guarantee
-------------------------------
A MocDigestLog row is written (unique on `date`) the moment an email is
successfully sent for that calendar day. Before sending, the command checks
for an existing log row and refuses to send a second time (use --force to
override deliberately, e.g. after fixing a bad send). This is stronger than
relying on the `emailed` flags alone, because it also stops a duplicate send
on a day with zero *new* alerts but where the report would otherwise just
resend the same totals.

If send_mail() raises, no MocDigestLog row is written and no alert/milestone
rows are marked emailed - they'll go out on the next run instead of being
silently lost.

Usage
-----
  python manage.py send_moc_daily_digest --dry-run
  python manage.py send_moc_daily_digest
  python manage.py send_moc_daily_digest --force
  python manage.py send_moc_daily_digest --test-email you@example.com
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from debt_app.models import CreditorMocAlert, CreditorNonAcceptMilestone, MocDigestLog
from debt_app.services.daily_digest import build_digest, today_london_date


class Command(BaseCommand):
    help = "Send one combined MOC daily digest email (HTML) for today's full CRM vote-sync report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be emailed without sending or marking anything as sent.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Send even if a digest has already been sent today (writes a new MocDigestLog row).",
        )
        parser.add_argument(
            "--test-email",
            metavar="ADDRESS",
            help=(
                "Send today's report to this address only, prefixed '[TEST]'. "
                "Does NOT mark alerts/milestones as emailed and does NOT count "
                "against the once-a-day guarantee - safe to run any number of times."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        test_email = options["test_email"]
        w = self.stdout.write
        style = self.style

        today = today_london_date()
        digest = build_digest(today)
        alerts = digest["alerts"]
        milestones = digest["milestones"]

        w(f"Date: {today.isoformat()}")
        w(f"Sync runs today: {digest['stats']['sync_runs_today']}")
        w(f"Creditors affected: {digest['stats']['distinct_creditors_affected']}")
        w(f"Vote changes: {digest['stats']['vote_change_events']['total']}")
        w(f"Un-emailed alerts: {len(alerts)}")
        w(f"Un-emailed milestones: {len(milestones)}")
        w("")

        if test_email:
            subject = f"[TEST] {digest['subject']}"
            w(style.WARNING(f"TEST MODE - sending to {test_email} only, no rows will be marked emailed."))
            if dry_run:
                w(style.WARNING("[DRY RUN] Test email not sent."))
                w(digest["text_body"])
                return
            self._send(subject, digest["text_body"], digest["html_body"], [test_email])
            w(style.SUCCESS(f"\nSent test digest email to {test_email}."))
            return

        if not settings.MOC_ALERT_RECIPIENTS:
            raise CommandError(
                "MOC_ALERT_RECIPIENTS is empty - set it in the environment before sending the real digest "
                "(use --test-email to send a preview to a specific address instead)."
            )

        already_sent = MocDigestLog.objects.filter(date=today).first()
        if already_sent and not force:
            w(style.SUCCESS(
                f"Digest already sent for {today.isoformat()} at "
                f"{already_sent.sent_at.isoformat()} - not sending again. Use --force to override."
            ))
            return

        if dry_run:
            w(style.WARNING("[DRY RUN] Email not sent, nothing marked as sent."))
            w(digest["text_body"])
            return

        self._send(digest["subject"], digest["text_body"], digest["html_body"], settings.MOC_ALERT_RECIPIENTS)

        with transaction.atomic():
            CreditorMocAlert.objects.filter(id__in=[a.id for a in alerts]).update(emailed=True)
            CreditorNonAcceptMilestone.objects.filter(id__in=[m.id for m in milestones]).update(emailed=True)
            MocDigestLog.objects.update_or_create(
                date=today,
                defaults={
                    "recipients": ", ".join(settings.MOC_ALERT_RECIPIENTS),
                    "alerts_count": len(alerts),
                    "milestones_count": len(milestones),
                    "vote_changes_total": digest["stats"]["vote_change_events"]["total"],
                },
            )

        w(style.SUCCESS(
            f"\nSent digest email to {len(settings.MOC_ALERT_RECIPIENTS)} recipient(s) and marked "
            f"{len(alerts) + len(milestones)} row(s) as emailed."
        ))

    @staticmethod
    def _send(subject, text_body, html_body, recipients):
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.MOC_ALERT_FROM_EMAIL,
            to=recipients,
            headers={"X-Auto-Response-Suppress": "All"},
        )
        message.attach_alternative(html_body, "text/html")
        message.send()
