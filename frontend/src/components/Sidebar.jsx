import { NavLink } from 'react-router-dom'
import {
  Search,
  Settings,
  Users,
  LayoutDashboard,
  CheckSquare,
  BarChart3,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * Sidebar component
 * Container: w-56 bg-slate-900 flex flex-col py-4 shrink-0
 */
export default function Sidebar() {
  const { isAdmin } = useAuth()

  const navItems = [
    // Admin-only section
    {
      to: '/admin',
      label: 'Dashboard',
      icon: <LayoutDashboard size={18} />,
      adminOnly: true,
      end: true,
    },

    // Available to all authenticated users
    { to: '/assess', label: 'Run Assessment', icon: <Search size={18} /> },

    // Admin-only management items
    {
      to: '/admin/decisions',
      label: 'Decisions',
      icon: <CheckSquare size={18} />,
      adminOnly: true,
    },
    {
      to: '/rules',
      label: 'Rule Management',
      icon: <Settings size={18} />,
      adminOnly: true,
    },
    {
      to: '/admin/users',
      label: 'User Management',
      icon: <Users size={18} />,
      adminOnly: true,
    },
    {
      to: '/reports',
      label: 'Reports',
      icon: <BarChart3 size={18} />,
      adminOnly: true,
      disabled: true,
      tooltip: 'Coming Soon',
    },
  ]

  const visibleItems = navItems.filter((item) => !item.adminOnly || isAdmin)

  return (
    <aside className="w-56 bg-slate-900 flex flex-col py-4 shrink-0 overflow-hidden">
      {/* Navigation section label */}
      <div className="px-4 mb-2">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Navigation</h2>
      </div>

      {/* Navigation items */}
      <nav className="flex-1 space-y-1 px-2 overflow-y-auto">
        {visibleItems.map((item) => (
          <div key={item.to} title={item.tooltip || ''}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 rounded text-sm transition-colors ${
                  item.disabled
                    ? 'text-slate-500 cursor-not-allowed opacity-50'
                    : isActive
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`
              }
              onClick={(e) => item.disabled && e.preventDefault()}
            >
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          </div>
        ))}
      </nav>

      {/* App version at bottom */}
      <div className="px-4 mt-auto pt-2">
        <p className="text-xs text-slate-600">v1.0.0</p>
      </div>
    </aside>
  )
}
