import os
import re
from datetime import datetime, time as time_of_day, timedelta
from django.db import transaction, connections, IntegrityError
from django.db.models import Count
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from debt_app.models import (
    CreditorCriteria,
    CouncilRule,
    CountyCouncil,
    CreditorVoteSummary,
    CreditorVoteChangeEvent,
    CreditorMocAlert,
    CreditorNonAcceptMilestone,
)
from debt_app.helpers import normalise_creditor_name, CREDITOR_ALIAS_MAP


def get_recent_vote_tally(vote_summary):
    """
    Count CreditorVoteChangeEvent rows for vote_summary in the last 30 days
    (by detected_at), grouped by status. Every VOTE_OUTCOME_CHOICES status is
    included as a key, defaulting to 0.
    """
    tally = {status: 0 for status, _label in CreditorVoteSummary.VOTE_OUTCOME_CHOICES}
    cutoff = timezone.now() - timedelta(days=30)
    events = CreditorVoteChangeEvent.objects.filter(
        vote_summary=vote_summary,
        detected_at__gte=cutoff,
    )
    for row in events.values("status").annotate(count=Count("id")):
        tally[row["status"]] = row["count"]
    return tally


def get_last_5_tally(vote_summary):
    """
    Count the 5 most recent CreditorVoteChangeEvent rows for vote_summary,
    grouped by status. Every VOTE_OUTCOME_CHOICES status is included as a key,
    defaulting to 0. A "total" key is included with the actual number of events
    found (up to 5). A "sequence" key holds those same statuses ordered
    newest-first (may be fewer than 5 if the creditor has fewer votes).
    """
    statuses = list(
        CreditorVoteChangeEvent.objects.filter(vote_summary=vote_summary)
        .order_by("-detected_at", "-id")[:5]
        .values_list("status", flat=True)
    )
    tally = {status: 0 for status, _label in CreditorVoteSummary.VOTE_OUTCOME_CHOICES}
    tally["total"] = len(statuses)
    tally["sequence"] = statuses
    for status in statuses:
        tally[status] += 1
    return tally



def resolve_vote_summary_creditor(vote_summary):
    """
    Resolve a CreditorVoteSummary to (creditor_name, creditor_criteria_or_None),
    using the same three-way creditor_criteria/council_rule/county_council
    resolution as CrmSyncRunCreditorBreakdownView
    (debt_app/views/criteria_views.py) - exactly one of the three FKs is set
    per Prompt 5. Returns creditor_criteria (not None) only when the
    vote_summary is backed by a CreditorCriteria, since only that model has
    the representative/dividend fields get_creditor_tags() needs.
    """
    if vote_summary.creditor_criteria:
        return vote_summary.creditor_criteria.creditor_name, vote_summary.creditor_criteria
    if vote_summary.council_rule:
        return vote_summary.council_rule.council_name, None
    if vote_summary.county_council:
        return vote_summary.county_council.county_name, None
    return None, None


def get_creditor_tags(creditor_criteria):
    """
    Return the list of display tags ("Representative-tagged", "Dividend
    creditor") for a CreditorCriteria instance. Only call this with an actual
    CreditorCriteria - CouncilRule/CountyCouncil don't have the
    representative/dividend fields this checks, so summaries backed by those
    models simply get no tags (see resolve_vote_summary_creditor()).
    """
    tags = []
    if creditor_criteria.representative != "NONE":
        tags.append("Representative-tagged")
    if (
        creditor_criteria.min_dividend_pence is not None
        or (creditor_criteria.dividend_notes and creditor_criteria.dividend_notes.strip())
        or creditor_criteria.source_sheet == "DIVIDEND"
    ):
        tags.append("Dividend creditor")
    return tags


