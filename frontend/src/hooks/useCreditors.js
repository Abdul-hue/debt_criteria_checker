  import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
  import api from '../lib/axios'

  /**
   * Hook to fetch all creditors
   */
  export function useCreditors() {
    return useQuery({
      queryKey: ['creditors'],
      queryFn: async () => {
        let resultsMap = new Map()
        let url = '/api/v1/criteria/creditors/?page_size=500'
        while (url) {
          const { data } = await api.get(url)
          const items = data.results ?? data
          items.forEach(item => resultsMap.set(item.id, item))
          url = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null
        }
        return Array.from(resultsMap.values())
      },
      staleTime: 0,
    })
  }

  /**
   * Hook to update a creditor
   */
  export function useUpdateCreditor() {
    const queryClient = useQueryClient()
    return useMutation({
      mutationFn: async ({ id, ...creditor }) => {
        const { data } = await api.put(`/api/v1/criteria/creditors/${id}/`, creditor)
        return data
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['creditors'] })
      },
    })
  }

  /**
   * Hook to create a creditor
   */
  export function useCreateCreditor() {
    const queryClient = useQueryClient()
    return useMutation({
      mutationFn: async (creditor) => {
        const { data } = await api.post('/api/v1/criteria/creditors/', creditor)
        return data
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['creditors'] })
      },
    })
  }

  /**
   * Hook to delete a creditor
   */
  export function useDeleteCreditor() {
    const queryClient = useQueryClient()
    return useMutation({
      mutationFn: async (id) => {
        await api.delete(`/api/v1/criteria/creditors/${id}/`)
        return id
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['creditors'] })
      },
    })
  }

  /**
   * Hook to fetch outcomes + tally for a creditor
   */
  export function useCreditorOutcomes(creditorId) {
    return useQuery({
      queryKey: ['creditor-outcomes', creditorId],
      queryFn: async () => {
        const { data } = await api.get(`/api/v1/criteria/creditors/${creditorId}/outcomes/`)
        return data
      },
      enabled: !!creditorId,
      staleTime: 0,
    })
  }

  /**
   * Hook to submit a new outcome for a creditor
   */
  export function useCreateCreditorOutcome(creditorId) {
    const queryClient = useQueryClient()
    return useMutation({
      mutationFn: async (payload) => {
        const { data } = await api.post(`/api/v1/criteria/creditors/${creditorId}/outcomes/`, payload)
        return data
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['creditor-outcomes', creditorId] })
      },
    })
  }

  /**
   * Hook to delete an outcome for a creditor
   */
  export function useDeleteCreditorOutcome(creditorId) {
    const queryClient = useQueryClient()
    return useMutation({
      mutationFn: async (outcomeId) => {
        await api.delete(`/api/v1/criteria/creditors/${creditorId}/outcomes/`, {
          data: { outcome_id: outcomeId },
        })
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['creditor-outcomes', creditorId] })
      },
    })
  }

  /**
   * Hook to fetch audit log for a creditor
   */
  export function useCreditorAuditLog(creditorId) {
    return useQuery({
      queryKey: ['creditor-audit-log', creditorId],
      queryFn: async () => {
        const { data } = await api.get(`/api/v1/criteria/creditors/${creditorId}/audit-log/`)
        return data
      },
      enabled: !!creditorId,
      staleTime: 0,
    })
  }

  /**
   * Hook to fetch CRM vote summary for a creditor (any type: creditors, councils, county-councils)
   */
  export function useCreditorVoteSummary(type, id) {
    return useQuery({
      queryKey: ['creditor-vote-summary', type, id],
      queryFn: async () => {
        const { data } = await api.get(`/api/v1/criteria/${type}/${id}/vote-summary/`)
        return data
      },
      enabled: !!type && !!id,
      staleTime: 0,
    })
  }
