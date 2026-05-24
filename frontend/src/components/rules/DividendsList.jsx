import React, { useState } from 'react'
import { useCreditors } from '../../hooks/useCreditors'
import { useAuth } from '../../context/AuthContext'
import LoadingSpinner from '../shared/LoadingSpinner'
import CreditorEditDrawer from './CreditorEditDrawer'
import { Search, X, ChevronDown, ChevronUp } from 'lucide-react'

// Representative colours
const REP_CONFIG = {
  WATCH:         { label: 'Watch',          bg: 'bg-blue-100',   text: 'text-blue-800',   border: 'border-blue-200',   dot: 'bg-blue-500'   },
  TIX:           { label: 'TIX',            bg: 'bg-indigo-100', text: 'text-indigo-800', border: 'border-indigo-200', dot: 'bg-indigo-500' },
  EVOLVE:        { label: 'Evolve',         bg: 'bg-teal-100',   text: 'text-teal-800',   border: 'border-teal-200',   dot: 'bg-teal-500'   },
  EVERYDAY_LOANS:{ label: 'Everyday Loans', bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-200', dot: 'bg-orange-500' },
  NONE:          { label: 'No Rep',         bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-200',   dot: 'bg-gray-400'   },
}

const rcfg = (rep) => REP_CONFIG[rep] ?? { label: rep, bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200', dot: 'bg-gray-300' }

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

export default function DividendsList() {
  const { data: creditors, isLoading, error } = useCreditors()
  const [search, setSearch] = useState('')
  const [editTarget, setEditTarget] = useState(null)

  // Filter for creditors that have dividend info
  const dividendCreditors = (creditors ?? []).filter(c => 
    (c.min_dividend_pence !== null && c.min_dividend_pence !== undefined) || 
    (c.dividend_notes && c.dividend_notes.trim() !== '') ||
    c.source_sheet === 'DIVIDEND'
  )

  const filtered = dividendCreditors.filter(c => 
    !search || 
    c.creditor_name.toLowerCase().includes(search.toLowerCase()) ||
    (c.dividend_notes && c.dividend_notes.toLowerCase().includes(search.toLowerCase())) ||
    (c.representative && c.representative.toLowerCase().includes(search.toLowerCase()))
  )

  if (isLoading) return <div className="py-20"><LoadingSpinner message="Loading dividend data…" /></div>

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        Could not load dividend data. Please refresh the page or contact support.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="flex flex-wrap gap-3 text-sm">
        <span className="font-semibold text-gray-700">{dividendCreditors.length} creditors with dividend requirements</span>
      </div>

      {/* Search */}
      <div className="flex flex-col md:flex-row md:items-start gap-3">
        <div className="relative w-full max-w-sm shrink-0">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by creditor or notes…"
            className="w-full pl-8 pr-8 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-400">
        This list shows all creditors that have specific dividend requirements or notes. Click a row to edit.
      </p>

      {/* Table */}
      <div className="border border-gray-200 rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <th className="pl-4 pr-3 py-3 min-w-[200px]">Creditor Name</th>
              <th className="px-3 py-3 w-[150px]">Representative</th>
              <th className="px-3 py-3 w-[120px]">Div Required</th>
              <th className="px-3 py-3 min-w-[300px]">Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length > 0 ? (
              filtered.map(creditor => (
                <tr
                  key={creditor.id}
                  onClick={() => setEditTarget(creditor)}
                  className="hover:bg-blue-50 cursor-pointer transition-colors align-top group"
                >
                  <td className="pl-4 pr-3 py-3">
                    <div className="flex flex-col gap-1">
                      <span className="font-medium text-gray-900 text-sm group-hover:text-blue-700 transition-colors">
                        {creditor.creditor_name}
                      </span>
                      {creditor.source_sheet === 'DIVIDEND' && (
                        <span className="w-fit px-1.5 py-0.5 bg-blue-50 text-blue-600 border border-blue-100 rounded text-[10px] font-medium uppercase tracking-tight">
                          Dividend Source
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <RepBadge rep={creditor.representative} />
                  </td>
                  <td className="px-3 py-3 font-medium text-gray-700">
                    {creditor.min_dividend_pence != null ? `${creditor.min_dividend_pence}p` : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-3 py-3">
                    <ExpandableText text={creditor.dividend_notes} maxLen={150} />
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="4" className="px-4 py-8 text-center text-gray-500">
                  No creditors found matching your search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Edit Drawer */}
      {editTarget && (
        <CreditorEditDrawer
          creditor={editTarget}
          isOpen={!!editTarget}
          onClose={() => setEditTarget(null)}
        />
      )}
    </div>
  )
}
