import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useRules, usePatchRule } from '../../hooks/useRules'
import api from '../../lib/axios'
import { vi } from 'vitest'

vi.mock('../../lib/axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useRules', () => {
  it('should unwrap paginated results from API', async () => {
    const mockRules = [{ rule_key: 'TIG-01', name: 'Min debt', criteria_set: 'TIG' }]
    api.get.mockResolvedValueOnce({ data: { count: 1, next: null, results: mockRules } })

    const { result } = renderHook(() => useRules(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockRules)
  })

  it('should call usePatchRule mutation and resolve', async () => {
    const mockResponse = { rule_key: 'TIG-01', is_active: false }
    api.put.mockResolvedValueOnce({ data: mockResponse })

    const { result } = renderHook(() => usePatchRule(), { wrapper: createWrapper() })
    result.current.mutate({ ruleKey: 'TIG-01', is_active: false })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockResponse)
    expect(api.put).toHaveBeenCalledWith('/api/v1/criteria/rules/TIG-01/', { is_active: false })
  })
})
