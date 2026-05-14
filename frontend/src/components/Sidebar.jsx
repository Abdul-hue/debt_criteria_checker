import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth.jsx'

const navItems = [
  { label: 'Criteria Lookup', to: '/criteria', description: 'Assess new cases and review results' },
  { label: 'Decision History', to: '/criteria/history', description: 'Audit past decisions and workflows', adminOnly: true },
  { label: 'Rule Admin', to: '/criteria/admin/rules', description: 'Manage hard blocks and rules', adminOnly: true },
  { label: 'Creditor Admin', to: '/criteria/admin/creditors', description: 'Manage creditor settings and watchlists', adminOnly: true },
]

const navClass = ({ isActive }) =>
  `block rounded-3xl px-4 py-4 transition hover:bg-slate-50 ${isActive ? 'bg-slate-100 font-semibold text-slate-900' : 'text-slate-600'}`

export default function Sidebar() {
  const { user, logout, isAdmin } = useAuth()

  return (
    <div className="flex h-full flex-col justify-between gap-8">
      <div>
        <Link to="/criteria" className="mb-8 inline-flex items-center gap-3 text-2xl font-semibold text-slate-900">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-800 text-white">C</span>
          Criteria Engine
        </Link>

        <div className="space-y-2">
          {navItems.filter((item) => !item.adminOnly || isAdmin).map((item) => (
            <NavLink key={item.to} to={item.to} className={navClass}>
              <div>{item.label}</div>
              <p className="mt-1 text-sm text-slate-500">{item.description}</p>
            </NavLink>
          ))}
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
        <div className="text-sm uppercase tracking-[0.18em] text-slate-500">Signed in as</div>
        <div className="mt-3 text-lg font-medium text-slate-900">{user?.username || 'Unknown user'}</div>
        <button
          type="button"
          onClick={logout}
          className="mt-5 inline-flex w-full items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
        >
          Sign out
        </button>
      </div>
    </div>
  )
}
