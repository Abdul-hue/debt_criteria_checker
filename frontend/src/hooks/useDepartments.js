import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

export function useDepartments() {
  return useQuery({
    queryKey: ['departments'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/departments/')
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useCreateDepartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload) => {
      const { data } = await api.post('/api/v1/criteria/departments/', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] })
    },
  })
}

export function useUpdateDepartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }) => {
      const { data } = await api.put(`/api/v1/criteria/departments/${id}/`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] })
    },
  })
}

export function useDepartmentRules(deptId, enabled = true) {
  return useQuery({
    queryKey: ['department-rules', deptId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/departments/${deptId}/rules/`)
      return data
    },
    enabled: enabled && !!deptId,
    staleTime: 0,
  })
}

export function useToggleDepartmentRule(deptId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ rule_key, is_visible }) => {
      const { data } = await api.post(
        `/api/v1/criteria/departments/${deptId}/rules/toggle/`,
        { rule_key, is_visible }
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['department-rules', deptId] })
    },
  })
}

export function useDepartmentCreditors(deptId, enabled = true) {
  return useQuery({
    queryKey: ['department-creditors', deptId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/departments/${deptId}/creditors/`)
      return data
    },
    enabled: enabled && !!deptId,
    staleTime: 0,
  })
}

export function useToggleDepartmentCreditor(deptId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ creditor_id, is_visible }) => {
      const { data } = await api.post(
        `/api/v1/criteria/departments/${deptId}/creditors/toggle/`,
        { creditor_id, is_visible }
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['department-creditors', deptId] })
    },
  })
}

export function useDepartmentCouncils(deptId, enabled = true) {
  return useQuery({
    queryKey: ['department-councils', deptId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/departments/${deptId}/councils/`)
      return data
    },
    enabled: enabled && !!deptId,
    staleTime: 0,
  })
}

export function useToggleDepartmentCouncil(deptId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ council_id, is_visible }) => {
      const { data } = await api.post(
        `/api/v1/criteria/departments/${deptId}/councils/toggle/`,
        { council_id, is_visible }
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['department-councils', deptId] })
    },
  })
}

export function useDepartmentSFS(deptId, enabled = true) {
  return useQuery({
    queryKey: ['department-sfs', deptId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/departments/${deptId}/sfs/`)
      return data
    },
    enabled: enabled && !!deptId,
    staleTime: 0,
  })
}

export function useToggleDepartmentSFS(deptId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ guideline_id, is_visible }) => {
      const { data } = await api.post(
        `/api/v1/criteria/departments/${deptId}/sfs/toggle/`,
        { guideline_id, is_visible }
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['department-sfs', deptId] })
    },
  })
}

export function useDepartmentFeatures(deptId, enabled = true) {
  return useQuery({
    queryKey: ['department-features', deptId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/departments/${deptId}/features/`)
      return data
    },
    enabled: enabled && !!deptId,
    staleTime: 0,
  })
}

export function useToggleDepartmentFeature(deptId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ feature_key, is_enabled }) => {
      const { data } = await api.post(
        `/api/v1/criteria/departments/${deptId}/features/toggle/`,
        { feature_key, is_enabled }
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['department-features', deptId] })
    },
  })
}

export function useDepartmentPermissions(deptId, enabled = true) {
  return useQuery({
    queryKey: ['department-permissions', deptId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/departments/${deptId}/permissions/`)
      return data
    },
    enabled: enabled && !!deptId,
    staleTime: 0,
  })
}

export function useSetDepartmentPermission(deptId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ feature_key, permission_level }) => {
      const { data } = await api.post(
        `/api/v1/criteria/departments/${deptId}/permissions/set/`,
        { feature_key, permission_level }
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['department-permissions', deptId] })
    },
  })
}
