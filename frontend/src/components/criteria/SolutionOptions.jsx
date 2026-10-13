import React from 'react'
import { Check, X, AlertTriangle, Info } from 'lucide-react'

// Advisor-answered questions for the DRO / Bankruptcy criteria that Aryza
// holds no data for. Kept in sync with SOLUTION_CHECKLIST_FIELDS in
// debt_app/engine/criteria.py. Each answer is true / false / null (not answered).
export const SOLUTION_QUESTIONS = [
  { field: 'assets_over_2000', label: 'Assets and savings worth more than £2,000?' },
  { field: 'england_wales_connection', label: 'Lived or worked in England or Wales in the last 3 years?' },
  { field: 'currently_insolvent', label: 'Currently bankrupt, under an interim order or in an IVA?' },
  { field: 'dro_in_last_6_years', label: 'Had a Debt Relief Order in the last 6 years?' },
]

export const DEFAULT_SOLUTION_CHECKLIST = Object.fromEntries(
  SOLUTION_QUESTIONS.map(({ field }) => [field, null])
)

const STATUS_META = {
  ELIGIBLE: {
    label: 'Eligible',
    card: 'border-emerald-300 bg-emerald-50',
    chip: 'bg-emerald-100 text-emerald-800',
    Icon: Check,
  },
  NEEDS_REVIEW: {
    label: 'Check needed',
    card: 'border-amber-300 bg-amber-50',
    chip: 'bg-amber-100 text-amber-800',
    Icon: AlertTriangle,
  },
  NOT_ELIGIBLE: {
    label: 'Not eligible',
    card: 'border-gray-200 bg-gray-50',
    chip: 'bg-red-100 text-red-700',
    Icon: X,
  },
}

const toSelectValue = (answer) => (answer === true ? 'yes' : answer === false ? 'no' : '')
const fromSelectValue = (value) => (value === 'yes' ? true : value === 'no' ? false : null)

function ReasonList({ items, Icon, className }) {
  if (!items?.length) return null
  return (
    <ul className="space-y-1">
      {items.map((text, idx) => (
        <li key={idx} className={`flex items-start gap-1.5 text-xs ${className}`}>
          <Icon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span>{text}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Every debt solution the customer may be eligible for, side by side —
 * more than one can be eligible at once. Answers to the advisor questions
 * re-run the assessment (handled by the page via onAnswerChange).
 */
export default function SolutionOptions({
  solutions = [],
  answers = DEFAULT_SOLUTION_CHECKLIST,
  onAnswerChange = () => {},
  disabled = false,
}) {
  if (!solutions.length) return null

  return (
    <section className="mt-6 bg-white rounded-2xl shadow-md border border-gray-100 p-6" aria-labelledby="solution-options-heading">
      <h2 id="solution-options-heading" className="font-display text-lg font-bold text-brand-navy">
        Potential solutions
      </h2>
      <p className="text-xs text-gray-500 mt-1">
        The customer can be eligible for more than one solution. These update as income, spending and debts change.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {solutions.map((solution) => {
          const meta = STATUS_META[solution.status] || STATUS_META.NEEDS_REVIEW
          return (
            <div key={solution.code} className={`rounded-xl border-2 p-4 ${meta.card}`} data-testid={`solution-${solution.code}`}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-gray-800">{solution.label}</h3>
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${meta.chip}`}>
                  <meta.Icon className="w-3 h-3" />
                  {meta.label}
                </span>
              </div>
              <div className="mt-3 space-y-2">
                <ReasonList items={solution.reasons} Icon={X} className="text-red-800" />
                <ReasonList items={solution.to_confirm} Icon={AlertTriangle} className="text-amber-900" />
                <ReasonList items={solution.notes} Icon={Info} className="text-gray-600" />
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-5 pt-4 border-t border-gray-100">
        <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Questions for the customer</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 mt-3">
          {SOLUTION_QUESTIONS.map(({ field, label }) => (
            <label key={field} className="flex items-center justify-between gap-3 text-xs text-gray-700">
              <span>{label}</span>
              <select
                className="border border-gray-300 rounded-md px-2 py-1 text-xs bg-white"
                value={toSelectValue(answers[field])}
                disabled={disabled}
                onChange={(e) => onAnswerChange(field, fromSelectValue(e.target.value))}
              >
                <option value="">Not answered</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>
          ))}
        </div>
      </div>
    </section>
  )
}
