import React from 'react'
import { render, screen } from '@testing-library/react'
import StatusBadge from '../../components/shared/StatusBadge'

describe('StatusBadge', () => {
  it('renders correct text for each status value', () => {
    render(<StatusBadge status="ACCEPT" />)
    expect(screen.getByText('ACCEPT')).toBeInTheDocument()
  })

  it('applies correct colour class for ACCEPT', () => {
    const { container } = render(<StatusBadge status="ACCEPT" />)
    const badge = container.firstChild
    expect(badge).toHaveClass('bg-green-100')
    expect(badge).toHaveClass('text-green-800')
  })

  it('applies correct colour class for REJECT', () => {
    const { container } = render(<StatusBadge status="REJECT" />)
    const badge = container.firstChild
    expect(badge).toHaveClass('bg-red-100')
    expect(badge).toHaveClass('text-red-800')
  })

  it('applies correct colour class for WILL_CONSIDER', () => {
    const { container } = render(<StatusBadge status="WILL_CONSIDER" />)
    const badge = container.firstChild
    expect(badge).toHaveClass('bg-amber-100')
    expect(badge).toHaveClass('text-amber-800')
  })

  it('renders with lg size prop', () => {
    const { container } = render(<StatusBadge status="ACCEPT" size="lg" />)
    const badge = container.firstChild
    expect(badge).toHaveClass('text-base')
    expect(badge).toHaveClass('px-4')
  })
})
