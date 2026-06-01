import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'

export function useMyPermissions() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-permissions'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/my-permissions/')
      return Object.fromEntries(data.map(p => [p.feature_key, p.permission_level]))
    },
    staleTime: 5 * 60 * 1000,
  })

  const permMap = data || {}

  return {
    permMap,
    hasWritePermission: (key) => {
      if (isLoading) return false
      return permMap[key] === 'WRITE'
    },
    isLoading,
  }
}

export function useFeatureAccess() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-features'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/my-features/')
      // Returns [{feature_key, is_enabled}] — build a lookup map
      return Object.fromEntries(data.map(f => [f.feature_key, f.is_enabled]))
    },
    staleTime: 5 * 60 * 1000,
  })

  const featureMap = data || {}

  return {
    featureMap,
    hasFeature: (key) => {
      if (isLoading) return false
      return featureMap[key] === true
    },
    isLoading,
  }
}
