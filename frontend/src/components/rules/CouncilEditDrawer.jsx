import React, { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useUpdateCouncil } from '../../hooks/useCouncils'
import { useCreditorVoteSummary } from '../../hooks/useCreditors'
import { useToast } from '../../hooks/useToast'
import Spinner from '../shared/Spinner'
import CrmVoteSummary from '../shared/CrmVoteSummary'

const STATUS_OPTIONS = [
  { value: 'ACCEPT',            label: 'Accepts — votes to approve IVAs'         },
  { value: 'REJECT',            label: 'Rejects — votes against IVAs'            },
  { value: 'WILL_CONSIDER',     label: 'Will Consider — reviews case by case'    },
  { value: 'DO_NOT_VOTE',       label: 'Does Not Vote — never submits a proxy'   },
  { value: 'CONDITIONAL_VOTER', label: 'Case by Case — conditional acceptance'   },
]

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

export default function CouncilEditDrawer({ council, onClose, readOnly }) {
  const toast = useToast()
  const updateCouncil = useUpdateCouncil()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm({ defaultValues: council || {} })

  useEffect(() => {
    if (council) reset(council)
  }, [council, reset])

  if (!council) return null
  
  const voteSummaryQuery = useCreditorVoteSummary('councils', council?.id)

  const onSubmit = (data) => {
    if (readOnly) return
    updateCouncil.mutate(
      { id: council.id, ...data },
      {
        onSuccess: () => {
          toast.success('Saved', `${data.council_name} updated successfully.`)
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
          <h2 className="text-base font-semibold text-gray-800 truncate pr-4">{council.council_name}</h2>
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
        <form id="council-form" onSubmit={handleSubmit(onSubmit)} className="flex-1 overflow-y-auto px-5 py-4 space-y-0">
          {readOnly && (
            <div className="mb-4 p-2.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">
              View only — admin access required to edit council settings.
            </div>
          )}

          {/* ── Core identity ── */}
          <Field label="Council Name">
            <input {...register('council_name', { required: true })} disabled={readOnly} className={inputCls} />
            {errors.council_name && <p className="text-xs text-red-500 mt-1">Council name is required.</p>}
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

          <hr className="my-4 border-gray-100" />

          {/* ── Excel sheet fields ── */}
          <Field label="Notes — voting history & special conditions">
            <textarea
              rows={5}
              {...register('blocked_reason')}
              disabled={readOnly}
              className={inputCls}
              placeholder="Record how the council has voted in the past, any conditions they set, and any special instructions for case workers…"
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

          <Field label="Date criteria changed from Rejection">
            <input
              {...register('criteria_changed_from_rej_date')}
              disabled={readOnly}
              className={inputCls}
              placeholder="e.g. 01/06/2024 — leave blank if council has always had this status"
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

          {/* ── Flags ── */}
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Special Behaviour</p>
          <p className="text-xs text-gray-400 mb-2">These flags affect how the system treats this council when running assessments.</p>

          <div className="bg-gray-50 rounded-md px-3 py-1 mb-4">
            <Toggle label="Do Not Chase — if we chase this council, treat as Rejection" name="do_not_chase" register={register} disabled={readOnly} />
            <Toggle label="Always include current year's council tax (even if not yet in arrears)" name="include_current_year_ct" register={register} disabled={readOnly} />
          </div>

          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">When Does This Council Reject?</p>
          <p className="text-xs text-gray-400 mb-2">Tick all the situations where this council will vote to reject an IVA.</p>

          <div className="bg-gray-50 rounded-md px-3 py-1 mb-4">
            <Toggle label="Client is employed (council can apply an Attachment of Earnings)" name="reject_if_employed" register={register} disabled={readOnly} />
            <Toggle label="Client is unemployed AND owns a home" name="reject_if_unemployed_and_homeowner" register={register} disabled={readOnly} />
            <Toggle label="Client's only income is benefits" name="reject_if_benefits_only" register={register} disabled={readOnly} />
            <Toggle label="Client receives any benefits at all" name="reject_if_any_benefits" register={register} disabled={readOnly} />
            <Toggle label="Client has had a previous IVA" name="reject_if_previous_iva" register={register} disabled={readOnly} />
            <Toggle label="Client qualifies for a Debt Relief Order (DRO)" name="reject_if_dro_criteria_met" register={register} disabled={readOnly} />
            <Toggle label="An Attachment of Earnings (AOE) is already in place" name="reject_if_aoe_in_place" register={register} disabled={readOnly} />
            <Toggle label="Sole application (only one person entering the IVA)" name="reject_if_sole" register={register} disabled={readOnly} />
            <Toggle label="Joint debt — only one party entering the IVA" name="reject_if_joint_one_party_only" register={register} disabled={readOnly} />
            <Toggle label="Joint debt — both parties entering the IVA" name="reject_if_joint_both_parties" register={register} disabled={readOnly} />
            <Toggle label="Joint case — one party is employed" name="reject_if_joint_one_employed" register={register} disabled={readOnly} />
          </div>
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
              form="council-form"
              disabled={updateCouncil.isPending || !isDirty}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updateCouncil.isPending && <Spinner className="w-4 h-4 mr-2" />}
              Save Changes
            </button>
          )}
        </div>
      </div>
    </>
  )
}
