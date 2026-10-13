import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import CreditorEditDrawer from '../../components/rules/CreditorEditDrawer'
import api from '../../lib/axios'

vi.mock('../../lib/axios', () => ({
  default: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }
vi.mock('../../hooks/useToast', () => ({ useToast: () => toast }))

/** A creditor as the API returns it (every field the form schema validates). */
const ratesetter = {
  id: 1970,
  creditor_name: 'Ratesetter',
  status: 'ACCEPT',
  representative: 'NONE',
  min_dividend_pence: 25,
  young_account_months: 6,
  young_account_min_dividend_pence: 50,
  dividend_notes: 'if under 6 months old it 50p',
  blocked_until_cleared: false,
  blocked_reason: '',
  reject_if_dmp: false,
  reject_if_never_made_payment: false,
  reject_if_second_iva: false,
  reject_if_police_employed: false,
  reject_if_majority_share_exceeds_pct: null,
  reject_if_debt_repayable_within_months: null,
  fees_cap_percentage: null,
  vehicle_arrears_repossession_months: null,
  requires_arrangement_call_before_proposing: false,
  fraud_claim_risk: false,
  conditional_voter: false,
  conditional_voter_min_dividend_pence: null,
  trading_names: [],
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  criteria_notes: '',
  raw_updated_criteria: '',
  account_age_months: null,
}

const renderDrawer = (creditor = ratesetter, props = {}) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const onClose = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <CreditorEditDrawer creditor={creditor} onClose={onClose} {...props} />
    </QueryClientProvider>,
  )
  return { onClose }
}

const field = {
  standard: () => screen.getByLabelText('Standard minimum dividend (pence in the £)'),
  months: () => screen.getByLabelText('Account age threshold (months)'),
  youngDiv: () => screen.getByLabelText('Younger-account minimum (pence in the £)'),
}

const setValue = (input, value) => fireEvent.change(input, { target: { value } })
const submit = () => fireEvent.submit(document.querySelector('form#creditor-form'))

describe('CreditorEditDrawer: age-dependent minimum dividend', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockImplementation(async (url) => {
      if (url.includes('/outcomes/')) return { data: { tally: { approved: 0, disapproved: 0, total: 0 }, outcomes: [] } }
      if (url.includes('/audit-log/')) return { data: [] }
      if (url.includes('/vote-summary/')) return { data: null }
      return { data: null }
    })
    api.put.mockResolvedValue({ data: {} })
  })

  it('shows the saved standard and younger-account values with distinct labels', () => {
    renderDrawer()
    expect(field.standard()).toHaveValue(25)
    expect(field.months()).toHaveValue(6)
    expect(field.youngDiv()).toHaveValue(50)
    expect(screen.getByText('Younger-account minimum dividend')).toBeInTheDocument()
    expect(screen.getByText(/Accounts younger than the threshold must meet this higher minimum/)).toBeInTheDocument()
  })

  it('saves edited tiers through the API without dropping the other fields', async () => {
    const { onClose } = renderDrawer()
    setValue(field.months(), '9')
    setValue(field.youngDiv(), '60')
    setValue(field.standard(), '30')
    submit()
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    const [url, body] = api.put.mock.calls[0]
    expect(url).toBe('/api/v1/criteria/creditors/1970/')
    expect(body).toMatchObject({
      creditor_name: 'Ratesetter',
      status: 'ACCEPT',
      representative: 'NONE',
      min_dividend_pence: 30,
      young_account_months: 9,
      young_account_min_dividend_pence: 60,
      reject_if_second_iva: false,
      trading_names: [],
    })
    expect(body.id).toBeUndefined()   // the hook moves the id into the URL
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('clearing both tier fields sends null for both', async () => {
    renderDrawer()
    setValue(field.months(), '')
    setValue(field.youngDiv(), '')
    submit()
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    const body = api.put.mock.calls[0][1]
    expect(body.young_account_months).toBeNull()
    expect(body.young_account_min_dividend_pence).toBeNull()
    expect(body.min_dividend_pence).toBe(25)
  })

  it('loads a creditor with no tier as blank fields', () => {
    renderDrawer({ ...ratesetter, young_account_months: null, young_account_min_dividend_pence: null })
    expect(field.months()).toHaveValue(null)
    expect(field.youngDiv()).toHaveValue(null)
    expect(field.standard()).toHaveValue(25)
  })

  it('refuses to save a threshold without a younger-account minimum', async () => {
    renderDrawer()
    setValue(field.youngDiv(), '')
    submit()
    expect(await screen.findByText('Set both the age threshold and the younger-account minimum dividend, or clear both.')).toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('refuses out-of-range values', async () => {
    renderDrawer()
    setValue(field.youngDiv(), '150')
    setValue(field.months(), '0')
    submit()
    expect(await screen.findByText('Cannot exceed 100p in the pound')).toBeInTheDocument()
    expect(screen.getByText('Must be at least 1 month')).toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
  })

  it('reports an API failure and does not claim success', async () => {
    api.put.mockRejectedValue(new Error('500'))
    const { onClose } = renderDrawer()
    setValue(field.youngDiv(), '55')
    submit()
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Error', expect.stringMatching(/Failed to update creditor/)))
    expect(toast.success).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('offers the UNKNOWN stance and saves it', async () => {
    renderDrawer()
    const status = document.querySelector('select[name="status"]')
    expect(Array.from(status.options).map(o => o.value)).toContain('UNKNOWN')
    fireEvent.change(status, { target: { value: 'UNKNOWN' } })
    submit()
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    expect(api.put.mock.calls[0][1].status).toBe('UNKNOWN')
  })

  it('is disabled in read-only mode', () => {
    renderDrawer(ratesetter, { readOnly: true })
    expect(field.months()).toBeDisabled()
    expect(field.youngDiv()).toBeDisabled()
    expect(field.standard()).toBeDisabled()
  })
})