def extract_tie_segments(name):
    segments = []

    for part in re.split(r"\s+t/a\s+|\s+trading as\s+", name, flags=re.IGNORECASE):
        segments.append(part)

    for part in re.split(r"\s+c/o\s+", name, flags=re.IGNORECASE):
        segments.append(part)

    for part in re.split(r"\bformerly\b", name, flags=re.IGNORECASE):
        segments.append(part)

    for m in re.finditer(r"\(([^)]+)\)", name):
        segments.append(m.group(1))
    no_paren = re.sub(r"\s*\([^)]*\)", "", name).strip()
    if no_paren:
        segments.append(no_paren)

    for part in re.split(r"\s+/\s+", name):
        segments.append(part)

    cleaned = []
    for s in segments:
        s = s.strip()
        if s and len(s) >= 3:
            cleaned.append(s)
    return cleaned


def key_of(s):
    return s.strip().lower()


def strip_county_council_suffix(name):
    s = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    s = re.sub(r"\s+county council$", "", s, flags=re.IGNORECASE).strip()
    return s


def _fetch_crm_vote_data(log=print, set_stage=None):
    """
    Fetch CRM vote data and return a tuple (result, crm_rows_fetched) where
    result is a structured dictionary mapping creditor names (for all 3 types)
    to their vote summary data, and crm_rows_fetched is the number of
    aggregate CRM rows returned by the CRM query.
    """
    log("Fetching CRM vote data...")
    if set_stage:
        set_stage("Connecting to CRM")

    # Step 1: Fetch aggregate vote counts per creditor
    cursor = connections["aryza"].cursor()
    cursor.execute("SET SESSION MAX_EXECUTION_TIME=600000")

    if set_stage:
        set_stage("Fetching aggregate vote counts")

    cursor.execute("""
        SELECT
            c.id,
            c.name,
            SUM(CASE WHEN mra.first_vote = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
            SUM(CASE WHEN mra.first_vote = 'accepted' THEN 1 ELSE 0 END) AS accepted_count,
            SUM(CASE WHEN mra.first_vote = 'modified' THEN 1 ELSE 0 END) AS modified_count,
            SUM(CASE WHEN mra.first_vote = 'pod' THEN 1 ELSE 0 END) AS pod_count,
            SUM(CASE WHEN mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod') THEN 1 ELSE 0 END) AS total_votes
        FROM theinsolvencygroup.iva_client_meeting_attendee mra
        INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
        INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
        WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
          AND mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod')
        GROUP BY c.id, c.name
    """)

    crm_aggregate = {}
    for crm_id, name, rejected_count, accepted_count, modified_count, pod_count, total_votes in cursor.fetchall():
        crm_aggregate[crm_id] = {
            "crm_id": crm_id,
            "name": name,
            # MySQL returns SUM(CASE WHEN ... THEN 1 ELSE 0 END) as decimal.Decimal,
            # not int - cast here so every downstream consumer (including the
            # range(delta) in _sync_vote_summary) gets a plain int.
            "accepted_count": int(accepted_count),
            "rejected_count": int(rejected_count),
            "modified_count": int(modified_count),
            "pod_count": int(pod_count),
            "total_votes": int(total_votes),
        }

    # Step 2: Fetch only the LATEST vote per creditor (not full history — the previous
    # version fetched every individual vote row ever cast and sorted in Python, which
    # meant transferring the entire vote history on every single sync run. A window
    # function pushes the "latest per creditor" computation into MySQL so we only ever
    # transfer one row per creditor.
    if set_stage:
        set_stage("Fetching latest vote per creditor")

    cursor.execute("""
        SELECT id, meeting_date, first_vote
        FROM (
            SELECT
                c.id AS id,
                m.meeting_date AS meeting_date,
                mra.first_vote AS first_vote,
                ROW_NUMBER() OVER (PARTITION BY c.id ORDER BY m.meeting_date DESC) AS rn
            FROM theinsolvencygroup.iva_client_meeting_attendee mra
            INNER JOIN theinsolvencygroup.iva_client_debt cd ON cd.id = mra.attendee_id
            INNER JOIN theinsolvencygroup.creditor c ON c.id = cd.creditorid
            INNER JOIN theinsolvencygroup.iva_client_meeting m ON m.id = mra.iva_client_meeting_id
            WHERE mra.attendee_type IN ('creditor', 'associate_creditor')
              AND mra.first_vote IN ('accepted', 'rejected', 'modified', 'pod')
        ) ranked
        WHERE rn = 1
    """)

    crm_vote_rows_by_id = {crm_id: {**data, "vote_rows": []} for crm_id, data in crm_aggregate.items()}
    for crm_id, meeting_date_ts, first_vote in cursor.fetchall():
        if crm_id in crm_vote_rows_by_id and meeting_date_ts and first_vote:
            try:
                meeting_date = datetime.fromtimestamp(meeting_date_ts).date()
            except (ValueError, TypeError, OverflowError):
                meeting_date = None
            crm_vote_rows_by_id[crm_id]["vote_rows"].append({
                "meeting_date": meeting_date,
                "first_vote": first_vote
            })
    crm_rows = list(crm_vote_rows_by_id.values())
    crm_rows_fetched = len(crm_rows)

    # Step 3: Build CRM indexes for O(1) lookups
    if set_stage:
        set_stage("Matching creditor names")

    crm_exact_index = {}
    crm_norm_index = {}
    crm_tie_index = {}
    crm_alias_index = {}
    crm_county_suffix_index = {}
    crm_by_id = {r["crm_id"]: r for r in crm_rows}

    for row in crm_rows:
        ek = key_of(row["name"])
        crm_exact_index.setdefault(ek, []).append(row)

        nk = normalise_creditor_name(row["name"])
        if nk:
            crm_norm_index.setdefault(nk, []).append(row)

        for seg in extract_tie_segments(row["name"]):
            sk = key_of(seg)
            if sk == ek:
                continue
            crm_tie_index.setdefault(sk, []).append(row)

        alias_target = CREDITOR_ALIAS_MAP.get(nk)
        if alias_target:
            crm_alias_index.setdefault(key_of(alias_target), []).append(row)

        stripped = strip_county_council_suffix(row["name"])
        if stripped and key_of(stripped) != ek:
            crm_county_suffix_index.setdefault(key_of(stripped), []).append(row)

    # Step 4: Prepare result structure
    result = {
        "creditor_criteria": {},
        "council_rule": {},
        "county_council": {},
    }

    # Helper to process a local creditor and get matched CRM creditors
    def process_local(name, is_county_council=False):
        ek = key_of(name)
        nk = normalise_creditor_name(name)

        hits = {}
        for r in crm_exact_index.get(ek, []):
            hits[r["crm_id"]] = True
        if nk:
            for r in crm_norm_index.get(nk, []):
                hits[r["crm_id"]] = True
        for r in crm_alias_index.get(ek, []):
            hits[r["crm_id"]] = True
        for r in crm_tie_index.get(ek, []):
            hits[r["crm_id"]] = True
        if is_county_council:
            for r in crm_county_suffix_index.get(ek, []):
                hits[r["crm_id"]] = True
        matched_ids = list(hits.keys())
        if not matched_ids:
            return None
        matched_crm = [crm_by_id[cid] for cid in matched_ids]

        total_votes = 0
        accepted_count = 0
        rejected_count = 0
        modified_count = 0
        pod_count = 0
        all_vote_rows = []
        for crm in matched_crm:
            total_votes += crm["total_votes"]
            accepted_count += crm["accepted_count"]
            rejected_count += crm["rejected_count"]
            modified_count += crm["modified_count"]
            pod_count += crm["pod_count"]
            all_vote_rows.extend(crm["vote_rows"])

        # Find latest vote
        latest_vote_date = None
        latest_vote_outcome = None
        if all_vote_rows:
            # Sort by meeting_date descending (handle possible None dates)
            sorted_votes = sorted(all_vote_rows, key=lambda x: (x["meeting_date"] is None, x["meeting_date"]), reverse=True)
            latest = sorted_votes[0]
            latest_vote_date = latest["meeting_date"]
            latest_vote_outcome = latest["first_vote"]

        # For creditors matched to more than one CRM row (representative bodies
        # like WATCH/TIX/EVOLVE aggregate hundreds of underlying real creditors),
        # all_vote_rows holds one real meeting_date per underlying row - i.e. real
        # per-vote chronology, not just an aggregate count. Record each status's
        # own real latest date here so _sync_vote_summary can stamp new
        # CreditorVoteChangeEvent rows with the vote's actual date instead of
        # "whenever this sync happened to run". Without this, a rejected vote
        # detected in an earlier sync and an unrelated modified vote (for a
        # different underlying creditor under the same representative) merely
        # noticed in today's sync would tie-break on sync time, not real vote
        # date - producing a last_5_tally that contradicts latest_vote_outcome.
        latest_date_by_status = {}
        for row in all_vote_rows:
            d = row["meeting_date"]
            fv = row["first_vote"]
            if d is not None and (fv not in latest_date_by_status or latest_date_by_status[fv] < d):
                latest_date_by_status[fv] = d

        return {
            "total_votes": total_votes,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "modified_count": modified_count,
            "pod_count": pod_count,
            "latest_vote_date": latest_vote_date,
            "latest_vote_outcome": latest_vote_outcome,
            "latest_date_by_status": latest_date_by_status,
            "crm_rows_covered": len(matched_ids),
        }

    # Process CreditorCriteria
    log("Processing CreditorCriteria...")
    for creditor in CreditorCriteria.objects.filter(is_active=True):
        summary = process_local(creditor.creditor_name, is_county_council=False)
        if summary:
            result["creditor_criteria"][creditor.creditor_name] = summary

    # Process CouncilRule
    log("Processing CouncilRule...")
    for council in CouncilRule.objects.all():
        summary = process_local(council.council_name, is_county_council=False)
        if summary:
            result["council_rule"][council.council_name] = summary

    # Process CountyCouncil
    log("Processing CountyCouncil...")
    for county in CountyCouncil.objects.all():
        summary = process_local(county.county_name, is_county_council=True)
        if summary:
            result["county_council"][county.county_name] = summary

    log("CRM vote data fetched successfully!")
    return result, crm_rows_fetched


