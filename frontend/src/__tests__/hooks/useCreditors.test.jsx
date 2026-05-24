import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useCreditors, useUpdateCreditor } from '../../hooks/useCreditors'
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

describe('useCreditors', () => {
  it('should unwrap paginated results from API', async () => {
    const mockCreditors = [{ id: 1, creditor_name: 'Bank A', status: 'ACCEPT' }]
    api.get.mockResolvedValueOnce({ data: { count: 1, next: null, results: mockCreditors } })

    const { result } = renderHook(() => useCreditors(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockCreditors)
  })

  it('should call useUpdateCreditor mutation correctly', async () => {
    const updatedCreditor = { id: 1, creditor_name: 'Bank B' }
    api.put.mockResolvedValueOnce({ data: updatedCreditor })

    const { result } = renderHook(() => useUpdateCreditor(), { wrapper: createWrapper() })
    result.current.mutate(updatedCreditor)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(updatedCreditor)
    expect(api.put).toHaveBeenCalledWith('/api/v1/criteria/creditors/1/', { creditor_name: 'Bank B' })
  })
})
