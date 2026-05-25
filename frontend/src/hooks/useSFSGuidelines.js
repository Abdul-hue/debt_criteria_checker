import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useSFSCategories() {
  return useQuery({
    queryKey: ['sfs-categories'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/sfs/categories/')
      return data.results ?? data
    },
    staleTime: 0,
  })
}

export function useSFSGuidelinesCount() {
  return useQuery({
    queryKey: ['sfs-guidelines-count'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/sfs/guidelines/?page_size=1')
      return typeof data.count === 'number' ? data.count : (data.results ?? data).length
    },
    staleTime: 60 * 1000,
  })
}

export function useUpdateSFSGuideline() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...fields }) => {
      const { data } = await api.patch(`/api/v1/criteria/sfs/guidelines/${id}/`, fields)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sfs-categories'] })
      queryClient.invalidateQueries({ queryKey: ['sfs-guidelines-count'] })
    },
  })
}

export function useUpdateSFSCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...fields }) => {
      const { data } = await api.patch(`/api/v1/criteria/sfs/categories/${id}/`, fields)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sfs-categories'] }),
  })
}
