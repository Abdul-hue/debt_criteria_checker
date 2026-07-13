"""
test_real_milestone_email.py
----------------------------
Sends a REAL milestone alert email over the configured SMTP backend
(smtp.office365.com:587 / TLS) without persisting any data.

Key behaviours
  - No EMAIL_BACKEND override -- uses whatever Django has configured.
  - Wraps everything in transaction.atomic() + set_rollback(True) so
    every DB write is rolled back at the end; nothing is left in the DB.
  - Synthesises: 1 creditor, 1 sync run, 3 non-accept events (2 rejected + 1 modified).
  - Calls check_and_send_non_accept_milestones(run) for real.
  - Prints confirmed subject, recipient list, and full email body.

Run from the project root:
  python debt_app/scratch/test_real_milestone_email.py
"""

import os, sys, django
from datetime import timedelta

# ---------------------------------------------------------------------------
# Bootstrap Django
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

# ---------------------------------------------------------------------------
# Now safe to import Django / project modules
# ---------------------------------------------------------------------------
from django.conf import settings
from django.db import transaction
from django.utils import timezone
import smtplib, traceback

from debt_app.models import (
    CreditorCriteria,
    CreditorVoteSummary,
    CreditorVoteChangeEvent,
    CreditorNonAcceptMilestone,
    CrmSyncRun,
)
from debt_app.services.crm_vote_sync import check_and_send_non_accept_milestones
from debt_app.helpers import get_london_day_boundary

# ---------------------------------------------------------------------------
# Report current email configuration
# ---------------------------------------------------------------------------
print("=" * 60)
print("EMAIL BACKEND CONFIGURATION")
print("=" * 60)
backend = getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
print(f"  EMAIL_BACKEND        : {backend}")
print(f"  EMAIL_HOST           : {settings.EMAIL_HOST!r}")
print(f"  EMAIL_PORT           : {settings.EMAIL_PORT}")
print(f"  EMAIL_USE_TLS        : {settings.EMAIL_USE_TLS}")
print(f"  EMAIL_HOST_USER      : {settings.EMAIL_HOST_USER!r}")
print(f"  EMAIL_HOST_PASSWORD  : {'<redacted - SET>' if settings.EMAIL_HOST_PASSWORD else '<NOT SET - EMPTY>'}")
print(f"  DEFAULT_FROM_EMAIL   : {settings.DEFAULT_FROM_EMAIL!r}")
print(f"  MOC_ALERT_FROM_EMAIL : {settings.MOC_ALERT_FROM_EMAIL!r}")
print(f"  MOC_ALERT_RECIPIENTS : {settings.MOC_ALERT_RECIPIENTS}")
print("=" * 60)

# Warn about known problem configurations
if not settings.EMAIL_HOST_USER:
    print("\n[WARN] EMAIL_HOST_USER is empty -- SMTP AUTH will likely fail on Office365.")
if not settings.MOC_ALERT_FROM_EMAIL:
    print("\n[WARN] MOC_ALERT_FROM_EMAIL resolved to empty string -- email From: will be blank.")
if settings.EMAIL_HOST_USER and settings.MOC_ALERT_FROM_EMAIL and \
   settings.EMAIL_HOST_USER.lower() != settings.MOC_ALERT_FROM_EMAIL.lower():
    print(f"\n[WARN] From/Auth mismatch: EMAIL_HOST_USER={settings.EMAIL_HOST_USER!r} "
          f"but From={settings.MOC_ALERT_FROM_EMAIL!r}. "
          f"Office365 may reject this with 5.7.x.")
else:
    print("\n[OK] EMAIL_HOST_USER and MOC_ALERT_FROM_EMAIL match (or both blank).")

print()

# ---------------------------------------------------------------------------
# Optional: smoke-test raw SMTP connectivity before the Django send
# ---------------------------------------------------------------------------
print("--- SMTP connectivity smoke test ---")
try:
    import socket
    host = settings.EMAIL_HOST.split()[0]   # strip inline comments dotenv may leave
    port = settings.EMAIL_PORT
    conn = smtplib.SMTP(host, port, timeout=10)
    greeting = conn.ehlo()
    print(f"  EHLO response: {greeting}")
    if settings.EMAIL_USE_TLS:
        conn.starttls()
        print("  STARTTLS: OK")
    conn.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
    print("  SMTP LOGIN: OK")
    conn.quit()
    print("  SMTP smoke test PASSED")
