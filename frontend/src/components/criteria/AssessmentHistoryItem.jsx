import React from 'react'
import { Calendar, User, AlertCircle } from 'lucide-react'
import DecisionBadge from './DecisionBadge'

/**
 * A single row representing a past assessment in the history list.
 * @param {Object} props.item - The history item data
 */
export default function AssessmentHistoryItem({ item }) {
  const {
    decision,
    evaluated_at,
    evaluated_by,
    recommended_solution,
    flagged_criteria_count
  } = item

  const formattedDate = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(evaluated_at))

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 hover:border-slate-300 transition-colors shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <DecisionBadge decision={decision} />
        {flagged_criteria_count > 0 && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-amber-50 text-amber-700 text-xs font-medium rounded-md border border-amber-100">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>{flagged_criteria_count} Flag{flagged_criteria_count !== 1 ? 's' : ''}</span>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-sm font-semibold text-slate-800">
          {recommended_solution?.label || 'No recommendation'}
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5" />
            <span>{formattedDate}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <User className="w-3.5 h-3.5" />
            <span>{evaluated_by}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
