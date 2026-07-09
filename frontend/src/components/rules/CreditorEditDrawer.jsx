import React, { useEffect } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { creditorSchema } from '../../schemas/creditorSchema'
import { useUpdateCreditor, useCreditorOutcomes, useCreateCreditorOutcome, useDeleteCreditorOutcome, useCreditorAuditLog, useCreditorVoteSummary } from '../../hooks/useCreditors'
import { useToast } from '../../hooks/useToast'
import TagInput from './TagInput'
import Spinner from '../shared/Spinner'
import CrmVoteSummary from '../shared/CrmVoteSummary'

/**
 * Slide-in panel for viewing and editing a creditor
 */
export default function CreditorEditDrawer({ creditor, onClose, readOnly }) {
  const toast = useToast()
  const updateCreditor = useUpdateCreditor()

  const {
    register,
    handleSubmit,
    reset,
    watch,
    control,
    formState: { errors, isDirty },
  } = useForm({
    resolver: zodResolver(creditorSchema),
    defaultValues: creditor || {},
  })

  // Reset form when creditor changes
  useEffect(() => {
    if (creditor) {
      reset({
        ...creditor,
        trading_names: creditor.trading_names ?? [],
      })
    }
  }, [creditor, reset])

  if (!creditor) return null

  const onSubmit = (data) => {
    if (readOnly) return

    updateCreditor.mutate(
      { ...creditor, ...data },
      {
        onSuccess: () => {
          toast.success('Success', 'Creditor updated successfully')
          onClose()
        },
        onError: () => {
          toast.error('Error', 'Failed to update creditor — please try again.')
        },
      }
    )
  }

  const isBlocked = watch('blocked_until_cleared')
  const isConditionalVoter = watch('conditional_voter')

  const outcomesQuery = useCreditorOutcomes(creditor?.id)
  const createOutcome = useCreateCreditorOutcome(creditor?.id)
  const deleteOutcome = useDeleteCreditorOutcome(creditor?.id)
  const auditLogQuery = useCreditorAuditLog(creditor?.id)
  const voteSummaryQuery = useCreditorVoteSummary('creditors', creditor?.id)

  const [outcomeForm, setOutcomeForm] = React.useState({
    case_reference: '',
    outcome: 'approved',
    outcome_date: '',
    comment: '',
  })
  const [outcomeError, setOutcomeError] = React.useState('')
  const [aryzaRefError, setAryzaRefError] = React.useState('')
  const [submitStatus, setSubmitStatus] = React.useState('idle') // 'idle' | 'checking' | 'success' | 'error'

  const handleOutcomeSubmit = () => {
    setOutcomeError('')
    setAryzaRefError('')

    // Client-side validation — keep existing logic
    if (!outcomeForm.case_reference.trim()) {
      setAryzaRefError('Case reference is required.')
      return
    }
    if (!outcomeForm.outcome_date) {
      setOutcomeError('Date is required.')
      return
    }

    // Enter checking state immediately
    setSubmitStatus('checking')

    createOutcome.mutate(outcomeForm, {
      onSuccess: () => {
        setSubmitStatus('success')
        // After 2 s: reset form and return button to idle
        setTimeout(() => {
          setSubmitStatus('idle')
          setOutcomeForm({ case_reference: '', outcome: 'approved', outcome_date: '', comment: '' })
          setAryzaRefError('')
          setOutcomeError('')
        }, 2000)
      },
      onError: (err) => {
        setSubmitStatus('error')
        const field = err?.response?.data?.field
        const detail = err?.response?.data?.detail
        if (field === 'case_reference') {
          // Aryza ref not found
          setAryzaRefError(detail || 'Case reference not found in Aryza \u2014 please check and try again')
        } else if (err?.response?.data?.aryza_connection === false) {
          // Connection / other Aryza error
          setOutcomeError('Unable to validate against Aryza \u2014 please try again')
        } else {
          setOutcomeError(detail || 'Failed to submit outcome.')
        }
        // Reset button immediately so user can correct and resubmit
        setSubmitStatus('idle')
      },
    })
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-xl z-50 
                    flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
        
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="text-base font-semibold text-gray-800">{creditor.creditor_name}</h2>
          <button 
            onClick={onClose}
            className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            aria-label="Close drawer"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <form id="creditor-form" onSubmit={handleSubmit(onSubmit)} className="flex-1 overflow-y-auto px-5 py-4">
          {readOnly && (
            <div className="mb-4 p-2.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">
              View only — admin access required to edit creditor settings.
            </div>
          )}

          {/* Group 1 — Core settings */}
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
            <select 
              {...register('status')} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            >
              <option value="ACCEPT">ACCEPT</option>
              <option value="REJECT">REJECT</option>
              <option value="WILL_CONSIDER">WILL_CONSIDER</option>
              <option value="DO_NOT_VOTE">DO_NOT_VOTE</option>
              <option value="CONDITIONAL_VOTER">CONDITIONAL_VOTER</option>
            </select>
            {errors.status && <p className="text-xs text-red-500 mt-1">{errors.status.message}</p>}
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Representative</label>
            <select 
              {...register('representative')} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            >
              <option value="WATCH">WATCH</option>
              <option value="TIX">TIX</option>
              <option value="EVOLVE">EVOLVE</option>
              <option value="EVERYDAY_LOANS">EVERYDAY_LOANS</option>
              <option value="NONE">NONE</option>
            </select>
            {errors.representative && <p className="text-xs text-red-500 mt-1">{errors.representative.message}</p>}
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Min Dividend (pence)</label>
            <input 
              type="number" 
              step="1" 
              min="0"
              {...register('min_dividend_pence', { 
                setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseInt(v, 10) 
              })} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {errors.min_dividend_pence && <p className="text-xs text-red-500 mt-1">{errors.min_dividend_pence.message}</p>}
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Dividend Notes</label>
            <textarea 
              rows={3}
              {...register('dividend_notes')} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
              placeholder="Enter specific dividend requirements or notes..."
            />
            {errors.dividend_notes && <p className="text-xs text-red-500 mt-1">{errors.dividend_notes.message}</p>}
          </div>

          <hr className="my-4 border-gray-100" />

          {/* Group 2 — Block settings */}
          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Blocked until cleared</label>
            <input 
              type="checkbox" 
              {...register('blocked_until_cleared')} 
              disabled={readOnly}
              className="w-4 h-4 accent-blue-600 cursor-pointer disabled:cursor-not-allowed" 
            />
          </div>

          {isBlocked && (
            <div className="mb-4">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Blocked Reason <span className="text-red-500">*</span>
              </label>
              <textarea 
                rows={2}
                {...register('blocked_reason')} 
                disabled={readOnly}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
                placeholder="Enter reason for blocking..."
              />
              {errors.blocked_reason && <p className="text-xs text-red-500 mt-1">{errors.blocked_reason.message}</p>}
            </div>
          )}

          <hr className="my-4 border-gray-100" />

          {/* Group 3 — Reject conditions */}
          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Reject if prior DMP</label>
            <input type="checkbox" {...register('reject_if_dmp')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Reject if never made payment</label>
            <input type="checkbox" {...register('reject_if_never_made_payment')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Reject if second IVA</label>
            <input type="checkbox" {...register('reject_if_second_iva')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Reject if police employed</label>
            <input type="checkbox" {...register('reject_if_police_employed')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Reject if majority share exceeds (%)</label>
            <input 
              type="number" 
              step="0.1" 
              {...register('reject_if_majority_share_exceeds_pct', { 
                setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseFloat(v) 
              })} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {errors.reject_if_majority_share_exceeds_pct && <p className="text-xs text-red-500 mt-1">{errors.reject_if_majority_share_exceeds_pct.message}</p>}
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Reject if debt repayable within (months)</label>
            <input 
              type="number" 
              step="1" 
              {...register('reject_if_debt_repayable_within_months', { 
                setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseInt(v, 10) 
              })} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {errors.reject_if_debt_repayable_within_months && <p className="text-xs text-red-500 mt-1">{errors.reject_if_debt_repayable_within_months.message}</p>}
          </div>

          <hr className="my-4 border-gray-100" />

          {/* Group 4 — Additional settings */}
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Fees cap (%)</label>
            <input 
              type="number" 
              step="0.1" 
              {...register('fees_cap_percentage', { 
                setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseFloat(v) 
              })} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {errors.fees_cap_percentage && <p className="text-xs text-red-500 mt-1">{errors.fees_cap_percentage.message}</p>}
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Vehicle arrears repossession (months)</label>
            <input 
              type="number" 
              step="1" 
              {...register('vehicle_arrears_repossession_months', { 
                setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseInt(v, 10) 
              })} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {errors.vehicle_arrears_repossession_months && <p className="text-xs text-red-500 mt-1">{errors.vehicle_arrears_repossession_months.message}</p>}
          </div>

          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Requires arrangement call before proposing</label>
            <input type="checkbox" {...register('requires_arrangement_call_before_proposing')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Fraud claim risk</label>
            <input type="checkbox" {...register('fraud_claim_risk')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          <hr className="my-4 border-gray-100" />

          {/* Group 5 — Conditional voter */}
          <div className="flex items-center justify-between mb-4">
            <label className="text-xs font-medium text-gray-600">Conditional voter</label>
            <input type="checkbox" {...register('conditional_voter')} disabled={readOnly} className="w-4 h-4 accent-blue-600" />
          </div>

          {isConditionalVoter && (
            <div className="mb-4">
              <label className="block text-xs font-medium text-gray-600 mb-1">Conditional voter min dividend (pence)</label>
              <input 
                type="number" 
                step="0.01" 
                {...register('conditional_voter_min_dividend_pence', { 
                  setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseFloat(v) 
                })} 
                disabled={readOnly}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
              />
              {errors.conditional_voter_min_dividend_pence && <p className="text-xs text-red-500 mt-1">{errors.conditional_voter_min_dividend_pence.message}</p>}
            </div>
          )}

          <hr className="my-4 border-gray-100" />

          {/* Group 6 — Trading names */}
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Trading Names</label>
            <Controller
              name="trading_names"
              control={control}
              render={({ field }) => (
                <TagInput 
                  value={field.value} 
                  onChange={field.onChange} 
                  disabled={readOnly} 
                />
              )}
            />
            {errors.trading_names && <p className="text-xs text-red-500 mt-1">{errors.trading_names.message}</p>}
          </div>

          <hr className="my-4 border-gray-100" />

          {/* Group 7 — Contact & General Criteria */}
          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Contact Name</label>
            <input 
              type="text" 
              {...register('contact_name')} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Contact Email</label>
            <input 
              type="email" 
              {...register('contact_email')} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
            {errors.contact_email && <p className="text-xs text-red-500 mt-1">{errors.contact_email.message}</p>}
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Contact Phone</label>
            <input 
              type="text" 
              {...register('contact_phone')} 
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">General Criteria Notes</label>
            <textarea 
              {...register('criteria_notes')} 
              rows={4}
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
          </div>

          <div className="mb-4">
            <label className="block text-xs font-medium text-gray-600 mb-1">Updated Criteria (Excel Reference)</label>
            <input
              type="text"
              {...register('raw_updated_criteria')}
              disabled={readOnly}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
            />
          </div>

          <hr className="my-4 border-gray-100" />

          {/* Group 7.5 — CRM Vote Summary */}
          <CrmVoteSummary summary={voteSummaryQuery.data} isLoading={voteSummaryQuery.isLoading} />

          <hr className="my-4 border-gray-100" />

          {/* Group 8 — Case Outcomes */}
          <div className="mb-4">
            <p className="text-xs font-semibold text-gray-700 mb-3 uppercase tracking-wide">Case Outcomes</p>

            {/* Tally */}
            {outcomesQuery.isLoading && (
              <p className="text-xs text-gray-400 mb-3">Loading outcomes...</p>
            )}
            {outcomesQuery.data && (
              <div className="flex gap-4 mb-4">
                <span className="text-sm font-medium text-green-700">
                  {outcomesQuery.data.tally.approved} Approved
                </span>
                <span className="text-sm font-medium text-red-600">
                  {outcomesQuery.data.tally.disapproved} Disapproved
                </span>
                <span className="text-sm text-gray-500">
                  {outcomesQuery.data.tally.total} Total
                </span>
              </div>
            )}

            {/* Submit form */}
            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">Case Reference</label>
              <input
                type="text"
                value={outcomeForm.case_reference}
                onChange={e => {
                  setAryzaRefError('')
                  setOutcomeForm(f => ({ ...f, case_reference: e.target.value }))
                }}
                className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 ${
                  aryzaRefError ? 'border-red-400 bg-red-50' : 'border-gray-300'
                }`}
                placeholder="e.g. IVA-12345"
              />
              {aryzaRefError && (
                <p className="text-xs text-red-500 mt-1">{aryzaRefError}</p>
              )}
            </div>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">Outcome Date</label>
              <input
                type="date"
                value={outcomeForm.outcome_date}
                onChange={e => setOutcomeForm(f => ({ ...f, outcome_date: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">Outcome</label>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setOutcomeForm(f => ({ ...f, outcome: 'approved' }))}
                  className={`px-3 py-1.5 text-sm rounded-md border font-medium transition-colors ${
                    outcomeForm.outcome === 'approved'
                      ? 'bg-green-600 text-white border-green-600'
                      : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  Approved
                </button>
                <button
                  type="button"
                  onClick={() => setOutcomeForm(f => ({ ...f, outcome: 'disapproved' }))}
                  className={`px-3 py-1.5 text-sm rounded-md border font-medium transition-colors ${
                    outcomeForm.outcome === 'disapproved'
                      ? 'bg-red-600 text-white border-red-600'
                      : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  Disapproved
                </button>
              </div>
            </div>

            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">Comment (optional)</label>
              <textarea
                rows={2}
                value={outcomeForm.comment}
                onChange={e => setOutcomeForm(f => ({ ...f, comment: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
                placeholder="Any notes about this outcome..."
              />
            </div>

            {outcomeError && (
              <p className="text-xs text-red-500 mb-2">{outcomeError}</p>
            )}

            {/* Submit Outcome — status-driven button */}
            <button
              type="button"
              onClick={handleOutcomeSubmit}
              disabled={submitStatus === 'checking' || submitStatus === 'success'}
              className={[
                'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border border-transparent rounded-md',
                'focus:outline-none focus:ring-2 focus:ring-offset-1',
                'transition-all duration-300',
                submitStatus === 'checking'
                  ? 'bg-blue-400 text-white cursor-not-allowed focus:ring-blue-300'
                  : submitStatus === 'success'
                  ? 'bg-green-600 text-white cursor-default focus:ring-green-400'
                  : 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-400',
              ].join(' ')}
            >
              {submitStatus === 'checking' && (
                <>
                  {/* Pulsing dot animation for 'checking' state */}
                  <span className="flex items-center gap-1" aria-hidden="true">
                    <span
                      style={{ animation: 'outcomeCheckPulse 1.1s ease-in-out infinite' }}
                      className="inline-block w-2 h-2 rounded-full bg-white/70"
                    />
                    <span
                      style={{ animation: 'outcomeCheckPulse 1.1s ease-in-out 0.2s infinite' }}
                      className="inline-block w-2 h-2 rounded-full bg-white/70"
                    />
                    <span
                      style={{ animation: 'outcomeCheckPulse 1.1s ease-in-out 0.4s infinite' }}
                      className="inline-block w-2 h-2 rounded-full bg-white/70"
                    />
                  </span>
                  Checking reference in Aryza...
                </>
              )}
              {submitStatus === 'success' && (
                <>
                  <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                  Outcome Recorded
                </>
              )}
              {(submitStatus === 'idle' || submitStatus === 'error') && 'Submit Outcome'}
            </button>

            {/* Keyframes injected inline — avoids needing a separate CSS file */}
            <style>{`
              @keyframes outcomeCheckPulse {
                0%, 100% { opacity: 0.3; transform: scale(0.85); }
                50%       { opacity: 1;   transform: scale(1.1);  }
              }
            `}</style>

            {/* Past outcomes list */}
            {outcomesQuery.data?.outcomes?.length > 0 && (
              <div className="mt-4 space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Past Entries</p>
                {outcomesQuery.data.outcomes.map(o => (
                  <div key={o.id} className="p-3 bg-gray-50 rounded-md border border-gray-100 text-xs text-gray-700">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium">{o.case_reference}</span>
                      <div className="flex items-center gap-2">
                        <span className={`font-semibold ${o.outcome === 'approved' ? 'text-green-700' : 'text-red-600'}`}>
                          {o.outcome === 'approved' ? 'Approved' : 'Disapproved'}
                        </span>
                        <button
                          type="button"
                          onClick={() => deleteOutcome.mutate(o.id)}
                          disabled={deleteOutcome.isPending}
                          className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                          aria-label="Delete outcome"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    <div className="text-gray-500">
                      {o.outcome_date} · {o.submitted_by}
                    </div>
                    {o.comment && <div className="mt-1 text-gray-600 italic">"{o.comment}"</div>}
                  </div>
                ))}
              </div>
            )}

            {outcomesQuery.data?.outcomes?.length === 0 && (
              <p className="mt-3 text-xs text-gray-400">No outcomes logged yet.</p>
            )}
          </div>

          <hr className="my-4 border-gray-100" />

          {/* Group 9 — Audit Trail */}
          <div className="mb-4">
            <p className="text-xs font-semibold text-gray-700 mb-3 uppercase tracking-wide">Audit Trail</p>

            {auditLogQuery.isLoading && (
              <p className="text-xs text-gray-400">Loading audit log...</p>
            )}

            {auditLogQuery.data?.length === 0 && (
              <p className="text-xs text-gray-400">No changes recorded yet.</p>
            )}

            {auditLogQuery.data?.length > 0 && (
              <div className="space-y-2">
                {auditLogQuery.data.map(log => (
                  <div key={log.id} className="p-3 bg-gray-50 rounded-md border border-gray-100 text-xs text-gray-700">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium capitalize">{log.field_name.replace(/_/g, ' ')}</span>
                      <span className="text-gray-400">{new Date(log.changed_at).toLocaleString('en-GB')}</span>
                    </div>
                    <div className="text-gray-500 mb-1">{log.changed_by}</div>
                    <div className="flex gap-2 items-center">
                      <span className="line-through text-red-400">{log.old_value || '—'}</span>
                      <svg className="w-3 h-3 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                      <span className="text-green-700">{log.new_value || '—'}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </form>

        {/* Footer */}
        {!readOnly && (
          <div className="px-5 py-4 border-t flex justify-end gap-2 bg-gray-50">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              Cancel
            </button>
            <button
              type="submit"
              form="creditor-form"
              disabled={updateCreditor.isPending}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updateCreditor.isPending && <Spinner className="w-4 h-4 mr-2" />}
              Save Changes
            </button>
          </div>
        )}
      </div>
    </>
  )
}
