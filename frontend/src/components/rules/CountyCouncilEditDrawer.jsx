import React, { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useUpdateCountyCouncil, useCountyCouncil } from '../../hooks/useCountyCouncils'
import { useCreditorVoteSummary } from '../../hooks/useCreditors'
import { useToast } from '../../hooks/useToast'
import Spinner from '../shared/Spinner'
import CrmVoteSummary from '../shared/CrmVoteSummary'

const STATUS_OPTIONS = [
  { value: 'NO_CRITERIA',       label: 'No Direct Criteria — delegates to districts, not a creditor' },
  { value: 'CONDITIONAL_VOTER', label: 'Case by Case — conditional criteria (see notes)'   },
  { value: 'ACCEPT',            label: 'Accepts — votes to approve IVAs'         },
  { value: 'REJECT',            label: 'Rejects — votes against IVAs'            },
  { value: 'WILL_CONSIDER',     label: 'Will Consider — reviews case by case'    },
  { value: 'DO_NOT_VOTE',       label: 'Does Not Vote — never submits a proxy'   },
]

const DISTRICT_STATUS_CONFIG = {
  ACCEPT:            { label: 'Accepts',      bg: 'bg-green-100',  text: 'text-green-800'  },
  REJECT:            { label: 'Rejects',      bg: 'bg-red-100',    text: 'text-red-800'    },
  WILL_CONSIDER:     { label: 'Will Consider', bg: 'bg-amber-100',  text: 'text-amber-800'  },
  DO_NOT_VOTE:       { label: 'Does Not Vote', bg: 'bg-gray-100',   text: 'text-gray-600'   },
  CONDITIONAL_VOTER: { label: 'Case by Case', bg: 'bg-purple-100', text: 'text-purple-800' },
}

function Field({ label, children }) {
  return (
    <div className="mb-4">
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      {children}
    </div>
  )
}

function Toggle({ label, name, register, disabled }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
      <span className="text-xs text-gray-600">{label}</span>
      <input
        type="checkbox"
        {...register(name)}
        disabled={disabled}
        className="w-4 h-4 accent-blue-600 cursor-pointer disabled:cursor-not-allowed"
      />
    </div>
  )
}

function DistrictsSection({ districts }) {
  return (
    <>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        Districts ({districts.length})
      </p>
      <p className="text-xs text-gray-400 mb-2">
        These districts are routed to this county for council tax matching. Each has its own voting behaviour, managed on the Councils tab.
      </p>
      {districts.length ? (
        <div className="border border-gray-100 rounded-md divide-y divide-gray-50 mb-4">
          {districts.map(d => {
            const cfg = DISTRICT_STATUS_CONFIG[d.council_rule_status] ?? { label: d.council_rule_status ?? 'Unmapped', bg: 'bg-gray-100', text: 'text-gray-500' }
            return (
              <div key={d.id} className="flex items-center justify-between px-3 py-2 text-xs">
                <div>
                  <p className="font-medium text-gray-700">{d.district_name}</p>
                  {d.council_rule_name && d.council_rule_name !== d.district_name && (
                    <p className="text-gray-400">{d.council_rule_name}</p>
                  )}
                </div>
                <span className={`inline-flex items-center px-2 py-0.5 rounded font-medium ${cfg.bg} ${cfg.text}`}>
                  {cfg.label}
                </span>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-xs text-gray-300 mb-4">No districts routed to this county yet.</p>
      )}
    </>
  )
}

export default function CountyCouncilEditDrawer({ county, onClose, readOnly }) {
  const toast = useToast()
  const updateCountyCouncil = useUpdateCountyCouncil()
  const { data: detail } = useCountyCouncil(county?.id)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm({ defaultValues: county || {} })

  useEffect(() => {
    if (county) reset(county)
  }, [county, reset])

  if (!county) return null
  
  const voteSummaryQuery = useCreditorVoteSummary('county-councils', county?.id)

  const onSubmit = (data) => {
    if (readOnly) return
    updateCountyCouncil.mutate(
      { id: county.id, ...data },
      {
        onSuccess: () => {
          toast.success('Saved', `${data.county_name} updated successfully.`)
          onClose()
        },
        onError: (err) => {
          toast.error('Save failed', err?.response?.data?.detail ?? err.message)
        },
      }
    )
  }

  const inputCls = `w-full px-3 py-2 text-sm border border-gray-300 rounded-md
    focus:outline-none focus:ring-2 focus:ring-blue-400
    disabled:bg-gray-50 disabled:text-gray-500`

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />

      <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-xl z-50
                      flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="text-base font-semibold text-gray-800 truncate pr-4">{county.county_name} County Council</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors shrink-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <form id="county-council-form" onSubmit={handleSubmit(onSubmit)} className="flex-1 overflow-y-auto px-5 py-4 space-y-0">
          {readOnly && (
            <div className="mb-4 p-2.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">
              View only — admin access required to edit county council settings.
            </div>
          )}

          {/* ── Core identity ── */}
          <Field label="County Name">
            <input {...register('county_name', { required: true })} disabled={readOnly} className={inputCls} />
            {errors.county_name && <p className="text-xs text-red-500 mt-1">County name is required.</p>}
          </Field>

          <Field label="Voting Behaviour">
            <select {...register('status')} disabled={readOnly} className={inputCls}>
              {STATUS_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>

          <Field label="Min Dividend (pence in the £)">
            <input
              type="number"
              step="1"
              min="0"
              max="100"
              {...register('min_dividend_pence', {
                setValueAs: v => (v === '' || v === null) ? null : parseInt(v, 10)
              })}
              disabled={readOnly}
              className={inputCls}
              placeholder="e.g. 50"
            />
          </Field>

          <div className="mb-4">
            <Toggle
              label="This county council deals with council tax directly (most delegate to their districts)"
              name="deals_with_council_tax"
              register={register}
              disabled={readOnly}
            />
          </div>

          <hr className="my-4 border-gray-100" />

          <Field label="Notes — voting history & special conditions">
            <textarea
              rows={5}
              {...register('blocked_reason')}
              disabled={readOnly}
              className={inputCls}
              placeholder="Record how the county council has voted in the past, any conditions they set, and any special instructions for case workers…"
            />
          </Field>

          <Field label="Date criteria was last updated">
            <input
              type="date"
              {...register('last_reviewed')}
              disabled={readOnly}
              className={inputCls}
            />
          </Field>

          <Field label="Contact Name">
            <input
              {...register('contact_name')}
              disabled={readOnly}
              className={inputCls}
              placeholder="e.g. Council Tax Recovery Team"
            />
          </Field>

          <Field label="Contact Number / Email">
            <input
              {...register('contact_number')}
              disabled={readOnly}
              className={inputCls}
              placeholder="Phone or email"
            />
          </Field>

          <hr className="my-4 border-gray-100" />
          
          <CrmVoteSummary summary={voteSummaryQuery.data} isLoading={voteSummaryQuery.isLoading} />
          
          <hr className="my-4 border-gray-100" />

          {/* ── Districts routed to this county ── */}
          <DistrictsSection districts={detail?.districts ?? county.districts ?? []} />
        </form>

        {/* Footer */}
        <div className="px-5 py-4 border-t flex justify-end gap-2 bg-gray-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Cancel
          </button>
          {!readOnly && (
            <button
              type="submit"
              form="county-council-form"
              disabled={updateCountyCouncil.isPending || !isDirty}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updateCountyCouncil.isPending && <Spinner className="w-4 h-4 mr-2" />}
              Save Changes
            </button>
          )}
        </div>
      </div>
    </>
  )
}