def _log_change(log_file, creditor_type, creditor_name, old_values, new_values):
    """Write a change entry to the audit log file."""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {creditor_type} - {creditor_name}\n")
        f.write(f"  OLD: {old_values}\n")
        f.write(f"  NEW: {new_values}\n")
        f.write("---\n")


def _sync_vote_summary(creditor_type, creditor_obj, vote_data, dry_run, log_file, log=print, run=None):
    """
    Create or update a CreditorVoteSummary record for the given creditor object.
    Returns a tuple (created: bool, updated: bool).
    """
    # Get the existing summary if it exists
    lookup_kwargs = {creditor_type: creditor_obj}
    summary, created = CreditorVoteSummary.objects.get_or_create(**lookup_kwargs)

    # Prepare old values for logging/dry-run
    old_values = {
        "total_votes": summary.total_votes,
        "accepted_count": summary.accepted_count,
        "rejected_count": summary.rejected_count,
        "modified_count": summary.modified_count,
        "pod_count": summary.pod_count,
        "latest_vote_date": summary.latest_vote_date,
        "latest_vote_outcome": summary.latest_vote_outcome,
        "crm_rows_covered": summary.crm_rows_covered,
    }

    # Prepare new values from vote_data
    new_values = {
        "total_votes": vote_data.get("total_votes", 0),
        "accepted_count": vote_data.get("accepted_count"),
        "rejected_count": vote_data.get("rejected_count"),
        "modified_count": vote_data.get("modified_count"),
        "pod_count": vote_data.get("pod_count"),
        "latest_vote_date": vote_data.get("latest_vote_date"),
        "latest_vote_outcome": vote_data.get("latest_vote_outcome"),
        "crm_rows_covered": vote_data.get("crm_rows_covered", 1),
    }

    # Compute per-status vote deltas and prepare CreditorVoteChangeEvent rows
    # for any status whose count increased. Decreases/corrections (delta <= 0)
    # are not logged as vote activity.
    #
    # Skip this entirely on the summary's first-ever sync (created=True): old_values
    # are all zero/defaults there, so every existing vote the creditor already has
    # would be misread as a fresh "delta" and bulk-created as synthetic change events.
    # Only genuine incremental deltas on later syncs represent real observed vote
    # transitions worth logging.
    #
    # Representative creditors (WATCH/TIX/EVOLVE) aggregate hundreds of underlying
    # real creditors, so a single sync run routinely finds several statuses each
    # gaining votes at once - e.g. a rejected vote for underlying creditor A and a
    # modified vote for underlying creditor B, discovered in the same run despite
    # having completely unrelated real meeting dates. If left at auto_now_add's
    # sync-wall-clock timestamp, get_last_5_tally()'s -detected_at ordering reflects
    # "when our sync noticed it", not real vote chronology - producing a tally that
    # can contradict latest_vote_outcome (which IS computed from real meeting_date).
    # vote_data["latest_date_by_status"] carries each status's own real latest
    # meeting_date (see process_local() above), so after creating this run's events
    # each status's batch gets re-stamped with a real-date-derived detected_at
    # below, making cross-run ordering reflect actual vote chronology instead of
    # detection time. As a fallback for statuses with no known date, the status
    # matching this run's confirmed latest_vote_outcome is still inserted last so
    # it wins same-instant ties.
    latest_status = new_values.get("latest_vote_outcome")
    ordered_statuses = sorted(
        (status_value for status_value, _label in CreditorVoteSummary.VOTE_OUTCOME_CHOICES),
        key=lambda status_value: status_value == latest_status,
    )
    latest_date_by_status = vote_data.get("latest_date_by_status") or {}

    events_to_create = []
    statuses_with_new_events = set()
    if not created:
        for status_value in ordered_statuses:
            count_field = f"{status_value}_count"
            old_count = old_values[count_field] or 0
            new_count = new_values[count_field] or 0
            delta = new_count - old_count
            if delta > 0:
                events_to_create.extend(
                    CreditorVoteChangeEvent(vote_summary=summary, sync_run=run, status=status_value)
                    for _ in range(delta)
                )
                statuses_with_new_events.add(status_value)

    # Check if changes are needed
    changes = {}
    for key, old_val in old_values.items():
        new_val = new_values[key]
        if old_val != new_val:
            changes[key] = (old_val, new_val)

    creditor_name = str(creditor_obj)
    updated = False
    if changes:
        # Log/dry-run output
        if dry_run:
            log(f"  [DRY-RUN] Would update {creditor_type}: {creditor_name}")
            for key, (old, new) in changes.items():
                log(f"    {key}: {old} -> {new}")
            if events_to_create:
                log(f"  [DRY-RUN] Would create {len(events_to_create)} CreditorVoteChangeEvent row(s) for {creditor_name}")
        else:
            # Update the summary
            for key, value in new_values.items():
                setattr(summary, key, value)
            summary.save()
            if events_to_create:
                if run is None:
                    raise ValueError(
                        f"Cannot create CreditorVoteChangeEvent rows for {creditor_name}: "
                        f"sync_run is required but run=None was passed to _sync_vote_summary()"
                    )
                CreditorVoteChangeEvent.objects.bulk_create(events_to_create)
                # auto_now_add stamps every row above with this call's wall-clock
                # instant regardless of what was set on the unsaved objects - so
                # re-stamp per status afterwards using its real meeting_date where
                # known. Scoping by (vote_summary, sync_run, status) safely selects
                # only the rows just created above: sync_run is unique to this one
                # run, and this function only creates events for `summary` once
                # per run, so no earlier historical row can match this triple.
                for status_value in statuses_with_new_events:
                    real_date = latest_date_by_status.get(status_value)
                    if real_date:
                        stamped_dt = timezone.make_aware(datetime.combine(real_date, time_of_day(12, 0)))
                        CreditorVoteChangeEvent.objects.filter(
                            vote_summary=summary, sync_run=run, status=status_value
                        ).update(detected_at=stamped_dt)
            _log_change(log_file, creditor_type, creditor_name, old_values, new_values)
            log(f"  Updated {creditor_type}: {creditor_name}")
            updated = True
    elif created:
        # New record created with default values
        if dry_run:
            log(f"  [DRY-RUN] Would create {creditor_type}: {creditor_name}")
        else:
            _log_change(log_file, creditor_type, creditor_name, {}, new_values)
            log(f"  Created {creditor_type}: {creditor_name}")
    else:
        # No changes needed
        log(f"  No changes for {creditor_type}: {creditor_name}")

    return created, updated


