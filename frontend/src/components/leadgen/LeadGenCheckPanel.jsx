import { useEffect, useId, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  AlertTriangle, CheckCircle2, ChevronDown, CircleDashed, FileSearch, FileText, Info, Loader2, Search, Upload, XCircle,
} from 'lucide-react'
import { apiErrorMessage, useLeadGenCheck, useLeadGenCreditReportStatus } from '../../hooks/useLeadGen'
import { Button, Card, Field, TextInput, TONES } from './ui.jsx'
import { formatDay, formatDayTime } from './format.js'

/** Backend outcome codes -> display tone. Codes and labels come from the API unchanged. */
const OUTCOME_TONE = {
  POTENTIALLY_SUITABLE: 'success',
  NEEDS_REVIEW: 'warning',
  NOT_SUITABLE: 'danger',
  NOT_ASSESSED: 'neutral',
  REFER: 'warning',
  REVIEW_REQUIRED: 'warning',
}

const OVERALL_TONE = {
  POTENTIALLY_SUITABLE: 'success',
  DRO_REFER: 'warning',
  DOES_NOT_MEET_CRITERIA: 'danger',
  REVIEW_REQUIRED: 'warning',
}

/** "IVA — Potentially suitable" -> ["IVA", "Potentially suitable"]; display only. */
function splitOutcomeLabel(label, fallbackName) {
  const i = (label || '').indexOf(' — ')
  return i > 0 ? [label.slice(0, i), label.slice(i + 3)] : [fallbackName, label]
}

function SectionLabel({ children, count }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <h3 className="text-sm font-semibold text-slate-900">{children}</h3>
      {count > 0 && (
        <span className="rounded-full bg-slate-100 px-1.5 text-xs font-medium tabular-nums text-slate-600" aria-label={`${count} items`}>
          {count}
        </span>
      )}
    </div>
  )
}

function OutcomeRow({ name, outcome }) {
  if (!outcome) return null
  const tone = TONES[OUTCOME_TONE[outcome.code] || 'neutral']
  const { Icon } = tone
  const [label, status] = splitOutcomeLabel(outcome.label, name)
  return (
    <li className="flex flex-col gap-1 px-3.5 py-3 sm:flex-row sm:items-center sm:gap-4">
      <span className="text-sm font-semibold text-slate-900 sm:w-40 sm:shrink-0">{label}</span>
      <span className={clsx('flex items-start gap-1.5 text-sm font-medium', tone.text)}>
        <Icon size={16} aria-hidden="true" className={clsx('mt-0.5 shrink-0', tone.icon)} />
        <span>{status}</span>
      </span>
    </li>
  )
}

/** A reason that opens to show the engine's plain-English explanation. */
function ExpandableItem({ text, detail, tone, Icon }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left text-sm text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-500"
      >
        <Icon size={16} aria-hidden="true" className={clsx('mt-0.5 shrink-0', tone.icon)} />
        <span className="flex-1">{text}</span>
        <ChevronDown
          size={16}
          aria-hidden="true"
          className={clsx('mt-0.5 shrink-0 text-slate-400 transition-transform', open && 'rotate-180')}
        />
      </button>
      <div id={panelId} hidden={!open} className={clsx('pb-3 pl-10 pr-3.5 text-sm', tone.text)}>
        {detail}
      </div>
    </li>
  )
}

/** Lists longer than this show the first few and a "Show N more" button. */
const VISIBLE_ITEMS = 3

