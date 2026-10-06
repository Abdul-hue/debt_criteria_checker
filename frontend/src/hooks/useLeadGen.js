import { useMutation, useQuery } from '@tanstack/react-query'
import api from '../lib/axios'
import { extractErrorMessage } from '../lib/errorHandler'

/** Backend Lead Gen / criteria-change endpoints return {error, code} on failure. */
export function apiErrorMessage(error) {
  return error?.response?.data?.error || extractErrorMessage(error)
}

/**
 * Is there a usable credit report on file for this case? Drives whether the
 * Lead Gen form shows "existing report found" or an upload control.
 */
export function useLeadGenCreditReportStatus(reference) {
  const ref = (reference || '').trim()
  return useQuery({
    queryKey: ['lead-gen-credit-report-status', ref],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/lead-gen/credit-report-status/', {
        params: { aryza_reference: ref },
      })
      return data
    },
    enabled: ref.length >= 3,
    staleTime: 30 * 1000,
    retry: false,
  })
}

/**
 * Run a Lead Gen pre-screen. Sends multipart when a credit report file is
 * attached (uploaded and extracted server-side by the existing parser).
 */
export function useLeadGenCheck() {
  return useMutation({
    mutationFn: async ({ aryza_reference, credit_report_id, file }) => {
      if (file) {
        const form = new FormData()
        form.append('aryza_reference', aryza_reference)
        form.append('credit_report', file)
        const { data } = await api.post('/api/v1/criteria/lead-gen/check/', form)
        return data
      }
      const { data } = await api.post('/api/v1/criteria/lead-gen/check/', {
        aryza_reference,
        ...(credit_report_id ? { credit_report_id } : {}),
      })
      return data
    },
  })
}

export function useLeadGenActivity(dateFrom, dateTo) {
  return useQuery({
    queryKey: ['lead-gen-activity', dateFrom, dateTo],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/criteria/lead-gen/activity/', {
        params: { date_from: dateFrom, date_to: dateTo },
      })
      return data
    },
    enabled: Boolean(dateFrom && dateTo),
  })
}
