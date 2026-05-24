import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import UsersList from '../../components/users/UsersList'
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

const mockUsers = [
  {
    id: 1,
    first_name: 'Alice',
    last_name: 'Smith',
    email: 'alice@test.com',
    role: 'admin',
    is_active: true,
  },
  {
    id: 2,
    first_name: 'Bob',
    last_name: 'Jones',
    email: 'bob@test.com',
    role: 'assessor',
    is_active: false,
  },
]

describe('UsersList', () => {
  beforeEach(() => {
    useUsers.mockReturnValue({ data: mockUsers, isLoading: false })
    useDeleteUser.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    useAuth.mockReturnValue({ user: { user_id: 99 } })
  })

  it('renders all users in the table', () => {
    render(<UsersList />)
    expect(screen.getByText('Alice Smith')).toBeInTheDocument()
    expect(screen.getByText('Bob Jones')).toBeInTheDocument()
    expect(screen.getByText('alice@test.com')).toBeInTheDocument()
    expect(screen.getByText('bob@test.com')).toBeInTheDocument()
  })

  it('filters users by search text (name)', async () => {
    render(<UsersList />)
    const search = screen.getByPlaceholderText(/search by name or email/i)
    await userEvent.type(search, 'alice')
    expect(screen.getByText('Alice Smith')).toBeInTheDocument()
    expect(screen.queryByText('Bob Jones')).not.toBeInTheDocument()
  })

  it('filters users by search text (email)', async () => {
    render(<UsersList />)
    const search = screen.getByPlaceholderText(/search by name or email/i)
    await userEvent.type(search, 'bob@test')
    expect(screen.getByText('Bob Jones')).toBeInTheDocument()
    expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument()
  })

  it('filters users by role', async () => {
    render(<UsersList />)
    const select = screen.getByRole('combobox')
    await userEvent.selectOptions(select, 'assessor')
    expect(screen.getByText('Bob Jones')).toBeInTheDocument()
    expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument()
  })

  it('shows empty state when no users match search', async () => {
    render(<UsersList />)
    const search = screen.getByPlaceholderText(/search by name or email/i)
    await userEvent.type(search, 'zzznomatch')
    expect(screen.getByText('No users found')).toBeInTheDocument()
  })

  it('disables delete button for the current user own account', () => {
    useAuth.mockReturnValue({ user: { user_id: 1 } })
    render(<UsersList />)
    const deleteButtons = screen.getAllByRole('button', { name: /delete/i })
    // First user (id=1) is self — button should be disabled
    expect(deleteButtons[0]).toBeDisabled()
    // Second user (id=2) is not self — button should be enabled
    expect(deleteButtons[1]).not.toBeDisabled()
  })

  it('shows Create User button', () => {
    render(<UsersList />)
    expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument()
  })

  it('shows loading spinner when data is loading', () => {
    useUsers.mockReturnValue({ data: undefined, isLoading: true })
    render(<UsersList />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})
