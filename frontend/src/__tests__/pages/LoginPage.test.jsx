import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LoginPage from '../../pages/LoginPage'
import { useAuth } from '../../context/AuthContext'
import { useNavigate, MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}))

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
      expect(navigateSpy).toHaveBeenCalledWith('/assess', { replace: true })
    })
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
