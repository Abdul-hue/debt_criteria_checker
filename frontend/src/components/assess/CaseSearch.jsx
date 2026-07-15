import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { assessmentFormSchema } from '../../schemas/assessmentSchema'
import { useAssessCase } from '../../hooks/useAssessCase'
import { useAssessHistory } from '../../hooks/useAssessHistory'
import { useCouncils } from '../../hooks/useCouncils'
import { useEnergyCompanies } from '../../hooks/useEnergyCompanies'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../shared/LoadingSpinner'
import axiosInstance from '../../lib/axios'

/**
 * CaseSearch component
 * Left sidebar search panel for triggering assessments
 */
export default function CaseSearch({ onResult, onError }) {
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

  // --- Manual council addition ---
  const { data: councils = [] } = useCouncils()
  const [councilSearch, setCouncilSearch] = useState('')
  const [councilSelectedId, setCouncilSelectedId] = useState('')
  const [councilBalanceInput, setCouncilBalanceInput] = useState('')
  const [manualCouncils, setManualCouncils] = useState([])
  const [councilError, setCouncilError] = useState('')

  const filteredCouncils = councils.filter((c) =>
    c.council_name?.toLowerCase().includes(councilSearch.toLowerCase())
  )

  const handleAddCouncil = () => {
    const id = Number(councilSelectedId)
    const balance = Number(councilBalanceInput)
    if (!id) {
      setCouncilError('Select a council')
      return
    }
    if (!(balance > 0)) {
      setCouncilError('Balance must be a positive number')
      return
    }
    if (manualCouncils.some((m) => m.council_id === id)) {
      setCouncilError('That council has already been added')
      return
    }
    const council = councils.find((c) => c.id === id)
    setManualCouncils((prev) => [
      ...prev,
      { council_id: id, council_name: council?.council_name ?? '', balance },
    ])
    setCouncilSelectedId('')
    setCouncilBalanceInput('')
    setCouncilError('')
  }

  const handleRemoveCouncil = (id) => {
    setManualCouncils((prev) => prev.filter((m) => m.council_id !== id))
  }

  // --- Manual energy company addition ---
  const [energySearch, setEnergySearch] = useState('')
  const { data: energyResults = [], isFetching: isEnergyLoading } = useEnergyCompanies(energySearch)
  const [energySelectedId, setEnergySelectedId] = useState('')
  const [energyBalanceInput, setEnergyBalanceInput] = useState('')
  const [manualEnergy, setManualEnergy] = useState([])
  const [energyError, setEnergyError] = useState('')

  const handleAddEnergy = () => {
    const id = Number(energySelectedId)
    const balance = Number(energyBalanceInput)
    if (!id) {
      setEnergyError('Select an energy company')
      return
    }
    if (!(balance > 0)) {
      setEnergyError('Balance must be a positive number')
      return
    }
    if (manualEnergy.some((m) => m.creditor_id === id)) {
      setEnergyError('That energy company has already been added')
      return
    }
    const creditor = energyResults.find((c) => c.id === id)
    setManualEnergy((prev) => [
      ...prev,
      { creditor_id: id, creditor_name: creditor?.creditor_name ?? '', balance },
    ])
    setEnergySelectedId('')
    setEnergyBalanceInput('')
    setEnergyError('')
  }

  const handleRemoveEnergy = (id) => {
    setManualEnergy((prev) => prev.filter((m) => m.creditor_id !== id))
  }

  // --- DMP Eligibility Checklist ---
  // Phase A: fields only — no rule reads these yet, so this section is
  // collapsed by default since most cases won't need it.
  const DMP_CHECKLIST_ITEMS = [
    { key: 'current_year_council_tax', label: "Current year's council tax" },
    { key: 'previous_year_council_tax', label: "Previous year's council tax" },
    { key: 'lost_right_to_pay_instalments', label: 'Lost the right to pay current year\'s balance by instalments' },
    { key: 'current_gas_bill', label: 'Current gas bill' },
    { key: 'current_electric_bill', label: 'Current electric bill' },
    { key: 'previous_gas_provider_debt', label: 'Previous gas provider debt' },
    { key: 'previous_electric_provider_debt', label: 'Previous electric provider debt' },
    { key: 'current_water_bill', label: 'Current water bill' },
    { key: 'government_parking_hmrc_debt', label: 'Government parking / HMRC debt' },
    { key: 'private_parking_debt', label: 'Private parking debt' },
    { key: 'current_phone_contract', label: 'Current phone contract' },
  ]
  const [dmpChecklistOpen, setDmpChecklistOpen] = useState(false)
  const [dmpChecklist, setDmpChecklist] = useState(
    () => Object.fromEntries(DMP_CHECKLIST_ITEMS.map(({ key }) => [key, false]))
  )
  const handleDmpChecklistToggle = (key) => {
    setDmpChecklist((prev) => ({ ...prev, [key]: !prev[key] }))
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
      manual_councils: manualCouncils.map(({ council_id, balance }) => ({ council_id, balance })),
      manual_energy: manualEnergy.map(({ creditor_id, balance }) => ({ creditor_id, balance })),
      dmp_checklist: dmpChecklist,
    }, {
      onSuccess: (data) => {
        setLastRun(new Date().toLocaleTimeString())
        onResult(data)
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
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide">
            Add Council
          </label>
          <input
            type="text"
            value={councilSearch}
            onChange={(e) => setCouncilSearch(e.target.value)}
            placeholder="Search councils..."
            className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <select
            value={councilSelectedId}
            onChange={(e) => setCouncilSelectedId(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Select a council...</option>
            {filteredCouncils.map((c) => (
              <option key={c.id} value={c.id}>{c.council_name}</option>
            ))}
          </select>
          <div className="flex gap-2">
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={councilBalanceInput}
              onChange={(e) => setCouncilBalanceInput(e.target.value)}
              placeholder="Balance (£)"
              className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={handleAddCouncil}
              className="shrink-0 border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-md px-3 py-1.5 text-sm font-medium"
            >
              Add
            </button>
          </div>
          {councilError && <p className="text-xs text-red-600">{councilError}</p>}
          {manualCouncils.length > 0 && (
            <ul className="space-y-1">
              {manualCouncils.map((m) => (
                <li key={m.council_id} className="flex items-center justify-between text-xs bg-gray-50 rounded px-2 py-1">
                  <span>{m.council_name} — £{m.balance.toFixed(2)}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveCouncil(m.council_id)}
                    className="text-red-600 hover:text-red-800 font-medium ml-2"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border border-gray-200 rounded-md p-3 space-y-2">
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide">
            Add Energy Company
          </label>
          <input
            type="text"
            value={energySearch}
            onChange={(e) => setEnergySearch(e.target.value)}
            placeholder="Search energy companies..."
            className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <select
            value={energySelectedId}
            onChange={(e) => setEnergySelectedId(e.target.value)}
            disabled={isEnergyLoading}
            className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">
              {isEnergyLoading ? 'Searching...' : 'Select an energy company...'}
            </option>
            {energyResults.map((c) => (
              <option key={c.id} value={c.id}>{c.creditor_name}</option>
            ))}
          </select>
          <div className="flex gap-2">
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={energyBalanceInput}
              onChange={(e) => setEnergyBalanceInput(e.target.value)}
              placeholder="Balance (£)"
              className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={handleAddEnergy}
              className="shrink-0 border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-md px-3 py-1.5 text-sm font-medium"
            >
              Add
            </button>
          </div>
          {energyError && <p className="text-xs text-red-600">{energyError}</p>}
          {manualEnergy.length > 0 && (
            <ul className="space-y-1">
              {manualEnergy.map((m) => (
                <li key={m.creditor_id} className="flex items-center justify-between text-xs bg-gray-50 rounded px-2 py-1">
                  <span>{m.creditor_name} — £{m.balance.toFixed(2)}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveEnergy(m.creditor_id)}
                    className="text-red-600 hover:text-red-800 font-medium ml-2"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
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