def _sync_creditor_criteria(crm_data, dry_run, log_file, log=print, run=None):
    """Sync CreditorVoteSummary for CreditorCriteria records. Returns (created_count, updated_count)."""
    created_count = 0
    updated_count = 0
    for name, vote_data in crm_data.get("creditor_criteria", {}).items():
        try:
            creditor = CreditorCriteria.objects.get(creditor_name=name)
            created, updated = _sync_vote_summary(
                creditor_type="creditor_criteria",
                creditor_obj=creditor,
                vote_data=vote_data,
                dry_run=dry_run,
                log_file=log_file,
                log=log,
                run=run,
            )
            if created:
                created_count += 1
            if updated:
                updated_count += 1
        except CreditorCriteria.DoesNotExist:
            log(f"CreditorCriteria not found: {name}")
            continue
    return created_count, updated_count


def _sync_council_rules(crm_data, dry_run, log_file, log=print, run=None):
    """Sync CreditorVoteSummary for CouncilRule records. Returns (created_count, updated_count)."""
    created_count = 0
    updated_count = 0
    for name, vote_data in crm_data.get("council_rule", {}).items():
        try:
            council = CouncilRule.objects.get(council_name=name)
            created, updated = _sync_vote_summary(
                creditor_type="council_rule",
                creditor_obj=council,
                vote_data=vote_data,
                dry_run=dry_run,
                log_file=log_file,
                log=log,
                run=run,
            )
            if created:
                created_count += 1
            if updated:
                updated_count += 1
        except CouncilRule.DoesNotExist:
            log(f"CouncilRule not found: {name}")
            continue
    return created_count, updated_count


