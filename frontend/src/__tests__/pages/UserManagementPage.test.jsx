import React from 'react'
import { render, screen } from '@testing-library/react'
import UserManagementPage from '../../pages/UserManagementPage'
import { useUsers, useDeleteUser } from '../../hooks/useUsers'
import { useAuth } from '../../context/AuthContext'
import { vi } from 'vitest'

vi.mock('../../hooks/useUsers', () => ({
  useUsers: vi.fn(),
  useDeleteUser: vi.fn(),
  useCreateUser: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateUser: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}))
vi.mock('../../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../hooks/useToast', () => ({
  useToast: vi.fn(() => ({ success: vi.fn(), error: vi.fn() })),
}))

describe('UserManagementPage', () => {
  beforeEach(() => {
    useUsers.mockReturnValue({ data: [], isLoading: false })
    useDeleteUser.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    useAuth.mockReturnValue({ user: { user_id: 1 } })
  })

  it('renders the page title', () => {
    render(<UserManagementPage />)
    expect(screen.getByRole('heading', { name: 'User Management' })).toBeInTheDocument()
  })

  it('renders the page subtitle', () => {
    render(<UserManagementPage />)
    expect(screen.getByText(/manage system users and their access roles/i)).toBeInTheDocument()
  })

  it('renders the UsersList component (Create User button present)', () => {
    render(<UserManagementPage />)
    expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument()
  })

  it('shows empty state when there are no users', () => {
    render(<UserManagementPage />)
    expect(screen.getByText('No users found')).toBeInTheDocument()
  })
})
