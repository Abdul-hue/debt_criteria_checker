import React from 'react'
import { render, screen } from '@testing-library/react'
import VerdictBanner from '../../components/assess/VerdictBanner'

describe('VerdictBanner', () => {
  const mockResult = {
    overall_status: 'PASS',
    recommended_solution: 'IVA',
    iva_term_months: 60,
    dividend_analysis: { estimated_pence: '33.5' },
    id: 'ASS-123',
    representative_flags: { WATCH: true, TIX: false, EVOLVE: false }
  }

  it('renders overall_status text', () => {
    render(<VerdictBanner result={mockResult} />)
    expect(screen.getByText('PASS')).toBeInTheDocument()
  })

  it('renders recommended_solution', () => {
    render(<VerdictBanner result={mockResult} />)
    expect(screen.getByText('IVA')).toBeInTheDocument()
  })

  it('applies red styling when status is BLOCKED', () => {
    const blockedResult = { ...mockResult, overall_status: 'BLOCKED' }
    const { container } = render(<VerdictBanner result={blockedResult} />)
    const banner = container.firstChild
    expect(banner).toHaveClass('bg-red-50')
    expect(banner).toHaveClass('border-red-300')
  })

  it('applies green styling when status is PASS', () => {
    const { container } = render(<VerdictBanner result={mockResult} />)
    const banner = container.firstChild
    expect(banner).toHaveClass('bg-green-50')
    expect(banner).toHaveClass('border-green-300')
  })

  it('renders iva_term_months', () => {
    render(<VerdictBanner result={mockResult} />)
    expect(screen.getByText('60 months')).toBeInTheDocument()
  })
})
