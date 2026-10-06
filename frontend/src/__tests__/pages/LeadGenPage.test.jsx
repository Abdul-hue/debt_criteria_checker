import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import LeadGenPage from '../../pages/LeadGenPage'

vi.mock('../../lib/axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

const auth = { user: { first_name: 'Ann', last_name: 'Lee', email: 'ann@example.com' }, isAdmin: true, logout: vi.fn() }
vi.mock('../../context/AuthContext.jsx', () => ({ useAuth: () => auth }))

const renderPage = () => render(
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter initialEntries={['/lead-gen']}><LeadGenPage /></MemoryRouter>
  </QueryClientProvider>,
)

describe('LeadGenPage', () => {
  beforeEach(() => { auth.isAdmin = true })

  it('labels the link out as Back to main app, never "CAT"', () => {
    renderPage()
    expect(screen.getByRole('link', { name: /Back to main app/ })).toHaveAttribute('href', '/')
    expect(screen.queryByText('CAT')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Lead Gen Criteria Check' })).toBeInTheDocument()
  })

  it('hides the main-app link from non-admin Lead Gen users', () => {
    auth.isAdmin = false
    renderPage()
    expect(screen.queryByRole('link', { name: /Back to main app/ })).not.toBeInTheDocument()
  })

  it('leads with the pop-out, with the in-page form as a fallback', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /Open Lead Gen check/ })).toBeInTheDocument()
    expect(screen.queryByLabelText('Case reference')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'or check a case on this page' }))
    expect(screen.getByLabelText('Case reference')).toBeInTheDocument()
  })
})