def _sync_county_councils(crm_data, dry_run, log_file, log=print, run=None):
    """Sync CreditorVoteSummary for CountyCouncil records. Returns (created_count, updated_count)."""
    created_count = 0
    updated_count = 0
    for name, vote_data in crm_data.get("county_council", {}).items():
        try:
            county = CountyCouncil.objects.get(county_name=name)
            created, updated = _sync_vote_summary(
                creditor_type="county_council",
                creditor_obj=county,
                vote_data=vote_data,
                dry_run=dry_run,
                log_file=log_file,
                log=log,
                run=run,
            )
            if created:
                created_count += 1
            if updated:
                updated_count += 1
        except CountyCouncil.DoesNotExist:
            log(f"CountyCouncil not found: {name}")
            continue
    return created_count, updated_count


def _send_moc_alert_email(newly_alerted):
    """
    Send a single batched email listing every CreditorMocAlert created this
    run - one email per run, not one per creditor, so a run with many vote
    changes doesn't spam MOC_ALERT_RECIPIENTS. No existing email-sending
    convention was found in this codebase (no send_mail/EmailMultiAlternatives/
    django.core.mail usage anywhere else), so this uses Django's built-in
    send_mail directly with the Prompt 8 settings.
    """
    vote_summary_ids = [alert.vote_summary_id for alert in newly_alerted]
    summaries_by_id = {
        s.id: s
        for s in CreditorVoteSummary.objects.filter(id__in=vote_summary_ids).select_related(
            "creditor_criteria", "council_rule", "county_council"
        )
    }

    lines = []
    for alert in newly_alerted:
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

    subject = f"MOC Alert: {len(lines)} creditor(s) with new vote activity"
    body = (
        "The following creditors had new vote activity in the latest CRM sync:\n\n"
        + "\n".join(lines)
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.MOC_ALERT_FROM_EMAIL,
        recipient_list=settings.MOC_ALERT_RECIPIENTS,
    )