function ItemList({ title, items, tone, Icon, renderText = (r) => r.text, getKey = (r) => r.code, note }) {
  const [showAll, setShowAll] = useState(false)
  if (!items || items.length === 0) return null
  const t = TONES[tone]
  const expandable = items.some((r) => r?.detail)
  const hidden = showAll ? 0 : Math.max(items.length - VISIBLE_ITEMS, 0)
  const visible = hidden ? items.slice(0, VISIBLE_ITEMS) : items
  return (
    <div>
      <SectionLabel count={items.length}>{title}</SectionLabel>
      {note && <p className="-mt-1 mb-2 text-xs text-slate-500">{note}</p>}
      {expandable && <p className="-mt-1 mb-2 text-xs text-slate-500">Select a reason to see why.</p>}
      <ul className="rounded-md border border-slate-200 divide-y divide-slate-100">
        {visible.map((r) => (r?.detail ? (
          <ExpandableItem key={getKey(r)} text={renderText(r)} detail={r.detail} tone={t} Icon={Icon} />
        ) : (
          <li key={getKey(r)} className="flex items-start gap-2.5 px-3.5 py-2.5 text-sm text-slate-800">
            <Icon size={16} aria-hidden="true" className={clsx('mt-0.5 shrink-0', t.icon)} />
            <span>{renderText(r)}</span>
          </li>
        )))}
      </ul>
      {items.length > VISIBLE_ITEMS && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-1.5 rounded text-xs font-medium text-slate-600 underline-offset-4 hover:text-slate-900 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
        >
          {hidden ? `Show ${hidden} more` : 'Show fewer'}
        </button>
      )}
    </div>
  )
}

const DETAIL_KIND = {
  reason: { tone: 'danger', Icon: XCircle },
  confirm: { tone: 'warning', Icon: AlertTriangle },
  note: { tone: 'neutral', Icon: Info },
}

/** A solution's reasons, details to confirm and notes, from the engine's own solution card. */
function SolutionDetail({ title, outcome }) {
  const [showAll, setShowAll] = useState(false)
  if (!outcome || outcome.code === 'NOT_ASSESSED') return null
  const rows = [
    ...(outcome.reasons || []).map((r) => ({ key: r.code, text: r.text, kind: 'reason' })),
    ...(outcome.to_confirm || []).map((text, i) => ({ key: `confirm-${i}`, text, kind: 'confirm' })),
    ...(outcome.notes || []).map((text, i) => ({ key: `note-${i}`, text, kind: 'note' })),
  ]
  if (rows.length === 0) return null
  const hidden = showAll ? 0 : Math.max(rows.length - VISIBLE_ITEMS, 0)
  const visible = hidden ? rows.slice(0, VISIBLE_ITEMS) : rows
  return (
    <div>
      <SectionLabel count={rows.length}>{title}</SectionLabel>
      <ul className="rounded-md border border-slate-200 divide-y divide-slate-100">
        {visible.map((row) => {
          const { tone, Icon } = DETAIL_KIND[row.kind]
          return (
            <li key={row.key} className="flex items-start gap-2.5 px-3.5 py-2.5 text-sm text-slate-800">
              <Icon size={16} aria-hidden="true" className={clsx('mt-0.5 shrink-0', TONES[tone].icon)} />
              <span>{row.text}</span>
            </li>
          )
        })}
      </ul>
      {rows.length > VISIBLE_ITEMS && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-1.5 rounded text-xs font-medium text-slate-600 underline-offset-4 hover:text-slate-900 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
        >
          {hidden ? `Show ${hidden} more` : 'Show fewer'}
        </button>
      )}
    </div>
  )
}

const GBP = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' })

const PER = { weekly: 'a week', fortnightly: 'a fortnight', '4_weekly': 'every 4 weeks' }

/** "Child Benefit £27.00 a week (£117.00 a month)" — Aryza's own figure behind the monthly total. */
const nonMonthlyNote = (items) => (items || [])
  .map((i) => `${i.source} ${GBP.format(i.amount)} ${PER[i.frequency] || i.frequency} (${GBP.format(i.monthly)} a month)`)
  .join('; ')

