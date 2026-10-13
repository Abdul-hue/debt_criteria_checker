import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'

/** Shared with the login redirect (queryClient.fetchQuery) so both use one cache entry. */
export const myDepartmentQuery = {
  queryKey: ['my-department'],
  queryFn: async () => {
    const { data } = await api.get('/api/v1/criteria/my-department/')
    return data.department // null if unassigned
  },
  staleTime: 5 * 60 * 1000,
}

export function useDepartment() {
  return useQuery(myDepartmentQuery)
}