def check_and_send_moc_alerts(run):
    """
    Find every vote_summary that got at least one CreditorVoteChangeEvent
    during this sync run and make sure it has a CreditorMocAlert for today
    (Europe/London calendar day).

    "Needs an alert" = has at least one CreditorVoteChangeEvent with
    sync_run=run. _sync_vote_summary() only ever creates an event when a
    status count *increased* during this run, so any event at all already
    means genuine new vote activity for that creditor - no extra threshold
    or business rule is introduced here.

    The unique constraint 'unique_moc_alert_per_creditor_per_day' on
    (vote_summary, alert_date) is the "already alerted today" check: we
    attempt the create for every affected vote_summary and let IntegrityError
    tell us it already happened, rather than running a .filter()/.exists()
    check first, which would leave a race window between the check and the
    create if two sync runs ever overlapped.

    Returns the list of newly-created CreditorMocAlert instances (i.e. the
    ones that were NOT already alerted today) - Prompt 10b will use this list
    to send emails.
    """
    events = CreditorVoteChangeEvent.objects.filter(sync_run=run).order_by("detected_at")

    # A vote_summary can have several events this run (one per status that
    # incremented). Record the earliest event's status per vote_summary just
    # for traceability on the alert row; it doesn't change which vote
    # summaries are considered "needing an alert" - that's any vote_summary
    # with >=1 event.
    status_by_summary_id = {}
    for event in events:
        status_by_summary_id.setdefault(event.vote_summary_id, event.status)

    if not status_by_summary_id:
        return []

    # timezone.now().date() would return the UTC calendar date. Europe/London
    # is UTC+1 during BST, so any sync that runs late evening BST (e.g.
    # 23:30 local / 22:30 UTC is fine, but 00:30 local / 23:30 UTC the
    # previous UTC day) would compute the wrong alert_date, either letting a
    # second alert through for what should be "today" or wrongly blocking one.
    # localtime() converts to the active Europe/London time first so the date
    # always matches the calendar day site users actually experience.
    alert_date = timezone.localtime(timezone.now()).date()

    newly_alerted = []
    for vote_summary_id, status in status_by_summary_id.items():
        if run.dry_run:
            continue
        try:
            alert = CreditorMocAlert.objects.create(
                vote_summary_id=vote_summary_id,
                alert_date=alert_date,
                triggered_by_status=status,
            )
            newly_alerted.append(alert)
        except IntegrityError:
            # Already alerted for this vote_summary today - expected/normal, not an error.
            continue

    if newly_alerted:
        _send_moc_alert_email(newly_alerted)

    return newly_alerted


