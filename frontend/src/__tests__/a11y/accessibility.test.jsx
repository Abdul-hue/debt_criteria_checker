import React from 'react'
import { render, screen } from '@testing-library/react'
import LoginPage from '../../pages/LoginPage'
import ConfirmDialog from '../../components/shared/ConfirmDialog'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

// NOTE: axe-core is not installed in this project. 
// These tests perform manual ARIA and role checks as a smoke test for accessibility.

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(() => ({ token: null, login: vi.fn() })),
}))

describe('Accessibility Smoke Tests', () => {
  it('LoginPage has proper form labels and roles', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('ConfirmDialog has alertdialog role', () => {
    render(
      <ConfirmDialog 
        isOpen={true} 
        title="Confirm?" 
        message="Are you sure?" 
        onConfirm={vi.fn()} 
        onClose={vi.fn()}
      />
    )
    // Radix UI AlertDialog.Content usually adds role="alertdialog"
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('LoadingSpinner has status role', () => {
    render(<LoadingSpinner />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByLabelText(/loading/i)).toBeInTheDocument()
  })
})
