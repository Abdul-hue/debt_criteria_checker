import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import LeadGenPage from '../../pages/LeadGenPage'
import App from '../../App'
import api from '../../lib/axios'

vi.mock('../../lib/axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

const auth = {
  user: { first_name: 'Ann', last_name: 'Lee', email: 'ann@example.com' },
  isAdmin: true, token: 'tok', isLoading: false, logout: vi.fn(),
}
vi.mock('../../context/AuthContext.jsx', () => ({ useAuth: () => auth }))

// Stand-ins for the two landing pages and the CAT layout, so the navigation
// tests exercise App's real routes and guards without their data fetching.
vi.mock('../../pages/DepartmentDashboard.jsx', () => ({ default: () => <h1>Department dashboard</h1> }))
vi.mock('../../pages/admin/AdminDashboard.jsx', () => ({ default: () => <h1>Admin dashboard</h1> }))
vi.mock('../../components/Layout.jsx', () => ({ default: ({ children }) => <>{children}</> }))

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

  it('shows non-admin Lead Gen users a Dashboard link to the main app', () => {
    auth.isAdmin = false
    renderPage()
    expect(screen.getByRole('link', { name: /Dashboard/ })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('link', { name: /Back to main app/ })).not.toBeInTheDocument()
  })

  it('leads with the pop-out, with the in-page form as a fallback', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /Open Lead Gen check/ })).toBeInTheDocument()
    expect(screen.queryByLabelText('Case reference')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'or check a case on this page' }))
    expect(screen.getByLabelText('Case reference')).toBeInTheDocument()
  })

  describe('link out, through the app routes', () => {
    const renderApp = () => render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/lead-gen']}><App /></MemoryRouter>
      </QueryClientProvider>,
    )

    beforeEach(() => {
      api.get.mockReset()
      api.get.mockResolvedValue({ data: [{ feature_key: 'lead_gen_check', is_enabled: true }] })
    })

    it('takes a Lead Gen user from the Criteria Check to their dashboard', async () => {
      auth.isAdmin = false
      renderApp()
      fireEvent.click(await screen.findByRole('link', { name: /Dashboard/ }))
      expect(await screen.findByRole('heading', { name: 'Department dashboard' })).toBeInTheDocument()
      expect(screen.queryByText(/no access/i)).not.toBeInTheDocument()
    })

    it('takes an admin from the Criteria Check back to the admin dashboard', async () => {
      renderApp()
      fireEvent.click(await screen.findByRole('link', { name: /Back to main app/ }))
      expect(await screen.findByRole('heading', { name: 'Admin dashboard' })).toBeInTheDocument()
    })
  })
})