def _send_non_accept_milestone_email(newly_created_milestones):
    """
    Send a single batched email listing every CreditorNonAcceptMilestone created this
    run. Reuses the MOC_ALERT_RECIPIENTS and settings.MOC_ALERT_FROM_EMAIL.
    """
    if not newly_created_milestones:
        return

    vote_summary_ids = [m.vote_summary_id for m in newly_created_milestones]
    summaries_by_id = {
        s.id: s
        for s in CreditorVoteSummary.objects.filter(id__in=vote_summary_ids).select_related(
            "creditor_criteria", "council_rule", "county_council"
        )
    }

    lines = []
    for milestone in newly_created_milestones:
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

        sentence = f"This creditor has achieved 3 {milestone.status} between {first_event_str} and {third_event_str}"
        line += f"\n  {sentence}"
        lines.append(line)

    subject = f"MOC Milestone Alert: {len(lines)} creditor(s) reached non-accept thresholds"
    body = (
        "The following creditors reached the non-accept threshold milestone (3+ non-accepted votes in a single London day):\n\n"
        + "\n\n".join(lines)
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.MOC_ALERT_FROM_EMAIL,
        recipient_list=settings.MOC_ALERT_RECIPIENTS,
    )


def check_and_send_non_accept_milestones(run, log=None):
    """
    Check non-accept milestones for all creditors that received a new
    CreditorVoteChangeEvent this run, and send a separate notification email if
    any new milestones were created.
    """
    from debt_app.views.criteria_views import check_non_accept_milestone

    events = CreditorVoteChangeEvent.objects.filter(sync_run=run)
    vote_summary_ids = set(events.values_list("vote_summary_id", flat=True))

    if not vote_summary_ids:
        return []

    newly_created_milestones = []
    vote_summaries = CreditorVoteSummary.objects.filter(id__in=vote_summary_ids)

    for summary in vote_summaries:
        try:
            milestones = check_non_accept_milestone(summary, run)
            newly_created_milestones.extend(milestones)
        except Exception as e:
            # Print to stdout/log with enough context
            msg = f"Error checking milestone for vote_summary_id={summary.id} in sync_run_id={run.id}: {e}"
            if log:
                log(msg)
            else:
                print(msg)

    if newly_created_milestones:
        _send_non_accept_milestone_email(newly_created_milestones)

    return newly_created_milestones


