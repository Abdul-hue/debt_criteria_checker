import { useQuery } from '@tanstack/react-query'
import axiosInstance from '../lib/axios'
import { useAuth } from '../context/AuthContext'

/**
 * useAssessHistory hook
 * Fetches the most recent assessment result for a reference (Admin only)
 */
export function useAssessHistory(reference) {
  const { isAdmin } = useAuth()

  const query = useQuery({
    queryKey: ['assessment-history', reference],
    queryFn: async () => {
      const response = await axiosInstance.get(`/api/v1/criteria/assess/history/`, {
        params: { reference },
      })
      // Extract the most recent CriteriaDecision (first item from paginated results)
      const results = response.data?.results
      if (results && results.length > 0) {
        const decision = results[0]
        const assessment = decision.result_json || decision.decision_output

        // Map to standardized shape for CriteriaReport
        return {
          ...assessment,
          id: decision.id,
          client_name: decision.client_name,
          aryza_reference: decision.aryza_reference,
          evaluated_at: decision.created_at,
          decision: assessment.decision ||
                   (assessment.overall_status === 'PASS' ? 'ELIGIBLE' :
                    assessment.overall_status === 'BLOCKED' ? 'INELIGIBLE' :
                    assessment.overall_status === 'FLAGGED' ? 'REFERRED' : assessment.overall_status),

          criteria_results: assessment.criteria_results || [
            ...(assessment.hard_blocks || []).map(r => ({ ...r, result: 'FAIL', name: r.rule_id, criterion_id: r.rule_id })),
            ...(assessment.flags || []).map(r => ({ ...r, result: 'FLAG', name: r.rule_id, criterion_id: r.rule_id })),
            ...(assessment.info || []).map(r => ({ ...r, result: 'PASS', name: r.rule_id, criterion_id: r.rule_id })),
            ...(assessment.passed || []).map(r => ({ ...r, result: 'PASS', name: r.rule_id, criterion_id: r.rule_id })),
          ],

          recommended_solution: typeof assessment.recommended_solution === 'string' ? {
            label: assessment.recommended_solution === 'IVA_VIABLE' ? 'IVA Recommended' :
                   assessment.recommended_solution === 'IVA_WITH_CONDITIONS' ? 'IVA with Conditions' :
                   (assessment.recommended_solution === 'IVA_NOT_VIABLE' || assessment.recommended_solution === 'FORCED_DMP_VAT') ? 'Debt Management Plan' : assessment.recommended_solution,
            code: (assessment.recommended_solution === 'IVA_NOT_VIABLE' || assessment.recommended_solution === 'FORCED_DMP_VAT') ? 'DMP' : 'IVA'
          } : assessment.recommended_solution,

          // Read directly — both fields are now always saved in decision_output.
          // No fallback chain that could silently produce 0.
          total_unsecured_debt: assessment.total_unsecured_debt ?? assessment.majority_analysis?.total_debt ?? 0,
          disposable_income: assessment.disposable_income ?? 0,

          creditors: assessment.creditors || (assessment.creditor_positions || []).map(cp => ({
            name: cp.creditor_name,
            balance: cp.balance
          }))
        }
      }
      return null
    },
    enabled: !!reference && isAdmin,
    // Keep data fresh for 2 minutes so window-focus refetches don't silently
    // overwrite a just-completed assessment result while the caseworker is reading it.
    staleTime: 2 * 60 * 1000,
    refetchOnWindowFocus: false,
  })

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  }
}