/** Informational estimate only — the IVA / DMP / DRO outcomes above are unaffected by it. */
function EstimatedDisposableIncome({ estimate }) {
  if (!estimate) return null
  if (!estimate.available) {
    const reasons = [...new Set((estimate.reasons || []).map((r) => r.text))]
    return (
      <div>
        <SectionLabel>Estimated disposable income</SectionLabel>
        <ul className="rounded-md border border-slate-200 divide-y divide-slate-100">
          {reasons.map((text) => (
            <li key={text} className="flex items-start gap-2.5 px-3.5 py-2.5 text-sm text-slate-800">
              <CircleDashed size={16} aria-hidden="true" className={clsx('mt-0.5 shrink-0', TONES.neutral.icon)} />
              <span>{text}</span>
            </li>
          ))}
        </ul>
      </div>
    )
  }
  const rows = [
    ['Adults', estimate.adults],
    ['Children', estimate.children],
    ['Monthly income', GBP.format(estimate.monthly_income), nonMonthlyNote(estimate.non_monthly_income)],
    ['Monthly rent', GBP.format(estimate.monthly_rent)],
    ['Estimated minimum expenditure', GBP.format(estimate.minimum_expenditure)],
  ]
  return (
    <div>
      <SectionLabel>Estimated disposable income</SectionLabel>
      <dl className="rounded-md border border-slate-200 divide-y divide-slate-100 text-sm">
        {rows.map(([label, value, note]) => (
          <div key={label} className="flex flex-wrap items-center justify-between gap-x-4 px-3.5 py-2">
            <dt className="text-slate-600">{label}</dt>
            <dd className="tabular-nums text-slate-900">{value}</dd>
            {note && <dd className="basis-full mt-0.5 text-xs text-slate-500">Includes {note}</dd>}
          </div>
        ))}
        <div className="flex items-center justify-between gap-4 px-3.5 py-2.5 bg-slate-50">
          <dt className="font-semibold text-slate-900">Estimated disposable income</dt>
          <dd className="tabular-nums font-semibold text-slate-900">{GBP.format(estimate.estimated_disposable_income)}</dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-slate-500">{estimate.message}</p>
    </div>
  )
}

const figure = (value) => (value === null || value === undefined ? 'Not recorded' : GBP.format(value))

