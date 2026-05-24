import React, { useState } from 'react'
import { useDecisions, useDeleteDecision } from '../../hooks/useDecisions'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import ConfirmDialog from '../../components/shared/ConfirmDialog'
import EditDrawer from '../../components/shared/EditDrawer'
import CriteriaReport from '../../components/criteria/CriteriaReport'
import { CheckSquare, Trash2, Eye, Filter, Search } from 'lucide-react'

function DecisionBadge({ decision }) {
  const map = {
    ELIGIBLE: { label: 'Eligible', color: 'bg-green-100 text-green-800' },
    INELIGIBLE: { label: 'Does Not Qualify', color: 'bg-red-100 text-red-800' },
    REFERRED: { label: 'Needs Review', color: 'bg-amber-100 text-amber-800' },
    INCOMPLETE: { label: 'Incomplete', color: 'bg-gray-100 text-gray-600' },
  }
  
  // Fallback mapping for legacy or alternative formats
  const normalized = decision?.toUpperCase() || 'INCOMPLETE'
  const config = map[normalized] || { label: decision, color: 'bg-slate-100 text-slate-700' }
  
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${config.color}`}>
      {config.label}
    </span>
  )
}

function StatBar({ result }) {
  if (!result || !result.criteria_results) return null
  
  const stats = result.criteria_results.reduce((acc, item) => {
    if (item.result === 'FAIL') acc.failed++
    else if (item.result === 'FLAG') acc.flagged++
    else if (item.result === 'PASS') acc.passed++
    return acc
  }, { failed: 0, flagged: 0, passed: 0 })

  return (
    <div className="flex items-center gap-3 mt-1">
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-red-500" />
        <span className="text-xs text-slate-500 font-medium">{stats.failed} blockers</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-amber-500" />
        <span className="text-xs text-slate-500 font-medium">{stats.flagged} flagged</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 rounded-full bg-green-500" />
        <span className="text-xs text-slate-500 font-medium">{stats.passed} passed</span>
      </div>
    </div>
  )
}

function DecisionCard({ decision, onView, onDelete, isAdmin }) {
  const dateStr = decision.created_at ? new Date(decision.created_at).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }) : '—'

  // Extract reference from result_json if available (Change 3)
  const aryzaRef = decision.result_json?.application_id || decision.aryza_reference || '—'
  const solution = decision.result_json?.recommended_solution?.label || decision.recommended_solution || '—'
  const decisionStatus = decision.result_json?.decision || (decision.passes_all_hard_blocks ? 'ELIGIBLE' : 'INELIGIBLE')

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-all group cursor-pointer" onClick={() => onView(decision)}>
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 leading-tight">
            {decision.client_name || 'Unknown Client'}
          </h3>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-sm text-slate-500 font-medium">Ref: {decision.id.slice(0, 8)}</span>
            <span className="text-slate-300">·</span>
            <span className="text-sm text-slate-500 font-mono">Aryza: {aryzaRef}</span>
            <span className="text-slate-300">·</span>
            <span className="text-sm text-slate-500">{dateStr}</span>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onView(decision)
          }}
          className="text-sm font-semibold text-slate-900 bg-slate-50 hover:bg-slate-100 px-4 py-2 rounded-lg border border-slate-200 transition-colors"
        >
          View Full Report
        </button>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <DecisionBadge decision={decisionStatus} />
        <span className="text-sm font-medium text-slate-700">{solution}</span>
        <span className="text-slate-300">·</span>
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Triggered by {decision.triggered_by || 'System'}
        </span>
      </div>

      <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
        <StatBar result={decision.result_json} />
        {isAdmin && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete(decision)
            }}
            className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>
    </div>
  )
}

export default function DecisionsPage() {
  const { isAdmin } = useAuth()
  const toast = useToast()
  const { data: decisions = [], isLoading } = useDecisions()
  const { mutateAsync: deleteDecision, isPending: isDeleting } = useDeleteDecision()

  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('ALL')
  const [viewTarget, setViewTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)

  if (isLoading) return <LoadingSpinner />

  const filtered = decisions.filter((d) => {
    const matchesSearch = search === '' ||
      (d.aryza_reference ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (d.client_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (d.triggered_by ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (d.result_json?.application_id ?? '').toLowerCase().includes(search.toLowerCase())

    const decisionStatus = d.result_json?.decision || (d.passes_all_hard_blocks ? 'ELIGIBLE' : 'INELIGIBLE')
    const matchesFilter = filterType === 'ALL' || decisionStatus === filterType

    return matchesSearch && matchesFilter
  })

  const handleDelete = async () => {
    try {
      await deleteDecision(deleteTarget.id)
      toast.success('Decision deleted', `Decision record has been removed.`)
      setDeleteTarget(null)
    } catch (err) {
      toast.error('Delete failed', err?.response?.data?.detail ?? err.message)
    }
  }

  return (
    <div className="p-4 sm:p-8 bg-slate-50 min-h-screen">
      <div className="max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Assessments</h1>
          <p className="mt-2 text-slate-500 font-medium">History of all criteria decisions and case reports.</p>
        </div>

        {/* Filters & Search */}
        <div className="flex flex-col sm:flex-row gap-4 mb-8">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by client name, reference or advisor..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/5 transition-all shadow-sm"
            />
          </div>
          <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-1 shadow-sm">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-transparent border-none text-sm font-semibold text-slate-700 focus:ring-0 cursor-pointer py-1.5"
            >
              <option value="ALL">All Decisions</option>
              <option value="ELIGIBLE">Eligible</option>
              <option value="INELIGIBLE">Does Not Qualify</option>
              <option value="REFERRED">Needs Review</option>
              <option value="INCOMPLETE">Incomplete</option>
            </select>
          </div>
        </div>

        {/* List */}
        {filtered.length === 0 ? (
          <div className="bg-white border border-dashed border-slate-300 rounded-2xl py-20 flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-4">
              <CheckSquare className="w-8 h-8 text-slate-300" />
            </div>
            <h3 className="text-lg font-bold text-slate-900">No assessments found</h3>
            <p className="text-slate-500 max-w-xs mx-auto mt-1">
              {search || filterType !== 'ALL' 
                ? "Try adjusting your filters or search terms." 
                : "No assessments have been run yet."}
            </p>
          </div>
        ) : (
          <div className="grid gap-4">
            {filtered.map((d) => (
              <DecisionCard 
                key={d.id} 
                decision={d} 
                onView={setViewTarget} 
                onDelete={setDeleteTarget}
                isAdmin={isAdmin}
              />
            ))}
          </div>
        )}
      </div>

      {/* View Drawer */}
      <EditDrawer
        isOpen={!!viewTarget}
        onClose={() => setViewTarget(null)}
        title="Case Report"
        subtitle={viewTarget ? `${viewTarget.client_name} · Ref: ${viewTarget.result_json?.application_id || viewTarget.aryza_reference}` : ''}
        width="max-w-2xl"
      >
        {viewTarget && (
          <div className="divide-y divide-slate-100">
            {viewTarget.result_json ? (
              <CriteriaReport result={viewTarget.result_json} />
            ) : (
              <div className="p-8 text-center">
                <p className="text-slate-500">Full report not available for this record.</p>
                <div className="mt-4 text-left bg-slate-50 p-4 rounded-lg">
                  <h4 className="text-xs font-bold uppercase text-slate-400 mb-2">Basic Metadata</h4>
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <dt className="text-slate-400">Solution</dt>
                      <dd className="font-semibold">{viewTarget.recommended_solution}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">Status</dt>
                      <dd className="font-semibold">{viewTarget.passes_all_hard_blocks ? 'Pass' : 'Fail'}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            )}
          </div>
        )}
      </EditDrawer>

      {/* Delete Confirm */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete Decision"
        message={deleteTarget ? `Are you sure you want to delete this assessment record? This cannot be undone.` : ''}
        confirmLabel="Delete"
        variant="danger"
        loading={isDeleting}
      />
    </div>
  )
}
