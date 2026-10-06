import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import LeadGenActivityPage from '../../pages/LeadGenActivityPage'
import api from '../../lib/axios'

vi.mock('../../lib/axios', () => ({ default: { get: vi.fn() } }))

describe('LeadGenActivityPage', () => {
  it('shows cases checked per Lead Gen user with totals', async () => {
    api.get.mockResolvedValueOnce({ data: {
      date_from: '2026-10-05', date_to: '2026-10-05', timezone: 'Europe/London',
      definition: 'A case checked is one distinct case reference successfully checked by a user on a London calendar day.',
      users: [
        { username: 'alice', department: 'Lead Generation', cases_checked: 12, iva_potential: 5, iva_needs_review: 1,
          dmp_potential: 8, dro_referral: 1, no_solution: 2, failed_attempts: 1 },
        { username: 'bob', department: 'Lead Generation', cases_checked: 4, iva_potential: 1, iva_needs_review: 0,
          dmp_potential: 3, dro_referral: 0, no_solution: 1, failed_attempts: 0 },
      ],
      totals: { cases_checked: 16, iva_potential: 6, iva_needs_review: 1, dmp_potential: 11, dro_referral: 1,
                no_solution: 3, failed_attempts: 1 },
    } })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><LeadGenActivityPage /></QueryClientProvider>)

    const aliceRow = (await screen.findByText('alice')).closest('tr')
    expect(within(aliceRow).getByText('12')).toBeInTheDocument()
    const totalRow = screen.getByText('Total').closest('tr')
    expect(within(totalRow).getByText('16')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/api/v1/criteria/lead-gen/activity/', expect.objectContaining({
      params: expect.objectContaining({ date_from: expect.any(String), date_to: expect.any(String) }),
    }))
    expect(screen.getByText(/one distinct case reference/)).toBeInTheDocument()
  })
})
