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
