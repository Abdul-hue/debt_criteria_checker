import { useState } from 'react'
import clsx from 'clsx'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { FlaskConical, Info, Plus, RotateCcw, X } from 'lucide-react'
import LoadingSpinner from '../components/shared/LoadingSpinner.jsx'
import CriteriaTargetCombobox from '../components/leadgen/CriteriaTargetCombobox.jsx'
import {
  Button, Card, CardHeader, Field, PageHeader, SelectInput, StatusPill, TextArea, TextInput,
} from '../components/leadgen/ui.jsx'
import { formatDayTime } from '../components/leadgen/format.js'
import { apiErrorMessage } from '../hooks/useLeadGen'
import {
  criteriaUrls,
  useCriteriaChange,
  useCriteriaChangeAction,
  useCriteriaChanges,
  useCriteriaTarget,
  useCriteriaVersions,
  useManagedFields,
} from '../hooks/useCriteriaChanges'

const MODEL_LABELS = {
  CreditorCriteria: 'Creditor',
  CouncilRule: 'Council',
  CountyCouncil: 'County council',
  GlobalCriteria: 'Global rule (on/off)',
}

/** Singular noun for the row picker of each criteria table. */
const TARGET_LABELS = {
  CreditorCriteria: 'Creditor',
  CouncilRule: 'Council',
  CountyCouncil: 'County council',
  GlobalCriteria: 'Global rule',
}

/** Backend change statuses -> display tone (labels come from the API's status_label). */
const STATUS_TONE = {
  DRAFT: 'neutral',
  TRIALLED: 'warning',
  LIVE: 'success',
  REJECTED: 'danger',
  CANCELLED: 'neutral',
}

const fmt = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v))
const fieldName = (f) => f.replace(/_/g, ' ')

function parseValue(raw, current, info) {
  if (info?.choices) return raw === '' ? null : raw
  if (typeof current === 'boolean') return raw === 'true'
  if (Array.isArray(current) || (current && typeof current === 'object')) {
    try { return JSON.parse(raw) } catch { return raw }
  }
  return raw === '' ? null : raw
}

function ErrorText({ error }) {
  if (!error) return null
  return <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{apiErrorMessage(error)}</p>
}

function LiveBadge({ version }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-semibold text-green-800">
      <span className="h-2 w-2 rounded-full bg-green-600" aria-hidden="true" />
      LIVE · {version || '—'}
    </span>
  )
}

const TH = 'px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500'
const TD = 'px-4 py-3 align-top'

