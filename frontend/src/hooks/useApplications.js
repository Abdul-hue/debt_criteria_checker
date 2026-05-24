import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useApplications() {
  return useQuery({
    queryKey: ['applications'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/applications/?page_size=500'
      while (url) {
        const { data } = await api.get(url)
        results = results.concat(data.results ?? data)
        url = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null
      }
      return results
    },
    staleTime: 2 * 60 * 1000,
  })
}

export function useCreateApplication() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload) => {
      const { data } = await api.post('/api/v1/criteria/applications/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['applications'] }),
  })
}

export function useUpdateApplication() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }) => {
      const { data } = await api.put(`/api/v1/criteria/applications/${id}/`, payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['applications'] }),
  })
}

export function useDeleteApplication() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/criteria/applications/${id}/`)
      return id
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['applications'] }),
  })
}
