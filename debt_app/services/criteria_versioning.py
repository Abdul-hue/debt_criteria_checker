"""
Controlled criteria changes: Draft -> Trial -> Second-manager sign-off -> Live,
with immutable numbered versions, field-level audit and rollback.

Scope (deliberately narrow — see MANAGED_FIELDS):
  Only DB-held criteria that the engine actually reads and that managers can
  already edit (creditor/council stances, reject flags, dividend minimums,
  blocks, representative mapping, and GlobalCriteria.is_active). Rule logic and
  hard-coded thresholds live in Python (debt_app/engine/criteria.py) and change
  only through code review + deployment; they are identified by `code_version`.

Trial safety:
  A trial NEVER writes to the live database. The live SQLite database is copied
  with SQLite's online-backup API to a temporary file, the proposed change is
  applied to that copy, and the engine is run against the copy through a
  context-local DB router (debt_app.db_router). Other requests/threads keep
  using the live database. Non-SQLite databases are refused rather than trialled
  unsafely.
"""

import contextlib
import datetime
import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import tempfile
import uuid
from decimal import Decimal
from functools import lru_cache

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from debt_app.models import (
    CouncilRule,
    CountyCouncil,
    CreditorCriteria,
    CriteriaChangeAudit,
    CriteriaChangeRequest,
    CriteriaDecision,
    CriteriaVersion,
    GlobalCriteria,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Managed scope
# ---------------------------------------------------------------------------

MANAGED_MODELS = {
    "CreditorCriteria": CreditorCriteria,
    "CouncilRule": CouncilRule,
    "CountyCouncil": CountyCouncil,
    "GlobalCriteria": GlobalCriteria,
}

# Decision-driving fields only. Identity (names), free-text notes, contact
# details and audit columns are excluded: they don't change outcomes and
# remain editable through the existing screens.
MANAGED_FIELDS = {
    "CreditorCriteria": [
        "trading_names", "representative", "status", "min_dividend_pence", "is_active",
        "account_age_months", "reject_if_recent_spend_months", "parent_group",
        "reject_if_in_dmp", "reject_if_never_made_payment", "reject_if_ie_doesnt_match_application",
        "reject_if_debt_repayable_within_months", "reject_if_client_still_has_asset",
        "reject_if_majority_share_exceeds_pct", "reject_if_second_iva", "reject_if_police_employed",
        "reject_if_equity_exceeds_debt", "reject_if_ccj", "reject_if_aoe",
        "requires_pg_called_up", "requires_arrangement_call_before_proposing",
        "requires_grant_overpayment_only", "vehicle_arrears_repossession_months",
        "fees_cap_percentage", "min_di_for_fees_pence", "termination_risk_if_vehicle_on_finance",
        "conditional_voter", "conditional_voter_min_dividend_pence", "open_banking_access",
        "requires_credit_report", "fraud_claim_risk", "blocked_until_cleared", "blocked_reason",
    ],
    "CouncilRule": [
        "status", "min_dividend_pence", "reject_if_employed", "reject_if_unemployed_and_homeowner",
        "reject_if_benefits_only", "reject_if_any_benefits", "reject_if_previous_iva",
        "reject_if_dro_criteria_met", "reject_if_aoe_in_place", "reject_if_joint_one_party_only",
        "reject_if_joint_both_parties", "reject_if_sole", "reject_if_joint_one_employed",
        "do_not_chase", "include_current_year_ct", "blocked_reason", "source_priority",
    ],
    "CountyCouncil": ["status", "deals_with_council_tax", "min_dividend_pence", "blocked_reason"],
    # threshold_value / severity are code-managed (RulesDetailView rejects
    # edits to them); only the on/off switch is read by the engine.
    "GlobalCriteria": ["is_active"],
}

LABEL_FIELD = {
    "CreditorCriteria": "creditor_name",
    "CouncilRule": "council_name",
    "CountyCouncil": "county_name",
    "GlobalCriteria": "rule_key",
}

# A trial runs the engine twice per case (before/after) inside one request.
# Measured on the local DB (2026-10-05): ~0.6s mean, 2.4s max per assessment;
# gunicorn's timeout is 120s (Dockerfile). Keep the worst case inside it.
MAX_TRIAL_CASES = 80
DEFAULT_TRIAL_CASES = 40


class CriteriaChangeError(Exception):
    """A change-control rule was violated (message is user-facing)."""

    def __init__(self, message, code="INVALID", status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Versions / fingerprints
# ---------------------------------------------------------------------------

def _json_value(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


def snapshot_managed_criteria(using=None):
    """{model: {str(pk): {field: value}}} for every managed row (JSON-safe)."""
    snap = {}
    for name, model in MANAGED_MODELS.items():
        qs = model.objects.using(using) if using else model.objects
        rows = qs.order_by("pk").values("pk", *MANAGED_FIELDS[name])
        snap[name] = {
            str(r["pk"]): {f: _json_value(r[f]) for f in MANAGED_FIELDS[name]} for r in rows
        }
    return snap


def fingerprint(snapshot):
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def live_fingerprint():
    return fingerprint(snapshot_managed_criteria())


@lru_cache(maxsize=1)
def get_code_version():
    """Deployed code identifier: APP_CODE_VERSION env/setting, else the local
    git SHA when a checkout is present, else 'unknown'. (The Docker image
    excludes .git, so deployments should set APP_CODE_VERSION.)"""
    configured = getattr(settings, "APP_CODE_VERSION", "") or os.environ.get("APP_CODE_VERSION", "")
    if configured:
        return configured[:64]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=str(settings.BASE_DIR), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return f"git:{out.stdout.strip()}"
    except Exception:
        pass
    return "unknown"


def current_criteria_version():
    """(label, live_fingerprint) for recording against a decision.

    label is "v<N>" when live criteria match the latest approved version,
    "v<N>+unapproved-changes" when they have been edited outside the
    controlled workflow since, and "unversioned" before any version exists.
    """
    fp = live_fingerprint()
    latest = CriteriaVersion.objects.order_by("-number").first()
    if latest is None:
        return "unversioned", fp
    if latest.fingerprint == fp:
        return latest.label, fp
    return f"{latest.label}+unapproved-changes", fp


# ---------------------------------------------------------------------------
# Draft
# ---------------------------------------------------------------------------

def managed_field_info():
    """{model: {field: {"type", "choices", "nullable"}}} so the UI can offer the
    exact allowed values (e.g. representative WATCH/TIX/...) instead of free text."""
    info = {}
    for model_name, fields in MANAGED_FIELDS.items():
        model = MANAGED_MODELS[model_name]
        info[model_name] = {}
        for name in fields:
            f = model._meta.get_field(name)
            info[model_name][name] = {
                "type": f.get_internal_type(),
                "choices": [[c[0], str(c[1])] for c in f.choices] if f.choices else None,
                "nullable": bool(f.null),
            }
    return info


def _coerce(model_name, field_name, value):
    """Validate/convert a proposed value with the model field's own rules."""
    field = MANAGED_MODELS[model_name]._meta.get_field(field_name)
    from django.core.exceptions import ValidationError
    if field.choices and isinstance(value, str):
        # Accept a choice typed in a different case ("watch") as the exact
        # stored value ("WATCH"); anything else still fails validation below.
        matches = [c[0] for c in field.choices if isinstance(c[0], str) and c[0].lower() == value.strip().lower()]
        if len(matches) == 1:
            value = matches[0]
    try:
        python_value = field.to_python(value)
        if python_value is None and not field.null:
            raise ValidationError("This field cannot be empty.")
        if field.choices and python_value not in {c[0] for c in field.choices} and not (
            python_value in (None, "") and field.blank
        ):
            raise ValidationError(f"{python_value!r} is not a valid choice.")
        field.run_validators(python_value) if python_value is not None else None
    except ValidationError as exc:
        raise CriteriaChangeError(
            f"{model_name}.{field_name}: {'; '.join(exc.messages)}", code="INVALID_VALUE",
        )
    return _json_value(python_value)


def build_items(raw_items):
    """Validate proposed items and capture each row's current (old) value."""
    if not raw_items:
        raise CriteriaChangeError("At least one change is required.", code="NO_CHANGES")
    items, seen = [], set()
    for raw in raw_items:
        model_name = raw.get("model")
        field_name = raw.get("field")
        object_id = raw.get("object_id")
        if model_name not in MANAGED_MODELS:
            raise CriteriaChangeError(f"{model_name!r} is not a managed criteria table.", code="NOT_MANAGED")
        if field_name not in MANAGED_FIELDS[model_name]:
            raise CriteriaChangeError(
                f"{model_name}.{field_name} is not manager-configurable through this workflow "
                "(rule logic and thresholds are code-managed).",
                code="NOT_MANAGED",
            )
        try:
            obj = MANAGED_MODELS[model_name].objects.get(pk=object_id)
        except (MANAGED_MODELS[model_name].DoesNotExist, ValueError, TypeError):
            raise CriteriaChangeError(f"{model_name} #{object_id} does not exist.", code="NOT_FOUND", status_code=404)
        key = (model_name, obj.pk, field_name)
        if key in seen:
            raise CriteriaChangeError(f"{model_name} #{obj.pk} {field_name} is listed twice.", code="DUPLICATE")
        seen.add(key)
        old_value = _json_value(getattr(obj, field_name))
        new_value = _coerce(model_name, field_name, raw.get("new_value"))
        if old_value == new_value:
            raise CriteriaChangeError(
                f"{model_name} #{obj.pk} {field_name} already has that value.", code="NO_CHANGE",
            )
        items.append({
            "model": model_name,
            "object_id": obj.pk,
            "object_label": str(getattr(obj, LABEL_FIELD[model_name])),
            "field": field_name,
            "old_value": old_value,
            "new_value": new_value,
        })
    return items


def create_change_request(user, title, reason, raw_items):
    if not (title or "").strip():
        raise CriteriaChangeError("A title is required.", code="TITLE_REQUIRED")
    if not (reason or "").strip():
        raise CriteriaChangeError("A reason is required.", code="REASON_REQUIRED")
    return CriteriaChangeRequest.objects.create(
        title=title.strip(), reason=reason.strip(), items=build_items(raw_items), created_by=user,
    )


def create_rollback_request(user, version_number, reason):
    """Draft a change that restores the managed fields of an earlier version.
    Goes through the same trial + sign-off as any other change."""
    try:
        target = CriteriaVersion.objects.get(number=version_number)
    except CriteriaVersion.DoesNotExist:
        raise CriteriaChangeError(f"Criteria version v{version_number} does not exist.", code="NOT_FOUND", status_code=404)
    if not (reason or "").strip():
        raise CriteriaChangeError("A reason is required.", code="REASON_REQUIRED")
    current = snapshot_managed_criteria()
    raw_items = []
    for model_name, rows in target.snapshot.items():
        if model_name not in MANAGED_MODELS:
            continue
        for pk, fields in rows.items():
            live_row = current.get(model_name, {}).get(pk)
            if live_row is None:
                continue  # row deleted since — cannot be restored by this workflow
            for field_name, value in fields.items():
                if field_name in MANAGED_FIELDS[model_name] and live_row.get(field_name) != value:
                    raw_items.append({"model": model_name, "object_id": int(pk), "field": field_name, "new_value": value})
    if not raw_items:
        raise CriteriaChangeError(f"Live criteria already match v{version_number}.", code="NO_CHANGES")
    return CriteriaChangeRequest.objects.create(
        title=f"Roll back to v{version_number}", reason=reason.strip(), items=build_items(raw_items),
        created_by=user, is_rollback=True, rollback_to_version=target,
    )


def cancel_change_request(change, user):
    if change.status not in (CriteriaChangeRequest.STATUS_DRAFT, CriteriaChangeRequest.STATUS_TRIALLED):
        raise CriteriaChangeError("Only a draft or trialled change can be cancelled.", code="WRONG_STATUS", status_code=409)
    if change.created_by_id != user.pk and not user.is_staff:
        raise CriteriaChangeError("Only the author (or an admin) can cancel this change.", code="FORBIDDEN", status_code=403)
    change.status = CriteriaChangeRequest.STATUS_CANCELLED
    change.decided_by = user
    change.decided_at = timezone.now()
    change.save(update_fields=["status", "decided_by", "decided_at"])
    return change


# ---------------------------------------------------------------------------
# Trial (isolated database copy)
# ---------------------------------------------------------------------------

def _require_sqlite():
    engine = connections["default"].settings_dict["ENGINE"]
    if "sqlite3" not in engine:
        raise CriteriaChangeError(
            "Trials run against an isolated copy of the database, which is only implemented for "
            f"SQLite. The configured database engine ({engine}) is not supported yet — a trial "
            "will not be run against live data.",
            code="TRIAL_UNSUPPORTED_DB", status_code=501,
        )


@contextlib.contextmanager
def isolated_database_copy():
    """Yield a Django DB alias backed by a private copy of the live database.

    Uses sqlite3's online-backup API (consistent copy, short read lock only).
    The connection is attached to the CURRENT THREAD only (it is never added to
    the global DATABASES settings), so no other request can resolve the alias.
    The connection and the temporary file are removed afterwards.
    """
    import copy
    from django.db.utils import load_backend

    _require_sqlite()
    alias = f"criteria_trial_{uuid.uuid4().hex[:12]}"
    fd, path = tempfile.mkstemp(prefix="criteria_trial_", suffix=".sqlite3")
    os.close(fd)
    source = connections["default"]
    source.ensure_connection()
    target = sqlite3.connect(path)
    try:
        source.connection.backup(target)
    finally:
        target.close()
    trial_settings = copy.deepcopy(source.settings_dict)
    trial_settings["NAME"] = path
    wrapper = load_backend(trial_settings["ENGINE"]).DatabaseWrapper(trial_settings, alias)
    connections[alias] = wrapper  # thread-local storage only
    try:
        yield alias
    finally:
        try:
            wrapper.close()
        except Exception:
            pass
        try:
            del connections[alias]
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError:
            logger.warning("[CRITERIA TRIAL] could not remove temp copy %s", path)


def _apply_items_to(alias, items):
    for item in items:
        model = MANAGED_MODELS[item["model"]]
        model.objects.using(alias).filter(pk=item["object_id"]).update(
            **{item["field"]: model._meta.get_field(item["field"]).to_python(item["new_value"])}
        )


def _evaluate_snapshot(case_json):
    """Engine + Lead Gen interpretation for one saved case snapshot."""
    from debt_app.engine.criteria import assess_case
    from debt_app.services.lead_gen import interpret_engine_result

    result = assess_case(json.loads(json.dumps(case_json)))
    rule_titles = dict(GlobalCriteria.objects.values_list("rule_key", "rule_name"))
    lead_gen = interpret_engine_result(
        engine_solution=result.get("recommended_solution"),
        hard_blocks=result.get("hard_blocks", []),
        flags=result.get("flags", []),
        creditor_positions=result.get("creditor_positions", []),
        dmp_eligibility=result.get("dmp_eligibility"),
        documents_supplied=bool(case_json.get("documents")),
        rule_titles=rule_titles,
    )
    return {
        "engine_solution": result.get("recommended_solution"),
        "hard_blocks": sorted({r.rule_id for r in result.get("hard_blocks", [])}),
        "flags": sorted({r.rule_id for r in result.get("flags", [])}),
        "dmp_status": (result.get("dmp_eligibility") or {}).get("status"),
        "lead_gen_overall": lead_gen["overall"]["code"],
        "lead_gen_iva": lead_gen["iva"]["code"],
        "lead_gen_dmp": lead_gen["dmp"]["code"],
    }


def run_trial(change, user, max_cases=DEFAULT_TRIAL_CASES):
    """Run the proposed change against saved case snapshots WITHOUT touching
    live criteria. Records the summary on the change request."""
    from debt_app.db_router import route_to

    if change.status not in (CriteriaChangeRequest.STATUS_DRAFT, CriteriaChangeRequest.STATUS_TRIALLED):
        raise CriteriaChangeError("Only a draft or trialled change can be trialled.", code="WRONG_STATUS", status_code=409)
    _require_sqlite()
    try:
        max_cases = max(1, min(int(max_cases or DEFAULT_TRIAL_CASES), MAX_TRIAL_CASES))
    except (TypeError, ValueError):
        max_cases = DEFAULT_TRIAL_CASES

    live_fp = live_fingerprint()
    _check_items_still_current(change)  # stale draft -> refuse before spending time

    decisions = list(
        CriteriaDecision.objects.order_by("-triggered_at").values("application_id", "input_snapshot")[:max_cases]
    )
    cases, changed, errors = [], [], []
    with isolated_database_copy() as alias:
        with route_to(alias):
            before = {}
            for d in decisions:
                try:
                    before[d["application_id"]] = _evaluate_snapshot(d["input_snapshot"] or {})
                except Exception as exc:
                    errors.append({"aryza_reference": d["application_id"], "error": str(exc)[:200]})
            _apply_items_to(alias, change.items)
            for d in decisions:
                ref = d["application_id"]
                if ref not in before:
                    continue
                try:
                    after = _evaluate_snapshot(d["input_snapshot"] or {})
                except Exception as exc:
                    errors.append({"aryza_reference": ref, "error": str(exc)[:200]})
                    continue
                diff = {k: {"before": before[ref][k], "after": after[k]}
                        for k in before[ref] if before[ref][k] != after[k]}
                cases.append(ref)
                if diff:
                    changed.append({"aryza_reference": ref, "differences": diff})

    # Nothing above wrote to the live database; prove it before recording.
    if live_fingerprint() != live_fp:
        raise CriteriaChangeError(
            "Live criteria changed while the trial was running. Re-run the trial.",
            code="LIVE_CHANGED_DURING_TRIAL", status_code=409,
        )
    summary = {
        "cases_evaluated": len(cases),
        "cases_changed": len(changed),
        "cases_errored": len(errors),
        "case_limit": max_cases,
        "changed": changed,
        "errors": errors,
        "criteria_differences": change.items,
        "source": "Most recent saved CAT assessment snapshot per case (CriteriaDecision.input_snapshot)",
    }
    change.trial_summary = summary
    change.trial_run_by = user
    change.trial_run_at = timezone.now()
    change.trial_live_fingerprint = live_fp
    change.status = CriteriaChangeRequest.STATUS_TRIALLED
    change.save(update_fields=["trial_summary", "trial_run_by", "trial_run_at", "trial_live_fingerprint", "status"])
    return summary


# ---------------------------------------------------------------------------
# Sign-off / Live
# ---------------------------------------------------------------------------

def _check_items_still_current(change):
    for item in change.items:
        model = MANAGED_MODELS[item["model"]]
        obj = model.objects.filter(pk=item["object_id"]).first()
        if obj is None:
            raise CriteriaChangeError(
                f"{item['model']} {item['object_label']} no longer exists.", code="STALE", status_code=409,
            )
        if _json_value(getattr(obj, item["field"])) != item["old_value"]:
            raise CriteriaChangeError(
                f"{item['model']} {item['object_label']} {item['field']} has changed since this draft "
                "was created. Cancel it and create a new change.",
                code="STALE", status_code=409,
            )


def _ensure_baseline_version():
    if CriteriaVersion.objects.exists():
        return
    snap = snapshot_managed_criteria()
    CriteriaVersion.objects.create(
        number=1, note="Baseline — live criteria before the first controlled change",
        snapshot=snap, fingerprint=fingerprint(snap), code_version=get_code_version(),
    )


def approve_and_apply(change, approver, note=""):
    """Second-manager sign-off: apply a trialled change atomically and create
    the next criteria version plus field-level audit rows."""
    if change.status != CriteriaChangeRequest.STATUS_TRIALLED:
        raise CriteriaChangeError("A change must be trialled before it can be approved.", code="NOT_TRIALLED", status_code=409)
    if change.created_by_id == approver.pk:
        raise CriteriaChangeError("You cannot approve your own change. A second manager must sign it off.",
                                  code="SELF_APPROVAL", status_code=403)

    with transaction.atomic():
        change = CriteriaChangeRequest.objects.select_for_update().get(pk=change.pk)
        if change.status != CriteriaChangeRequest.STATUS_TRIALLED:
            raise CriteriaChangeError("This change is no longer awaiting sign-off.", code="WRONG_STATUS", status_code=409)
        if live_fingerprint() != change.trial_live_fingerprint:
            raise CriteriaChangeError(
                "Live criteria have changed since this trial ran. Re-run the trial before approving.",
                code="RETRIAL_REQUIRED", status_code=409,
            )
        _check_items_still_current(change)
        _ensure_baseline_version()

        code_version = get_code_version()
        for item in change.items:
            model = MANAGED_MODELS[item["model"]]
            obj = model.objects.select_for_update().get(pk=item["object_id"])
            setattr(obj, item["field"], model._meta.get_field(item["field"]).to_python(item["new_value"]))
            update_fields = [item["field"]]
            if any(f.name == "updated_by" for f in model._meta.concrete_fields):
                obj.updated_by = approver
                update_fields.append("updated_by")
            obj.save(update_fields=update_fields)

        snap = snapshot_managed_criteria()
        latest = CriteriaVersion.objects.order_by("-number").first()
        version = CriteriaVersion.objects.create(
            number=latest.number + 1,
            created_by=approver,
            change_request=change,
            note=(f"Rollback to v{change.rollback_to_version.number}: " if change.is_rollback else "") + change.title[:200],
            snapshot=snap,
            fingerprint=fingerprint(snap),
            code_version=code_version,
        )
        now = timezone.now()
        for item in change.items:
            CriteriaChangeAudit.objects.create(
                version=version, change_request=change, model=item["model"], object_id=item["object_id"],
                object_label=item["object_label"], field=item["field"], old_value=item["old_value"],
                new_value=item["new_value"], proposed_by=change.created_by, approved_by=approver,
                applied_at=now, code_version=code_version,
            )
        change.status = CriteriaChangeRequest.STATUS_LIVE
        change.decided_by = approver
        change.decided_at = now
        change.decision_note = note or ""
        change.applied_version = version
        change.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "applied_version"])
    return version


def reject_change(change, approver, note=""):
    if change.status not in (CriteriaChangeRequest.STATUS_DRAFT, CriteriaChangeRequest.STATUS_TRIALLED):
        raise CriteriaChangeError("Only a draft or trialled change can be rejected.", code="WRONG_STATUS", status_code=409)
    if change.created_by_id == approver.pk:
        raise CriteriaChangeError("You cannot sign off (approve or reject) your own change.",
                                  code="SELF_APPROVAL", status_code=403)
    if not (note or "").strip():
        raise CriteriaChangeError("A reason is required to reject a change.", code="REASON_REQUIRED")
    change.status = CriteriaChangeRequest.STATUS_REJECTED
    change.decided_by = approver
    change.decided_at = timezone.now()
    change.decision_note = note.strip()
    change.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    return change
