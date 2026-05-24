import React, { useEffect } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { creditorSchema } from '../../schemas/creditorSchema'
import { useUpdateCreditor } from '../../hooks/useCreditors'
import { useToast } from '../../hooks/useToast'
import TagInput from './TagInput'
import Spinner from '../shared/Spinner'

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
