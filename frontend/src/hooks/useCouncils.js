import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useCouncils() {
  return useQuery({
    queryKey: ['councils'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/councils/?page_size=500'
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

export function useCreateCouncil() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (council) => {
      const { data } = await api.post('/api/v1/criteria/councils/', council)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['councils'] }),
  })
}

export function useUpdateCouncil() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...council }) => {
      const { data } = await api.put(`/api/v1/criteria/councils/${id}/`, council)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['councils'] }),
  })
}

export function useDeleteCouncil() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/criteria/councils/${id}/`)
      return id
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['councils'] }),
  })
}
