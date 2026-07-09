import React from 'react'
import Spinner from './Spinner'

/**
 * Displays a read-only CRM Vote Summary component
 */
export default function CrmVoteSummary({ summary, isLoading }) {
  if (isLoading) {
    return (
      <div className="mb-4">
        <p className="text-xs font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          CRM Vote Summary
        </p>
        <p className="text-xs text-gray-400">Loading CRM vote summary...</p>
      </div>
    )
  }

  if (!summary) {
    return (
      <div className="mb-4">
        <p className="text-xs font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          CRM Vote Summary
        </p>
        <p className="text-xs text-gray-400">No CRM vote summary available.</p>
      </div>
    )
  }

  const getOutcomeColor = (outcome) => {
    if (!outcome) return 'text-gray-500'
    if (outcome === 'accepted') return 'text-green-700'
    if (outcome === 'rejected') return 'text-red-600'
    if (outcome === 'modified') return 'text-amber-700'
    return 'text-gray-700'
  }

  const formatOutcome = (outcome) => {
    if (!outcome) return '—'
    return outcome.charAt(0).toUpperCase() + outcome.slice(1)
  }

  return (
    <div className="mb-4">
      <p className="text-xs font-semibold text-gray-700 mb-3 uppercase tracking-wide">
        CRM Vote Summary
      </p>
      
      <div className="p-3 bg-blue-50 border border-blue-100 rounded-md">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <span className="text-xs text-gray-500 block mb-0.5">Total Votes</span>
            <span className="text-sm font-semibold text-gray-800">{summary.total_votes}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block mb-0.5">CRM Rows</span>
            <span className="text-sm font-semibold text-gray-800">{summary.crm_rows_covered}</span>
          </div>
        </div>
        
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div>
            <span className="text-xs text-gray-500 block mb-0.5">Accepted</span>
            <span className="text-sm font-semibold text-green-700">
              {summary.accepted_count !== null ? summary.accepted_count : '—'}
            </span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block mb-0.5">Rejected</span>
            <span className="text-sm font-semibold text-red-600">
              {summary.rejected_count !== null ? summary.rejected_count : '—'}
            </span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block mb-0.5">Modified</span>
            <span className="text-sm font-semibold text-amber-700">
              {summary.modified_count !== null ? summary.modified_count : '—'}
            </span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block mb-0.5">POD</span>
            <span className="text-sm font-semibold text-blue-700">
              {summary.pod_count !== null ? summary.pod_count : '—'}
            </span>
          </div>
        </div>

        <div className="border-t border-blue-100 pt-3 mt-2">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-xs text-gray-500 block mb-0.5">Latest Outcome</span>
              <span className={`text-sm font-semibold ${getOutcomeColor(summary.latest_vote_outcome)}`}>
                {formatOutcome(summary.latest_vote_outcome)}
              </span>
            </div>
            <div>
              <span className="text-xs text-gray-500 block mb-0.5">Latest Date</span>
              <span className="text-sm font-semibold text-gray-800">
                {summary.latest_vote_date ? new Date(summary.latest_vote_date).toLocaleDateString('en-GB') : '—'}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-2 pt-2 border-t border-blue-100">
          <span className="text-xs text-gray-400">
            Last synced: {new Date(summary.last_synced_at).toLocaleString('en-GB')}
          </span>
        </div>
      </div>
    </div>
  )
}
