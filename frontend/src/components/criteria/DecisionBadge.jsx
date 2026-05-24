import React from 'react'

const DECISION_STYLES = {
  ELIGIBLE: 'bg-green-100 text-green-800 border-green-200',
  INELIGIBLE: 'bg-red-100 text-red-800 border-red-200',
  REFERRED: 'bg-amber-100 text-amber-800 border-amber-200',
  INCOMPLETE: 'bg-slate-100 text-slate-700 border-slate-200',
}

export default function DecisionBadge({ decision }) {
  const style = DECISION_STYLES[decision] || DECISION_STYLES.INCOMPLETE
  
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${style}`}>
      {decision?.replace('_', ' ') || 'UNKNOWN'}
    </span>
  )
}
