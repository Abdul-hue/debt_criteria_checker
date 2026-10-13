import { render, screen, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import DecisionsPage from '../../pages/admin/DecisionsPage'
import api from '../../lib/axios'

vi.mock('../../lib/axios', () => ({
  default: { get: vi.fn(), delete: vi.fn() },
}))
vi.mock('../../context/AuthContext', () => ({ useAuth: () => ({ isAdmin: false }) }))
vi.mock('../../hooks/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

/** A standalone CriteriaDecision as /assess/history/ returns it (result_json empty). */
const record = (id, client, overallStatus, recommendedSolution, passes = true) => ({
  id: `${id}-0000-0000-0000-000000000000`,
  aryza_reference: `REF-${id}`,
  client_name: client,
  recommended_solution: typeof recommendedSolution === 'object' ? recommendedSolution.code : recommendedSolution,
  passes_all_hard_blocks: passes,
  triggered_by: 'caseworker',
  created_at: '2026-10-12T10:00:00+01:00',
  result_json: null,
  decision_output: {
    overall_status: overallStatus,
    recommended_solution: recommendedSolution,
    hard_blocks: [], flags: [], info: [], passed: [],
  },
})

const RECORDS = [
  record('a1', 'Conflict Client', 'PASS',
    { code: 'REVIEW_REQUIRED', label: 'Caseworker Review Required', rationale: 'r', confidence: 'LOW' }),
  record('b2', 'Iva Client', 'PASS', { code: 'IVA', label: 'Individual Voluntary Arrangement' }),
  record('c3', 'Vat Client', 'PASS', { code: 'DMP', label: 'Debt Management Plan' }),
  record('d4', 'Flagged Client', 'FLAGGED', { code: 'IVA', label: 'Individual Voluntary Arrangement' }),
  record('e5', 'Blocked Client', 'BLOCKED', { code: 'DMP', label: 'Debt Management Plan' }, false),
  record('f6', 'Legacy Client', 'PASS', 'IVA_VIABLE'),
]

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DecisionsPage />
    </QueryClientProvider>,
  )
}

/** The card for a client: its heading's card container. */
const card = (client) => screen.getByText(client).closest('.rounded-xl')

const badgeOf = (client) => within(card(client)).getByText(
  (_, el) => el.tagName === 'SPAN' && el.className.includes('rounded-full'),
)

const filterBy = (value) => fireEvent.change(screen.getByRole('combobox'), { target: { value } })

describe('DecisionsPage status', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({ data: { results: RECORDS, next: null } })
  })

  it('shows a saved REVIEW_REQUIRED recommendation as Needs Review, never Eligible', async () => {
    renderPage()
    await screen.findByText('Conflict Client')
    expect(badgeOf('Conflict Client')).toHaveTextContent('Needs Review')
    expect(within(card('Conflict Client')).queryByText('Eligible')).not.toBeInTheDocument()
    expect(within(card('Conflict Client')).getByText('Caseworker Review Required')).toBeInTheDocument()
  })

  it('lists the REVIEW_REQUIRED record under Needs Review and not under Eligible', async () => {
    renderPage()
    await screen.findByText('Conflict Client')
    filterBy('REFERRED')
    expect(screen.getByText('Conflict Client')).toBeInTheDocument()
    expect(screen.getByText('Flagged Client')).toBeInTheDocument()
    expect(screen.queryByText('Iva Client')).not.toBeInTheDocument()
    filterBy('ELIGIBLE')
    expect(screen.queryByText('Conflict Client')).not.toBeInTheDocument()
    expect(screen.getByText('Iva Client')).toBeInTheDocument()
  })

  it('keeps the existing mapping for every other record', async () => {
    renderPage()
    await screen.findByText('Iva Client')
    expect(badgeOf('Iva Client')).toHaveTextContent('Eligible')
    expect(badgeOf('Vat Client')).toHaveTextContent('Eligible') // forced-DMP VAT: unchanged
    expect(badgeOf('Flagged Client')).toHaveTextContent('Needs Review')
    expect(badgeOf('Blocked Client')).toHaveTextContent('Does Not Qualify')
  })

  it('keeps the existing behaviour for a legacy plain-text recommendation', async () => {
    renderPage()
    await screen.findByText('Legacy Client')
    expect(badgeOf('Legacy Client')).toHaveTextContent('Eligible')
    expect(within(card('Legacy Client')).getByText('IVA Recommended')).toBeInTheDocument()
    filterBy('ELIGIBLE')
    expect(screen.getByText('Legacy Client')).toBeInTheDocument()
  })
})
