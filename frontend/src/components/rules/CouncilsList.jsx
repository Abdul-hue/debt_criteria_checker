import React, { useState } from 'react'
import { useCouncils, useDeleteCouncil } from '../../hooks/useCouncils'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../shared/LoadingSpinner'
import ConfirmDialog from '../shared/ConfirmDialog'
import CouncilEditDrawer from './CouncilEditDrawer'
import { Trash2, ChevronDown, ChevronUp, Search, X } from 'lucide-react'

// ── Human-readable labels & colours per status ──────────────────────────────
const STATUS_CONFIG = {
  ACCEPT:           { label: 'Accepts',        bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-200',  dot: 'bg-green-500',  row: 'border-l-green-400'  },
  REJECT:           { label: 'Rejects',         bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-200',    dot: 'bg-red-500',    row: 'border-l-red-400'    },
  WILL_CONSIDER:    { label: 'Will Consider',   bg: 'bg-amber-100',  text: 'text-amber-800',  border: 'border-amber-200',  dot: 'bg-amber-400',  row: 'border-l-amber-400'  },
  DO_NOT_VOTE:      { label: 'Does Not Vote',   bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-200',   dot: 'bg-gray-400',   row: 'border-l-gray-300'   },
  CONDITIONAL_VOTER:{ label: 'Case by Case',    bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-200', dot: 'bg-purple-400', row: 'border-l-purple-400' },
}

const cfg = (status) => STATUS_CONFIG[status] ?? { label: status, bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200', dot: 'bg-gray-300', row: 'border-l-gray-200' }

function StatusChip({ status, active, onClick }) {
  const c = cfg(status)
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full border transition-all ${
        active
          ? `${c.bg} ${c.text} ${c.border} shadow-sm`
          : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${active ? c.dot : 'bg-gray-300'}`} />
      {c.label}
    </button>
  )
}

function StatusBadge({ status }) {
  const c = cfg(status)
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border ${c.bg} ${c.text} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  )
}

// Expandable notes cell
function NotesCell({ text }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return <span className="text-gray-300">—</span>
  const isLong = text.length > 120
  return (
    <div className="text-xs text-gray-600 leading-relaxed">
      <span>{expanded || !isLong ? text : `${text.slice(0, 120)}…`}</span>
      {isLong && (
        <button
          onClick={e => { e.stopPropagation(); setExpanded(v => !v) }}
          className="ml-1 inline-flex items-center gap-0.5 text-blue-500 hover:text-blue-700 font-medium whitespace-nowrap"
        >
          {expanded ? <><ChevronUp size={11} />Less</> : <><ChevronDown size={11} />More</>}
        </button>
      )}
    </div>
  )
}

export default function CouncilsList() {
  const { isAdmin } = useAuth()
  const toast = useToast()
  const { data: councils, isLoading, error } = useCouncils()
  const { mutateAsync: deleteCouncil, isPending: isDeleting } = useDeleteCouncil()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState([])
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [editTarget, setEditTarget] = useState(null)

  const handleDelete = async () => {
    try {
      await deleteCouncil(deleteTarget.id)
      toast.success('Council removed', `${deleteTarget.council_name} has been deleted.`)
      setDeleteTarget(null)
    } catch (err) {
      toast.error('Delete failed', err?.response?.data?.detail ?? err.message)
    }
  }

  const toggleStatus = (val) =>
    setStatusFilter(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])

  const filtered = (councils ?? [])
    .filter(c => !search || c.council_name.toLowerCase().includes(search.toLowerCase()))
    .filter(c => statusFilter.length === 0 || statusFilter.includes(c.status))

  // Stats
  const counts = (councils ?? []).reduce((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1
    return acc
  }, {})

  if (isLoading) return <div className="py-20"><LoadingSpinner message="Loading councils…" /></div>

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        Could not load council data. Please refresh the page or contact support.
      </div>
    )
  }

  return (
    <div className="space-y-4">

      {/* ── Stats bar ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 text-sm">
        <span className="font-semibold text-gray-700">{councils?.length ?? 0} councils</span>
        <span className="text-gray-300">|</span>
        {Object.entries(STATUS_CONFIG).map(([key, c]) =>
          counts[key] ? (
            <span key={key} className="flex items-center gap-1 text-gray-500">
              <span className={`w-2 h-2 rounded-full ${c.dot}`} />
              <span className="font-medium text-gray-700">{counts[key]}</span> {c.label}
            </span>
          ) : null
        )}
      </div>

      {/* ── Search and Filters ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center gap-3">
        {/* Search */}
        <div className="relative w-full max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by council name…"
            className="w-full pl-8 pr-8 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X size={13} />
            </button>
          )}
        </div>

        {/* Status filters */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-400 font-medium">Filter by voting behaviour:</span>
          {Object.keys(STATUS_CONFIG).map(s => (
            <StatusChip
              key={s}
              status={s}
              active={statusFilter.includes(s)}
              onClick={() => toggleStatus(s)}
            />
          ))}
          {statusFilter.length > 0 && (
            <button
              onClick={() => setStatusFilter([])}
              className="text-xs text-gray-400 hover:text-gray-600 underline ml-1"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Help text ─────────────────────────────────────────────────────── */}
      <p className="text-xs text-gray-400">
        Click any row to view or edit that council's details. Colour on the left shows their voting behaviour at a glance.
      </p>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <th className="pl-4 pr-3 py-3 min-w-[200px]">Council Name</th>
              <th className="px-3 py-3 w-[150px]">Voting Behaviour</th>
              <th className="px-3 py-3 min-w-[240px]">Notes</th>
              <th className="px-3 py-3 w-[110px]">Last Updated</th>
              <th className="px-3 py-3 w-[120px]">Changed From Rejection</th>
              <th className="px-3 py-3 w-[200px]">Contact</th>
              <th className="px-3 py-3 w-[60px]" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length > 0 ? (
              filtered.map(council => {
                const c = cfg(council.status)
                return (
                  <tr
                    key={council.id}
                    onClick={() => setEditTarget(council)}
                    className={`border-l-4 ${c.row} hover:bg-blue-50 cursor-pointer transition-colors align-top group`}
                  >
                    {/* Council Name */}
                    <td className="pl-4 pr-3 py-3">
                      <span className="font-medium text-gray-900 text-sm group-hover:text-blue-700 transition-colors">
                        {council.council_name}
                      </span>
                      {/* Rejection flags as tiny pills */}
                      <div className="flex flex-wrap gap-1 mt-1">
                        {council.reject_if_employed && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">Employed → Reject</span>}
                        {council.reject_if_any_benefits && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">Benefits → Reject</span>}
                        {council.reject_if_dro_criteria_met && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">DRO → Reject</span>}
                        {council.reject_if_aoe_in_place && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">AOE → Reject</span>}
                        {council.reject_if_previous_iva && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">Prev IVA → Reject</span>}
                        {council.min_dividend_pence != null && <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 border border-blue-200 rounded text-[10px]">Min {council.min_dividend_pence}p/£</span>}
                        {council.do_not_chase && <span className="px-1.5 py-0.5 bg-red-50 text-red-600 border border-red-200 rounded text-[10px]">Do Not Chase</span>}
                      </div>
                    </td>

                    {/* Voting behaviour */}
                    <td className="px-3 py-3">
                      <StatusBadge status={council.status} />
                    </td>

                    {/* Notes */}
                    <td className="px-3 py-3 max-w-[260px]" onClick={e => e.stopPropagation()}>
                      <NotesCell text={council.blocked_reason} />
                    </td>

                    {/* Last updated */}
                    <td className="px-3 py-3 text-xs text-gray-500">
                      {council.last_reviewed || <span className="text-gray-300">—</span>}
                    </td>

                    {/* Changed from rejection */}
                    <td className="px-3 py-3 text-xs text-gray-500">
                      {council.criteria_changed_from_rej_date || <span className="text-gray-300">—</span>}
                    </td>

                    {/* Contact (combined) */}
                    <td className="px-3 py-3">
                      {council.contact_name || council.contact_number ? (
                        <div className="text-xs">
                          {council.contact_name && <p className="font-medium text-gray-700">{council.contact_name}</p>}
                          {council.contact_number && <p className="text-gray-500 mt-0.5">{council.contact_number}</p>}
                        </div>
                      ) : <span className="text-gray-300 text-xs">—</span>}
                    </td>

                    {/* Delete (admin only, stop row click) */}
                    <td className="px-3 py-3 text-right" onClick={e => e.stopPropagation()}>
                      {isAdmin && (
                        <button
                          onClick={() => setDeleteTarget(council)}
                          className="p-1.5 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                          title="Delete council"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })
            ) : (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center">
                  <p className="text-sm text-gray-500 font-medium">No councils found</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {search ? `No council names match "${search}"` : 'Try clearing your filters'}
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">
        Showing {filtered.length} of {councils?.length ?? 0} councils
      </p>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Remove Council"
        message={deleteTarget
          ? `Are you sure you want to remove ${deleteTarget.council_name}? This will delete all criteria for this council and cannot be undone.`
          : ''}
        confirmLabel="Remove"
        variant="danger"
        loading={isDeleting}
      />

      {editTarget && (
        <CouncilEditDrawer
          council={editTarget}
          onClose={() => setEditTarget(null)}
          readOnly={!isAdmin}
        />
      )}
    </div>
  )
}
