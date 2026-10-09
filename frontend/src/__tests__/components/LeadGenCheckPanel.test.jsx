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
    expect(api.post).toHaveBeenCalledWith('/api/v1/criteria/lead-gen/check/', {
      aryza_reference: '123456',
      dmp_checklist: {
        council_tax_current_year: false,
        council_tax_previous_year: false,
        lost_right_to_pay_instalments: false,
      },
    })
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

  it('shows the estimated disposable income breakdown alongside the unchanged IVA outcome', async () => {
    const message = 'For 2 adult(s) and 1 child(ren), the estimated disposable income is -£9.00 per month. '
      + 'Please use this estimate as a guideline only when making your decision. '
      + 'A full I&E assessment is still required to confirm affordability and suitability.'
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      estimated_disposable_income: {
        available: true, adults: 2, children: 1, monthly_income: 2500, monthly_rent: 800,
        minimum_expenditure: 1709, estimated_disposable_income: -9, message,
      },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText(message)).toBeInTheDocument()
    const row = (label) => screen.getByText(label, { selector: 'dt' }).closest('div')
    expect(within(row('Adults')).getByText('2')).toBeInTheDocument()
    expect(within(row('Children')).getByText('1')).toBeInTheDocument()
    expect(within(row('Monthly income')).getByText('£2,500.00')).toBeInTheDocument()
    expect(within(row('Monthly rent')).getByText('£800.00')).toBeInTheDocument()
    expect(within(row('Estimated minimum expenditure')).getByText('£1,709.00')).toBeInTheDocument()
    expect(within(row('Estimated disposable income')).getByText('-£9.00')).toBeInTheDocument()
    expect(within(solutionRow('IVA')).getByText('Potentially suitable')).toBeInTheDocument()
  })

  it("shows Aryza's own weekly figure under the converted monthly income", async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      estimated_disposable_income: {
        available: true, adults: 1, children: 1, monthly_income: 1617, monthly_rent: 500,
        minimum_expenditure: 1130, estimated_disposable_income: -13, message: 'm',
        non_monthly_income: [{ source: 'Child Benefit', amount: 27, frequency: 'weekly', monthly: 117 }],
      },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    const row = (await screen.findByText('Monthly income', { selector: 'dt' })).closest('div')
    expect(within(row).getByText('£1,617.00')).toBeInTheDocument()
    expect(within(row).getByText('Includes Child Benefit £27.00 a week (£117.00 a month)')).toBeInTheDocument()
  })

  it('warns that income is not recorded instead of showing a DRO referral', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      dro: null,
      warnings: [{ code: 'INCOME-NOT-RECORDED', text: 'Income not recorded — check the fact find' }],
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Income not recorded — check the fact find')
    expect(screen.queryByText(/Debt Relief Order/)).not.toBeInTheDocument()
    expect(screen.queryByText('No issues identified at this stage.')).not.toBeInTheDocument()
  })

  it('shows why the estimated disposable income is unavailable instead of a figure', async () => {
    const reason = 'Estimated disposable income unavailable — current rent is not recorded.'
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      estimated_disposable_income: { available: false, reasons: [{ code: 'RENT_NOT_RECORDED', text: reason }] },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText(reason)).toBeInTheDocument()
    expect(screen.queryByText('Monthly rent')).not.toBeInTheDocument()
    expect(screen.queryByText(/£0\.00/)).not.toBeInTheDocument()
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
    expect(JSON.parse(body.get('dmp_checklist'))).toEqual({
      council_tax_current_year: false,
      council_tax_previous_year: false,
      lost_right_to_pay_instalments: false,
    })
  })

  it('sends the DMP checklist answers and shows a council tax DMP rejection', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'NOT_SUITABLE', label: 'DMP — Not currently suitable' },
      reasons: [{ code: 'DMP-COUNCIL-TAX', text: 'Council tax instalment rights lost with arrears for both the current and previous year' }],
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByLabelText('Council tax arrears for this year'))
    fireEvent.click(screen.getByLabelText('Council tax arrears for last year'))
    fireEvent.click(screen.getByLabelText('Lost the right to pay council tax by instalments'))
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    await screen.findByText('Case 123456')
    expect(api.post).toHaveBeenCalledWith('/api/v1/criteria/lead-gen/check/', {
      aryza_reference: '123456',
      dmp_checklist: {
        council_tax_current_year: true,
        council_tax_previous_year: true,
        lost_right_to_pay_instalments: true,
      },
    })
    expect(within(solutionRow('DMP')).getByText('Not currently suitable')).toBeInTheDocument()
    expect(screen.getByText(/Council tax instalment rights lost/)).toBeInTheDocument()
  })

  it('clears the DMP checklist answers when the case reference changes', async () => {
    renderPanel()
    await typeRef()
    const box = screen.getByLabelText('Council tax arrears for this year')
    fireEvent.click(box)
    expect(box).toBeChecked()
    api.get.mockClear()
    await typeRef('654321')
    await waitFor(() => expect(screen.getByLabelText('Council tax arrears for this year')).not.toBeChecked())
  })
})
