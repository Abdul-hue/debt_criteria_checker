import React, { useState } from 'react'
import { CheckCircle2, XCircle, AlertCircle, ChevronDown, ChevronUp, MinusCircle } from 'lucide-react'

const RESULT_ICONS = {
  PASS: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  FAIL: <XCircle className="w-4 h-4 text-red-500" />,
  FLAG: <AlertCircle className="w-4 h-4 text-amber-500" />,
  NA: <MinusCircle className="w-4 h-4 text-slate-400" />,
}

const ROW_STYLES = {
  PASS: 'bg-white text-slate-600',
  FAIL: 'bg-red-50 text-red-900 border-red-100',
  FLAG: 'bg-amber-50 text-amber-900 border-amber-100',
  NA: 'bg-slate-50 text-slate-400 border-slate-100',
}

const isNotApplicable = (message) => {
  const msg = (message || '').toLowerCase()
  return msg.includes('not applicable') || 
         msg.includes('not required') || 
         msg.includes('not evaluated') || 
         msg.includes('not a creditor')
}

export default function CriteriaResultsList({ results = [] }) {
  const [isOpen, setIsOpen] = useState(true)

  if (!results.length) return null

  return (
    <div className="border border-slate-200 rounded-lg">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 transition-colors rounded-t-lg"
      >
        <span className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
          Criteria breakdown ({results.length})
        </span>
        {isOpen ? <ChevronUp size={18} className="text-slate-400" /> : <ChevronDown size={18} className="text-slate-400" />}
      </button>

      {isOpen && (
        <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto overscroll-contain bg-white rounded-b-lg">
          {results.map((item, idx) => {
            const na = isNotApplicable(item.message)
            const resultType = na ? 'NA' : item.result
            
            return (
              <div 
                key={item.criterion_id || idx} 
                className={`p-4 flex gap-3 border-l-4 ${resultType === 'PASS' ? 'border-transparent' : resultType === 'FAIL' ? 'border-red-400' : resultType === 'FLAG' ? 'border-amber-400' : 'border-slate-300'} ${ROW_STYLES[resultType] || ROW_STYLES.PASS}`}
              >
                <div className="shrink-0 mt-0.5">
                  {RESULT_ICONS[resultType]}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-bold">{item.name}</span>
                    {item.value_checked && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200/50 text-slate-500 font-mono">
                        {item.value_checked}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm opacity-90 leading-snug">
                    {item.message}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
