import ErrorCard from './ErrorCard'

/**
 * Shared result summary for a finished CrmSyncRun — used both by the
 * "Sync CRM Votes Now" button (right after a run finishes) and by the
 * CRM Vote Sync History panel (when a past row is expanded), so both
 * places show the exact same breakdown.
 */
export default function CrmSyncSummaryPanel({ run, className = '' }) {
  if (!run) return null

  if (run.status === 'FAILED') {
    return (
      <div className={className}>
        <ErrorCard message={run.error_message || 'The CRM sync failed. Check the server logs for details.'} />
      </div>
    )
  }

  if (run.status !== 'SUCCESS') return null

  return (
    <div className={`rounded-xl bg-brand-navy text-white px-5 py-4 shadow-md ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="flex-none w-5 h-5 rounded-full bg-emerald-400 text-brand-navy flex items-center justify-center text-xs font-bold">
            ✓
          </span>
          <span className="text-sm font-semibold">Sync complete</span>
        </div>
        <span className="text-xs text-slate-300 tabular-nums">
          {run.duration_seconds != null ? `${Math.round(run.duration_seconds)}s` : ''}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">CRM rows fetched</div>
          <div className="font-semibold tabular-nums">
            {(run.crm_rows_fetched ?? 0).toLocaleString('en-GB')}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">Records touched</div>
          <div className="font-semibold tabular-nums">
            {(run.records_created ?? 0) + (run.records_updated ?? 0)}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">New</div>
          <div className="font-semibold tabular-nums text-emerald-300">{run.records_created ?? 0}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">Updated</div>
          <div className="font-semibold tabular-nums text-sky-300">{run.records_updated ?? 0}</div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-white/10 flex items-center gap-4 text-[11px] text-slate-300">
        <span>Creditors: {run.creditor_criteria_count ?? 0}</span>
        <span>Councils: {run.council_rule_count ?? 0}</span>
        <span>Counties: {run.county_council_count ?? 0}</span>
      </div>
    </div>
  )
}