def run_crm_vote_sync(run=None, dry_run=False, log_file=None):
    """
    Runs the CRM -> CreditorVoteSummary sync end-to-end.

    run: optional CrmSyncRun instance to update with live progress (stage, counts)
         as the sync proceeds.
    Returns a summary dict: {crm_rows_fetched, records_created, records_updated,
         creditor_criteria_count, council_rule_count, county_council_count}
    Raises on failure (caller is responsible for catching and marking run as FAILED).
    """
    if log_file is None:
        log_file = os.path.join(settings.BASE_DIR, "creditor_vote_sync.log")

    def set_stage(stage):
        if run is not None:
            run.stage = stage
            run.save(update_fields=["stage"])

    def log(message):
        print(message)

    # Initialize log file
    if not dry_run:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n=== Sync started at {datetime.now().isoformat()} ===\n")

    # Step 1: Fetch CRM vote data
    crm_vote_data, crm_rows_fetched = _fetch_crm_vote_data(log=log, set_stage=set_stage)

    # Step 2: Process and sync data for each creditor type
    with transaction.atomic():
        set_stage("Updating CreditorCriteria records")
        created1, updated1 = _sync_creditor_criteria(crm_vote_data, dry_run, log_file, log=log, run=run)

        set_stage("Updating CouncilRule records")
        created2, updated2 = _sync_council_rules(crm_vote_data, dry_run, log_file, log=log, run=run)

        set_stage("Updating CountyCouncil records")
        created3, updated3 = _sync_county_councils(crm_vote_data, dry_run, log_file, log=log, run=run)

    if run is not None:
        try:
            check_and_send_moc_alerts(run)
        except Exception as e:
            log(f"MOC alert check failed: {e}")

        try:
            check_and_send_non_accept_milestones(run, log=log)
        except Exception as e:
            log(f"Non-accept milestone check failed: {e}")
    else:
        log("Skipping MOC alert check: no CrmSyncRun instance provided")

    set_stage("Done")

    summary = {
        "crm_rows_fetched": crm_rows_fetched,
        "records_created": created1 + created2 + created3,
        "records_updated": updated1 + updated2 + updated3,
        "creditor_criteria_count": len(crm_vote_data.get("creditor_criteria", {})),
        "council_rule_count": len(crm_vote_data.get("council_rule", {})),
        "county_council_count": len(crm_vote_data.get("county_council", {})),
    }

    if run is not None:
        run.crm_rows_fetched = summary["crm_rows_fetched"]
        run.records_created = summary["records_created"]
        run.records_updated = summary["records_updated"]
        run.creditor_criteria_count = summary["creditor_criteria_count"]
        run.council_rule_count = summary["council_rule_count"]
        run.county_council_count = summary["county_council_count"]
        run.save(update_fields=[
            "crm_rows_fetched", "records_created", "records_updated",
            "creditor_criteria_count", "council_rule_count", "county_council_count",
        ])

    log("Sync completed successfully!")
    return summary
