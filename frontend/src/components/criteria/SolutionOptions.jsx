import React, { useState } from 'react'
import { Check, X, AlertTriangle, Info, ChevronDown, Loader2, HelpCircle } from 'lucide-react'

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
    accent: 'border-t-emerald-600',
    chip: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    iconWrap: 'bg-emerald-100 text-emerald-700',
    Icon: Check,
  },
  NEEDS_REVIEW: {
    label: 'Check needed',
    accent: 'border-t-amber-500',
    chip: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
    iconWrap: 'bg-amber-100 text-amber-700',
    Icon: AlertTriangle,
  },
  NOT_ELIGIBLE: {
    label: 'Not eligible',
    accent: 'border-t-red-700',
    chip: 'bg-red-50 text-red-700 ring-1 ring-red-200',
    iconWrap: 'bg-red-100 text-red-700',
    Icon: X,
  },
}

// Most useful first: what the customer can do, then what needs checking.
const STATUS_ORDER = ['ELIGIBLE', 'NEEDS_REVIEW', 'NOT_ELIGIBLE']

const REASON_GROUPS = [
  { key: 'reasons', title: 'Why not', Icon: X, box: 'bg-red-50 border-red-100', heading: 'text-red-400', text: 'text-red-800', icon: 'text-red-500' },
  { key: 'to_confirm', title: 'To check', Icon: AlertTriangle, box: 'bg-amber-50 border-amber-100', heading: 'text-amber-500', text: 'text-amber-900', icon: 'text-amber-500' },
  { key: 'notes', title: 'Good to know', Icon: Info, box: 'bg-slate-50 border-slate-100', heading: 'text-slate-400', text: 'text-gray-600', icon: 'text-slate-400' },
]

const isAnswered = (answer) => answer === true || answer === false

const pluralise = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`

// The one line shown on a collapsed card: the most important point first.
const headlineFor = (solution) =>
  solution.reasons?.[0] || solution.to_confirm?.[0] || solution.notes?.[0] || 'Nothing further to check.'

const countsFor = (solution) => [
  solution.reasons?.length && pluralise(solution.reasons.length, 'reason'),
  solution.to_confirm?.length && `${pluralise(solution.to_confirm.length, 'point')} to check`,
  solution.notes?.length && pluralise(solution.notes.length, 'note'),
].filter(Boolean).join(' · ')

function ReasonGroup({ title, items, Icon, box, heading, text, icon }) {
  if (!items?.length) return null
  return (
    <div className={`rounded-lg border p-3 ${box}`}>
      <div className={`text-[9px] font-bold uppercase tracking-widest mb-1.5 ${heading}`}>{title}</div>
      <ul className="space-y-1.5">
        {items.map((item, idx) => (
          <li key={idx} className={`flex items-start gap-1.5 text-xs leading-relaxed ${text}`}>
            <Icon className={`w-3.5 h-3.5 flex-shrink-0 mt-0.5 ${icon}`} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SolutionCard({ solution, isOpen, onToggle }) {
  const meta = STATUS_META[solution.status] || STATUS_META.NEEDS_REVIEW
  const counts = countsFor(solution)
  const detailId = `solution-detail-${solution.code}`
  return (
    <div
      className={`rounded-xl bg-white shadow-sm border border-gray-200 border-t-4 ${meta.accent} transition-shadow hover:shadow-md`}
      data-testid={`solution-${solution.code}`}
    >
      <button
        type="button"
        onClick={onToggle}
        disabled={!counts}
        aria-expanded={isOpen}
        aria-controls={detailId}
        className="w-full text-left p-4 rounded-xl disabled:cursor-default focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-navy/30"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${meta.iconWrap}`}>
              <meta.Icon className="w-4 h-4" />
            </span>
            <h3 className="text-sm font-bold text-brand-navy leading-snug">{solution.label}</h3>
          </div>
          <span className={`flex-shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${meta.chip}`}>
            {meta.label}
          </span>
        </div>
        {!isOpen && (
          <p className="mt-3 text-xs leading-relaxed text-gray-600 line-clamp-2">{headlineFor(solution)}</p>
        )}
        {counts && (
          <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-gray-400">
            <span>{counts}</span>
            <span className="inline-flex items-center gap-1 font-semibold text-brand-navy">
              {isOpen ? 'Hide details' : 'Show details'}
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </span>
          </div>
        )}
      </button>
      {isOpen && (
        <div id={detailId} className="px-4 pb-4 space-y-2">
          {REASON_GROUPS.map((group) => (
            <ReasonGroup key={group.key} items={solution[group.key]} {...group} />
          ))}
        </div>
      )}
    </div>
  )
}

