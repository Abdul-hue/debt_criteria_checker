import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import LeadGenCheckPanel from '../../components/leadgen/LeadGenCheckPanel'
import api from '../../lib/axios'

vi.mock('../../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

const renderPanel = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LeadGenCheckPanel />
    </QueryClientProvider>,
  )
}

const baseResult = {
  success: true,
  check_id: 1,
  aryza_reference: '123456',
  client: 'J. Smith',
  checked_at: '2026-10-05T10:00:00+01:00',
  dro: null,
  reasons: [],
  review_reasons: [],
  evidence_required_later: [],
  credit_report: { status: 'on_file' },
  criteria_version: 'v2',
}

/** Solution row: name column + status text (the API label split for display). */
const solutionRow = (name) => screen.getByText(name, { selector: 'li > span' }).closest('li')

const typeRef = async (value = '123456') => {
  fireEvent.change(screen.getByLabelText('Case reference'), { target: { value } })
  // debounce (400ms) then the credit-report status lookup
  await waitFor(() => expect(api.get).toHaveBeenCalled(), { timeout: 2000 })
}

describe('LeadGenCheckPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({ data: { has_usable_report: true, agency: 'Experian', uploaded_at: '2026-10-01T09:00:00Z' } })
  })

  it('shows an existing credit report and no upload control', async () => {
    renderPanel()
    await typeRef()
    expect(await screen.findByText('Credit report on file')).toBeInTheDocument()
    expect(screen.getByText(/Experian · 1 Oct 2026/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Credit report \(PDF\)/)).not.toBeInTheDocument()
  })

  it('offers an upload when no usable credit report exists', async () => {
    api.get.mockResolvedValue({ data: { has_usable_report: false, latest_upload_status: null } })
    renderPanel()
    await typeRef()
    expect(await screen.findByLabelText(/Credit report \(PDF\)/)).toBeInTheDocument()
    expect(screen.getByText(/No credit report on file/)).toBeInTheDocument()
  })

  it('shows IVA and DMP potentially suitable with evidence required later', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      evidence_required_later: ['Wage slip', 'Bank statement'],
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText('Case 123456')).toBeInTheDocument()
    expect(within(solutionRow('IVA')).getByText('Potentially suitable')).toBeInTheDocument()
    expect(within(solutionRow('DMP')).getByText('Potentially suitable')).toBeInTheDocument()
    expect(screen.getByText('Evidence required later')).toBeInTheDocument()
    expect(screen.getByText('Wage slip')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/api/v1/criteria/lead-gen/check/', { aryza_reference: '123456' })
  })

  it('shows does-not-meet-criteria with reasons', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'DOES_NOT_MEET_CRITERIA', label: 'Does not currently meet criteria' },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'NOT_SUITABLE', label: 'DMP — Not currently suitable' },
      reasons: [{ code: 'TIG-01', text: 'Minimum debt — criteria not met' }],
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText('Does not currently meet criteria')).toBeInTheDocument()
    expect(screen.getByText('Reason')).toBeInTheDocument()
    expect(screen.getByText('Minimum debt — criteria not met')).toBeInTheDocument()
  })

  it('shows the DRO referral separately', async () => {
    const dro = 'Debt Relief Order (DRO) — Potentially suitable / Refer for review'
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'DRO_REFER', label: dro },
      dro: { code: 'REFER', label: dro },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText(dro)).toBeInTheDocument() // overall outcome
    expect(within(solutionRow('Debt Relief Order (DRO)')).getByText('Potentially suitable / Refer for review')).toBeInTheDocument()
  })

  it('shows the server error message', async () => {
    api.post.mockRejectedValueOnce({ response: { status: 404, data: { error: 'Case 999 was not found in Aryza.', code: 'CASE_NOT_FOUND' } } })
    renderPanel()
    await typeRef('999')
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Case 999 was not found in Aryza.')
  })

  it('uploads the credit report as multipart when attached', async () => {
    api.get.mockResolvedValue({ data: { has_usable_report: false } })
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      credit_report: { status: 'uploaded' },
    } })
    renderPanel()
    await typeRef()
    const input = await screen.findByLabelText(/Credit report \(PDF\)/)
    const file = new File(['%PDF-1.4'], 'report.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    await screen.findByText('Case 123456')
    const [url, body] = api.post.mock.calls[0]
    expect(url).toBe('/api/v1/criteria/lead-gen/check/')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('credit_report')).toBe(file)
  })
})
