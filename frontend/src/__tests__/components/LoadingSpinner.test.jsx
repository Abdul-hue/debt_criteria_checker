import React from 'react'
import { render, screen } from '@testing-library/react'
import LoadingSpinner from '../../components/shared/LoadingSpinner'

describe('LoadingSpinner', () => {
  it('renders with role="status"', () => {
    render(<LoadingSpinner />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('fullScreen=true adds overlay wrapper', () => {
    const { container } = render(<LoadingSpinner fullScreen={true} />)
    const overlay = container.firstChild
    expect(overlay).toHaveClass('fixed')
    expect(overlay).toHaveClass('inset-0')
    expect(overlay).toHaveClass('z-50')
  })

  it('size prop changes rendered class', () => {
    const { container } = render(<LoadingSpinner size="lg" />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('h-12')
    expect(svg).toHaveClass('w-12')
  })
})
