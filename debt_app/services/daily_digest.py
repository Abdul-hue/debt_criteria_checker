"""
daily_digest.py
------------------------------------------------------------------------------
Shared "today" stats + HTML/text rendering for:
  - CrmSyncTodayView (the dashboard's "Today's Sync Report" tile)
  - send_moc_daily_digest (the once-a-day email)

Keeping the stats query in one place means the dashboard numbers and the
emailed numbers can never drift apart.
"""

from datetime import datetime, time, timedelta

from django.db.models import Count
from django.utils import timezone
from django.utils.html import escape

from debt_app.models import (
    CreditorMocAlert,
    CreditorNonAcceptMilestone,
    CreditorVoteChangeEvent,
    CreditorVoteSummary,
    CrmSyncRun,
)
from debt_app.services.crm_vote_sync import get_creditor_tags, resolve_vote_summary_creditor


def today_london_date():
    return timezone.localtime(timezone.now()).date()


def london_day_bounds(day):
    current_tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(day, time.min), current_tz)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def compute_daily_stats(day=None):
    """Same rolled-up totals shown by CrmSyncTodayView, for `day` (defaults
    to today, Europe/London calendar day)."""
    day = day or today_london_date()
    day_start, day_end = london_day_bounds(day)

    events_today = CreditorVoteChangeEvent.objects.filter(
        detected_at__gte=day_start, detected_at__lt=day_end
    )
    counts_by_status = dict(
        events_today.values('status').annotate(count=Count('id')).values_list('status', 'count')
    )
    vote_change_totals = {
        "accepted": counts_by_status.get('accepted', 0),
        "rejected": counts_by_status.get('rejected', 0),
        "modified": counts_by_status.get('modified', 0),
        "pod": counts_by_status.get('pod', 0),
    }
    vote_change_totals["total"] = sum(vote_change_totals.values())

    distinct_creditors_affected = events_today.values('vote_summary_id').distinct().count()
    sync_runs_today = CrmSyncRun.objects.filter(
        started_at__gte=day_start, started_at__lt=day_end
    ).count()
    moc_alerts_today = CreditorMocAlert.objects.filter(alert_date=day).count()

    return {
        "date": day,
        "vote_change_events": vote_change_totals,
        "moc_alerts_today": moc_alerts_today,
        "sync_runs_today": sync_runs_today,
        "distinct_creditors_affected": distinct_creditors_affected,
    }


def _alert_rows(alerts):
    if not alerts:
        return []
    vote_summary_ids = [a.vote_summary_id for a in alerts]
    summaries_by_id = {
        s.id: s
        for s in CreditorVoteSummary.objects.filter(id__in=vote_summary_ids).select_related(
            "creditor_criteria", "council_rule", "county_council"
        )
    }
    rows = []
    for alert in alerts:
        summary = summaries_by_id.get(alert.vote_summary_id)
        if summary is None:
            continue
        creditor_name, creditor_criteria = resolve_vote_summary_creditor(summary)
        tags = get_creditor_tags(creditor_criteria) if creditor_criteria else []
        rows.append({
            "creditor_name": creditor_name,
            "status": alert.triggered_by_status,
            "alert_date": alert.alert_date,
            "tags": tags,
        })
    return rows


def _milestone_rows(milestones):
    if not milestones:
        return []
    vote_summary_ids = [m.vote_summary_id for m in milestones]
    summaries_by_id = {
        s.id: s
        for s in CreditorVoteSummary.objects.filter(id__in=vote_summary_ids).select_related(
            "creditor_criteria", "council_rule", "county_council"
        )
    }
    rows = []
    for milestone in milestones:
        summary = summaries_by_id.get(milestone.vote_summary_id)
        if summary is None:
            continue
        creditor_name, creditor_criteria = resolve_vote_summary_creditor(summary)
        tags = get_creditor_tags(creditor_criteria) if creditor_criteria else []
        rows.append({
            "creditor_name": creditor_name,
            "status": milestone.status,
            "tags": tags,
            "first_event_at": timezone.localtime(milestone.first_event_at),
            "third_event_at": timezone.localtime(milestone.third_event_at),
            "count": milestone.count,
        })
    return rows


_STATUS_COLORS = {
    "accepted": "#0f9d58",
    "rejected": "#d93025",
    "modified": "#f29900",
    "pod": "#1a73e8",
}


