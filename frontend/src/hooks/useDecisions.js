import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useDecisions() {
  return useQuery({
    queryKey: ['decisions'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/assess/history/?page_size=200'
      while (url) {
        const { data } = await api.get(url)
        const rawResults = data.results ?? data
        
        // Map each decision to ensure result_json is compatible with CriteriaReport
        const mappedResults = rawResults.map(decision => {
          const assessment = decision.result_json || decision.decision_output
          if (!assessment) return decision

          // If result_json already exists and has criteria_results, it's the new format
          if (decision.result_json && decision.result_json.criteria_results) {
            return decision
          }

          // Otherwise, map decision_output to the standardized shape
          const mappedAssessment = {
            ...assessment,
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
                     assessment.recommended_solution === 'IVA_NOT_VIABLE' ? 'Debt Management Plan' : assessment.recommended_solution,
              code: assessment.recommended_solution === 'IVA_NOT_VIABLE' ? 'DMP' : 'IVA'
            } : assessment.recommended_solution,
            
            total_unsecured_debt: assessment.total_unsecured_debt ?? (assessment.majority_analysis?.total_debt || 0),
            disposable_income: assessment.disposable_income ?? (assessment.dividend_analysis?.monthly_di || 0),
            
            creditors: assessment.creditors || (assessment.creditor_positions || []).map(cp => ({
              name: cp.creditor_name,
              balance: cp.balance
            })),
            evaluated_at: decision.created_at,
            client_name: decision.client_name,
            aryza_reference: decision.aryza_reference
          }

          return {
            ...decision,
            result_json: mappedAssessment
          }
        })

        results = results.concat(mappedResults)
        url = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null
      }
      return results
    },
    staleTime: 1 * 60 * 1000,
  })
}

export function useDeleteDecision() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/criteria/assess/history/${id}/`)
      return id
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['decisions'] }),
  })
}
