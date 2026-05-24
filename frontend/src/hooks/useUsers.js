import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/users/?page_size=500'
      while (url) {
        const { data } = await api.get(url)
        results = results.concat(data.results ?? data)
        url = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null
      }
      return results
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (userData) => {
      const { data } = await api.post('/api/v1/criteria/users/', userData)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...data }) => {
      const { response } = await api.put(`/api/v1/criteria/users/${id}/`, data)
      return response?.data ?? { id, ...data }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/criteria/users/${id}/`)
      return id
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}
