import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAssessCase } from '../../hooks/useAssessCase'
import axiosInstance from '../../lib/axios'
import { vi } from 'vitest'

vi.mock('../../lib/axios', () => ({
  default: {
    post: vi.fn(),
  },
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useAssessCase', () => {
  it('should define runAssessment and handle success', async () => {
    const mockData = { id: 1, status: 'pass' }
    axiosInstance.post.mockResolvedValueOnce({ data: mockData })

    const { result } = renderHook(() => useAssessCase(), {
      wrapper: createWrapper(),
    })

    expect(result.current.runAssessment).toBeDefined()

    result.current.runAssessment({ aryza_reference: '123' })

    await waitFor(() => expect(result.current.data).toEqual(mockData))
    expect(axiosInstance.post).toHaveBeenCalledWith('/api/v1/criteria/assess/', {
      aryza_reference: '123',
    })
  })

  it('should handle 400 error correctly', async () => {
    const errorResponse = {
      response: {
        status: 400,
        data: { detail: 'Invalid reference' },
      },
    }
    axiosInstance.post.mockRejectedValueOnce(errorResponse)

    const { result } = renderHook(() => useAssessCase(), {
      wrapper: createWrapper(),
    })

    result.current.runAssessment({ aryza_reference: 'invalid' })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBe('Invalid reference')
  })
})
