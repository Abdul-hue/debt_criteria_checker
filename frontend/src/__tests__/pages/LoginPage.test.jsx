import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LoginPage from '../../pages/LoginPage'
import { useAuth } from '../../context/AuthContext'
import { useNavigate, MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import api from '../../lib/axios'
import queryClient from '../../lib/queryClient'

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../lib/axios', () => ({
  default: { get: vi.fn() },
}))

const department = (slug, name) => ({ data: { department: { id: 1, name, slug } } })

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: vi.fn(),
  }
})

describe('LoginPage', () => {
  const loginSpy = vi.fn()
  const navigateSpy = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    api.get.mockResolvedValue(department('default', 'Default'))
    useAuth.mockReturnValue({ token: null, isAdmin: false, login: loginSpy })
    useNavigate.mockReturnValue(navigateSpy)
  })

  it('renders email and password inputs', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('shows validation error when submitted empty', async () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    
    const submitBtn = screen.getByRole('button', { name: /sign in/i })
    fireEvent.click(submitBtn)
    
    await waitFor(() => {
      expect(screen.getByText(/valid email required/i)).toBeInTheDocument()
      expect(screen.getByText(/password must be at least/i)).toBeInTheDocument()
    })
  })

  it('calls login API on valid submission', async () => {
    loginSpy.mockResolvedValueOnce()
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'password123' } })
    
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    
    await waitFor(() => {
      expect(loginSpy).toHaveBeenCalledWith('test@test.com', 'password123')
      expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true })
    })
  })

  const submitValid = () => {
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'password123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
  }

  it('sends a Lead Generation user to the Criteria Check after login', async () => {
    loginSpy.mockResolvedValueOnce({ role: 'assessor' })
    api.get.mockResolvedValue(department('lead-generation', 'Lead Generation'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    submitValid()
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/lead-gen', { replace: true }))
    expect(api.get).toHaveBeenCalledWith('/api/v1/criteria/my-department/')
    expect(navigateSpy).not.toHaveBeenCalledWith('/dashboard', expect.anything())
  })

  it('sends a user from another department to the dashboard', async () => {
    loginSpy.mockResolvedValueOnce({ role: 'assessor' })
    api.get.mockResolvedValue(department('collections', 'Collections'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    submitValid()
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true }))
  })

  it('sends a user with no department to the dashboard', async () => {
    loginSpy.mockResolvedValueOnce({ role: 'assessor' })
    api.get.mockResolvedValue({ data: { department: null } })
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    submitValid()
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true }))
  })

  it('falls back to the dashboard when the department cannot be read', async () => {
    loginSpy.mockResolvedValueOnce({ role: 'assessor' })
    api.get.mockRejectedValue(new Error('network'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    submitValid()
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true }))
  })

  it('still sends an admin to /admin without looking up the department', async () => {
    loginSpy.mockResolvedValueOnce({ role: 'admin' })
    api.get.mockResolvedValue(department('lead-generation', 'Lead Generation'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    submitValid()
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/admin', { replace: true }))
    expect(api.get).not.toHaveBeenCalled()
  })

  it('sends an already logged-in Lead Generation user to the Criteria Check', async () => {
    useAuth.mockReturnValue({ token: 'tok', isAdmin: false, login: loginSpy })
    api.get.mockResolvedValue(department('lead-generation', 'Lead Generation'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/lead-gen', { replace: true }))
  })

  it('sends an already logged-in admin to /admin', async () => {
    useAuth.mockReturnValue({ token: 'tok', isAdmin: true, login: loginSpy })
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/admin', { replace: true }))
    expect(api.get).not.toHaveBeenCalled()
  })

  it('displays error message on auth failure', async () => {
    loginSpy.mockRejectedValueOnce(new Error('Invalid credentials'))
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    )
    
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrongpass' } })
    
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    
    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument()
    })
  })
})
