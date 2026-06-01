import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'

export function useDepartment() {
  return useQuery({
    queryKey: ['my-department'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/my-department/')
      return data.department // null if unassigned
    },
    staleTime: 5 * 60 * 1000,
  })
}
