// TEMPORARY investigation test — proves whether selecting "Current year" on
// a council-tax row's DMP dropdown actually changes the outgoing recalc
// payload. Not meant to be kept as a permanent regression test.
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AssessPage from '../../pages/AssessPage'
import axiosInstance from '../../lib/axios'
import { vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../../lib/axios', () => ({
  default: { post: vi.fn() },
}))

vi.mock('../../components/assess/CaseSearch', () => ({
  default: ({ onResult }) => (
    <button onClick={() => onResult({
      overall: 'pass',
      overall_status: 'PASS',
      hard_blocks: [], flags: [], info: [], passed: [],
      creditor_positions: [
        {
          creditor_name: 'Brighton and Hove City Council',
          original_aryza_name: 'Brighton & Hove City Council',
          debt_type_normalised: 'council_tax',
          effective_status: 'WILL_CONSIDER',
          balance: 1500,
          is_secured: false,
          findings: [],
        },
      ],
      council_positions: [],
      majority_analysis: {},
      dividend_analysis: {},
      representatives_detected: [],
      dmp_eligibility: { status: 'DMP_ELIGIBLE', reasons: [], notes: [] },
      aryza_reference: 'TEST-REF',
      client_name: 'Test Client',
      evaluated_at: new Date(0).toISOString(),
    }, undefined)}>
      Mock Run
    </button>
  ),
}))

const createWrapper = () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }) => (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

describe('DMP council-tax dropdown -> recalc payload (investigation)', () => {
  it('changes the creditor_rows sent to /assess/ when "Current year" is selected', async () => {
    axiosInstance.post.mockResolvedValue({
      data: {
        overall: 'pass', overall_status: 'PASS',
        hard_blocks: [], flags: [], info: [], passed: [],
        creditor_positions: [],
        dmp_eligibility: { status: 'DMP_ELIGIBLE', reasons: [], notes: [] },
        aryza_reference: 'TEST-REF',
      },
    })

    render(<AssessPage />, { wrapper: createWrapper() })
    fireEvent.click(screen.getByText('Mock Run'))

    await waitFor(() => expect(screen.getByText('Brighton & Hove City Council')).toBeInTheDocument())

    const select = screen.getByRole('combobox')
    console.log('[TEMP DEBUG] select value BEFORE change:', select.value)

    fireEvent.change(select, { target: { value: 'current' } })

    await waitFor(() => expect(axiosInstance.post).toHaveBeenCalledTimes(1))

    const [, body] = axiosInstance.post.mock.calls[0]
    console.log('[TEMP DEBUG] recalc POST body:', JSON.stringify(body, null, 2))

    expect(body.creditor_rows).toEqual([
      { debt_type_normalised: 'council_tax', value: 'current' },
    ])
  })
})
