import { useEffect, useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { getHistory, getHistoryDetail } from '../../services/criteriaService.js'
import ErrorCard from '../../components/shared/ErrorCard.jsx'
import Spinner from '../../components/shared/Spinner.jsx'
import { formatDateTime } from '../../utils/format.js'

const statuses = ['ALL', 'PASS', 'REVIEW', 'BLOCK']

export default function DecisionHistory() {
  const [filters, setFilters] = useState({ application_id: '', status: 'ALL', fromDate: '', toDate: '' })
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  const fetchHistory = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getHistory({
        application_id: filters.application_id || undefined,
        status: filters.status === 'ALL' ? undefined : filters.status,
        start_date: filters.fromDate || undefined,
        end_date: filters.toDate || undefined,
      })
      setHistory(response)
    } catch (err) {
      setError('Unable to retrieve decision history. Try again later.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHistory()
  }, [])

  const openDetail = async (id) => {
    setSelectedId(id)
    setDialogOpen(true)
    setDetail(null)
    try {
      const response = await getHistoryDetail(id)
      setDetail(response)
    } catch {
      setDetail(null)
    }
  }

  const selectedItem = useMemo(() => history.find((item) => item.id === selectedId), [history, selectedId])

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-200 bg-[#f8fafc] p-8 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-500">Decision history</p>
            <h2 className="mt-3 text-3xl font-semibold text-slate-900">Audit past assessments</h2>
          </div>
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-3xl bg-brand-navy px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
            onClick={fetchHistory}
          >
            Refresh
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="block text-sm font-semibold text-slate-700">
            Application ID
            <input
              value={filters.application_id}
              onChange={(e) => setFilters((prev) => ({ ...prev, application_id: e.target.value }))}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="Search case ID"
            />
          </label>

          <label className="block text-sm font-semibold text-slate-700">
            Status
            <select
              value={filters.status}
              onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
            >
              {statuses.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-semibold text-slate-700">
            From date
            <input
              type="date"
              value={filters.fromDate}
              onChange={(e) => setFilters((prev) => ({ ...prev, fromDate: e.target.value }))}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
            />
          </label>

          <label className="block text-sm font-semibold text-slate-700">
            To date
            <input
              type="date"
              value={filters.toDate}
              onChange={(e) => setFilters((prev) => ({ ...prev, toDate: e.target.value }))}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
            />
          </label>
        </div>
      </div>

      {error && <ErrorCard message={error} />}

      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-6 py-4 font-semibold">Application ID</th>
              <th className="px-6 py-4 font-semibold">Client name</th>
              <th className="px-6 py-4 font-semibold">Solution</th>
              <th className="px-6 py-4 font-semibold">Blocks</th>
              <th className="px-6 py-4 font-semibold">Flags</th>
              <th className="px-6 py-4 font-semibold">Triggered</th>
              <th className="px-6 py-4 font-semibold">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {loading ? (
              <tr>
                <td colSpan="7" className="px-6 py-10 text-center text-slate-500">
                  <Spinner /> Loading history...
                </td>
              </tr>
            ) : history.length === 0 ? (
              <tr>
                <td colSpan="7" className="px-6 py-10 text-center text-slate-500">No history records found.</td>
              </tr>
            ) : (
              history.map((record) => {
                const blocks = record.decision_output?.hard_blocks?.length ?? '—'
                const flags = record.decision_output?.flags?.length ?? '—'
                return (
                  <tr key={record.id} className="hover:bg-slate-50">
                    <td className="px-6 py-4 font-medium text-slate-900">{record.application_id}</td>
                    <td className="px-6 py-4 text-slate-700">{record.client_name || '—'}</td>
                    <td className="px-6 py-4 text-slate-700">{record.recommended_solution || '—'}</td>
                    <td className="px-6 py-4 text-slate-700">{blocks}</td>
                    <td className="px-6 py-4 text-slate-700">{flags}</td>
                    <td className="px-6 py-4 text-slate-700">{formatDateTime(record.triggered_at)}</td>
                    <td className="px-6 py-4">
                      <button
                        type="button"
                        className="rounded-2xl bg-brand-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
                        onClick={() => openDetail(record.id)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm" />
          <Dialog.Content className="fixed right-0 top-0 z-50 h-full w-full max-w-2xl overflow-y-auto bg-white p-8 shadow-2xl sm:w-[720px]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <Dialog.Title className="text-2xl font-semibold text-slate-900">Decision details</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm text-slate-600">Review the full assessment and rule output for the selected case.</Dialog.Description>
              </div>
              <Dialog.Close className="rounded-2xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200">Close</Dialog.Close>
            </div>

            <div className="mt-8 space-y-6">
              {detail ? (
                <div className="space-y-6">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                      <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Application ID</p>
                      <p className="mt-3 text-lg font-semibold text-slate-900">{detail.application_id}</p>
                    </div>
                    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                      <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Potential solution</p>
                      <p className="mt-3 text-lg font-semibold text-slate-900">{detail.recommended_solution || '—'}</p>
                    </div>
                  </div>

                  <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                    <h3 className="text-lg font-semibold text-slate-900">Decision output</h3>
                    <pre className="mt-4 overflow-x-auto rounded-3xl bg-white p-4 text-xs leading-6 text-slate-700">
                      {JSON.stringify(detail.decision_output, null, 2)}
                    </pre>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                      <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Hard blocks</p>
                      <p className="mt-3 text-lg font-semibold text-slate-900">{detail.decision_output?.hard_blocks?.length ?? 0}</p>
                    </div>
                    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                      <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Flags</p>
                      <p className="mt-3 text-lg font-semibold text-slate-900">{detail.decision_output?.flags?.length ?? 0}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex min-h-[320px] items-center justify-center rounded-3xl border border-dashed border-slate-200 bg-slate-50">
                  <div className="text-center text-slate-600">
                    <Spinner />
                    <p className="mt-3 text-sm">Loading selected decision details...</p>
                  </div>
                </div>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