function AnswerToggle({ field, label, answer, disabled, onAnswerChange }) {
  const labelId = `solution-question-${field}`
  return (
    <div className={`flex items-center justify-between gap-3 rounded-lg border bg-white px-3 py-2 ${isAnswered(answer) ? 'border-gray-200' : 'border-amber-200'}`}>
      <span id={labelId} className="text-xs text-gray-700">{label}</span>
      <div className="flex flex-shrink-0 items-center gap-2">
        <div role="radiogroup" aria-labelledby={labelId} className="inline-flex rounded-md border border-gray-300 overflow-hidden">
          {[{ value: true, text: 'Yes' }, { value: false, text: 'No' }].map(({ value, text }) => {
            const selected = answer === value
            return (
              <button
                key={text}
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={disabled}
                onClick={() => onAnswerChange(field, value)}
                className={`px-3 py-1 text-xs font-semibold transition-colors disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-navy/30 ${
                  selected ? 'bg-brand-navy text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
                } ${value === false ? 'border-l border-gray-300' : ''}`}
              >
                {text}
              </button>
            )
          })}
        </div>
        <button
          type="button"
          onClick={() => onAnswerChange(field, null)}
          disabled={disabled || !isAnswered(answer)}
          className="text-[11px] text-gray-400 hover:text-gray-600 disabled:invisible"
        >
          Clear
        </button>
      </div>
    </div>
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
  const [openCodes, setOpenCodes] = useState(() => new Set())
  if (!solutions.length) return null

  const toggle = (code) => setOpenCodes((prev) => {
    const next = new Set(prev)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    return next
  })

  const sorted = [...solutions].sort(
    (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
  )
  const counts = STATUS_ORDER
    .map((status) => ({ status, count: solutions.filter((s) => s.status === status).length }))
    .filter(({ count }) => count > 0)
  const answeredCount = SOLUTION_QUESTIONS.filter(({ field }) => isAnswered(answers[field])).length
  const allAnswered = answeredCount === SOLUTION_QUESTIONS.length

  return (
    <section className="mt-6 bg-white rounded-2xl shadow-md border border-gray-100 p-6" aria-labelledby="solution-options-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="solution-options-heading" className="font-display text-lg font-bold text-brand-navy">
            Potential solutions
          </h2>
          <p className="text-xs text-gray-500 mt-1">
            The customer can be eligible for more than one solution. These update as income, spending and debts change.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" aria-live="polite">
          {disabled ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
              <Loader2 className="w-3 h-3 animate-spin" />
              Updating…
            </span>
          ) : counts.map(({ status, count }) => {
            const meta = STATUS_META[status]
            return (
              <span key={status} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${meta.chip}`}>
                <meta.Icon className="w-3 h-3" />
                {count} {meta.label.toLowerCase()}
              </span>
            )
          })}
        </div>
      </div>

      <div className={`mt-5 rounded-xl border p-4 ${allAnswered ? 'border-gray-200 bg-slate-50' : 'border-amber-200 bg-amber-50/60'}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-1.5 text-xs font-bold text-brand-navy">
            {allAnswered
              ? <Check className="w-4 h-4 text-emerald-600" />
              : <HelpCircle className="w-4 h-4 text-amber-600" />}
            {allAnswered ? 'Customer questions answered' : 'Ask the customer to confirm the results'}
          </h3>
          <span className="text-[11px] text-gray-500">{answeredCount} of {SOLUTION_QUESTIONS.length} answered</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-3">
          {SOLUTION_QUESTIONS.map(({ field, label }) => (
            <AnswerToggle
              key={field}
              field={field}
              label={label}
              answer={answers[field]}
              disabled={disabled}
              onAnswerChange={onAnswerChange}
            />
          ))}
        </div>
      </div>

      <div className={`grid grid-cols-1 md:grid-cols-2 items-start gap-4 mt-5 transition-opacity ${disabled ? 'opacity-60' : ''}`}>
        {sorted.map((solution) => (
          <SolutionCard
            key={solution.code}
            solution={solution}
            isOpen={openCodes.has(solution.code)}
            onToggle={() => toggle(solution.code)}
          />
        ))}
      </div>
    </section>
  )
}
