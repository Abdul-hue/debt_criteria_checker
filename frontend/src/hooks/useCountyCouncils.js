import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useCountyCouncils() {
  return useQuery({
    queryKey: ['county-councils'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/county-councils/?page_size=500'
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

export function useCountyCouncil(id) {
  return useQuery({
    queryKey: ['county-councils', id],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/county-councils/${id}/`)
      return data
    },
    enabled: !!id,
  })
}

export function useCreateCountyCouncil() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (county) => {
      const { data } = await api.post('/api/v1/criteria/county-councils/', county)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['county-councils'] }),
  })
}

export function useUpdateCountyCouncil() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...county }) => {
      const { data } = await api.put(`/api/v1/criteria/county-councils/${id}/`, county)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['county-councils'] }),
  })
}

export function useDeleteCountyCouncil() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/criteria/county-councils/${id}/`)
      return id
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['county-councils'] }),
  })
}
