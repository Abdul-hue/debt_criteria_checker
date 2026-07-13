import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import LoadingSpinner from '../shared/LoadingSpinner'
import Badge from '../shared/Badge'
import CrmSyncSummaryPanel from '../shared/CrmSyncSummaryPanel'
import { formatDateTime } from '../../utils/format'
import { RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'

const TRIGGER_LABELS = {
  MANUAL: 'Manual',
  SCHEDULED: 'Scheduled',
  CLI: 'CLI',
}

const TRIGGER_VARIANTS = {
  MANUAL: 'info',
  SCHEDULED: 'default',
  CLI: 'default',
}

function relativeTime(isoString) {
  if (!isoString) return '—'
  const date = new Date(isoString)
  const diffMs = Date.now() - date.getTime()
  const diffSec = Math.round(diffMs / 1000)

  if (diffSec < 60) return 'just now'
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`
  const diffDay = Math.round(diffHr / 24)
  if (diffDay < 30) return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`
  return formatDateTime(isoString)
}

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  return `${minutes}m ${remainder}s`
}

function StatusPill({ status }) {
  const styles = {
    RUNNING: 'bg-blue-600 text-white',
    SUCCESS: 'bg-emerald-700 text-white',
    FAILED: 'bg-brand-red text-white',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${styles[status] || 'bg-slate-500 text-white'}`}>
      {status === 'RUNNING' && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
      {status === 'SUCCESS' ? 'Success' : status === 'FAILED' ? 'Failed' : 'Running'}
    </span>
  )
}

const CREDITOR_STATUS_COLUMNS = [
  { key: 'accepted', label: 'Accepted' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'modified', label: 'Modified' },
  { key: 'pod', label: 'POD' },
]

function CreditorBreakdownTable({ runId }) {
  const [expanded, setExpanded] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['crm-sync-creditors', runId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/crm-sync/creditors/${runId}/`)
      return data
    },
    enabled: expanded,
  })

  const creditors = data?.creditors ?? []

  return (
    <div className="mt-3 pt-3 border-t border-slate-200">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1.5 text-xs font-semibold text-brand-navy hover:text-brand-navy/80 transition-colors"
      >
        {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        Creditor breakdown
      </button>

      {expanded && (
        <div className="mt-2">
          {isLoading && <LoadingSpinner size="sm" />}
          {isError && <p className="text-sm text-brand-red font-medium">Failed to load creditor breakdown.</p>}

          {!isLoading && !isError && creditors.length === 0 && (
            <p className="text-sm text-slate-400">No changes recorded</p>
          )}

          {!isLoading && !isError && creditors.length > 0 && (
            <div className="overflow-x-auto rounded-lg bg-brand-navy">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[10px] font-bold text-slate-300 uppercase tracking-widest border-b border-white/10">
                    <th className="py-2 px-3">Creditor</th>
                    {CREDITOR_STATUS_COLUMNS.map((col) => (
                      <th key={col.key} className="py-2 px-3 text-right">{col.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {creditors.map((creditor) => (
                    <tr key={creditor.vote_summary_id} className="border-t border-white/10">
                      <td className="py-2 px-3 text-sm text-white">{creditor.creditor_name}</td>
                      {CREDITOR_STATUS_COLUMNS.map((col) => (
                        <td key={col.key} className="py-2 px-3 text-sm text-white text-right tabular-nums">
                          {creditor[col.key] ?? 0}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SyncRunRow({ run }) {
  const [expanded, setExpanded] = useState(false)
  const canExpand = run.status === 'SUCCESS' || run.status === 'FAILED'

  return (
    <>
      <tr
        className={`border-t border-slate-100 hover:bg-slate-50/50 ${canExpand ? 'cursor-pointer' : ''}`}
        onClick={() => canExpand && setExpanded((prev) => !prev)}
      >
        <td className="py-2.5 px-3 text-sm text-slate-700" title={run.started_at}>
          <div className="flex items-center gap-1.5">
            {canExpand ? (
              expanded ? (
                <ChevronDown className="w-3.5 h-3.5 text-slate-400 flex-none" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-slate-400 flex-none" />
              )
            ) : (
              <span className="w-3.5 flex-none" />
            )}
            {relativeTime(run.started_at)}
          </div>
        </td>
        <td className="py-2.5 px-3">
          <Badge label={TRIGGER_LABELS[run.trigger_source] || run.trigger_source} variant={TRIGGER_VARIANTS[run.trigger_source] || 'default'} />
        </td>
        <td className="py-2.5 px-3">
          <StatusPill status={run.status} />
        </td>
        <td className="py-2.5 px-3 text-sm text-slate-600">{formatDuration(run.duration_seconds)}</td>
        <td className="py-2.5 px-3 text-sm text-slate-600">
          {run.records_created} created / {run.records_updated} updated
        </td>
      </tr>
      {expanded && canExpand && (
        <tr className="border-t border-slate-100 bg-slate-50/30">
          <td colSpan={5} className="py-3 px-3">
            <CrmSyncSummaryPanel run={run} className="max-w-xl" />
            {run.status === 'SUCCESS' && <CreditorBreakdownTable runId={run.id} />}
          </td>
        </tr>
      )}
    </>
  )
}

export default function CrmSyncHistoryPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['crm-sync-history'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/crm-sync/history/?page_size=10')
      return data
    },
    refetchInterval: 30000,
  })

  const runs = data?.results ?? []

  return (
    <div className="col-span-full bg-white rounded-lg border border-slate-200 border-t-4 border-t-brand-navy shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-slate-100 text-brand-navy">
            <RefreshCw className="w-4 h-4" />
          </div>
          <h3 className="text-sm font-bold text-brand-navy">CRM Vote Sync History</h3>
        </div>
      </div>

      {isLoading && <LoadingSpinner size="sm" />}
      {isError && <p className="text-sm text-brand-red font-medium">Failed to load sync history.</p>}

      {!isLoading && !isError && runs.length === 0 && (
        <p className="text-sm text-slate-400">No sync runs recorded yet.</p>
      )}

      {!isLoading && !isError && runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] font-bold text-slate-500 uppercase tracking-widest border-b-2 border-slate-100">
                <th className="py-2 px-3">Started</th>
                <th className="py-2 px-3">Trigger</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Duration</th>
                <th className="py-2 px-3">Records</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <SyncRunRow key={run.id} run={run} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