function NewChangeForm({ onCreated }) {
  const fields = useManagedFields()
  const action = useCriteriaChangeAction()
  const [model, setModel] = useState('CreditorCriteria')
  const [objectId, setObjectId] = useState('')
  const [selectedLabel, setSelectedLabel] = useState('')
  const [field, setField] = useState('')
  const [rawValue, setRawValue] = useState('')
  const [items, setItems] = useState([])
  const [title, setTitle] = useState('')
  const [reason, setReason] = useState('')
  const target = useCriteriaTarget(model, objectId)
  const current = target.data?.values?.[field]
  const info = fields.data?.field_info?.[model]?.[field]
  const targetLabel = TARGET_LABELS[model]

  const addItem = () => {
    if (!objectId || !field) return
    setItems((prev) => [...prev, {
      model, object_id: Number(objectId), field, new_value: parseValue(rawValue, current, info),
      _label: `${MODEL_LABELS[model]}: ${target.data?.label}`, _old: current,
    }])
    setField('')
    setRawValue('')
  }

  const submit = (e) => {
    e.preventDefault()
    action.mutate({
      url: criteriaUrls.create,
      body: { title, reason, items: items.map(({ _label, _old, ...rest }) => rest) },
    }, { onSuccess: (data) => { setItems([]); setTitle(''); setReason(''); onCreated(data.id) } })
  }

  const missing = [!items.length && 'at least one change', !title && 'a title', !reason && 'a reason'].filter(Boolean)

  return (
    <Card as="form" onSubmit={submit} aria-labelledby="propose-title">
      <CardHeader
        id="propose-title"
        title="Propose a criteria change"
        description="Changes are saved as a draft. A draft is trialled against saved cases and must be approved by a second manager before it goes live."
      />

      <div className="px-5 py-5 space-y-5">
        {fields.data?.note && (
          <p className="flex items-start gap-2 text-xs text-slate-500">
            <Info size={14} aria-hidden="true" className="mt-px shrink-0" /> {fields.data.note}
          </p>
        )}

        <fieldset>
          <legend className="block text-sm font-medium text-slate-800 mb-1.5">Criteria type</legend>
          <div className="inline-flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
            {Object.entries(MODEL_LABELS).map(([k, v]) => (
              <label
                key={k}
                className={clsx(
                  'cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-slate-500',
                  model === k ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200' : 'text-slate-600 hover:text-slate-900',
                )}
              >
                <input
                  type="radio"
                  name="criteria-model"
                  value={k}
                  checked={model === k}
                  onChange={() => { setModel(k); setObjectId(''); setSelectedLabel(''); setField('') }}
                  className="sr-only"
                />
                {v}
              </label>
            ))}
          </div>
        </fieldset>

        <Field id="criteria-target" label={targetLabel} className="max-w-xl">
          <CriteriaTargetCombobox
            id="criteria-target"
            model={model}
            label={targetLabel}
            selected={objectId ? { id: objectId, label: target.data?.label || selectedLabel } : null}
            onSelect={(r) => {
              setObjectId(r ? String(r.id) : '')
              setSelectedLabel(r?.label || '')
              setField('')
            }}
          />
        </Field>

        {objectId && target.data && (
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
              <Field id="criteria-field" label="Field to change">
                <SelectInput
                  id="criteria-field"
                  value={field}
                  onChange={(e) => { setField(e.target.value); setRawValue(fmt(target.data.values[e.target.value]) === '—' ? '' : String(target.data.values[e.target.value])) }}
                >
                  <option value="">Select a field…</option>
                  {(fields.data?.managed_fields?.[model] || []).map((f) => <option key={f} value={f}>{fieldName(f)}</option>)}
                </SelectInput>
              </Field>
              <div>
                <p className="block text-sm font-medium text-slate-800 mb-1.5">Current value</p>
                <p className="flex h-10 items-center rounded-md border border-dashed border-slate-300 bg-white px-3 text-sm text-slate-700 truncate">
                  {field ? fmt(current) : <span className="text-slate-400">—</span>}
                </p>
              </div>
              <Field id="criteria-new-value" label="New value">
                {!field ? (
                  <TextInput id="criteria-new-value" disabled placeholder="Select a field first" />
                ) : info?.choices ? (
                  <SelectInput id="criteria-new-value" value={rawValue} onChange={(e) => setRawValue(e.target.value)}>
                    {info.nullable && <option value="">(none)</option>}
                    {info.choices.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </SelectInput>
                ) : typeof current === 'boolean' ? (
                  <SelectInput id="criteria-new-value" value={rawValue} onChange={(e) => setRawValue(e.target.value)}>
                    <option value="true">true</option><option value="false">false</option>
                  </SelectInput>
                ) : (
                  <TextInput id="criteria-new-value" value={rawValue} onChange={(e) => setRawValue(e.target.value)} />
                )}
              </Field>
              <Button variant="secondary" onClick={addItem} disabled={!field}>
                <Plus size={15} aria-hidden="true" /> Add to draft
              </Button>
            </div>
          </div>
        )}

        {items.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">
              Changes in this draft <span className="font-normal text-slate-500">({items.length})</span>
            </h3>
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th scope="col" className={TH}>Criteria</th>
                    <th scope="col" className={TH}>Field</th>
                    <th scope="col" className={TH}>Current</th>
                    <th scope="col" className={TH}>Proposed</th>
                    <th scope="col" className={TH}><span className="sr-only">Remove</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((it, i) => (
                    <tr key={i}>
                      <td className={TD}>{it._label}</td>
                      <td className={clsx(TD, 'text-slate-600')}>{fieldName(it.field)}</td>
                      <td className={clsx(TD, 'text-slate-500')}>{fmt(it._old)}</td>
                      <td className={clsx(TD, 'font-semibold text-slate-900')}>{fmt(it.new_value)}</td>
                      <td className="px-2 py-2 text-right">
                        <Button variant="ghost" size="sm" aria-label={`Remove ${fieldName(it.field)} change`}
                                onClick={() => setItems(items.filter((_, j) => j !== i))}>
                          <X size={15} aria-hidden="true" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <Field id="change-title" label="Title">
            <TextInput id="change-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Argos now accepts IVAs" />
          </Field>
          <Field id="change-reason" label="Reason for the change">
            <TextArea id="change-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                      placeholder="Why is this change needed? (required)" />
          </Field>
        </div>

        <ErrorText error={action.isError && action.error} />
      </div>

      <div className="flex flex-col-reverse gap-3 border-t border-slate-200 bg-slate-50/70 px-5 py-4 rounded-b-lg sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-slate-500">
          {missing.length
            ? `To save, add ${missing.join(', ').replace(/, ([^,]*)$/, ' and $1')}.`
            : 'Nothing changes on live criteria until a second manager approves this draft.'}
        </p>
        <Button type="submit" variant="primary" disabled={missing.length > 0 || action.isPending}>
          Save draft
        </Button>
      </div>
    </Card>
  )
}

function ChangeDetail({ id }) {
  const { data, isLoading } = useCriteriaChange(id)
  const action = useCriteriaChangeAction()
  const [note, setNote] = useState('')
  if (isLoading || !data) return <Card className="p-8"><LoadingSpinner /></Card>
  const viewer = data.viewer || {}
  const open = ['DRAFT', 'TRIALLED'].includes(data.status)
  const run = (url, body) => action.mutate({ url, body })
  const canSignOff = viewer.can_approve || viewer.can_reject

  return (
    <Card aria-labelledby="change-detail-title">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4 border-b border-slate-200">
        <div className="min-w-0">
          <h2 id="change-detail-title" className="text-[15px] font-semibold text-slate-900">
            <span className="text-slate-400 font-normal">#{data.id}</span> {data.title}
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Proposed by {data.created_by} · {formatDayTime(data.created_at, ' · ')}
          </p>
        </div>
        <StatusPill tone={STATUS_TONE[data.status]}>{data.status_label}</StatusPill>
      </div>

      <div className="px-5 py-4 space-y-5">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Reason</h3>
          <p className="text-sm text-slate-700 whitespace-pre-line">{data.reason}</p>
        </div>

        <div className="overflow-x-auto rounded-md border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className={TH}>Criteria</th>
                <th scope="col" className={TH}>Field</th>
                <th scope="col" className={TH}>Live</th>
                <th scope="col" className={TH}>Proposed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((it, i) => (
                <tr key={i}>
                  <td className={TD}>{MODEL_LABELS[it.model]}: {it.object_label}</td>
                  <td className={clsx(TD, 'text-slate-600')}>{fieldName(it.field)}</td>
                  <td className={clsx(TD, 'text-slate-500')}>{fmt(it.old_value)}</td>
                  <td className={clsx(TD, 'font-semibold text-slate-900')}>{fmt(it.new_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data.trial_summary && (
          <div className="rounded-md border border-slate-200 bg-slate-50 p-4 space-y-2">
            <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <FlaskConical size={16} aria-hidden="true" className="text-slate-500" />
              Trial: {data.trial_summary.cases_changed} of {data.trial_summary.cases_evaluated} saved cases would change
              {data.trial_summary.cases_errored ? ` (${data.trial_summary.cases_errored} could not be evaluated)` : ''}
            </p>
            <p className="text-xs text-slate-500">
              Run by {data.trial_run_by} · {formatDayTime(data.trial_run_at, ' · ')} · live criteria were not changed
            </p>
            {(data.trial_summary.changed || []).slice(0, 50).map((c) => (
              <details key={c.aryza_reference} className="rounded-md border border-slate-200 bg-white px-3 py-2">
                <summary className="cursor-pointer text-sm font-medium text-slate-800">Case {c.aryza_reference}</summary>
                <ul className="mt-2 space-y-1 text-xs text-slate-700">
                  {Object.entries(c.differences).map(([k, d]) => (
                    <li key={k}><span className="font-semibold">{k}</span>: {fmt(d.before)} → {fmt(d.after)}</li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        )}

        {data.decided_by && (
          <p className="text-sm text-slate-600">
            {data.status === 'LIVE' ? 'Approved' : data.status === 'REJECTED' ? 'Rejected' : 'Closed'} by{' '}
            <span className="font-medium text-slate-800">{data.decided_by}</span>
            {data.decided_at ? ` · ${formatDayTime(data.decided_at, ' · ')}` : ''}
            {data.applied_version ? ` · live as v${data.applied_version}` : ''}
            {data.decision_note ? ` — ${data.decision_note}` : ''}
          </p>
        )}

        <ErrorText error={action.isError && action.error} />
      </div>

      {open && (
        <div className="border-t border-slate-200 bg-slate-50/70 px-5 py-4 rounded-b-lg space-y-3">
          {viewer.is_author && <p className="text-xs text-slate-500">A second manager must sign this off.</p>}
          {!viewer.is_author && !canSignOff && (
            <p className="text-xs text-amber-800">
              You can propose and trial changes, but signing off needs the &ldquo;Criteria Approval&rdquo;
              feature on your department (Admin &rarr; Departments).
            </p>
          )}
          {canSignOff && !viewer.can_approve && (
            <p className="text-xs text-slate-500">Run the trial before this change can be approved.</p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {viewer.can_trial && (
              <Button variant="secondary" onClick={() => run(criteriaUrls.trial(id))} disabled={action.isPending}>
                <FlaskConical size={15} aria-hidden="true" />
                {data.status === 'TRIALLED' ? 'Re-run trial' : 'Run trial'}
              </Button>
            )}
            {viewer.can_cancel && (
              <Button variant="ghost" onClick={() => run(criteriaUrls.cancel(id))} disabled={action.isPending}>
                Cancel change
              </Button>
            )}
          </div>

          {canSignOff && (
            <div className="flex flex-col gap-2 border-t border-slate-200 pt-3 sm:flex-row sm:items-center">
              <label htmlFor="signoff-note" className="sr-only">Sign-off note</label>
              <TextInput id="signoff-note" value={note} onChange={(e) => setNote(e.target.value)}
                         placeholder="Sign-off note (optional)" className="sm:flex-1" />
              <div className="flex gap-2">
                <Button variant="danger" disabled={!viewer.can_reject || action.isPending}
                        onClick={() => run(criteriaUrls.reject(id), { note })}>
                  Reject
                </Button>
                <Button variant="success" disabled={!viewer.can_approve || action.isPending}
                        onClick={() => run(criteriaUrls.approve(id), { note })}>
                  Approve &amp; make live
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function RollbackDialog({ version, onClose }) {
  const action = useCriteriaChangeAction()
  const [reason, setReason] = useState('')
  const submit = () => action.mutate(
    { url: criteriaUrls.rollback(version.number), body: { reason } },
    { onSuccess: onClose },
  )
  return (
    <AlertDialog.Root open onOpenChange={(o) => !o && onClose()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-slate-900/40" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl focus:outline-none">
          <AlertDialog.Title className="flex items-center gap-2 text-lg font-semibold text-slate-900">
            <RotateCcw size={18} aria-hidden="true" className="text-red-600" /> Roll back to {version.label}?
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-sm text-slate-600">
            This drafts a change that restores the criteria as they were in {version.label}. Like any other change,
            it must be trialled and approved by a second manager before it goes live.
          </AlertDialog.Description>
          <div className="mt-4">
            <Field id="rollback-reason" label="Reason for rollback">
              <TextArea id="rollback-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)}
                        placeholder="Required" />
            </Field>
          </div>
          <div className="mt-4"><ErrorText error={action.isError && action.error} /></div>
          <div className="mt-6 flex justify-end gap-3">
            <AlertDialog.Cancel asChild>
              <Button variant="secondary" disabled={action.isPending}>Keep current version</Button>
            </AlertDialog.Cancel>
            <Button variant="dangerSolid" onClick={submit} disabled={!reason.trim() || action.isPending}>
              Draft rollback
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}

function Versions() {
  const { data } = useCriteriaVersions()
  const [rollbackTo, setRollbackTo] = useState(null)
  if (!data) return null
  return (
    <Card aria-labelledby="versions-title">
      <CardHeader
        id="versions-title"
        title="Version history"
        description="Every approved change creates a new version. Rolling back drafts a change that needs sign-off like any other."
        actions={<LiveBadge version={data.live_version} />}
      />
      {data.results.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-slate-500">
          No versions yet — v1 is captured automatically when the first change goes live.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th scope="col" className={TH}>Version</th>
                <th scope="col" className={TH}>Date</th>
                <th scope="col" className={TH}>Change</th>
                <th scope="col" className={TH}>Approved by</th>
                <th scope="col" className={TH}>Status</th>
                <th scope="col" className={clsx(TH, 'text-right')}>Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.results.map((v, i) => {
                const isLive = v.label === data.live_version
                return (
                  <tr key={v.number} className={isLive ? 'bg-green-50/40' : undefined}>
                    <td className={clsx(TD, 'font-semibold text-slate-900 tabular-nums')}>{v.label}</td>
                    <td className={clsx(TD, 'whitespace-nowrap text-slate-600 tabular-nums')}>{formatDayTime(v.created_at, ' · ')}</td>
                    <td className={clsx(TD, 'text-slate-800')}>{v.note || '—'}</td>
                    <td className={clsx(TD, 'text-slate-600')}>{v.created_by || '—'}</td>
                    <td className={TD}>{isLive && <StatusPill tone="success">Live</StatusPill>}</td>
                    <td className={clsx(TD, 'text-right')}>
                      {i > 0 && (
                        <Button variant="danger" size="sm" onClick={() => setRollbackTo(v)}>
                          <RotateCcw size={13} aria-hidden="true" /> Roll back to {v.label}
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {rollbackTo && <RollbackDialog version={rollbackTo} onClose={() => setRollbackTo(null)} />}
    </Card>
  )
}

/** Draft -> Trial -> Second-manager sign-off -> Live, with versions and rollback. */
export default function CriteriaChangesPage() {
  const { data, isLoading } = useCriteriaChanges()
  const [selected, setSelected] = useState(null)
  const changes = data?.results || []

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-8">
      <PageHeader
        title="Criteria Management"
        description="Manage database-held criteria through controlled changes: draft, trial against saved cases, then second-manager sign-off before anything goes live."
        actions={<LiveBadge version={data?.live_version} />}
      />

      <NewChangeForm onCreated={setSelected} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-start">
        <Card aria-labelledby="changes-title">
          <CardHeader id="changes-title" title="Change requests"
                      description={data ? `${changes.length} ${changes.length === 1 ? 'request' : 'requests'}` : undefined} />
          {isLoading && <div className="p-6"><LoadingSpinner /></div>}
          <ul className="max-h-[32rem] overflow-y-auto divide-y divide-slate-100">
            {changes.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelected(c.id)}
                  aria-current={selected === c.id ? 'true' : undefined}
                  className={clsx(
                    'w-full text-left px-5 py-3 border-l-2 transition-colors focus:outline-none focus-visible:bg-slate-50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-500',
                    selected === c.id ? 'border-brand-navy bg-slate-50' : 'border-transparent hover:bg-slate-50',
                  )}
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0 text-sm font-medium text-slate-900">
                      <span className="text-slate-400 font-normal">#{c.id}</span> {c.title}
                    </span>
                    <StatusPill tone={STATUS_TONE[c.status]} className="shrink-0">{c.status_label || c.status}</StatusPill>
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {c.created_by} · {formatDayTime(c.created_at, ' · ')}
                  </span>
                </button>
              </li>
            ))}
            {data && changes.length === 0 && <li className="px-5 py-8 text-center text-sm text-slate-500">No changes yet.</li>}
          </ul>
        </Card>
        <div className="min-w-0">
          {selected ? <ChangeDetail id={selected} /> : (
            <Card className="flex items-center justify-center border-dashed px-6 py-16 text-center">
              <p className="text-sm text-slate-500">Select a change request to review it.</p>
            </Card>
          )}
        </div>
      </div>

      <Versions />
    </div>
  )
}
