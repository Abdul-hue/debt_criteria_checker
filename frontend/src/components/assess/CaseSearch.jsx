import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { assessmentFormSchema } from '../../schemas/assessmentSchema'
import { useAssessCase } from '../../hooks/useAssessCase'
import { useAssessHistory } from '../../hooks/useAssessHistory'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../hooks/useToast'
import LoadingSpinner from '../shared/LoadingSpinner'

/**
 * CaseSearch component
 * Left sidebar search panel for triggering assessments
 */
export default function CaseSearch({ onResult, onError }) {
  const [lastRun, setLastRun] = useState(null)
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

  const onSubmit = (values) => {
    runAssessment(values, {
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

        <button
          type="submit"
          disabled={isPending}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-md py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
