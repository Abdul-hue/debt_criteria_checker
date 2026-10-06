import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/axios'

const BASE = '/api/v1/criteria/criteria-changes/'

export function useCriteriaChanges() {
  return useQuery({
    queryKey: ['criteria-changes'],
    queryFn: async () => (await api.get(BASE)).data,
  })
}

export function useCriteriaChange(id) {
  return useQuery({
    queryKey: ['criteria-change', id],
    queryFn: async () => (await api.get(`${BASE}${id}/`)).data,
    enabled: Boolean(id),
  })
}

export function useManagedFields() {
  return useQuery({
    queryKey: ['criteria-managed-fields'],
    queryFn: async () => (await api.get(`${BASE}managed-fields/`)).data,
    staleTime: Infinity,
  })
}

export function useCriteriaTargets(model, q) {
  return useQuery({
    queryKey: ['criteria-targets', model, q],
    queryFn: async () => (await api.get(`${BASE}targets/`, { params: { model, q } })).data.results,
    enabled: Boolean(model),
  })
}

export function useCriteriaTarget(model, id) {
  return useQuery({
    queryKey: ['criteria-target', model, id],
    queryFn: async () => (await api.get(`${BASE}targets/`, { params: { model, id } })).data,
    enabled: Boolean(model && id),
  })
}

export function useCriteriaVersions() {
  return useQuery({
    queryKey: ['criteria-versions'],
    queryFn: async () => (await api.get('/api/v1/criteria/criteria-versions/')).data,
  })
}

/** POST helper for create / trial / approve / reject / cancel / rollback. */
export function useCriteriaChangeAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ url, body }) => (await api.post(url, body || {})).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria-changes'] })
      queryClient.invalidateQueries({ queryKey: ['criteria-change'] })
      queryClient.invalidateQueries({ queryKey: ['criteria-versions'] })
      queryClient.invalidateQueries({ queryKey: ['criteria-target'] })
    },
  })
}

export const criteriaUrls = {
  create: BASE,
  trial: (id) => `${BASE}${id}/trial/`,
  approve: (id) => `${BASE}${id}/approve/`,
  reject: (id) => `${BASE}${id}/reject/`,
  cancel: (id) => `${BASE}${id}/cancel/`,
  rollback: (n) => `/api/v1/criteria/criteria-versions/${n}/rollback/`,
}
