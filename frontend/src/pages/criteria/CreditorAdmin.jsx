import { useEffect, useState } from 'react'
import { getCreditors, updateCreditor } from '../../services/criteriaService.js'
import ErrorCard from '../../components/shared/ErrorCard.jsx'
import Spinner from '../../components/shared/Spinner.jsx'

export default function CreditorAdmin() {
  const [filters, setFilters] = useState({ search: '', rep: '' })
  const [creditors, setCreditors] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeCreditor, setActiveCreditor] = useState(null)
  const [editableCreditor, setEditableCreditor] = useState(null)
  const [saving, setSaving] = useState(false)

  const fetchCreditors = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getCreditors({
        q: filters.search || undefined,
        rep: filters.rep || undefined,
      })
      setCreditors(response)
    } catch {
      setError('Unable to load creditor data. Please refresh and try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCreditors()
  }, [])

  const openEditor = (creditor) => {
    setActiveCreditor(creditor)
    setEditableCreditor({
      ...creditor,
      parent_group: creditor.parent_group || '',
    })
  }

  const handleSave = async () => {
    if (!editableCreditor) return
    setSaving(true)
    try {
      await updateCreditor(editableCreditor.id, {
        name:               editableCreditor.name,
        trading_names:      editableCreditor.trading_names,
        representative:     editableCreditor.representative,
        min_dividend_pence: editableCreditor.min_dividend_pence,
        contact_email:      editableCreditor.contact_email,
        contact_phone:      editableCreditor.contact_phone,
        is_watch:           editableCreditor.is_watch,
        is_tix:             editableCreditor.is_tix,
        is_evolve:          editableCreditor.is_evolve,
        parent_group:       editableCreditor.parent_group || null,
        is_active:          editableCreditor.is_active,
      })
      setCreditors((current) => current.map((item) => (item.id === editableCreditor.id ? editableCreditor : item)))
      setActiveCreditor(null)
      setEditableCreditor(null)
    } catch {
      setError('Unable to save creditor updates. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-200 bg-[#f8fafc] p-8 shadow-sm">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-500">Creditor admin</p>
          <h2 className="mt-3 text-3xl font-semibold text-slate-900">Manage creditor settings</h2>
          <p className="mt-2 text-sm text-slate-600">Filter creditors by name or representative, then edit watchlist and routing settings.</p>
        </div>
      </div>

      {error && <ErrorCard message={error} />}

      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="block text-sm font-semibold text-slate-700">
            Search creditor
            <input
              value={filters.search}
              onChange={(e) => setFilters((prev) => ({ ...prev, search: e.target.value }))}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="Creditor name"
            />
          </label>
          <label className="block text-sm font-semibold text-slate-700">
            Representative
            <input
              value={filters.rep}
              onChange={(e) => setFilters((prev) => ({ ...prev, rep: e.target.value }))}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="Representative name"
            />
          </label>
          <div className="flex items-end gap-3">
            <button
              type="button"
              className="inline-flex w-full items-center justify-center rounded-3xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
              onClick={fetchCreditors}
            >
              Update list
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-6 py-4 font-semibold">Creditor</th>
              <th className="px-6 py-4 font-semibold">Representative</th>
              <th className="px-6 py-4 font-semibold">Watchlist</th>
              <th className="px-6 py-4 font-semibold">TIX</th>
              <th className="px-6 py-4 font-semibold">Evolve</th>
              <th className="px-6 py-4 font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {loading ? (
              <tr>
                <td colSpan="6" className="px-6 py-10 text-center text-slate-500">
                  <Spinner /> Loading creditors...
                </td>
              </tr>
            ) : creditors.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-6 py-10 text-center text-slate-500">No creditors found.</td>
              </tr>
            ) : (
              creditors.map((creditor) => (
                <tr key={creditor.id} className="hover:bg-slate-50">
                  <td className="px-6 py-4 font-medium text-slate-900">{creditor.name}</td>
                  <td className="px-6 py-4 text-slate-700">{creditor.representative || '—'}</td>
                  <td className="px-6 py-4 text-slate-700">{creditor.is_watch ? 'Yes' : 'No'}</td>
                  <td className="px-6 py-4 text-slate-700">{creditor.is_tix ? 'Yes' : 'No'}</td>
                  <td className="px-6 py-4 text-slate-700">{creditor.is_evolve ? 'Yes' : 'No'}</td>
                  <td className="px-6 py-4">
                    <button
                      type="button"
                      className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
                      onClick={() => openEditor(creditor)}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {activeCreditor && editableCreditor && (
        <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6 shadow-sm">
          <div className="mb-6 flex items-center justify-between gap-4">
            <div>
              <h3 className="text-xl font-semibold text-slate-900">Edit creditor settings</h3>
              <p className="mt-2 text-sm text-slate-600">Update watchlist and network routing flags for this creditor.</p>
            </div>
            <button
              type="button"
              className="rounded-3xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
              onClick={() => {
                setActiveCreditor(null)
                setEditableCreditor(null)
              }}
            >
              Close
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center justify-between gap-3 rounded-3xl border border-slate-200 bg-white px-4 py-4 text-sm font-semibold text-slate-700">
              Watchlist
              <input
                type="checkbox"
                checked={editableCreditor.is_watch}
                onChange={(event) => setEditableCreditor((prev) => ({ ...prev, is_watch: event.target.checked }))}
              />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-3xl border border-slate-200 bg-white px-4 py-4 text-sm font-semibold text-slate-700">
              TIX enabled
              <input
                type="checkbox"
                checked={editableCreditor.is_tix}
                onChange={(event) => setEditableCreditor((prev) => ({ ...prev, is_tix: event.target.checked }))}
              />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-3xl border border-slate-200 bg-white px-4 py-4 text-sm font-semibold text-slate-700">
              Evolve enabled
              <input
                type="checkbox"
                checked={editableCreditor.is_evolve}
                onChange={(event) => setEditableCreditor((prev) => ({ ...prev, is_evolve: event.target.checked }))}
              />
            </label>
          </div>

          <div className="mt-4 space-y-1">
            <label className="text-sm font-medium text-gray-700">
              Parent Group
            </label>
            <input
              type="text"
              value={editableCreditor.parent_group || ''}
              onChange={(e) =>
                setEditableCreditor(prev => ({
                  ...prev,
                  parent_group: e.target.value
                }))
              }
              placeholder="e.g. Lloyds Banking Group"
              className="w-full border border-gray-300 rounded-md px-3 py-2 
                         text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500">
              Banking group this creditor belongs to
            </p>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-3xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-70"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save updates'}
            </button>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-3xl bg-white px-5 py-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-100"
              onClick={() => {
                setActiveCreditor(null)
                setEditableCreditor(null)
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
