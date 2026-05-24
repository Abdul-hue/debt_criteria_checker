import React from 'react'
import { render, screen } from '@testing-library/react'
import EmptyState from '../../components/shared/EmptyState'

describe('EmptyState', () => {
  it('renders title and message', () => {
    render(<EmptyState title="No Data" message="Try adjusting your filters" />)
    expect(screen.getByText('No Data')).toBeInTheDocument()
    expect(screen.getByText('Try adjusting your filters')).toBeInTheDocument()
  })

  it('renders action slot when provided', () => {
    render(<EmptyState title="No Data" action={<button>Add New</button>} />)
    expect(screen.getByRole('button', { name: /add new/i })).toBeInTheDocument()
  })

  it('renders default icon when no icon prop given', () => {
    const { container } = render(<EmptyState title="No Data" />)
    // The default icon is an Inbox component from lucide-react which renders an svg
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})
