import React, { useState } from 'react'
import { useCreditors, useDeleteCreditor } from '../../hooks/useCreditors'
import { useAuth } from '../../context/AuthContext'
import { useMyPermissions } from '../../hooks/useFeatureAccess'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../shared/LoadingSpinner'
import ConfirmDialog from '../shared/ConfirmDialog'
import CreditorEditDrawer from './CreditorEditDrawer'
import { Trash2, ChevronDown, ChevronUp, Search, X } from 'lucide-react'

// ── Voting status colours ────────────────────────────────────────────────────
const STATUS_CONFIG = {
  ACCEPT:           { label: 'Accepts',        bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-200',  dot: 'bg-green-500',  row: 'border-l-green-400'  },
  REJECT:           { label: 'Rejects',         bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-200',    dot: 'bg-red-500',    row: 'border-l-red-400'    },
  WILL_CONSIDER:    { label: 'Will Consider',   bg: 'bg-amber-100',  text: 'text-amber-800',  border: 'border-amber-200',  dot: 'bg-amber-400',  row: 'border-l-amber-400'  },
  DO_NOT_VOTE:      { label: 'Does Not Vote',   bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-200',   dot: 'bg-gray-400',   row: 'border-l-gray-300'   },
  CONDITIONAL_VOTER:{ label: 'Case by Case',    bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-200', dot: 'bg-purple-400', row: 'border-l-purple-400' },
}

// ── Representative colours ───────────────────────────────────────────────────
const REP_CONFIG = {
  WATCH:         { label: 'Watch',          bg: 'bg-blue-100',   text: 'text-blue-800',   border: 'border-blue-200',   dot: 'bg-blue-500'   },
  TIX:           { label: 'TIX',            bg: 'bg-indigo-100', text: 'text-indigo-800', border: 'border-indigo-200', dot: 'bg-indigo-500' },
  EVOLVE:        { label: 'Evolve',         bg: 'bg-teal-100',   text: 'text-teal-800',   border: 'border-teal-200',   dot: 'bg-teal-500'   },
  EVERYDAY_LOANS:{ label: 'Everyday Loans', bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-200', dot: 'bg-orange-500' },
}

const scfg = (status) => STATUS_CONFIG[status] ?? { label: status, bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200', dot: 'bg-gray-300', row: 'border-l-gray-200' }
const rcfg = (rep)    => REP_CONFIG[rep]    ?? { label: rep,    bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200', dot: 'bg-gray-300' }

function StatusChip({ status, active, onClick }) {
  const c = scfg(status)
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full border transition-all ${
        active ? `${c.bg} ${c.text} ${c.border} shadow-sm` : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${active ? c.dot : 'bg-gray-300'}`} />
      {c.label}
    </button>
  )
}

function RepChip({ rep, active, onClick }) {
  const c = rcfg(rep)
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-full border transition-all ${
        active ? `${c.bg} ${c.text} ${c.border} shadow-sm` : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${active ? c.dot : 'bg-gray-300'}`} />
      {c.label}
    </button>
  )
}

function StatusBadge({ status }) {
  const c = scfg(status)
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border ${c.bg} ${c.text} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  )
}

function RepBadge({ rep }) {
  const c = rcfg(rep)
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border ${c.bg} ${c.text} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  )
}

function ExpandableText({ text, maxLen = 100 }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return <span className="text-gray-300">—</span>
  const isLong = text.length > maxLen
  return (
    <div className="text-xs text-gray-600 leading-relaxed">
      <span>{expanded || !isLong ? text : `${text.slice(0, maxLen)}…`}</span>
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

export default function CreditorsList() {
  const { isAdmin } = useAuth()
  const { hasWritePermission } = useMyPermissions()
  const canEdit = isAdmin || hasWritePermission('representative_creditors')
  const toast = useToast()
  const { data: creditors, isLoading, error } = useCreditors()
  const { mutateAsync: deleteCreditor, isPending: isDeleting } = useDeleteCreditor()

  const [search, setSearch] = useState('')
  const [repFilter, setRepFilter] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)

  const toggleRep = (val) => setRepFilter(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])

  const filtered = (creditors ?? [])
    .filter(c => c.representative !== 'NONE') // Only show creditors with a representative
    .filter(c => !search || c.creditor_name.toLowerCase().includes(search.toLowerCase()) ||
      (c.trading_names ?? []).some(n => n.toLowerCase().includes(search.toLowerCase())))
    .filter(c => repFilter.length === 0 || repFilter.includes(c.representative))

  // Stats
  const repCounts = (creditors ?? []).reduce((acc, c) => {
    acc[c.representative] = (acc[c.representative] ?? 0) + 1
    return acc
  }, {})

  const handleDelete = async () => {
    try {
      await deleteCreditor(deleteTarget.id)
      toast.success('Creditor removed', `${deleteTarget.creditor_name} has been deleted.`)
      setDeleteTarget(null)
    } catch (err) {
      toast.error('Delete failed', err?.response?.data?.detail ?? err.message)
    }
  }

  if (isLoading) return <div className="py-20"><LoadingSpinner message="Loading creditors…" /></div>

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        Could not load creditor data. Please refresh the page or contact support.
      </div>
    )
  }

  return (
    <div className="space-y-4">

      {/* ── Stats bar ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 text-sm">
        <span className="font-semibold text-gray-700">{filtered.length} creditors</span>
        <span className="text-gray-300">|</span>
        {Object.entries(REP_CONFIG).map(([key, c]) =>
          repCounts[key] ? (
            <span key={key} className="flex items-center gap-1 text-gray-500">
              <span className={`w-2 h-2 rounded-full ${c.dot}`} />
              <span className="font-medium text-gray-700">{repCounts[key]}</span> {c.label}
            </span>
          ) : null
        )}
      </div>

      {/* ── Search and Filters ────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-start gap-3">
        <div className="relative w-full max-w-sm shrink-0">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by creditor name or trading name…"
            className="w-full pl-8 pr-8 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X size={13} />
            </button>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-400 font-medium">Representative:</span>
            {Object.keys(REP_CONFIG).map(r => (
              <RepChip key={r} rep={r} active={repFilter.includes(r)} onClick={() => toggleRep(r)} />
            ))}
            {repFilter.length > 0 && (
              <button onClick={() => setRepFilter([])} className="text-xs text-gray-400 hover:text-gray-600 underline ml-1">Clear</button>
            )}
          </div>
        </div>
      </div>

      {/* ── Help text ─────────────────────────────────────────────────────── */}
      <p className="text-xs text-gray-400">
        Click any row to view or edit that creditor's criteria.
      </p>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <th className="pl-4 pr-3 py-3 min-w-[200px]">Creditor Name</th>
              <th className="px-3 py-3 w-[160px]">Which Representative</th>
              <th className="px-3 py-3 min-w-[160px]">Trading Names</th>
              <th className="px-3 py-3 w-[100px]">Min Dividend</th>
              <th className="px-3 py-3 min-w-[180px]">Notes</th>
              <th className="px-3 py-3 w-[60px]" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length > 0 ? (
              filtered.map(creditor => {
                const sc = scfg(creditor.status)
                return (
                  <tr
                    key={creditor.id}
                    onClick={() => setEditTarget(creditor)}
                    className={`border-l-4 ${sc.row} hover:bg-blue-50 cursor-pointer transition-colors align-top group`}
                  >
                    {/* Name + flags */}
                    <td className="pl-4 pr-3 py-3">
                      <span className="font-medium text-gray-900 text-sm group-hover:text-blue-700 transition-colors">
                        {creditor.creditor_name}
                      </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {creditor.blocked_until_cleared && <span className="px-1.5 py-0.5 bg-red-50 text-red-600 border border-red-200 rounded text-[10px]">Blocked</span>}
                        {creditor.reject_if_in_dmp      && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">DMP → Reject</span>}
                        {creditor.reject_if_second_iva  && <span className="px-1.5 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded text-[10px]">2nd IVA → Reject</span>}
                        {creditor.min_dividend_pence != null && creditor.min_dividend_pence > 0 && (
                          <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 border border-blue-200 rounded text-[10px]">Min {creditor.min_dividend_pence}p/£</span>
                        )}
                        {creditor.conditional_voter     && <span className="px-1.5 py-0.5 bg-purple-50 text-purple-600 border border-purple-200 rounded text-[10px]">Conditional</span>}
                        {creditor.open_banking_access   && <span className="px-1.5 py-0.5 bg-cyan-50 text-cyan-600 border border-cyan-200 rounded text-[10px]">Open Banking</span>}
                        {creditor.fraud_claim_risk      && <span className="px-1.5 py-0.5 bg-red-50 text-red-700 border border-red-200 rounded text-[10px]">Fraud Risk</span>}
                      </div>
                    </td>

                    {/* Representative */}
                    <td className="px-3 py-3">
                      <RepBadge rep={creditor.representative} />
                    </td>

                    {/* Trading names */}
                    <td className="px-3 py-3 max-w-[180px]" onClick={e => e.stopPropagation()}>
                      {creditor.trading_names?.length > 0
                        ? <ExpandableText text={creditor.trading_names.join(', ')} maxLen={80} />
                        : <span className="text-gray-300 text-xs">—</span>}
                    </td>

                    {/* Min dividend */}
                    <td className="px-3 py-3 text-xs text-gray-600">
                      {creditor.min_dividend_pence != null && creditor.min_dividend_pence > 0
                        ? <span className="font-medium">{creditor.min_dividend_pence}p/£</span>
                        : <span className="text-gray-300">—</span>}
                    </td>

                    {/* Notes */}
                    <td className="px-3 py-3 max-w-[200px]" onClick={e => e.stopPropagation()}>
                      <ExpandableText text={creditor.blocked_reason} maxLen={100} />
                    </td>

                    {/* Delete (admin only) */}
                    <td className="px-3 py-3 text-right" onClick={e => e.stopPropagation()}>
                      {isAdmin && (
                        <button
                          onClick={() => setDeleteTarget(creditor)}
                          className="p-1.5 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                          title="Delete creditor"
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
                <td colSpan={6} className="px-4 py-12 text-center">
                  <p className="text-sm text-gray-500 font-medium">No creditors found</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {search ? `No creditors match "${search}"` : 'Try clearing your filters'}
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">
        Showing {filtered.length} of {creditors?.length ?? 0} creditors
      </p>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Remove Creditor"
        message={deleteTarget
          ? `Are you sure you want to remove ${deleteTarget.creditor_name}? This cannot be undone.`
          : ''}
        confirmLabel="Remove"
        variant="danger"
        loading={isDeleting}
      />

      {editTarget && (
        <CreditorEditDrawer
          creditor={editTarget}
          onClose={() => setEditTarget(null)}
          readOnly={!canEdit}
        />
      )}
    </div>
  )
}
