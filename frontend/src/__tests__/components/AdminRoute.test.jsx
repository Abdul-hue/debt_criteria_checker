import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import AdminRoute from '../../components/AdminRoute'
import { useAuth } from '../../context/AuthContext'
import { vi } from 'vitest'

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}))

describe('AdminRoute', () => {
  it('redirects to /login when not authenticated', () => {
    useAuth.mockReturnValue({ token: null, isAdmin: false, isLoading: false })
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <Routes>
          <Route element={<AdminRoute />}>
            <Route path="/admin/users" element={<div>Admin Page</div>} />
          </Route>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/assess" element={<div>Assess Page</div>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Admin Page')).not.toBeInTheDocument()
  })

  it('redirects to /assess when authenticated but not admin', () => {
    useAuth.mockReturnValue({ token: 'tok', isAdmin: false, isLoading: false })
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <Routes>
          <Route element={<AdminRoute />}>
            <Route path="/admin/users" element={<div>Admin Page</div>} />
          </Route>
          <Route path="/assess" element={<div>Assess Page</div>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Assess Page')).toBeInTheDocument()
    expect(screen.queryByText('Admin Page')).not.toBeInTheDocument()
  })

  it('renders child routes when authenticated and isAdmin', () => {
    useAuth.mockReturnValue({ token: 'tok', isAdmin: true, isLoading: false })
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <Routes>
          <Route element={<AdminRoute />}>
            <Route path="/admin/users" element={<div>Admin Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Admin Page')).toBeInTheDocument()
  })

  it('shows loading spinner while auth is initializing', () => {
    useAuth.mockReturnValue({ token: null, isAdmin: false, isLoading: true })
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <Routes>
          <Route element={<AdminRoute />}>
            <Route path="/admin/users" element={<div>Admin Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('Admin Page')).not.toBeInTheDocument()
  })
})
