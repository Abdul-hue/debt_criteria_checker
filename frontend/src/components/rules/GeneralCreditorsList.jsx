import React, { useState } from 'react'
import { useCreditors } from '../../hooks/useCreditors'
import LoadingSpinner from '../shared/LoadingSpinner'
import CreditorEditDrawer from './CreditorEditDrawer'
import { Search, X, Mail, Phone, User, Calendar, Info } from 'lucide-react'

const STATUS_CONFIG = {
  ACCEPT:         { label: 'Accept',         bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-200' },
  REJECT:         { label: 'Reject',         bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-200'   },
  WILL_CONSIDER:  { label: 'Consider',       bg: 'bg-blue-100',   text: 'text-blue-800',   border: 'border-blue-200'  },
  DO_NOT_VOTE:    { label: 'Do Not Vote',    bg: 'bg-gray-100',   text: 'text-gray-800',   border: 'border-gray-200'  },
  CONDITIONAL_VOTER: { label: 'Conditional', bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-200' },
}

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] ?? STATUS_CONFIG.ACCEPT
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${c.bg} ${c.text} ${c.border}`}>
      {c.label}
    </span>
  )
}

export default function GeneralCreditorsList() {
  const { data: creditors, isLoading, error } = useCreditors()
  const [search, setSearch] = useState('')
  const [editTarget, setEditTarget] = useState(null)

  const uniqueCreditors = Array.from(new Map((creditors ?? []).map(c => [c.id, c])).values())

  const countsBySource = uniqueCreditors.reduce((acc, c) => {
    const s = c.source_sheet || 'None'
    acc[s] = (acc[s] || 0) + 1
    return acc
  }, {})

  const filtered = uniqueCreditors.filter(c => 
    c.source_sheet === 'GENERAL_CREDITOR' && (
      !search || 
      c.creditor_name.toLowerCase().includes(search.toLowerCase()) ||
      (c.criteria_notes && c.criteria_notes.toLowerCase().includes(search.toLowerCase())) ||
      (c.contact_email && c.contact_email.toLowerCase().includes(search.toLowerCase())) ||
      (c.contact_name && c.contact_name.toLowerCase().includes(search.toLowerCase()))
    )
  )

  if (isLoading) return <div className="py-20"><LoadingSpinner message="Loading general creditors…" /></div>

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        Could not load general creditors. Please refresh the page.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Debug Info */}
      <div className="p-2 bg-gray-50 border border-gray-200 rounded text-[10px] text-gray-500 flex gap-4">
        {Object.entries(countsBySource).map(([src, count]) => (
          <span key={src}>{src}: <strong>{count}</strong></span>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="text-sm">
          <span className="font-semibold text-gray-700">{filtered.length}</span>
          <span className="text-gray-500 ml-1">creditors listed</span>
        </div>

        <div className="relative w-full max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search creditors, notes, or contacts..."
            className="w-full pl-8 pr-8 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-xs font-bold text-gray-600 uppercase tracking-wider min-w-[200px]">Creditor</th>
                <th className="px-4 py-3 text-xs font-bold text-gray-600 uppercase tracking-wider w-[120px]">Status</th>
                <th className="px-4 py-3 text-xs font-bold text-gray-600 uppercase tracking-wider min-w-[300px]">Criteria / Notes</th>
                <th className="px-4 py-3 text-xs font-bold text-gray-600 uppercase tracking-wider min-w-[200px]">Contact Info</th>
                <th className="px-4 py-3 text-xs font-bold text-gray-600 uppercase tracking-wider w-[140px]">Last Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.length > 0 ? (
                filtered.map(creditor => (
                  <tr 
                    key={creditor.id}
                    onClick={() => setEditTarget(creditor)}
                    className="hover:bg-blue-50/50 cursor-pointer transition-colors group align-top"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900 group-hover:text-blue-700">{creditor.creditor_name}</div>
                      {creditor.parent_group && (
                        <div className="text-[10px] text-gray-400 mt-0.5 uppercase font-semibold">{creditor.parent_group}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={creditor.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-xs text-gray-600 leading-relaxed line-clamp-3">
                        {creditor.criteria_notes || <span className="text-gray-300 italic">No notes recorded</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="space-y-1.5">
                        {creditor.contact_name && (
                          <div className="flex items-center gap-2 text-xs text-gray-700">
                            <User size={12} className="text-gray-400" />
                            {creditor.contact_name}
                          </div>
                        )}
                        {creditor.contact_email && (
                          <div className="flex items-center gap-2 text-xs text-blue-600 hover:underline">
                            <Mail size={12} className="text-gray-400" />
                            {creditor.contact_email}
                          </div>
                        )}
                        {creditor.contact_phone && (
                          <div className="flex items-center gap-2 text-xs text-gray-700">
                            <Phone size={12} className="text-gray-400" />
                            {creditor.contact_phone}
                          </div>
                        )}
                        {!creditor.contact_name && !creditor.contact_email && !creditor.contact_phone && (
                          <span className="text-gray-300 text-xs">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 text-[11px] text-gray-500 font-medium">
                        <Calendar size={12} className="text-gray-400" />
                        {creditor.raw_updated_criteria || 'Unknown'}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="5" className="px-4 py-12 text-center text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <Info size={24} className="text-gray-300" />
                      <p>No creditors found matching your search.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

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
