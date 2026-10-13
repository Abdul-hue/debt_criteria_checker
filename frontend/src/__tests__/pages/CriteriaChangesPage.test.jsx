import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import CriteriaChangesPage from '../../pages/CriteriaChangesPage'
import api from '../../lib/axios'

vi.mock('../../lib/axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

const VERSIONS = {
  live_version: 'v3',
  results: [
    { number: 3, label: 'v3', created_at: '2026-10-06T01:39:00+01:00', created_by: 'admin', note: 'Rollback to v1' },
    { number: 1, label: 'v1', created_at: '2026-10-05T10:00:00+01:00', created_by: 'manager.test', note: 'Baseline' },
  ],
}

function mockApi() {
  api.get.mockImplementation((url, config) => {
    if (url.endsWith('criteria-versions/')) return Promise.resolve({ data: VERSIONS })
    if (url.endsWith('managed-fields/')) {
      return Promise.resolve({ data: { managed_fields: { CreditorCriteria: ['accepts_iva'] }, field_info: {}, note: 'Only database-held criteria.' } })
    }
    if (url.endsWith('targets/')) {
      const { id, q } = config.params
      if (id) return Promise.resolve({ data: { id: 7, label: 'Argos', values: { accepts_iva: true } } })
      const all = [{ id: 7, label: 'Argos' }, { id: 8, label: 'Barclays' }]
      return Promise.resolve({ data: { results: all.filter((t) => !q || t.label.toLowerCase().includes(q.toLowerCase())) } })
    }
    return Promise.resolve({ data: { live_version: 'v3', results: [] } })
  })
}

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><CriteriaChangesPage /></QueryClientProvider>)
}

describe('CriteriaChangesPage', () => {
  beforeEach(() => { vi.clearAllMocks(); mockApi() })

  it('finds a creditor by typing instead of a giant select', async () => {
    renderPage()
    const box = screen.getByRole('combobox', { name: 'Creditor' })
    fireEvent.focus(box)
    fireEvent.change(box, { target: { value: 'Arg' } })
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/v1/criteria/criteria-changes/targets/', { params: { model: 'CreditorCriteria', q: 'Arg' } },
    ))
    const listbox = await screen.findByRole('listbox')
    await waitFor(() => expect(within(listbox).queryByText('Barclays')).not.toBeInTheDocument())
    fireEvent.mouseDown(within(listbox).getByRole('option'))
    expect(await screen.findByLabelText('Field to change')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change creditor' })).toBeInTheDocument()
  })

  it('shows when a trial case was last assessed and warns about an unreliable snapshot', async () => {
    const change = {
      id: 3, title: 'Creditor statuses', reason: 'Excel sync', status: 'TRIALLED', status_label: 'Trialled — awaiting sign-off',
      created_by: 'Abdul.wasay', created_at: '2026-10-13T02:50:00+01:00', items: [], viewer: {},
      trial_run_by: 'Abdul.wasay', trial_run_at: '2026-10-13T03:00:00+01:00',
      trial_summary: {
        cases_evaluated: 22, cases_changed: 2, cases_errored: 0,
        changed: [
          {
            aryza_reference: '373236', snapshot_saved_at: '2026-06-25T11:46:06+01:00',
            warnings: ['This case was last assessed on 25 Jun 2026, before a fix to how a previous IVA is read from Aryza.'],
            differences: { flags: { before: ['TIG-18'], after: ['MAJORITY-IMPOSSIBLE', 'TIG-18'] } },
          },
          { aryza_reference: '420180', differences: { majority: { before: 'achievable', after: 'not achievable' } } },
        ],
      },
    }
    api.get.mockImplementation((url) => {
      if (url.endsWith('criteria-changes/3/')) return Promise.resolve({ data: change })
      if (url.endsWith('criteria-changes/')) return Promise.resolve({ data: { live_version: 'v4', results: [change] } })
      return Promise.resolve({ data: { live_version: 'v4', results: [] } })
    })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Creditor statuses/ }))
    const flagged = (await screen.findByText('Case 373236')).closest('details')
    expect(within(flagged).getByText('Check before relying on this')).toBeInTheDocument()
    expect(within(flagged).getByText(/before a fix to how a previous IVA is read/)).toBeInTheDocument()
    expect(within(flagged).getByText(/Last assessed/)).toBeInTheDocument()
    const clean = screen.getByText('Case 420180').closest('details')
    expect(within(clean).queryByText('Check before relying on this')).not.toBeInTheDocument()
    expect(within(clean).queryByText(/Last assessed/)).not.toBeInTheDocument()
  })

  it('marks the live version and drafts a rollback only with a reason', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 9 } })
    renderPage()
    const table = (await screen.findByText('Version history')).closest('section')
    const liveRow = within(table).getByText('Rollback to v1').closest('tr')
    expect(within(liveRow).getByText('Live')).toBeInTheDocument()
    expect(within(liveRow).queryByRole('button')).not.toBeInTheDocument()

    fireEvent.click(within(table).getByRole('button', { name: /Roll back to v1/ }))
    const dialog = await screen.findByRole('alertdialog')
    const confirm = within(dialog).getByRole('button', { name: 'Draft rollback' })
    expect(confirm).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Reason for rollback'), { target: { value: 'Bad change' } })
    fireEvent.click(confirm)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/v1/criteria/criteria-versions/1/rollback/', { reason: 'Bad change' },
    ))
  })
})