except Exception as exc:
    print(f"  SMTP smoke test FAILED: {exc}")
    traceback.print_exc()
print()

# ---------------------------------------------------------------------------
# Main test -- wrapped in a rolled-back transaction
# ---------------------------------------------------------------------------
def main():
    print("Starting real-send milestone email test...")

    with transaction.atomic():
        try:
            # 1. Dummy sync run
            sync_run = CrmSyncRun.objects.create(
                status="SUCCESS",
                stage="TEST REAL EMAIL RUN -- WILL BE ROLLED BACK",
            )
            print(f"  Created CrmSyncRun id={sync_run.id}")

            # 2. Dummy CreditorCriteria
            creditor_criteria, created = CreditorCriteria.objects.get_or_create(
                creditor_name="Test Creditor Milestone Corp",
                representative="NONE",
                min_dividend_pence=10,
                source_sheet="DIVIDEND",
            )
            print(f"  CreditorCriteria id={creditor_criteria.id} (created={created})")

            # 3. Dummy CreditorVoteSummary
            vote_summary, created = CreditorVoteSummary.objects.get_or_create(
                creditor_criteria=creditor_criteria,
            )
            print(f"  CreditorVoteSummary id={vote_summary.id} (created={created})")

            # 4. Clear today's milestone + non-accept events for this summary
            _, _, today_date = get_london_day_boundary()
            day_start, day_end, _ = get_london_day_boundary()

            del_m = CreditorNonAcceptMilestone.objects.filter(
                vote_summary=vote_summary, milestone_date=today_date).delete()
            del_e = CreditorVoteChangeEvent.objects.filter(
                vote_summary=vote_summary,
                detected_at__gte=day_start,
                detected_at__lt=day_end,
            ).exclude(status="accepted").delete()
            print(f"  Cleared existing: milestones={del_m}, events={del_e}")

            # 5. Synthesise 3 non-accept events, ALL "rejected" -- the current
            # per-status milestone logic (check_non_accept_milestone) requires
            # 3+ events of the SAME status within one London day, not 3 mixed
            # non-accept events.
            now = timezone.now()
            e1 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary, sync_run=sync_run, status="rejected")
            e1.detected_at = now - timedelta(minutes=30); e1.save()

            e2 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary, sync_run=sync_run, status="rejected")
            e2.detected_at = now - timedelta(minutes=15); e2.save()

            e3 = CreditorVoteChangeEvent.objects.create(
                vote_summary=vote_summary, sync_run=sync_run, status="rejected")
            e3.detected_at = now; e3.save()

            print("\n  Synthesised events:")
            for e in [e1, e2, e3]:
                local_ts = timezone.localtime(e.detected_at).strftime("%d/%m/%Y %H:%M:%S")
                print(f"    id={e.id}  status={e.status}  detected_at(London)={local_ts}")

            # 6. Call the real milestone check
            print("\n  Calling check_and_send_non_accept_milestones(run)...")
            milestones = check_and_send_non_accept_milestones(sync_run)
            print(f"  Done. Milestones returned: {len(milestones)}")

            if not milestones:
                print("\n  [WARN] No milestones created -- threshold not met or already exists.")
            else:
                for m in milestones:
                    print(f"  Milestone id={m.id}  date={m.milestone_date}  status={m.status}  count={m.count}  first={m.first_event_at}  third={m.third_event_at}")

            print("\n" + "=" * 60)
            print("SEND SUMMARY")
            print("=" * 60)
            print(f"  Recipients : {settings.MOC_ALERT_RECIPIENTS}")
            print(f"  From       : {settings.MOC_ALERT_FROM_EMAIL!r}")
            print(f"  Backend    : {backend}")
            if milestones:
                print("  Status     : Email dispatched to SMTP (check inbox / server log for delivery)")
            else:
                print("  Status     : No email sent (no milestone triggered)")
            print("=" * 60)

        finally:
            transaction.set_rollback(True)
            print("\n[ROLLBACK] Transaction rolled back -- no data persisted.")


if __name__ == "__main__":
    main()