def _status_badge_html(status):
    color = _STATUS_COLORS.get((status or "").lower(), "#5f6368")
    label = (status or "UNKNOWN").upper()
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'background:{color};color:#ffffff;font-size:11px;font-weight:600;'
        f'letter-spacing:.03em;">{escape(label)}</span>'
    )


def render_digest_subject(day, stats, alert_count, milestone_count):
    return (
        f"CRM Vote Sync — Daily Digest for {day.strftime('%d/%m/%Y')} "
        f"({stats['vote_change_events']['total']} vote change(s), "
        f"{alert_count} alert(s), {milestone_count} milestone(s))"
    )


def render_digest_text(day, stats, alert_rows, milestone_rows):
    events = stats["vote_change_events"]
    lines = [
        f"CRM Vote Sync — Daily Digest for {day.strftime('%d/%m/%Y')}",
        "=" * 60,
        "",
        "SUMMARY",
        f"  Sync runs today:          {stats['sync_runs_today']}",
        f"  Creditors affected:       {stats['distinct_creditors_affected']}",
        f"  Vote changes:             {events['total']}",
        f"    Accepted: {events['accepted']}  Rejected: {events['rejected']}  "
        f"Modified: {events['modified']}  POD: {events['pod']}",
        f"  MOC alerts today:         {stats['moc_alerts_today']}",
        "",
    ]

    lines.append(f"MOC ALERTS ({len(alert_rows)})")
    if alert_rows:
        for row in alert_rows:
            tag_str = f" [{', '.join(row['tags'])}]" if row["tags"] else ""
            lines.append(f"  - {row['creditor_name']}: {row['status']}{tag_str}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append(f"MOC MILESTONES ({len(milestone_rows)})")
    if milestone_rows:
        for row in milestone_rows:
            tag_str = f" [{', '.join(row['tags'])}]" if row["tags"] else ""
            lines.append(
                f"  - {row['creditor_name']}{tag_str}: reached 3x {row['status']} "
                f"between {row['first_event_at'].strftime('%d/%m/%Y %H:%M')} and "
                f"{row['third_event_at'].strftime('%d/%m/%Y %H:%M')}"
            )
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def render_digest_html(day, stats, alert_rows, milestone_rows):
    events = stats["vote_change_events"]

    def stat_tile(label, value):
        return f"""
        <td style="padding:6px;">
          <div style="background:#f8f9fb;border:1px solid #e3e6ea;border-radius:8px;
                      padding:14px 16px;text-align:center;">
            <div style="font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.06em;
                        text-transform:uppercase;">{escape(label)}</div>
            <div style="margin-top:4px;font-size:22px;font-weight:700;color:#0b1f3a;">{value}</div>
          </div>
        </td>"""

    stat_tiles = "".join([
        stat_tile("Sync Runs", stats["sync_runs_today"]),
        stat_tile("Creditors Affected", stats["distinct_creditors_affected"]),
        stat_tile("Vote Changes", events["total"]),
        stat_tile("MOC Alerts", stats["moc_alerts_today"]),
    ])

    vote_breakdown_rows = "".join([
        f"""<tr>
              <td style="padding:8px 12px;color:#ffffff;font-size:13px;">{label}</td>
              <td style="padding:8px 12px;color:#ffffff;font-size:13px;text-align:right;
                         font-variant-numeric:tabular-nums;">{events[key]}</td>
            </tr>"""
        for key, label in (
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("modified", "Modified"),
            ("pod", "POD"),
        )
    ])

    if alert_rows:
        alert_items = "".join(
            f"""<tr>
                  <td style="padding:8px 12px;border-bottom:1px solid #eef0f2;font-size:13px;color:#111827;">
                    {escape(row['creditor_name'])}
                    {f'<span style="color:#9aa1ab;font-size:11px;"> [{escape(", ".join(row["tags"]))}]</span>' if row['tags'] else ''}
                  </td>
                  <td style="padding:8px 12px;border-bottom:1px solid #eef0f2;text-align:right;">
                    {_status_badge_html(row['status'])}
                  </td>
                </tr>"""
            for row in alert_rows
        )
        alerts_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="border-collapse:collapse;margin-top:8px;">
          {alert_items}
        </table>"""
    else:
        alerts_html = '<p style="color:#9aa1ab;font-size:13px;margin:8px 0 0;">No new MOC alerts today.</p>'

    if milestone_rows:
        milestone_items = "".join(
            f"""<tr>
                  <td style="padding:8px 12px;border-bottom:1px solid #eef0f2;font-size:13px;color:#111827;">
                    {escape(row['creditor_name'])}
                    {f'<span style="color:#9aa1ab;font-size:11px;"> [{escape(", ".join(row["tags"]))}]</span>' if row['tags'] else ''}
                    <br/>
                    <span style="color:#6b7280;font-size:12px;">
                      Reached 3x {escape(row['status'])} between
                      {row['first_event_at'].strftime('%d/%m/%Y %H:%M')} and
                      {row['third_event_at'].strftime('%d/%m/%Y %H:%M')}
                    </span>
                  </td>
                  <td style="padding:8px 12px;border-bottom:1px solid #eef0f2;text-align:right;vertical-align:top;">
                    {_status_badge_html(row['status'])}
                  </td>
                </tr>"""
            for row in milestone_rows
        )
        milestones_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="border-collapse:collapse;margin-top:8px;">
          {milestone_items}
        </table>"""
    else:
        milestones_html = '<p style="color:#9aa1ab;font-size:13px;margin:8px 0 0;">No non-accept milestones reached today.</p>'

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRM Vote Sync — Daily Digest</title>
</head>
<body style="margin:0;padding:0;background:#f1f2f4;font-family:Segoe UI, Arial, sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f2f4;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:10px;overflow:hidden;
                      box-shadow:0 1px 3px rgba(0,0,0,0.08);">
          <tr>
            <td style="background:#0b1f3a;padding:20px 28px;">
              <div style="font-size:11px;font-weight:700;color:#9db4d9;letter-spacing:.08em;
                          text-transform:uppercase;">CRM Vote Sync</div>
              <div style="margin-top:2px;font-size:18px;font-weight:700;color:#ffffff;">
                Daily Digest — {day.strftime('%A %d %B %Y')}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 28px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>{stat_tiles}</tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 24px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                     style="background:#0b1f3a;border-radius:8px;overflow:hidden;">
                <tr>
                  <td colspan="2" style="padding:10px 12px;font-size:10px;font-weight:700;
                      color:#9db4d9;letter-spacing:.06em;text-transform:uppercase;
                      border-bottom:1px solid rgba(255,255,255,0.12);">
                    Vote Change Breakdown
                  </td>
                </tr>
                {vote_breakdown_rows}
                <tr>
                  <td style="padding:8px 12px;color:#ffffff;font-size:13px;font-weight:700;
                      border-top:1px solid rgba(255,255,255,0.12);">Total</td>
                  <td style="padding:8px 12px;color:#ffffff;font-size:13px;font-weight:700;text-align:right;
                      border-top:1px solid rgba(255,255,255,0.12);">{events['total']}</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px 8px;">
              <div style="font-size:13px;font-weight:700;color:#0b1f3a;border-bottom:2px solid #eef0f2;
                          padding-bottom:6px;">MOC Alerts ({stats['moc_alerts_today']})</div>
              {alerts_html}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 28px 24px;">
              <div style="font-size:13px;font-weight:700;color:#0b1f3a;border-bottom:2px solid #eef0f2;
                          padding-bottom:6px;">MOC Milestones ({len(milestone_rows)})</div>
              {milestones_html}
            </td>
          </tr>
          <tr>
            <td style="background:#f8f9fb;padding:14px 28px;border-top:1px solid #eef0f2;">
              <div style="font-size:11px;color:#9aa1ab;">
                Automated daily digest from the Debt Criteria Check CRM vote sync.
                This email is sent at most once per calendar day.
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def build_digest(day=None):
    """Gathers everything needed for one digest send: stats, alert/milestone
    querysets + rendered rows, subject/text/html. Does NOT send or mark
    anything as emailed - the caller (management command) owns that."""
    day = day or today_london_date()
    stats = compute_daily_stats(day)

    alerts = list(CreditorMocAlert.objects.filter(alert_date=day, emailed=False).order_by("id"))
    milestones = list(
        CreditorNonAcceptMilestone.objects.filter(milestone_date=day, emailed=False).order_by("id")
    )
    alert_rows = _alert_rows(alerts)
    milestone_rows = _milestone_rows(milestones)

    subject = render_digest_subject(day, stats, len(alert_rows), len(milestone_rows))
    text_body = render_digest_text(day, stats, alert_rows, milestone_rows)
    html_body = render_digest_html(day, stats, alert_rows, milestone_rows)

    return {
        "day": day,
        "stats": stats,
        "alerts": alerts,
        "milestones": milestones,
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
    }
