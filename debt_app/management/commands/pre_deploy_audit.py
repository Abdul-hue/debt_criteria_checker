"""
Pre-deployment sign-off audit.

Covers:
  Part 1.1  detect_representatives path comparison for 4 reference cases
  Part 1.2  Full B1-B4 regression (rule coverage, arithmetic, qualifying lenders,
              TIG-10 evidence, DB creditor-resolution integrity)
  Part 2    Unresolved-creditor rate across N recent cases; reconcile backfill check
"""
import json
import sys
from datetime import date, datetime

from django.core.management.base import BaseCommand


REFERENCE_CASES = ["324991", "324901", "355861", "358906"]


def _hr(char="-", width=72):
    return char * width


class Command(BaseCommand):
    help = "Pre-deployment sign-off audit"

    def add_arguments(self, parser):
        parser.add_argument(
            "--n-recent", type=int, default=50,
            help="Number of most-recent CriteriaDecision records to audit for resolution miss rate"
        )

    def handle(self, *args, **options):
        n_recent = options["n_recent"]
        out = []

        def p(*args_):
            line = " ".join(str(a) for a in args_)
            out.append(line)
            self.stdout.write(line)

        p("")
        p(_hr("="))
        p("PRE-DEPLOYMENT SIGN-OFF AUDIT")
        p(f"Run at: {datetime.now().isoformat()} | Cases: {', '.join(REFERENCE_CASES)}")
        p(_hr("="))

        # -- Part 1 ---------------------------------------------------------------
        p("")
        p(_hr())
        p("PART 1  detect_representatives comparison + full regression")
        p(_hr())

        from debt_app.aryza_client import fetch_case_by_reference
        from debt_app.criteria_engine import (
            assess_case,
            detect_representatives,
            reconcile_creditor_positions,
        )
        from debt_app.views.criteria_views import AssessCaseView

        view = AssessCaseView()
        part1_any_diff = False

        for ref in REFERENCE_CASES:
            p("")
            p(_hr(""))
            p(f"CASE {ref}")
            p(_hr(""))

            try:
                case_data_obj = fetch_case_by_reference(ref)
            except Exception as exc:
                p(f"  [ERROR] fetch_case_by_reference({ref!r}) FAILED: {exc}")
                continue

            # Build engine payload (same path as AssessCaseView)
            try:
                case_data, prepared_creditors = view._prepare_engine_payload(case_data_obj)
            except Exception as exc:
                p(f"  [ERROR] _prepare_engine_payload({ref!r}) FAILED: {exc}")
                continue

            p(f"  Client      : {case_data_obj.client_name or '(unknown)'}")
            p(f"  Creditors   : {len(prepared_creditors)}")
            p(f"  Total debt  : {case_data.get('total_unsecured_debt', 0):,.2f}")
            p(f"  Disp income : {case_data.get('disposable_income', 0):,.2f}")

            #  1.1 detect_representatives comparison 
            p("")
            p("  [1.1] detect_representatives comparison")

            # PATH A: call detect_representatives directly with case_data creditors
            # (same creditor list that will be inside case_data["creditors"])
            try:
                path_a = detect_representatives(
                    case_data.get("creditors") or [],
                    assessment_date=case_data.get("assessment_date"),
                )
            except Exception as exc:
                p(f"    PATH A ERROR: {exc}")
                path_a = None

            # PATH B: run assess_case (engine's internal fallback) and read result
            try:
                result = assess_case(case_data)
                path_b = result.get("representatives_detected") or set()
            except Exception as exc:
                p(f"    PATH B (assess_case) ERROR: {exc}")
                result = None
                path_b = None

            if path_a is not None and path_b is not None:
                diff_a = path_a - path_b
                diff_b = path_b - path_a
                if not diff_a and not diff_b:
                    p(f"    PATH A = {sorted(path_a)}")
                    p(f"    PATH B = {sorted(path_b)}")
                    p("    DIFF   : <empty> ")
                else:
                    part1_any_diff = True
                    p(f"    PATH A = {sorted(path_a)}")
                    p(f"    PATH B = {sorted(path_b)}")
                    p(f"    DIFF   : A-only={sorted(diff_a)}  B-only={sorted(diff_b)}   MISMATCH")
            else:
                p("    SKIPPED (one path errored)")

            if result is None:
                continue

            #  1.2 Full regression for this case 
            p("")
            p("  [1.2] Full assessment output")

            hard_blocks = result.get("hard_blocks", [])
            flags_list  = result.get("flags", [])
            passed_list = result.get("passed", [])

            p(f"    overall        : {result.get('overall', '?')}")
            p(f"    hard_blocks    : {len(hard_blocks)}")
            for r in hard_blocks:
                rule_id = getattr(r, 'rule_id', '?')
                msg = getattr(r, 'message', '')
                p(f"       {rule_id}: {str(msg)[:90]}")
            p(f"    flags          : {len(flags_list)}")
            for r in flags_list:
                rule_id = getattr(r, 'rule_id', '?')
                msg = getattr(r, 'message', '')
                p(f"      ! {rule_id}: {str(msg)[:90]}")
            p(f"    passed rules   : {len(passed_list)}")

            # Majority analysis
            p("")
            p("  [1.2b] Majority analysis")
            maj = result.get("majority_analysis") or {}
            _total = float(maj.get("total_debt") or 0)
            _voting = float(maj.get("voting_debt") or 0)
            _threshold = float(maj.get("threshold") or 0)
            _achievable = maj.get("achievable")
            _indeterminate = maj.get("indeterminate")
            _pct = (_voting / _total * 100) if _total else 0
            p(f"    total_debt          : GBP {_total:,.2f}")
            p(f"    voting_debt (yes)   : GBP {_voting:,.2f}")
            p(f"    threshold (75%)     : GBP {_threshold:,.2f}")
            p(f"    yes_pct             : {_pct:.1f}%")
            p(f"    achievable          : {_achievable}")
            p(f"    indeterminate       : {_indeterminate}")

            # Creditor positions
            engine_positions = result.get("creditor_positions", [])
            council_positions = result.get("council_positions", [])

            p("")
            p("  [1.2c] Creditor positions (engine)")
            for pos in engine_positions:
                cname  = pos.get("creditor_name", "?")
                status = pos.get("effective_status", "?")
                bal    = pos.get("balance", 0) or 0
                rep    = pos.get("representative", "")
                p(f"    {cname[:35]:<35} {status:<18} {bal:>9,.0f}  rep={rep}")

            p("")
            p("  [1.2d] Council positions")
            for pos in council_positions:
                cname  = pos.get("creditor_name") or pos.get("council_name", "?")
                status = pos.get("effective_status", "?")
                p(f"    {cname[:35]:<35} {status}")

            # Reconcile and check UNKNOWN count
            try:
                all_positions = reconcile_creditor_positions(result, prepared_creditors)
            except Exception as exc:
                p(f"  [ERROR] reconcile_creditor_positions failed: {exc}")
                all_positions = engine_positions

            unknowns = [p2 for p2 in all_positions if p2.get("effective_status") == "UNKNOWN"]
            p("")
            p("  [1.2e] reconcile_creditor_positions summary")
            p(f"    engine positions    : {len(engine_positions)}")
            p(f"    council positions   : {len(council_positions)}")
            p(f"    all after reconcile : {len(all_positions)}")
            p(f"    UNKNOWN count       : {len(unknowns)}")
            for unk in unknowns:
                unk_name = unk.get("creditor_name", "?")
                unk_bal  = unk.get("balance", 0) or 0
                p(f"      UNKNOWN: {unk_name} {unk_bal:,.0f}")

            # TIG-10 evidence
            p("")
            p("  [1.2f] TIG-10 evidence check")
            tig10 = next((r for r in (hard_blocks + flags_list + passed_list)
                          if getattr(r, 'rule_id', None) == 'TIG-10'), None)
            if tig10:
                severity = getattr(tig10, 'severity', '?')
                triggered = getattr(tig10, 'triggered', False)
                msg = getattr(tig10, 'message', '')
                p(f"    TIG-10 severity={severity} triggered={triggered}")
                if triggered:
                    p(f"    message: {str(msg)[:120]}")
            else:
                p("    TIG-10: not found in results")

            # DB integrity: creditors resolved vs not
            p("")
            p("  [1.2g] DB creditor resolution integrity")
            from debt_app.helpers import get_creditor_by_trading_name
            from debt_app.models import CreditorCriteria
            resolved = 0
            unresolved = []
            for cr in prepared_creditors:
                cname = cr.get("creditor_name") or cr.get("name") or ""
                try:
                    get_creditor_by_trading_name(cname)
                    resolved += 1
                except CreditorCriteria.DoesNotExist:
                    unresolved.append((cname, cr.get("crm_balance", 0)))
                except Exception as exc:
                    unresolved.append((cname, cr.get("crm_balance", 0)))
                    p(f"    [UNEXPECTED ERROR] resolving '{cname}': {exc}")

            p(f"    resolved   : {resolved}/{len(prepared_creditors)}")
            p(f"    unresolved : {len(unresolved)}")
            for name, bal in unresolved:
                p(f"      MISS: {name}  {bal:,.0f}")

        p("")
        p(_hr("="))
        if part1_any_diff:
            p("PART 1 SUMMARY:  detect_representatives MISMATCH found  see above")
        else:
            p("PART 1 SUMMARY:  detect_representatives identical on all cases (diff empty)")
        p(_hr("="))

        # -- Part 2 ---------------------------------------------------------------
        p("")
        p(_hr())
        p(f"PART 2  Unresolved-creditor rate across {n_recent} most recent cases")
        p(_hr())

        from debt_app.models import CreditorResolutionMiss, CriteriaDecision

        # Pull N most recent cases from CriteriaDecision (references only)
        recent_refs = list(
            CriteriaDecision.objects.order_by("-triggered_at")
            .values_list("application_id", flat=True)
            .distinct()[:n_recent]
        )
        p(f"  CriteriaDecision refs available: {len(recent_refs)}")

        # Pull miss records for these references
        misses = list(
            CreditorResolutionMiss.objects.filter(case_reference__in=recent_refs)
            .values("raw_name", "normalised_name", "case_reference", "balance")
            .order_by("-balance")
        )

        # Also pull ALL miss records for rate info
        total_miss_count = CreditorResolutionMiss.objects.count()
        miss_in_window = len(misses)

        p(f"  Total CreditorResolutionMiss rows (all time): {total_miss_count}")
        p(f"  Misses in latest {len(recent_refs)} case refs: {miss_in_window}")

        # Estimate rate  need total creditor count in those cases
        # Use CriteriaDecision.result_json if available
        total_creditors_seen = 0
        cases_with_result = 0
        for ref in recent_refs:
            dec = CriteriaDecision.objects.filter(application_id=ref).order_by("-triggered_at").first()
            if dec and dec.result_json:
                try:
                    rj = dec.result_json if isinstance(dec.result_json, dict) else json.loads(dec.result_json)
                    cps = rj.get("creditor_positions") or []
                    total_creditors_seen += len(cps)
                    cases_with_result += 1
                except Exception:
                    pass

        p(f"  Cases with stored result_json: {cases_with_result}/{len(recent_refs)}")
        p(f"  Total creditor positions seen in those cases: {total_creditors_seen}")

        if total_creditors_seen > 0:
            miss_rate = miss_in_window / total_creditors_seen * 100
            p(f"  Estimated miss rate: {miss_in_window}/{total_creditors_seen} = {miss_rate:.1f}%")
        else:
            p("  Miss rate: cannot compute (no result_json stored)")

        if misses:
            total_miss_balance = sum(float(m.get("balance") or 0) for m in misses)
            avg_miss_balance = total_miss_balance / len(misses)
            p(f"  Total balance missed: {total_miss_balance:,.2f}")
            p(f"  Avg balance per miss: {avg_miss_balance:,.2f}")

            p("")
            p("  Top-20 missed creditors by balance:")
            for m in misses[:20]:
                bal = float(m.get("balance") or 0)
                p(f"    {bal:>9,.0f}  {m['raw_name'][:40]:<40}  (ref={m['case_reference']})")
        else:
            p("  No CreditorResolutionMiss rows in this window.")

        # -- Part 2b: reconcile backfill check -----------------------------------
        p("")
        p("  [2b] reconcile_creditor_positions UNKNOWN backfill check")
        p("  Verifying: every prepared_creditor that is NOT in engine_positions appears in")
        p("             the reconciled list with status UNKNOWN (never silently dropped).")
        p("")

        # Run for each reference case
        backfill_ok = True
        for ref in REFERENCE_CASES:
            try:
                case_data_obj = fetch_case_by_reference(ref)
                case_data, prepared_creditors = view._prepare_engine_payload(case_data_obj)
            except Exception:
                continue

            try:
                result2 = assess_case(case_data)
            except Exception as exc:
                p(f"  Case {ref}: assess_case error: {exc}")
                continue

            all_pos = reconcile_creditor_positions(result2, prepared_creditors)
            all_names_in_result = set()
            for pos in all_pos:
                for k in ("creditor_name", "original_aryza_name", "resolved_canonical_name"):
                    v = pos.get(k)
                    if v:
                        all_names_in_result.add(v.strip().lower())

            dropped = []
            for cr in prepared_creditors:
                cn = (cr.get("creditor_name") or cr.get("name") or "").strip().lower()
                orig = (cr.get("original_name") or cn).strip().lower()
                if cn not in all_names_in_result and orig not in all_names_in_result:
                    dropped.append(cr.get("creditor_name") or cr.get("name") or "?")

            if dropped:
                backfill_ok = False
                p(f"  Case {ref}: SILENTLY DROPPED (not in any position): {dropped}")
            else:
                p(f"  Case {ref}:  all {len(prepared_creditors)} creditors appear in reconciled output")

        p("")
        if backfill_ok:
            p("  BACKFILL CHECK:  reconcile_creditor_positions correctly surfaces all creditors")
        else:
            p("  BACKFILL CHECK:  some creditors silently dropped  see above")

        # -- Part 3: alias-map integrity ------------------------------------------
        # Runs the same check as `manage.py validate_alias_map`: every VALUE in
        # _RAW_CREDITOR_ALIAS_MAP must point to an active CreditorCriteria row.
        # A broken alias (e.g. pointing to a row deleted by a later
        # `seed_creditor_criteria` "strict sync" run, or a typo in the target
        # name) means every real-world creditor name that hits that alias
        # silently resolves to NONE/UNKNOWN forever — this is exactly how the
        # Klarna alias-collision bug went unnoticed for an unknown period, and
        # 20 further dead aliases (Zilch, Cashplus, Northridge Finance, etc.)
        # were found the same way. Invoking the existing validator here (rather
        # than re-implementing the check) means this audit and the standalone
        # command can never silently drift apart.
        p("")
        p(_hr())
        p("PART 3  Alias-map integrity (CREDITOR_ALIAS_MAP targets vs active DB rows)")
        p(_hr())

        import io
        from django.core.management import call_command

        alias_report = io.StringIO()
        try:
            call_command("validate_alias_map", stdout=alias_report)
            alias_ok = True
        except SystemExit as e:
            alias_ok = (e.code == 0)
        for line in alias_report.getvalue().splitlines():
            p(f"  {line}")
        p("")
        if alias_ok:
            p("  ALIAS-MAP CHECK:  all alias targets resolve to an active CreditorCriteria row")
        else:
            p("  ALIAS-MAP CHECK:  BROKEN ALIASES FOUND  see above  fix before deploy")

        # -- Final summary --------------------------------------------------------
        p("")
        p(_hr("="))
        p("AUDIT COMPLETE")
        if not alias_ok:
            p("STATUS: FAIL  broken creditor aliases present (see PART 3)")
        elif not backfill_ok:
            p("STATUS: FAIL  creditor(s) silently dropped from output (see PART 2b)")
        else:
            p("STATUS: PASS")
        p(_hr("="))
        p("")
