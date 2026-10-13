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
        current_gas_bill: false,
        current_electric_bill: false,
        previous_gas_provider_debt: false,
        previous_electric_provider_debt: false,
        current_phone_contract: false,
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

  it('shows DRO and bankruptcy with what to confirm', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'NOT_SUITABLE', label: 'DMP — Not currently suitable' },
      dro: {
        code: 'NEEDS_REVIEW', label: 'DRO — Potentially suitable, details to confirm',
        reasons: [], to_confirm: ['Confirm the customer has not had a DRO in the last six years.'],
        notes: ['No application fee. The DRO normally lasts 12 months.'],
      },
      bankruptcy: {
        code: 'NOT_SUITABLE', label: 'Bankruptcy — Not currently suitable',
        reasons: [{ code: 'BANKRUPTCY-1', text: 'No unsecured debts are recorded on this case.', detail: null }],
        to_confirm: [], notes: [],
      },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText('Case 123456')).toBeInTheDocument()
    expect(within(solutionRow('DRO')).getByText('Potentially suitable, details to confirm')).toBeInTheDocument()
    expect(screen.getByText('DRO details')).toBeInTheDocument()
    expect(screen.getByText('Confirm the customer has not had a DRO in the last six years.')).toBeInTheDocument()
    // Another option works, so bankruptcy is not shown.
    expect(screen.queryByText('Bankruptcy', { selector: 'li > span' })).not.toBeInTheDocument()
    expect(screen.queryByText('Bankruptcy details')).not.toBeInTheDocument()
  })

  it('shows bankruptcy when it is the only option left', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'DOES_NOT_MEET_CRITERIA', label: 'Does not currently meet criteria' },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'NOT_SUITABLE', label: 'DMP — Not currently suitable' },
      dro: { code: 'NOT_SUITABLE', label: 'DRO — Not currently suitable', reasons: [], to_confirm: [], notes: [] },
      bankruptcy: {
        code: 'NEEDS_REVIEW', label: 'Bankruptcy — Potentially suitable, details to confirm', reasons: [],
        to_confirm: ['Confirm the customer has the required England and Wales connection.'],
        notes: ['The £680 application fee must be paid in full before applying.'],
      },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText('Case 123456')).toBeInTheDocument()
    expect(within(solutionRow('Bankruptcy')).getByText('Potentially suitable, details to confirm')).toBeInTheDocument()
    expect(screen.getByText('The £680 application fee must be paid in full before applying.')).toBeInTheDocument()
  })

  it('sends only the DRO and bankruptcy questions that were answered', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
    } })
    renderPanel()
    await typeRef()
    fireEvent.change(screen.getByLabelText('Had a Debt Relief Order in the last 6 years?'), { target: { value: 'no' } })
    fireEvent.change(screen.getByLabelText('Assets and savings worth more than £2,000?'), { target: { value: 'yes' } })
    expect(screen.getByText('2 of 4 answered')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    await screen.findByText('Case 123456')
    expect(api.post.mock.calls[0][1].solution_checklist).toEqual({ assets_over_2000: true, dro_in_last_6_years: false })
  })

  it('groups reasons by solution and shows every one on request', async () => {
    const iva = ['TIG-01', 'TIG-02', 'CREDITOR-BLOCKED', 'TIG-21.2'].map((code) => ({ code, text: `${code} failed`, detail: null }))
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'DOES_NOT_MEET_CRITERIA', label: 'Does not currently meet criteria' },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'NOT_SUITABLE', label: 'DMP — Not currently suitable' },
      reasons: iva.slice(0, 3),
      iva_reasons: iva,
      dmp_reasons: [{ code: 'DMP-MIN-DEBT', text: 'Total debt is below the minimum', detail: null }],
      review_reasons: [{ code: 'BPO-DEBT', text: 'Debt listed under a debt collector — needs checking', detail: null }],
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    expect(await screen.findByText('Why IVA is not suitable')).toBeInTheDocument()
    expect(screen.getByText('Why DMP is not suitable')).toBeInTheDocument()
    expect(screen.getByText('Total debt is below the minimum')).toBeInTheDocument()
    expect(screen.getByText('Debt listed under a debt collector — needs checking')).toBeInTheDocument()
    expect(screen.queryByText('TIG-21.2 failed')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show 1 more' }))
    expect(screen.getByText('TIG-21.2 failed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show fewer' }))
    expect(screen.queryByText('TIG-21.2 failed')).not.toBeInTheDocument()
  })

  it('opens a reason to show the engine explanation, and shows the case figures', async () => {
    const detail = "The customer's total unsecured debt is £2,400.00. An IVA usually requires total debt of at least £6,000.00."
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'DOES_NOT_MEET_CRITERIA', label: 'Does not currently meet criteria' },
      iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
      dmp: { code: 'NOT_SUITABLE', label: 'DMP — Not currently suitable' },
      reasons: [{ code: 'TIG-01', text: 'Minimum debt — criteria not met', detail }],
      case_figures: {
        total_unsecured_debt: 2400, monthly_income: null, monthly_expenditure: 1605, disposable_income: 45,
      },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))

    const reason = await screen.findByRole('button', { name: /Minimum debt — criteria not met/ })
    expect(reason).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText(detail)).not.toBeVisible()
    fireEvent.click(reason)
    expect(reason).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(detail)).toBeVisible()

    expect(screen.getByText('Case figures')).toBeInTheDocument()
    expect(screen.getByText('£2,400.00')).toBeInTheDocument()
    expect(screen.getByText('£1,605.00')).toBeInTheDocument()
    expect(screen.getByText('£45.00')).toBeInTheDocument()
    expect(screen.getByText('Not recorded')).toBeInTheDocument()
    expect(screen.getByText('Disposable income (per month)')).toBeInTheDocument()
  })

  it('shows which disposable income the checks used when it is the estimate', async () => {
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      case_figures: {
        total_unsecured_debt: 8772, monthly_income: 2297, monthly_expenditure: 2178, disposable_income: 748,
        disposable_income_basis: 'ESTIMATE', full_ie_disposable_income: 119,
      },
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    const used = (await screen.findByText('Disposable income used for the checks (estimate)')).closest('div')
    expect(within(used).getByText('£748.00')).toBeInTheDocument()
    const fullIe = screen.getByText('Disposable income from the I&E (per month)').closest('div')
    expect(within(fullIe).getByText('£119.00')).toBeInTheDocument()
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
      + 'The Lead Gen checks use this estimate. '
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
    expect(screen.queryByText(/Refer for review/)).not.toBeInTheDocument()
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
      current_gas_bill: false,
      current_electric_bill: false,
      previous_gas_provider_debt: false,
      previous_electric_provider_debt: false,
      current_phone_contract: false,
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
        current_gas_bill: false,
        current_electric_bill: false,
        previous_gas_provider_debt: false,
        previous_electric_provider_debt: false,
        current_phone_contract: false,
      },
    })
    expect(within(solutionRow('DMP')).getByText('Not currently suitable')).toBeInTheDocument()
    expect(screen.getByText(/Council tax instalment rights lost/)).toBeInTheDocument()
  })

  it('sends the utility and phone answers and shows the DMP notes', async () => {
    const note = 'The following debt(s) must be left out of the DMP arrangement: current gas bill.'
    api.post.mockResolvedValueOnce({ data: {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
      dmp_notes: [note],
    } })
    renderPanel()
    await typeRef()
    fireEvent.click(screen.getByLabelText('Current gas bill'))
    fireEvent.click(screen.getByLabelText('Current phone contract'))
    fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
    await screen.findByText('Case 123456')
    expect(api.post.mock.calls[0][1].dmp_checklist).toMatchObject({
      current_gas_bill: true,
      current_phone_contract: true,
      current_electric_bill: false,
    })
    expect(screen.getByText('DMP notes')).toBeInTheDocument()
    expect(screen.getByText(note)).toBeInTheDocument()
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

  describe('HMRC VAT question', () => {
    const suitable = {
      ...baseResult,
      overall: { code: 'POTENTIALLY_SUITABLE', label: 'Potentially suitable at Lead Gen stage' },
      iva: { code: 'POTENTIALLY_SUITABLE', label: 'IVA — Potentially suitable' },
      dmp: { code: 'POTENTIALLY_SUITABLE', label: 'DMP — Potentially suitable' },
    }
    const checkCase = async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
      await screen.findByText('Case 123456')
    }
    const vatBox = () => screen.getByLabelText('HMRC debt includes VAT')

    it('is listed but disabled before a case has been checked', async () => {
      renderPanel()
      await typeRef()
      expect(vatBox()).toBeDisabled()
      expect(screen.getByText('Check the case first to see if HMRC is a creditor.')).toBeInTheDocument()
    })

    it('stays disabled when the case has no HMRC creditor', async () => {
      api.post.mockResolvedValueOnce({ data: { ...suitable, hmrc_is_creditor: false } })
      renderPanel()
      await typeRef()
      await checkCase()
      expect(vatBox()).toBeDisabled()
      expect(screen.getByText('No HMRC debt found on this case.')).toBeInTheDocument()
    })

    it('is disabled while the check is running', async () => {
      let resolve
      api.post.mockReturnValueOnce(new Promise((r) => { resolve = r }))
      renderPanel()
      await typeRef()
      fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
      await screen.findByText('Checking…')
      expect(vatBox()).toBeDisabled()
      resolve({ data: { ...suitable, hmrc_is_creditor: true } })
      await waitFor(() => expect(vatBox()).toBeEnabled())
    })

    it('is disabled again when the check fails', async () => {
      api.post.mockResolvedValueOnce({ data: { ...suitable, hmrc_is_creditor: true } })
      api.post.mockRejectedValueOnce({ response: { status: 503, data: { error: 'Aryza is not responding.', code: 'ARYZA_TIMEOUT' } } })
      renderPanel()
      await typeRef()
      await checkCase()
      fireEvent.click(vatBox())
      fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
      expect(await screen.findByRole('alert')).toHaveTextContent('Aryza is not responding.')
      expect(vatBox()).toBeDisabled()
      expect(vatBox()).not.toBeChecked()
    })

    it('is enabled for an HMRC creditor and sends the answers on the next check', async () => {
      api.post.mockResolvedValueOnce({ data: { ...suitable, hmrc_is_creditor: true } })
      api.post.mockResolvedValueOnce({ data: {
        ...suitable,
        hmrc_is_creditor: true,
        iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
        reasons: [{ code: 'FORCED_DMP_VAT', text: 'A previous-year HMRC VAT debt is an automatic IVA fail' }],
      } })
      renderPanel()
      await typeRef()
      await checkCase()
      expect(api.post.mock.calls[0][1].dmp_checklist).not.toHaveProperty('hmrc_debt_has_vat')
      expect(screen.queryByLabelText('The VAT is from a previous year')).not.toBeInTheDocument()
      fireEvent.click(vatBox())
      fireEvent.click(screen.getByLabelText('The VAT is from a previous year'))
      await checkCase()
      expect(api.post.mock.calls[1][1].dmp_checklist).toMatchObject({
        hmrc_debt_has_vat: true,
        hmrc_previous_year_vat: true,
        current_gas_bill: false,
      })
      expect(within(solutionRow('IVA')).getByText('Not currently suitable')).toBeInTheDocument()
      expect(screen.getByText('A previous-year HMRC VAT debt is an automatic IVA fail')).toBeInTheDocument()
      expect(screen.getByLabelText('The VAT is from a previous year')).toBeChecked()
    })

    it('unticking "includes VAT" clears the previous-year answer', async () => {
      api.post.mockResolvedValueOnce({ data: { ...suitable, hmrc_is_creditor: true } })
      renderPanel()
      await typeRef()
      await checkCase()
      fireEvent.click(vatBox())
      fireEvent.click(screen.getByLabelText('The VAT is from a previous year'))
      fireEvent.click(vatBox())
      fireEvent.click(vatBox())
      expect(screen.getByLabelText('The VAT is from a previous year')).not.toBeChecked()
    })

    it('shows the VAT and DRO conflict as a caseworker review, with no DRO referral', async () => {
      const text = 'A previous-year HMRC VAT debt and the Lead Gen DRO threshold both apply, '
        + 'so a caseworker needs to decide between a DRO and a DMP'
      api.post.mockResolvedValueOnce({ data: {
        ...suitable,
        hmrc_is_creditor: true,
        overall: { code: 'REVIEW_REQUIRED', label: 'Caseworker review needed — DRO or DMP' },
        iva: { code: 'NOT_SUITABLE', label: 'IVA — Not currently suitable' },
        dmp: { code: 'REVIEW_REQUIRED', label: 'DMP — Caseworker review needed' },
        dro: null,
        reasons: [{ code: 'FORCED-SOLUTION-CONFLICT', text: 'IVA is not currently suitable for this conflict' }],
        review_reasons: [{ code: 'FORCED-SOLUTION-CONFLICT', text, detail: null }],
      } })
      renderPanel()
      await typeRef()
      await checkCase()
      expect(screen.getByText('Caseworker review needed — DRO or DMP')).toBeInTheDocument()
      expect(within(solutionRow('IVA')).getByText('Not currently suitable')).toBeInTheDocument()
      expect(within(solutionRow('DMP')).getByText('Caseworker review needed')).toBeInTheDocument()
      expect(screen.queryByText('Potentially suitable')).not.toBeInTheDocument()
      expect(screen.getByText('IVA is not currently suitable for this conflict')).toBeInTheDocument()
      expect(screen.getByText('Needs review')).toBeInTheDocument()
      expect(screen.getByText(text)).toBeInTheDocument()
      expect(screen.queryByText(/Refer for review/)).not.toBeInTheDocument()
      expect(screen.queryByText('No issues identified at this stage.')).not.toBeInTheDocument()
    })

    it('is disabled and cleared when the case reference changes', async () => {
      api.post.mockResolvedValueOnce({ data: { ...suitable, hmrc_is_creditor: true } })
      renderPanel()
      await typeRef()
      await checkCase()
      fireEvent.click(vatBox())
      fireEvent.change(screen.getByLabelText('Case reference'), { target: { value: '654321' } })
      expect(vatBox()).toBeDisabled()
      expect(vatBox()).not.toBeChecked()
      api.post.mockResolvedValueOnce({ data: { ...suitable, aryza_reference: '654321', hmrc_is_creditor: false } })
      fireEvent.click(screen.getByRole('button', { name: 'Check case' }))
      await screen.findByText('Case 654321')
      expect(api.post.mock.calls[1][1].dmp_checklist).not.toHaveProperty('hmrc_debt_has_vat')
    })
  })
})
