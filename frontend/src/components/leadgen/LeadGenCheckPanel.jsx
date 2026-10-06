import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  AlertTriangle, CheckCircle2, CircleDashed, FileSearch, FileText, Loader2, Search, Upload, XCircle,
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
}

const OVERALL_TONE = {
  POTENTIALLY_SUITABLE: 'success',
  DRO_REFER: 'warning',
  DOES_NOT_MEET_CRITERIA: 'danger',
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

function ItemList({ title, items, tone, Icon, renderText = (r) => r.text, getKey = (r) => r.code, note }) {
  if (!items || items.length === 0) return null
  const t = TONES[tone]
  return (
    <div>
      <SectionLabel count={items.length}>{title}</SectionLabel>
      {note && <p className="-mt-1 mb-2 text-xs text-slate-500">{note}</p>}
      <ul className="rounded-md border border-slate-200 divide-y divide-slate-100">
        {items.map((r) => (
          <li key={getKey(r)} className="flex items-start gap-2.5 px-3.5 py-2.5 text-sm text-slate-800">
            <Icon size={16} aria-hidden="true" className={clsx('mt-0.5 shrink-0', t.icon)} />
            <span>{renderText(r)}</span>
          </li>
        ))}
      </ul>
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
    && !result.review_reasons?.length && !result.evidence_required_later?.length
  const crNote = result.credit_report?.warning || result.credit_report?.message

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
            {result.dro && <OutcomeRow name="DRO" outcome={result.dro} />}
            <OutcomeRow name="IVA" outcome={result.iva} />
            <OutcomeRow name="DMP" outcome={result.dmp} />
          </ul>
        </div>

        <ItemList title={reasonsTitle} items={result.reasons} tone="danger" Icon={XCircle} />
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
  }, [debouncedRef])

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
    check.mutate(
      { aryza_reference: ref, file: showUpload ? file : null },
      {
        onSuccess: (data) => {
          setResult(data)
          setFile(null)
          setWantsUpload(false)
          if (fileInput.current) fileInput.current.value = ''
          queryClient.invalidateQueries({ queryKey: ['lead-gen-credit-report-status', ref] })
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
