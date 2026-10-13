import { render, screen, fireEvent, within } from '@testing-library/react'
import { vi } from 'vitest'
import SolutionOptions, { DEFAULT_SOLUTION_CHECKLIST } from '../../components/criteria/SolutionOptions'

const solutions = [
  { code: 'IVA', label: 'Individual Voluntary Arrangement (IVA)', status: 'NOT_ELIGIBLE',
    reasons: ['1 IVA criteria blocker failed.'], to_confirm: [], notes: [] },
  { code: 'DMP', label: 'Debt Management Plan (DMP)', status: 'ELIGIBLE',
    reasons: [], to_confirm: [], notes: ['Priority commitments are dealt with separately.'] },
  { code: 'DRO', label: 'Debt Relief Order (DRO)', status: 'NEEDS_REVIEW',
    reasons: [], to_confirm: ['Confirm the customer has not had a DRO in the last six years.'], notes: [] },
  { code: 'BANKRUPTCY', label: 'Bankruptcy', status: 'ELIGIBLE', reasons: [], to_confirm: [], notes: [] },
]

describe('SolutionOptions', () => {
  it('shows every solution with its own status, so more than one can be eligible', () => {
    render(<SolutionOptions solutions={solutions} />)
    expect(within(screen.getByTestId('solution-IVA')).getByText('Not eligible')).toBeInTheDocument()
    expect(within(screen.getByTestId('solution-DMP')).getByText('Eligible')).toBeInTheDocument()
    expect(within(screen.getByTestId('solution-DRO')).getByText('Check needed')).toBeInTheDocument()
    expect(within(screen.getByTestId('solution-BANKRUPTCY')).getByText('Eligible')).toBeInTheDocument()
    expect(screen.getByText('Confirm the customer has not had a DRO in the last six years.')).toBeInTheDocument()
  })

  it('renders nothing when the result has no solutions', () => {
    const { container } = render(<SolutionOptions solutions={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('reports Yes / No / Clear as true / false / null', () => {
    const onAnswerChange = vi.fn()
    const answers = { ...DEFAULT_SOLUTION_CHECKLIST, dro_in_last_6_years: true }
    render(<SolutionOptions solutions={solutions} answers={answers} onAnswerChange={onAnswerChange} />)
    const group = screen.getByRole('radiogroup', { name: 'Had a Debt Relief Order in the last 6 years?' })
    expect(within(group).getByRole('radio', { name: 'Yes' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(within(group).getByRole('radio', { name: 'No' }))
    fireEvent.click(within(group).getByRole('radio', { name: 'Yes' }))
    fireEvent.click(within(group.parentElement).getByRole('button', { name: 'Clear' }))
    expect(onAnswerChange).toHaveBeenNthCalledWith(1, 'dro_in_last_6_years', false)
    expect(onAnswerChange).toHaveBeenNthCalledWith(2, 'dro_in_last_6_years', true)
    expect(onAnswerChange).toHaveBeenNthCalledWith(3, 'dro_in_last_6_years', null)
  })

  it('lists eligible solutions first and expands a card to show every point', () => {
    render(<SolutionOptions solutions={solutions} />)
    expect(screen.getAllByTestId(/^solution-/).map((card) => card.dataset.testid)).toEqual([
      'solution-DMP', 'solution-BANKRUPTCY', 'solution-DRO', 'solution-IVA',
    ])
    const dmp = screen.getByTestId('solution-DMP')
    const toggle = within(dmp).getByRole('button', { expanded: false })
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(within(dmp).getByText('Good to know')).toBeInTheDocument()
  })
})