/** The figures the criteria were run on, so the advisor can see why a rule fired. */
function CaseFigures({ figures }) {
  if (!figures) return null
  // The checks use the estimated disposable income when there is one, and the
  // full I&E figure otherwise; both are shown when the estimate was used.
  const estimate = figures.disposable_income_basis === 'ESTIMATE'
  const rows = [
    ['Total unsecured debt', figures.total_unsecured_debt],
    ['Monthly income', figures.monthly_income],
    ['Monthly expenditure', figures.monthly_expenditure],
    ...(estimate ? [['Disposable income from the I&E (per month)', figures.full_ie_disposable_income]] : []),
    [estimate ? 'Disposable income used for the checks (estimate)' : 'Disposable income (per month)', figures.disposable_income],
  ]
  return (
    <div>
      <SectionLabel>Case figures</SectionLabel>
      <dl className="rounded-md border border-slate-200 divide-y divide-slate-100 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex flex-wrap items-center justify-between gap-x-4 px-3.5 py-2">
            <dt className="text-slate-600">{label}</dt>
            <dd className={clsx('tabular-nums', value === null || value === undefined ? 'text-slate-500' : 'text-slate-900')}>
              {figure(value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function CreditReportStatus({ reference, status, isLoading, isError, wantsUpload, onWantUpload, onCancelUpload }) {
  if (reference.length < 3) {
    return <p className="text-sm text-slate-500">Enter a case reference to look for a credit report on file.</p>
  }
  if (isLoading) {
    return (
      <p className="text-sm text-slate-500 flex items-center gap-2">
        <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Looking for a credit report…
      </p>
    )
  }
  if (isError && !status) {
    return <p className="text-sm text-slate-500">Couldn&apos;t look up a credit report for this reference.</p>
  }
  if (!status) return null
  if (status.has_usable_report) {
    const meta = [status.agency, formatDay(status.uploaded_at)].filter(Boolean).join(' · ')
    return (
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <CheckCircle2 size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-green-600" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-900">Credit report on file</p>
            {meta && <p className="text-xs text-slate-500 truncate">{meta}</p>}
          </div>
        </div>
        {wantsUpload ? (
          <Button variant="ghost" size="sm" onClick={onCancelUpload}>Use report on file</Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={onWantUpload}>
            <Upload size={14} aria-hidden="true" /> Upload newer
          </Button>
        )}
      </div>
    )
  }
  const unusable = ['failed', 'extracted_empty'].includes(status.latest_upload_status)
  return (
    <div className="flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5">
      <AlertTriangle size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-amber-600" />
      <p className="text-sm text-amber-900">
        {unusable
          ? 'The last credit report uploaded for this case could not be used. Upload a new one (PDF).'
          : 'No credit report on file for this case. Upload one (PDF) if you have it.'}
      </p>
    </div>
  )
}

/**
 * The council tax three drive the engine's DMP rule (not possible when all
 * three apply). The utility / phone answers only add DMP notes.
 */
const DMP_QUESTIONS = [
  { key: 'council_tax_current_year', label: 'Council tax arrears for this year' },
  { key: 'council_tax_previous_year', label: 'Council tax arrears for last year' },
  { key: 'lost_right_to_pay_instalments', label: 'Lost the right to pay council tax by instalments' },
  { key: 'current_gas_bill', label: 'Current gas bill' },
  { key: 'current_electric_bill', label: 'Current electric bill' },
  { key: 'previous_gas_provider_debt', label: 'Previous gas provider debt' },
  { key: 'previous_electric_provider_debt', label: 'Previous electric provider debt' },
  { key: 'current_phone_contract', label: 'Current phone contract' },
]

const NO_DMP_ANSWERS = Object.fromEntries(DMP_QUESTIONS.map((q) => [q.key, false]))

const NO_VAT_ANSWERS = { hmrc_debt_has_vat: false, hmrc_previous_year_vat: false }

const VAT_HINT = {
  unknown: 'Check the case first to see if HMRC is a creditor.',
  none: 'No HMRC debt found on this case.',
  hmrc: 'HMRC is a creditor on this case. Answer, then check the case again.',
}

/**
 * Always listed in the DMP checklist (as on the Run Assessment screen), but
 * only answerable once a check has shown this case has an HMRC creditor
 * (status 'hmrc'); before that, or with no HMRC debt, it is greyed out with
 * a hint. A previous-year VAT debt rules out an IVA; "has VAT" alone changes
 * nothing, so the previous-year tick only appears under it.
 */
function VatQuestion({ answers, onToggle, status }) {
  const box = 'mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-slate-900 focus-visible:ring-2 focus-visible:ring-slate-500 disabled:opacity-50'
  const enabled = status === 'hmrc'
  return (
    <fieldset className="space-y-2.5">
      <legend className="sr-only">HMRC VAT</legend>
      <label
        htmlFor="lg-vat-has"
        className={clsx('flex items-start gap-2.5 text-sm', enabled ? 'text-slate-800 cursor-pointer' : 'text-slate-400')}
      >
        <input id="lg-vat-has" type="checkbox" checked={enabled && answers.hmrc_debt_has_vat} disabled={!enabled}
          onChange={() => onToggle('hmrc_debt_has_vat')} aria-describedby="lg-vat-hint" className={box} />
        <span>HMRC debt includes VAT</span>
      </label>
      <p id="lg-vat-hint" className="-mt-1.5 ml-6 text-xs text-slate-500">{VAT_HINT[status]}</p>
      {enabled && answers.hmrc_debt_has_vat && (
        <label htmlFor="lg-vat-prev" className="ml-6 flex items-start gap-2.5 text-sm text-slate-800 cursor-pointer">
          <input id="lg-vat-prev" type="checkbox" checked={answers.hmrc_previous_year_vat}
            onChange={() => onToggle('hmrc_previous_year_vat')} className={box} />
          <span>The VAT is from a previous year</span>
        </label>
      )}
    </fieldset>
  )
}

/** The engine's DRO / Bankruptcy questions (solution_checklist): Yes / No / not answered. */
const SOLUTION_QUESTIONS = [
  { key: 'assets_over_2000', label: 'Assets and savings worth more than £2,000?' },
  { key: 'england_wales_connection', label: 'Lived or worked in England or Wales in the last 3 years?' },
  { key: 'currently_insolvent', label: 'Currently bankrupt, under an interim order or in an IVA?' },
  { key: 'dro_in_last_6_years', label: 'Had a Debt Relief Order in the last 6 years?' },
]

const NO_SOLUTION_ANSWERS = Object.fromEntries(SOLUTION_QUESTIONS.map((q) => [q.key, null]))

const answeredOnly = (answers) => Object.fromEntries(Object.entries(answers).filter(([, v]) => v !== null))

function SolutionQuestions({ answers, onChange }) {
  const answered = Object.keys(answeredOnly(answers)).length
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded text-sm font-medium text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500">
        <span>
          DRO and bankruptcy questions
          <span className="ml-1.5 text-xs font-normal text-slate-500">
            {answered ? `${answered} of ${SOLUTION_QUESTIONS.length} answered` : 'optional'}
          </span>
        </span>
        <ChevronDown size={16} aria-hidden="true" className="shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3 space-y-2.5">
        {SOLUTION_QUESTIONS.map((q) => (
          <label key={q.key} htmlFor={`lg-sol-${q.key}`} className="flex items-center justify-between gap-3 text-sm text-slate-800">
            <span>{q.label}</span>
            <select
              id={`lg-sol-${q.key}`}
              value={answers[q.key] === null ? '' : answers[q.key] ? 'yes' : 'no'}
              onChange={(e) => onChange(q.key, e.target.value === '' ? null : e.target.value === 'yes')}
              className="h-8 shrink-0 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
            >
              <option value="">Not answered</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </label>
        ))}
      </div>
    </details>
  )
}

function DmpChecklist({ answers, onToggle }) {
  return (
    <fieldset className="space-y-2.5">
      <legend className="text-sm font-medium text-slate-800">DMP checklist</legend>
      <p className="text-xs text-slate-500">Tick any that apply to the customer.</p>
      {DMP_QUESTIONS.map((q) => (
        <label key={q.key} htmlFor={`lg-dmp-${q.key}`} className="flex items-start gap-2.5 text-sm text-slate-800 cursor-pointer">
          <input
            id={`lg-dmp-${q.key}`}
            type="checkbox"
            checked={answers[q.key]}
            onChange={() => onToggle(q.key)}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-slate-900 focus-visible:ring-2 focus-visible:ring-slate-500"
          />
          <span>{q.label}</span>
        </label>
      ))}
    </fieldset>
  )
}

function ResultPlaceholder({ pending }) {
  return (
    <div className="hidden lg:flex flex-col items-center justify-center text-center rounded-lg border border-dashed border-slate-300 bg-white/60 px-6 py-16">
      {pending ? (
        <>
          <Loader2 size={24} aria-hidden="true" className="animate-spin text-slate-400" />
          <p className="mt-3 text-sm font-medium text-slate-700">Checking case…</p>
        </>
      ) : (
        <>
          <FileSearch size={28} aria-hidden="true" className="text-slate-300" />
          <p className="mt-3 text-sm font-medium text-slate-700">No case checked yet</p>
          <p className="mt-1 text-sm text-slate-500 max-w-xs">
            Enter a case reference and select <span className="font-medium text-slate-700">Check case</span> to see the pre-screen result here.
          </p>
        </>
      )}
    </div>
  )
}

function ResultCard({ result }) {
  const overallTone = TONES[OVERALL_TONE[result.overall.code] || 'neutral']
  const OverallIcon = overallTone.Icon
  const reasonsTitle = result.overall.code === 'DOES_NOT_MEET_CRITERIA' ? 'Reason' : 'Why not'
  const noIssues = result.overall.code === 'POTENTIALLY_SUITABLE' && !result.reasons?.length
    && !result.review_reasons?.length && !result.evidence_required_later?.length && !result.warnings?.length
  const crNote = result.credit_report?.warning || result.credit_report?.message
  // Bankruptcy is possible on almost every case (its only hard test, the
  // England and Wales connection, is not in Aryza), so it is shown only when
  // nothing else is: IVA, DMP and DRO all not suitable.
  const showBankruptcy = result.overall.code === 'DOES_NOT_MEET_CRITERIA'
    && Boolean(result.bankruptcy) && result.bankruptcy.code !== 'NOT_ASSESSED'
  // Newer responses send every IVA and DMP reason separately; group them by solution.
  const grouped = Array.isArray(result.iva_reasons) && Array.isArray(result.dmp_reasons)

  return (
    <Card aria-live="polite" aria-labelledby="lg-result-title">
      <div className="px-5 pt-4 pb-3 border-b border-slate-200">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Pre-screen result</p>
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <h2 id="lg-result-title" className="text-lg font-semibold text-slate-900">Case {result.aryza_reference}</h2>
          {result.client && <span className="text-sm text-slate-600">{result.client}</span>}
        </div>
      </div>

      <div className="p-5 space-y-5">
        {result.warnings?.length > 0 && (
          <div role="alert" className="flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 px-3.5 py-3">
            <AlertTriangle size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-amber-600" />
            <div className="space-y-0.5">
              {result.warnings.map((w) => (
                <p key={w.code} className="text-sm font-semibold text-amber-900">{w.text}</p>
              ))}
            </div>
          </div>
        )}

        <div>
          <SectionLabel>Overall outcome</SectionLabel>
          <div className={clsx('flex items-start gap-3 rounded-md border px-4 py-3', overallTone.bg, overallTone.border)}>
            <OverallIcon size={20} aria-hidden="true" className={clsx('mt-0.5 shrink-0', overallTone.icon)} />
            <div>
              <p className={clsx('text-[15px] font-semibold', overallTone.text)}>{result.overall.label}</p>
              <p className="mt-0.5 text-sm text-slate-600">
                Based on the current Lead Gen pre-screen criteria — not a full assessment.
              </p>
            </div>
          </div>
        </div>

        <div>
          <SectionLabel>Solutions</SectionLabel>
          <ul className="rounded-md border border-slate-200 divide-y divide-slate-100">
            {result.dro?.code === 'REFER' && <OutcomeRow name="DRO" outcome={result.dro} />}
            <OutcomeRow name="IVA" outcome={result.iva} />
            <OutcomeRow name="DMP" outcome={result.dmp} />
            {result.dro && result.dro.code !== 'REFER' && result.dro.code !== 'NOT_ASSESSED' && (
              <OutcomeRow name="DRO" outcome={result.dro} />
            )}
            {showBankruptcy && (
              <OutcomeRow name="Bankruptcy" outcome={result.bankruptcy} />
            )}
          </ul>
        </div>

        <ItemList
          title="DMP notes"
          items={result.dmp_notes}
          tone="neutral"
          Icon={Info}
          renderText={(n) => n}
          getKey={(n) => n}
        />

        <SolutionDetail title="DRO details" outcome={result.dro} />
        {showBankruptcy && <SolutionDetail title="Bankruptcy details" outcome={result.bankruptcy} />}

        <EstimatedDisposableIncome estimate={result.estimated_disposable_income} />

        <CaseFigures figures={result.case_figures} />

        {grouped ? (
          <>
            <ItemList title="Why IVA is not suitable" items={result.iva_reasons} tone="danger" Icon={XCircle} />
            <ItemList title="Why DMP is not suitable" items={result.dmp_reasons} tone="danger" Icon={XCircle} />
          </>
        ) : (
          <ItemList title={reasonsTitle} items={result.reasons} tone="danger" Icon={XCircle} />
        )}
        <ItemList title="Needs review" items={result.review_reasons} tone="warning" Icon={AlertTriangle} />
        <ItemList
          title="Evidence required later"
          note="Not yet received — these documents will be needed later."
          items={result.evidence_required_later}
          tone="neutral"
          Icon={CircleDashed}
          renderText={(e) => e}
          getKey={(e) => e}
        />

        {noIssues && (
          <p className="flex items-center gap-2 text-sm text-slate-700">
            <CheckCircle2 size={16} aria-hidden="true" className="text-green-600" />
            No issues identified at this stage.
          </p>
        )}

        {crNote && (
          <div className="flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5">
            <FileText size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-amber-600" />
            <p className="text-sm text-amber-900">{crNote}</p>
          </div>
        )}
      </div>

      <div className="px-5 py-3 border-t border-slate-100 text-xs text-slate-500">
        Checked <time dateTime={result.checked_at}>{formatDayTime(result.checked_at)}</time>
        {result.criteria_version && (
          <><span aria-hidden="true" className="mx-1.5">·</span>Criteria {result.criteria_version}</>
        )}
      </div>
    </Card>
  )
}

/**
 * Lead Gen pre-screen: case reference (+ credit report if none on file) ->
 * simplified IVA / DMP / DRO outcome. Rendered on /lead-gen and inside the
 * pop-out window, so it must not depend on page layout (the two-column split
 * only applies when the window itself is wide).
 */
export default function LeadGenCheckPanel() {
  const queryClient = useQueryClient()
  const [reference, setReference] = useState('')
  const [debouncedRef, setDebouncedRef] = useState('')
  const [file, setFile] = useState(null)
  const [wantsUpload, setWantsUpload] = useState(false)
  const [result, setResult] = useState(null)
  const [refError, setRefError] = useState('')
  const [dmpAnswers, setDmpAnswers] = useState(NO_DMP_ANSWERS)
  const [vatAnswers, setVatAnswers] = useState(NO_VAT_ANSWERS)
  const [solutionAnswers, setSolutionAnswers] = useState(NO_SOLUTION_ANSWERS)
  // Reference a successful check confirmed has an HMRC creditor (else null).
  const [hmrcRef, setHmrcRef] = useState(null)
  const fileInput = useRef(null)
  const check = useLeadGenCheck()
  const crStatus = useLeadGenCreditReportStatus(debouncedRef)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedRef(reference.trim()), 400)
    return () => clearTimeout(t)
  }, [reference])

  useEffect(() => {
    setWantsUpload(false)
    setFile(null)
    setDmpAnswers(NO_DMP_ANSWERS)
    setSolutionAnswers(NO_SOLUTION_ANSWERS)
  }, [debouncedRef])

  // VAT is answerable only once a successful check of this reference found HMRC.
  const vatStatus = check.isPending ? 'unknown'
    : hmrcRef !== null && hmrcRef === reference.trim() ? 'hmrc'
      : result?.aryza_reference === reference.trim() && result?.hmrc_is_creditor === false ? 'none'
        : 'unknown'

  useEffect(() => {
    if (hmrcRef !== null && hmrcRef !== reference.trim()) {
      setHmrcRef(null)
      setVatAnswers(NO_VAT_ANSWERS)
    }
  }, [reference, hmrcRef])

  const toggleVat = (key) => setVatAnswers((prev) => (
    key === 'hmrc_debt_has_vat' && prev.hmrc_debt_has_vat
      ? NO_VAT_ANSWERS
      : { ...prev, [key]: !prev[key] }
  ))

  const showUpload = debouncedRef.length >= 3 && !crStatus.isLoading
    && (wantsUpload || (crStatus.data && !crStatus.data.has_usable_report))

  const onSubmit = (e) => {
    e.preventDefault()
    const ref = reference.trim()
    if (!ref) {
      setRefError('Enter a case reference to check.')
      return
    }
    setResult(null)
    const dmpChecklist = hmrcRef === ref ? { ...dmpAnswers, ...vatAnswers } : dmpAnswers
    const solutionChecklist = answeredOnly(solutionAnswers)
    check.mutate(
      {
        aryza_reference: ref,
        file: showUpload ? file : null,
        dmp_checklist: dmpChecklist,
        ...(Object.keys(solutionChecklist).length ? { solution_checklist: solutionChecklist } : {}),
      },
      {
        onSuccess: (data) => {
          setResult(data)
          if (data.hmrc_is_creditor === true) {
            setHmrcRef(ref)
          } else {
            setHmrcRef(null)
            setVatAnswers(NO_VAT_ANSWERS)
          }
          setFile(null)
          setWantsUpload(false)
          if (fileInput.current) fileInput.current.value = ''
          queryClient.invalidateQueries({ queryKey: ['lead-gen-credit-report-status', ref] })
        },
        onError: () => {
          setHmrcRef(null)
          setVatAnswers(NO_VAT_ANSWERS)
        },
      },
    )
  }

  return (
    <div className="grid gap-6 items-start lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
      <Card as="form" onSubmit={onSubmit} noValidate aria-label="Lead Gen criteria check">
        <div className="px-5 py-4 border-b border-slate-200">
          <h2 className="text-[15px] font-semibold text-slate-900">Check a case</h2>
          <p className="mt-0.5 text-sm text-slate-500">Run the Lead Gen pre-screen against the live criteria.</p>
        </div>

        <div className="px-5 py-4">
          <Field id="lg-ref" label="Case reference" error={refError} hint="The Aryza case reference, e.g. 324991.">
            <TextInput
              id="lg-ref"
              size="lg"
              value={reference}
              onChange={(e) => { setReference(e.target.value); if (refError) setRefError('') }}
              autoComplete="off"
              inputMode="text"
              placeholder="Enter a case reference"
              invalid={Boolean(refError)}
              aria-describedby={refError ? 'lg-ref-error' : 'lg-ref-hint'}
            />
          </Field>
        </div>

        <div className="px-5 py-4 border-t border-slate-100 space-y-3">
          <h3 className="text-sm font-medium text-slate-800">Credit report</h3>
          <CreditReportStatus
            reference={debouncedRef}
            status={crStatus.data}
            isLoading={crStatus.isLoading}
            isError={crStatus.isError}
            wantsUpload={wantsUpload}
            onWantUpload={() => setWantsUpload(true)}
            onCancelUpload={() => { setWantsUpload(false); setFile(null) }}
          />
          {showUpload && (
            <div>
              <label htmlFor="lg-cr" className="block text-xs font-medium text-slate-700 mb-1.5">Credit report (PDF)</label>
              <input
                id="lg-cr"
                ref={fileInput}
                type="file"
                accept=".pdf,application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                aria-describedby="lg-cr-hint"
                className={clsx(
                  'block w-full rounded-md border border-dashed border-slate-300 bg-slate-50 p-2 text-sm text-slate-600',
                  'file:mr-3 file:h-8 file:rounded-md file:border file:border-solid file:border-slate-300 file:bg-white',
                  'file:px-3 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-50',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500',
                )}
              />
              <p id="lg-cr-hint" className="mt-1.5 text-xs text-slate-500">PDF only. Read when you check the case.</p>
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-slate-100">
          <DmpChecklist
            answers={dmpAnswers}
            onToggle={(key) => setDmpAnswers((prev) => ({ ...prev, [key]: !prev[key] }))}
          />
          <div className="mt-3 pt-3 border-t border-slate-100">
            <VatQuestion answers={vatAnswers} onToggle={toggleVat} status={vatStatus} />
          </div>
        </div>

        <div className="px-5 py-4 border-t border-slate-100">
          <SolutionQuestions
            answers={solutionAnswers}
            onChange={(key, value) => setSolutionAnswers((prev) => ({ ...prev, [key]: value }))}
          />
        </div>


        <div className="px-5 py-4 border-t border-slate-100 bg-slate-50/70 rounded-b-lg">
          <Button type="submit" variant="primary" size="lg" className="w-full" disabled={check.isPending}>
            {check.isPending
              ? <><Loader2 size={16} className="animate-spin" aria-hidden="true" /> Checking…</>
              : <><Search size={16} aria-hidden="true" /> Check case</>}
          </Button>
        </div>
      </Card>

      <div className="min-w-0 space-y-4">
        {check.isError && (
          <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <XCircle size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-red-600" />
            <span>{apiErrorMessage(check.error)}</span>
          </div>
        )}
        {result ? <ResultCard result={result} /> : !check.isError && <ResultPlaceholder pending={check.isPending} />}
      </div>
    </div>
  )
}
