import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import axiosInstance from '../lib/axios'
import { extractErrorMessage } from '../lib/errorHandler'

/**
 * useAssessCase hook
 * TanStack Query mutation for triggering an assessment
 */
export function useAssessCase() {
  const queryClient = useQueryClient()
  const resultRef = useRef(null)

  const mutation = useMutation({
    mutationFn: async ({ aryza_reference, credit_report_id, dmp_checklist, creditor_rows, signal }) => {
      const body = {
        aryza_reference,
        ...(credit_report_id ? { credit_report_id } : {}),
        ...(dmp_checklist ? { dmp_checklist } : {}),
        ...(creditor_rows && creditor_rows.length ? { creditor_rows } : {}),
      }
      // Only pass a request config when a signal was actually supplied —
      // callers that don't need cancellation (and existing tests) see the
      // exact same 2-arg axios.post call as before.
      const { data: response } = signal
        ? await axiosInstance.post('/api/v1/criteria/assess/', body, { signal })
        : await axiosInstance.post('/api/v1/criteria/assess/', body)
      
      // Map to standardized shape for CriteriaReport
      const mappedData = {
        ...response,
        // Bug 1: Read decision_id, client_name, and aryza_reference directly
        decision_id: response.decision_id,
        client_name: response.client_name,
        aryza_reference: response.aryza_reference || aryza_reference,
        
        decision: response.overall_status === 'PASS' ? 'ELIGIBLE' : 
                 response.overall_status === 'BLOCKED' ? 'INELIGIBLE' : 
                 response.overall_status === 'FLAGGED' ? 'REFERRED' : response.overall_status,
        
        // CriteriaReport expects criteria_results array
        criteria_results: [
          ...(response.hard_blocks || []).map(r => ({ ...r, result: 'FAIL', name: r.rule_name, criterion_id: r.rule_id })),
          ...(response.flags || []).map(r => ({ ...r, result: 'FLAG', name: r.rule_name, criterion_id: r.rule_id })),
          ...(response.info || []).map(r => ({ ...r, result: 'PASS', name: r.rule_name, criterion_id: r.rule_id })),
          ...(response.passed || []).map(r => ({ ...r, result: 'PASS', name: r.rule_name, criterion_id: r.rule_id })),
        ],
        
        // Bug 4: Map recommended_solution to human labels
        recommended_solution: response.recommended_solution,
        
        // Bug 2 & 3: Financial extraction logic moved to report but ensuring fallback here
        total_unsecured_debt: response.total_unsecured_debt,
        disposable_income: response.disposable_income,
        
        // Add evaluated_at if missing
        evaluated_at: response.evaluated_at || new Date().toISOString(),
        
        // Add creditors for the report table
        creditors: response.creditors || (response.creditor_positions || []).map(cp => ({
          name: cp.creditor_name,
          balance: cp.balance
        }))
      }
      
      // Return the full response object as-is (it is already the correctly shaped object)
      return response
    },
    onSuccess: (data, variables) => {
      resultRef.current = data
      // Cache the result by reference
      queryClient.setQueryData(['assessment', variables.aryza_reference], data)
    },
  })

  return {
    runAssessment: mutation.mutate,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error ? extractErrorMessage(mutation.error) : null,
    data: mutation.data,
    reset: mutation.reset,
  }
}
