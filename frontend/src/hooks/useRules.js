import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

/**
 * Hook to fetch all global rules
 */
export function useRules() {
  return useQuery({
    queryKey: ['rules'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/rules/?page_size=500'
      while (url) {
        const { data } = await api.get(url)
        results = results.concat(data.results ?? data)
        url = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null
      }
      return results
    },
    staleTime: 0,
  })
}

/**
 * Hook to fetch a single rule with full details
 */
export function useRuleDetail(ruleKey, enabled = true) {
  return useQuery({
    queryKey: ['rule', ruleKey],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/rules/${ruleKey}/`)
      return data
    },
    enabled: enabled && !!ruleKey,
    staleTime: 60000, // 1 minute
  })
}

/**
 * Hook to update a rule
 */
export function usePatchRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ ruleKey, ...payload }) => {
      const { data } = await api.put(`/api/v1/criteria/rules/${ruleKey}/`, payload)
      return data
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      queryClient.invalidateQueries({ queryKey: ['rule', variables.ruleKey] })
    },
  })
}

/**
 * Hook to create a rule
 */
export function useCreateRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload) => {
      const { data } = await api.post('/api/v1/criteria/rules/', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })
}

/**
 * Hook to delete a rule
 */
export function useDeleteRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (ruleKey) => {
      await api.delete(`/api/v1/criteria/rules/${ruleKey}/`)
      return ruleKey
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })
}
