import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AssessPage from '../../pages/AssessPage'
import { useAssessCase } from '../../hooks/useAssessCase'
import { vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../../hooks/useAssessCase', () => ({
  useAssessCase: vi.fn(),
}))

// Mock CaseSearch because it uses useAssessCase internally
vi.mock('../../components/assess/CaseSearch', () => ({
  default: ({ onResult }) => (
    <div>
      <button onClick={() => onResult({ id: 'ASS-1', overall_status: 'PASS', client_name: 'Jane Doe', aryza_reference: 'REF-1', recommended_solution: 'IVA_VIABLE' })}>Mock Run</button>
    </div>
  )
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }) => (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

describe('AssessPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAssessCase.mockReturnValue({
      runAssessment: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      data: null,
      reset: vi.fn(),
    })
  })

  it('renders case search form (via mock)', () => {
    render(<AssessPage />, { wrapper: createWrapper() })
    expect(screen.getByText('Mock Run')).toBeInTheDocument()
  })

  it('renders the criteria report when a result is available', async () => {
    render(<AssessPage />, { wrapper: createWrapper() })

    const runBtn = screen.getByText('Mock Run')
    fireEvent.click(runBtn)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Jane Doe' })).toBeInTheDocument()
    })
    expect(screen.getByText('IVA Recommended')).toBeInTheDocument()
  })

  it('shows empty state when no assessment loaded', () => {
    render(<AssessPage />, { wrapper: createWrapper() })
    expect(screen.getByRole('heading', { name: 'Run Case Assessment' })).toBeInTheDocument()
    expect(screen.queryByText('IVA Recommended')).not.toBeInTheDocument()
  })
})
