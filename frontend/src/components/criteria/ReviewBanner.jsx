import React from 'react'
import { AlertTriangle } from 'lucide-react'

export default function ReviewBanner({ flaggedCriteria = [], criteriaResults = [] }) {
  if (!flaggedCriteria.length) return null

  const flaggedNames = flaggedCriteria
    .map(id => criteriaResults.find(r => r.criterion_id === id)?.name)
    .filter(Boolean)
    .join(', ')

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
      <div className="flex gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
        <div>
          <h3 className="text-sm font-semibold text-amber-900">Manual review required</h3>
          <p className="mt-1 text-sm text-amber-700">
            Flags detected: {flaggedNames}
          </p>
        </div>
      </div>
    </div>
  )
}
