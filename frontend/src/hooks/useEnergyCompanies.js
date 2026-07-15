import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'

// CreditorCriteria has no dedicated "category" field, so energy suppliers
// are identified by name keyword — matches real UK provider names (British
// Gas, EDF Energy, NPower, Scottish Power, Utilita Energy, etc.) without
// pulling in unrelated creditors (banks, credit unions, retailers...).
const ENERGY_KEYWORD_RE = /gas|electric|energy|power|utilit/i

/**
 * Hook to list energy-company creditors. Fetches the full creditor list
 * once (same approach as useCouncils) and filters client-side — both by
 * the energy keyword and by the user's search text — so the dropdown is
 * always populated with energy suppliers, never empty-until-typed, and
 * typing doesn't fire a request per keystroke.
 */
export function useEnergyCompanies(search = '') {
  const query = useQuery({
    queryKey: ['energy-companies'],
    queryFn: async () => {
      let results = []
      let url = '/api/v1/criteria/creditors/?page_size=500'
      while (url) {
        const { data } = await api.get(url)
        results = results.concat(data.results ?? data)
        url = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null
      }
      return results.filter((c) => ENERGY_KEYWORD_RE.test(c.creditor_name))
    },
    staleTime: 5 * 60 * 1000,
  })

  const term = search.trim().toLowerCase()
  const data = term
    ? (query.data ?? []).filter((c) => c.creditor_name?.toLowerCase().includes(term))
    : query.data

  return { ...query, data }
}
