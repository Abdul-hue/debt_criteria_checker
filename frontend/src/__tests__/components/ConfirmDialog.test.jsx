import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import ConfirmDialog from '../../components/shared/ConfirmDialog'
import { vi } from 'vitest'

describe('ConfirmDialog', () => {
  it('does not render when isOpen=false', () => {
    render(<ConfirmDialog isOpen={false} title="Confirm?" message="Are you sure?" />)
    expect(screen.queryByText('Confirm?')).not.toBeInTheDocument()
  })

  it('renders title and message when open', () => {
    render(<ConfirmDialog isOpen={true} title="Confirm?" message="Are you sure?" />)
    expect(screen.getByText('Confirm?')).toBeInTheDocument()
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button clicked', () => {
    const onConfirm = vi.fn()
    render(<ConfirmDialog isOpen={true} title="Confirm?" message="Are you sure?" onConfirm={onConfirm} />)
    
    const confirmBtn = screen.getByRole('button', { name: /confirm/i })
    fireEvent.click(confirmBtn)
    expect(onConfirm).toHaveBeenCalled()
  })

  it('calls onClose when cancel button clicked', () => {
    const onClose = vi.fn()
    render(<ConfirmDialog isOpen={true} title="Confirm?" message="Are you sure?" onClose={onClose} />)
    
    const cancelBtn = screen.getByRole('button', { name: /cancel/i })
    fireEvent.click(cancelBtn)
    expect(onClose).toHaveBeenCalled()
  })

  it('confirm button is disabled when loading=true', () => {
    render(<ConfirmDialog isOpen={true} title="Confirm?" message="Are you sure?" loading={true} />)
    const confirmBtn = screen.getByRole('button', { name: /processing/i })
    expect(confirmBtn).toBeDisabled()
  })

  it('confirm button has danger styling when variant="danger"', () => {
    render(<ConfirmDialog isOpen={true} title="Confirm?" message="Are you sure?" variant="danger" />)
    const confirmBtn = screen.getByRole('button', { name: /confirm/i })
    expect(confirmBtn).toHaveClass('bg-red-600')
  })
})
