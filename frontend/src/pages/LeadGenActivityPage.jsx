import { useState } from 'react'
import clsx from 'clsx'
import { Info, Users, XCircle } from 'lucide-react'
import LoadingSpinner from '../components/shared/LoadingSpinner.jsx'
import { Button, Card, PageHeader } from '../components/leadgen/ui.jsx'
import { formatIsoDate } from '../components/leadgen/format.js'
import { apiErrorMessage, useLeadGenActivity } from '../hooks/useLeadGen'

/** Today's date in Europe/London as YYYY-MM-DD (matches the backend's day boundary). */
function londonToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/London' }).format(new Date())
}

const COLUMNS = [
  ['cases_checked', 'Cases checked'],
  ['iva_potential', 'IVA'],
  ['dmp_potential', 'DMP'],
  ['dro_referral', 'DRO refer'],
  ['no_solution', 'No solution'],
  ['failed_attempts', 'Failed attempts'],
]

const DATE_INPUT = 'h-10 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 tabular-nums '
  + 'focus:outline-none focus:ring-2 focus:ring-slate-500/30 focus:border-slate-500'

function cellClass(key, value) {
  if (key === 'cases_checked') return 'font-semibold text-slate-900'
  if (!value) return 'text-slate-400'
  if (key === 'failed_attempts') return 'font-medium text-amber-700'
  return 'text-slate-700'
}

/**
 * Manager view: cases checked per Lead Gen user per London day / date range.
 * A case checked = one distinct case reference successfully checked by a user
 * on a London calendar day (repeat checks that day count once).
 */
export default function LeadGenActivityPage() {
  const today = londonToday()
  const [dateFrom, setDateFrom] = useState(today)
  const [dateTo, setDateTo] = useState(today)
  const { data, isLoading, isError, error } = useLeadGenActivity(dateFrom, dateTo)
  const singleDay = dateFrom === dateTo
  const isToday = singleDay && dateFrom === today

  const subtitle = `${singleDay
    ? (isToday ? 'Cases checked today' : `Cases checked on ${formatIsoDate(dateFrom)}`)
    : `Cases checked ${formatIsoDate(dateFrom)} to ${formatIsoDate(dateTo)}`} (UK time)`

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-8">
      <PageHeader
        title="Lead Gen Activity"
        description={subtitle}
        actions={(
          <fieldset className="flex flex-wrap items-end gap-3">
            <legend className="sr-only">Date range</legend>
            <div>
              <label htmlFor="activity-from" className="block text-xs font-medium text-slate-600 mb-1">From</label>
              <input id="activity-from" type="date" value={dateFrom} max={today} className={DATE_INPUT}
                     onChange={(e) => { setDateFrom(e.target.value); if (e.target.value > dateTo) setDateTo(e.target.value) }} />
            </div>
            <span aria-hidden="true" className="hidden sm:block pb-2.5 text-slate-400">–</span>
            <div>
              <label htmlFor="activity-to" className="block text-xs font-medium text-slate-600 mb-1">To</label>
              <input id="activity-to" type="date" value={dateTo} min={dateFrom} max={today} className={DATE_INPUT}
                     onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <Button variant="secondary" onClick={() => { setDateFrom(today); setDateTo(today) }} disabled={isToday}>
              Today
            </Button>
          </fieldset>
        )}
      />

      {isLoading && <Card className="p-10"><LoadingSpinner /></Card>}
      {isError && (
        <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <XCircle size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-red-600" />
          {apiErrorMessage(error)}
        </div>
      )}

      {data && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <caption className="sr-only">{subtitle}</caption>
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Lead Gen</th>
                  {COLUMNS.map(([key, label]) => (
                    <th key={key} scope="col"
                        className={clsx('px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide whitespace-nowrap',
                          key === 'cases_checked' ? 'text-slate-700' : 'text-slate-500')}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.users.length === 0 && (
                  <tr>
                    <td colSpan={COLUMNS.length + 1} className="px-5 py-14 text-center">
                      <Users size={24} aria-hidden="true" className="mx-auto text-slate-300" />
                      <p className="mt-2 text-sm font-medium text-slate-700">No checks in this period.</p>
                      <p className="text-sm text-slate-500">Try a different date range.</p>
                    </td>
                  </tr>
                )}
                {data.users.map((u) => (
                  <tr key={u.username} className="hover:bg-slate-50/70">
                    <td className="px-5 py-3">
                      <span className="font-medium text-slate-900">{u.username}</span>
                      {u.department && <span className="block text-xs text-slate-500">{u.department}</span>}
                    </td>
                    {COLUMNS.map(([key]) => (
                      <td key={key} className={clsx('px-5 py-3 text-right tabular-nums', cellClass(key, u[key]))}>
                        {u[key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
              {data.users.length > 0 && (
                <tfoot className="bg-slate-50 border-t-2 border-slate-200">
                  <tr>
                    <th scope="row" className="px-5 py-3 text-left text-sm font-semibold text-slate-900">Total</th>
                    {COLUMNS.map(([key]) => (
                      <td key={key} className="px-5 py-3 text-right font-semibold tabular-nums text-slate-900">{data.totals[key]}</td>
                    ))}
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          <p className="flex items-start gap-2 px-5 py-3 text-xs text-slate-500 border-t border-slate-100">
            <Info size={14} aria-hidden="true" className="mt-px shrink-0" />
            {data.definition}
          </p>
        </Card>
      )}
    </div>
  )
}
