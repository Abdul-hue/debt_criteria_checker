import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { assessmentFormSchema } from '../../schemas/assessmentSchema'
import { useAssessCase } from '../../hooks/useAssessCase'
import { useAssessHistory } from '../../hooks/useAssessHistory'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../shared/LoadingSpinner'
import axiosInstance from '../../lib/axios'

/**
 * CaseSearch component
 * Left sidebar search panel for triggering assessments
 */
export default function CaseSearch({ onResult, onError, dmpChecklist, onDmpChecklistChange, hmrcIsCreditor = null }) {
  const [lastRun, setLastRun] = useState(null)
  const [uploadState, setUploadState] = useState('idle') // idle | uploading | success | error
  const [uploadResult, setUploadResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const { isAdmin } = useAuth()
  const toast = useToast()
  
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(assessmentFormSchema),
    defaultValues: {
      aryza_reference: '',
    },
  })

  const reference = watch('aryza_reference')

  const { runAssessment, isPending } = useAssessCase()
  const { refetch: fetchHistory, isLoading: isHistoryLoading } = useAssessHistory(reference)

  // --- DMP Eligibility Checklist ---
  // Reduced from 11 to 6 case-level checkboxes — council tax current/previous,
  // water, and parking government/private now come from per-row dropdowns on
  // the Creditor Positions table (CriteriaReport.jsx) instead. These 6 remain
  // here because no reliable per-creditor signal exists for them (no gas/
  // electric distinguishing signal in Aryza data; lost-right-to-pay is a
  // case-level fact, never per-row).
  const DMP_CHECKLIST_ITEMS = [
    { key: 'current_gas_bill', label: 'Current gas bill' },
    { key: 'current_electric_bill', label: 'Current electric bill' },
    { key: 'previous_gas_provider_debt', label: 'Previous gas provider debt' },
    { key: 'previous_electric_provider_debt', label: 'Previous electric provider debt' },
    { key: 'current_phone_contract', label: 'Current phone contract (fallback — only if it doesn\'t appear as its own row)' },
    { key: 'lost_right_to_pay_instalments', label: 'Lost the right to pay current year\'s balance by instalments' },
  ]
  const [dmpChecklistOpen, setDmpChecklistOpen] = useState(false)
  const handleDmpChecklistToggle = (key) => {
    onDmpChecklistChange((prev) => {
      const next = !prev[key]
      // Unticking the parent hides the nested "Previous year VAT" checkbox
      // (it only renders when hmrc_debt_has_vat is true), but its own state
      // otherwise survives untouched — orphaning hmrc_previous_year_vat=true
      // with no visible control left to clear it, and the backend forces DMP
      // off that stale flag alone regardless of the parent's state.
      if (key === 'hmrc_debt_has_vat' && !next) {
        return { ...prev, hmrc_debt_has_vat: false, hmrc_previous_year_vat: false }
      }
      return { ...prev, [key]: next }
    })
  }

  const onSubmit = (values) => {
    // Pin the assessment to the exact credit report just uploaded for this
    // reference — without this, the backend re-derives "the" credit report
    // from history, which can silently pick a stale extraction over the one
    // the user just uploaded.
    const creditReportId =
      uploadResult?.aryza_reference === values.aryza_reference
        ? uploadResult?.credit_report_id
        : undefined

    runAssessment({
      ...values,
      credit_report_id: creditReportId,
      dmp_checklist: dmpChecklist,
    }, {
      onSuccess: (data) => {
        setLastRun(new Date().toLocaleTimeString())
        onResult(data, creditReportId)
        toast.success('Assessment complete', 'Results loaded below')
      },
      onError: (error) => {
        const errorMessage = error?.message ?? 'Assessment failed. Please try again.'
        onError(errorMessage)
        toast.error('Assessment failed', errorMessage)
      },
    })
  }

  const handleCreditReportChange = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    const currentRef = reference.trim()
    if (!currentRef) {
      setUploadError('Enter a case reference before uploading')
      setUploadState('error')
      e.target.value = ''
      return
    }

    setUploadState('uploading')
    setUploadResult(null)
    setUploadError(null)

    const formData = new FormData()
    formData.append('aryza_reference', currentRef)
    formData.append('credit_report', file)

    try {
      const { data } = await axiosInstance.post('/api/v1/criteria/upload-credit-report/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadState('success')
      setUploadResult(data)
    } catch (err) {
      const msg = err?.response?.data?.error || 'Upload failed. Please try again.'
      setUploadState('error')
      setUploadError(msg)
    } finally {
      e.target.value = ''
    }
  }

  const handleLoadSaved = async () => {
    try {
      const { data } = await fetchHistory()
      if (data) {
        onResult(data)
        toast.success('Saved result loaded', 'Previous assessment data retrieved')
      } else {
        toast.info('No history found', 'No previous assessments for this reference')
      }
    } catch (err) {
      toast.error('History fetch failed', 'Could not retrieve previous assessment')
    }
  }

  return (
    <div className="w-72 bg-white border-r border-gray-200 flex flex-col p-5 shrink-0 h-full overflow-y-auto">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
        Run Assessment
      </h2>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Case Reference
          </label>
          <input
            {...register('aryza_reference')}
            type="text"
            placeholder="e.g. ARZ-2024-001"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {errors.aryza_reference && (
            <p className="text-xs text-red-600 mt-1">{errors.aryza_reference.message}</p>
          )}
        </div>

        <div className="border border-gray-200 rounded-md p-3 space-y-2">
          <button
            type="button"
            onClick={() => setDmpChecklistOpen((prev) => !prev)}
            className="w-full flex items-center justify-between text-xs font-medium text-gray-500 uppercase tracking-wide"
          >
            <span>DMP Eligibility Checklist</span>
            <span className="text-gray-400">{dmpChecklistOpen ? '−' : '+'}</span>
          </button>
          {dmpChecklistOpen && (
            <ul className="space-y-1.5 pt-1">
              {DMP_CHECKLIST_ITEMS.map(({ key, label }) => (
                <li key={key}>
                  <label className="flex items-start gap-2 text-xs text-gray-700">
                    <input
                      type="checkbox"
                      checked={dmpChecklist[key]}
                      onChange={() => handleDmpChecklistToggle(key)}
                      className="mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span>{label}</span>
                  </label>
                </li>
              ))}

              {/* HMRC VAT — gated on hmrc_is_creditor from the last assessment
                  result. hmrcIsCreditor is tri-state: null = no result yet,
                  true/false = known from the last run. */}
              <li className="pt-2 mt-1 border-t border-gray-100">
                <label
                  className={`flex items-start gap-2 text-xs ${hmrcIsCreditor ? 'text-gray-700' : 'text-gray-400'}`}
                >
                  <input
                    type="checkbox"
                    checked={dmpChecklist.hmrc_debt_has_vat}
                    disabled={!hmrcIsCreditor}
                    onChange={() => handleDmpChecklistToggle('hmrc_debt_has_vat')}
                    className="mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                  />
                  <span>HMRC Debt has VAT</span>
                </label>

                {!hmrcIsCreditor && (
                  <p className="text-[10px] text-gray-400 mt-1 ml-6">
                    {hmrcIsCreditor === null
                      ? 'Run assessment first to check HMRC status'
                      : 'No HMRC debt detected in this case'}
                  </p>
                )}

                {hmrcIsCreditor && (
                  <span className="ml-6 mt-1 inline-block text-[10px] font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded px-1.5 py-0.5">
                    Current year VAT
                  </span>
                )}

                {hmrcIsCreditor && dmpChecklist.hmrc_debt_has_vat && (
                  <label className="flex items-start gap-2 text-xs text-gray-700 mt-1.5 ml-6">
                    <input
                      type="checkbox"
                      checked={dmpChecklist.hmrc_previous_year_vat}
                      onChange={() => handleDmpChecklistToggle('hmrc_previous_year_vat')}
                      className="mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span>Previous year VAT</span>
                  </label>
                )}
              </li>
            </ul>
          )}
        </div>

        <button
          type="submit"
          disabled={isPending}
          className="w-full bg-brand-navy hover:bg-slate-800 text-white rounded-md py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {isPending ? (
            <>
              <LoadingSpinner size="sm" />
              <span>Running...</span>
            </>
          ) : (
            'Run Assessment'
          )}
        </button>
      </form>

      <div className="mt-4 space-y-2">
        <label className="block text-xs font-medium text-gray-500 mb-1">
          Credit Report (optional PDF)
        </label>
        <input
          type="file"
          accept=".pdf"
          onChange={handleCreditReportChange}
          disabled={uploadState === 'uploading'}
          className="w-full text-xs text-gray-500 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 disabled:opacity-50"
        />
        {uploadState === 'uploading' && (
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <LoadingSpinner size="sm" /> Uploading...
          </span>
        )}
        {uploadState === 'success' && uploadResult && (
          <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded p-2">
            <span className="font-medium">Uploaded</span>
            {uploadResult.agency && uploadResult.agency !== 'Unknown' && (
              <span> — {uploadResult.agency}</span>
            )}
            {uploadResult.accounts_found > 0 && (
              <span>, {uploadResult.accounts_found} account{uploadResult.accounts_found !== 1 ? 's' : ''} found</span>
            )}
          </div>
        )}
        {uploadState === 'error' && uploadError && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2">
            {uploadError}
          </p>
        )}
      </div>

      <div className="my-6 border-t border-gray-100" />

      {isAdmin && (
        <div className="space-y-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Admin: Last Saved Result
          </h3>
          <button
            onClick={handleLoadSaved}
            disabled={!reference || isHistoryLoading}
            className="w-full border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-md py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isHistoryLoading ? <LoadingSpinner size="sm" /> : 'Load Saved Result'}
          </button>
        </div>
      )}

      <div className="mt-auto pt-4">
        {lastRun && (
          <p className="text-xs text-gray-400">
            Last run: {lastRun}
          </p>
        )}
      </div>
    </div>
  )
}
