import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import CriteriaReport from '../../components/criteria/CriteriaReport'

vi.mock('../../hooks/useCreditors', () => ({
  useCreditorVoteSummary: () => ({ data: null, isLoading: false }),
}))

const baseResult = {
  overall_status: 'PASS',
  hard_blocks: [], flags: [], info: [], passed: [],
  creditor_positions: [], council_positions: [],
  majority_analysis: {}, dividend_analysis: {},
  representatives_detected: [],
  dmp_eligibility: { status: 'DMP_ELIGIBLE', reasons: [], notes: [] },
  aryza_reference: 'RA-1',
  client_name: 'Test Client',
  evaluated_at: new Date(0).toISOString(),
}

describe('CriteriaReport potential solution', () => {
  it('shows the VAT / DRO conflict as a caseworker review, not a solution', () => {
    const rationale = 'Because both apply, no solution is recommended: '
      + 'a caseworker must review the case and decide between a DRO and a DMP.'
    render(<CriteriaReport result={{
      ...baseResult,
      recommended_solution: { code: 'REVIEW_REQUIRED', label: 'Caseworker Review Required', rationale, confidence: 'LOW' },
      alternative_solutions: [],
    }} />)
    const label = screen.getByText('Caseworker Review Required')
    expect(label.parentElement.className).toContain('border-amber-400')
    expect(screen.getByText(rationale)).toBeInTheDocument()
    expect(screen.queryByText('Individual Voluntary Arrangement')).not.toBeInTheDocument()
    expect(screen.queryByText('Debt Relief Order')).not.toBeInTheDocument()
  })

  it('still shows an ordinary recommendation', () => {
    render(<CriteriaReport result={{
      ...baseResult,
      recommended_solution: { code: 'IVA', label: 'Individual Voluntary Arrangement', rationale: 'Meets the criteria.' },
    }} />)
    const label = screen.getByText('Individual Voluntary Arrangement')
    expect(label.parentElement.className).toContain('border-emerald-400')
  })
})
