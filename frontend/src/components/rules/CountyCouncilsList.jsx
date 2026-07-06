import React, { useState } from 'react'
import { useCountyCouncils, useDeleteCountyCouncil } from '../../hooks/useCountyCouncils'
import { useAuth } from '../../context/AuthContext'
import { useMyPermissions } from '../../hooks/useFeatureAccess'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../shared/LoadingSpinner'
import ConfirmDialog from '../shared/ConfirmDialog'
import CountyCouncilEditDrawer from './CountyCouncilEditDrawer'
import { Trash2, ChevronDown, ChevronUp, Search, X } from 'lucide-react'

// ── Human-readable labels & colours per status ──────────────────────────────
// Most county councils delegate council tax entirely to their districts and
// never vote as a creditor themselves — NO_CRITERIA reflects that honestly.
// The rest only apply to the rare county with its own stated criteria.
const STATUS_CONFIG = {
  NO_CRITERIA:      { label: 'No Direct Criteria', bg: 'bg-slate-100', text: 'text-slate-500',  border: 'border-slate-200',  dot: 'bg-slate-300',  row: 'border-l-slate-200'  },
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
    <div className="text-xs text-gray-600 leading-relaxed whitespace-pre-line">
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

// Districts cell — each district as its own highlighted pill, not a comma-run-on
function DistrictsCell({ districts }) {
  const [expanded, setExpanded] = useState(false)
  const names = (districts ?? []).map(d => d.district_name)
  if (names.length === 0) return <span className="text-gray-300">—</span>

  const VISIBLE_COUNT = 4
  const isLong = names.length > VISIBLE_COUNT
  const shown = expanded || !isLong ? names : names.slice(0, VISIBLE_COUNT)

  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex flex-wrap gap-1">
        {shown.map((name, i) => (
          <span
            key={i}
            className="inline-flex items-center px-1.5 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded text-[11px] font-medium leading-tight"
          >
            {name}
          </span>
        ))}
      </div>
      {isLong && (
        <button
          onClick={e => { e.stopPropagation(); setExpanded(v => !v) }}
          className="inline-flex items-center gap-0.5 text-blue-500 hover:text-blue-700 text-[11px] font-medium whitespace-nowrap"
        >
          {expanded ? <><ChevronUp size={11} />Show less</> : <><ChevronDown size={11} />{names.length - VISIBLE_COUNT} more</>}
        </button>
      )}
    </div>
  )
}

export default function CountyCouncilsList() {
  const { isAdmin } = useAuth()
  const { hasWritePermission } = useMyPermissions()
  const canEdit = isAdmin || hasWritePermission('councils')
  const toast = useToast()
  const { data: counties, isLoading, error } = useCountyCouncils()
  const { mutateAsync: deleteCounty, isPending: isDeleting } = useDeleteCountyCouncil()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState([])
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [editTarget, setEditTarget] = useState(null)

  const handleDelete = async () => {
    try {
      await deleteCounty(deleteTarget.id)
      toast.success('County council removed', `${deleteTarget.county_name} has been deleted.`)
      setDeleteTarget(null)
    } catch (err) {
      toast.error('Delete failed', err?.response?.data?.detail ?? err.message)
    }
  }

  const toggleStatus = (val) =>
    setStatusFilter(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])

  const filtered = (counties ?? [])
    .filter(c => !search || c.county_name.toLowerCase().includes(search.toLowerCase()))
    .filter(c => statusFilter.length === 0 || statusFilter.includes(c.status))

  // Stats
  const counts = (counties ?? []).reduce((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1
    return acc
  }, {})

  if (isLoading) return <div className="py-20"><LoadingSpinner message="Loading county councils…" /></div>

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        Could not load county council data. Please refresh the page or contact support.
      </div>
    )
  }

  return (
    <div className="space-y-4">

      {/* ── Stats bar ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 text-sm">
        <span className="font-semibold text-gray-700">{counties?.length ?? 0} county councils</span>
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
            placeholder="Search by county name…"
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
        County councils are the two-tier parent authority — most delegate council tax to their districts (shown below), but may carry their own IVA voting criteria. Click any row to view or edit.
      </p>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <th className="pl-4 pr-3 py-3 min-w-[200px]">County Council</th>
              <th className="px-3 py-3 w-[150px]">Voting Behaviour</th>
              <th className="px-3 py-3 min-w-[260px]">Districts</th>
              <th className="px-3 py-3 min-w-[240px]">Notes</th>
              <th className="px-3 py-3 w-[110px]">Last Updated</th>
              <th className="px-3 py-3 w-[200px]">Contact</th>
              <th className="px-3 py-3 w-[60px]" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length > 0 ? (
              filtered.map(county => {
                const c = cfg(county.status)
                return (
                  <tr
                    key={county.id}
                    onClick={() => setEditTarget(county)}
                    className={`border-l-4 ${c.row} hover:bg-blue-50 cursor-pointer transition-colors align-top group`}
                  >
                    {/* County name */}
                    <td className="pl-4 pr-3 py-3">
                      <span className="font-medium text-gray-900 text-sm group-hover:text-blue-700 transition-colors">
                        {county.county_name}
                      </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {county.deals_with_council_tax && <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 border border-blue-200 rounded text-[10px]">Deals with Council Tax</span>}
                        {county.min_dividend_pence != null && <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 border border-blue-200 rounded text-[10px]">Min {county.min_dividend_pence}p/£</span>}
                      </div>
                    </td>

                    {/* Voting behaviour */}
                    <td className="px-3 py-3">
                      <StatusBadge status={county.status} />
                    </td>

                    {/* Districts */}
                    <td className="px-3 py-3 max-w-[320px]" onClick={e => e.stopPropagation()}>
                      <DistrictsCell districts={county.districts} />
                    </td>

                    {/* Notes */}
                    <td className="px-3 py-3 max-w-[260px]" onClick={e => e.stopPropagation()}>
                      <NotesCell text={county.blocked_reason} />
                    </td>

                    {/* Last updated */}
                    <td className="px-3 py-3 text-xs text-gray-500">
                      {county.last_reviewed || <span className="text-gray-300">—</span>}
                    </td>

                    {/* Contact (combined) */}
                    <td className="px-3 py-3">
                      {county.contact_name || county.contact_number ? (
                        <div className="text-xs">
                          {county.contact_name && <p className="font-medium text-gray-700">{county.contact_name}</p>}
                          {county.contact_number && <p className="text-gray-500 mt-0.5">{county.contact_number}</p>}
                        </div>
                      ) : <span className="text-gray-300 text-xs">—</span>}
                    </td>

                    {/* Delete (admin only, stop row click) */}
                    <td className="px-3 py-3 text-right" onClick={e => e.stopPropagation()}>
                      {isAdmin && (
                        <button
                          onClick={() => setDeleteTarget(county)}
                          className="p-1.5 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                          title="Delete county council"
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
                  <p className="text-sm text-gray-500 font-medium">No county councils found</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {search ? `No county names match "${search}"` : 'Try clearing your filters'}
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">
        Showing {filtered.length} of {counties?.length ?? 0} county councils
      </p>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Remove County Council"
        message={deleteTarget
          ? `Are you sure you want to remove ${deleteTarget.county_name}? This will delete all criteria for this county council and cannot be undone.`
          : ''}
        confirmLabel="Remove"
        variant="danger"
        loading={isDeleting}
      />

      {editTarget && (
        <CountyCouncilEditDrawer
          county={editTarget}
          onClose={() => setEditTarget(null)}
          readOnly={!canEdit}
        />
      )}
    </div>
  )
}
