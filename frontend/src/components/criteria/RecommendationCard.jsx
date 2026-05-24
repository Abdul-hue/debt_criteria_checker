import React, { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

const CONFIDENCE_STYLES = {
  HIGH: 'bg-green-100 text-green-700',
  MEDIUM: 'bg-amber-100 text-amber-700',
  LOW: 'bg-slate-100 text-slate-600',
}

export default function RecommendationCard({ recommendation, alternatives = [] }) {
  const [expanded, setExpanded] = useState(false)

  if (!recommendation) return null

  return (
    <div className="space-y-4 mb-6">
      {/* Primary Recommendation */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-slate-900">{recommendation.label}</h3>
          <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider ${CONFIDENCE_STYLES[recommendation.confidence] || CONFIDENCE_STYLES.LOW}`}>
            {recommendation.confidence} Confidence
          </span>
        </div>
        <p className="text-sm text-slate-600 leading-relaxed">
          {recommendation.rationale}
        </p>

        {/* Alternatives Collapsible */}
        {alternatives.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors uppercase tracking-tight"
            >
              Alternative options
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            
            {expanded && (
              <div className="mt-3 space-y-3">
                {alternatives.map((alt, idx) => (
                  <div key={idx} className="bg-slate-50 rounded p-3 border border-slate-100">
                    <h4 className="text-sm font-semibold text-slate-800">{alt.label}</h4>
                    <p className="mt-1 text-xs text-slate-500">{alt.rationale}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
