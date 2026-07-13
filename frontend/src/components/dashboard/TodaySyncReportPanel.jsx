import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import LoadingSpinner from '../shared/LoadingSpinner'
import { formatDate } from '../../utils/format'
import { CalendarClock, Mail, MailX } from 'lucide-react'

const VOTE_STATUS_COLUMNS = [
  { key: 'accepted', label: 'Accepted' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'modified', label: 'Modified' },
  { key: 'pod', label: 'POD' },
]

function StatTile({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{label}</div>
      <div className="mt-1 text-2xl font-display font-bold text-brand-navy tabular-nums">{value}</div>
    </div>
  )
}

export default function TodaySyncReportPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['crm-sync-today'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/crm-sync/today/')
      return data
    },
    refetchInterval: 30000,
  })

  const events = data?.vote_change_events
  const hasActivity = data && (
    (events?.total ?? 0) > 0 ||
    data.sync_runs_today > 0 ||
    data.moc_alerts_today > 0 ||
    data.distinct_creditors_affected > 0
  )

  return (
    <div className="col-span-full bg-white rounded-lg border border-slate-200 border-t-4 border-t-brand-navy shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-slate-100 text-brand-navy">
            <CalendarClock className="w-4 h-4" />
          </div>
          <h3 className="text-sm font-bold text-brand-navy">Today's Sync Report</h3>
        </div>
        {data && <span className="text-xs font-semibold text-slate-400">{formatDate(data.date)}</span>}
      </div>

      {isLoading && <LoadingSpinner size="sm" />}
      {isError && <p className="text-sm text-brand-red font-medium">Failed to load today's sync report.</p>}

      {!isLoading && !isError && data && !hasActivity && (
        <p className="text-sm text-slate-400">No sync activity today.</p>
      )}

      {!isLoading && !isError && hasActivity && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatTile label="Sync Runs" value={data.sync_runs_today} />
            <StatTile label="Creditors Affected" value={data.distinct_creditors_affected} />
            <StatTile label="Vote Changes" value={events.total} />
            <StatTile label="MOC Alerts" value={data.moc_alerts_today} />
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Email Sent</div>
              <div className={`mt-1 flex items-center gap-1.5 text-sm font-semibold ${data.email_sent_today ? 'text-emerald-700' : 'text-slate-400'}`}>
                {data.email_sent_today ? <Mail className="w-4 h-4" /> : <MailX className="w-4 h-4" />}
                {data.email_sent_today ? 'Yes' : 'No'}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg bg-brand-navy">
            <table className="w-full text-left">
              <thead>
                <tr className="text-[10px] font-bold text-slate-300 uppercase tracking-widest border-b border-white/10">
                  <th className="py-2 px-3">Vote Change Breakdown</th>
                  {VOTE_STATUS_COLUMNS.map((col) => (
                    <th key={col.key} className="py-2 px-3 text-right">{col.label}</th>
                  ))}
                  <th className="py-2 px-3 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-white/10">
                  <td className="py-2 px-3 text-sm text-white">Events</td>
                  {VOTE_STATUS_COLUMNS.map((col) => (
                    <td key={col.key} className="py-2 px-3 text-sm text-white text-right tabular-nums">
                      {events[col.key] ?? 0}
                    </td>
                  ))}
                  <td className="py-2 px-3 text-sm text-white text-right tabular-nums font-bold">
                    {events.total}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
