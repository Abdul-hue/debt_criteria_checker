import { NavLink } from 'react-router-dom'
import {
  Search,
  Settings,
  Users,
  LayoutDashboard,
  CheckSquare,
  BarChart3,
  Building2,
  Paperclip,
  BookOpen,
  Home,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext.jsx'
import { useFeatureAccess } from '../hooks/useFeatureAccess.js'

function SectionLabel({ children }) {
  return (
    <div className="px-2 mb-1 mt-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider px-2">{children}</h2>
    </div>
  )
}

function NavItem({ item }) {
  return (
    <div title={item.tooltip || ''}>
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
  )
}

/**
 * Sidebar component
 * Container: w-56 bg-slate-900 flex flex-col py-4 shrink-0
 */
export default function Sidebar() {
  const { isAdmin } = useAuth()
  const { hasFeature, isLoading: featuresLoading } = useFeatureAccess()

  const adminItems = [
    { to: '/admin', label: 'Dashboard', icon: <LayoutDashboard size={18} />, end: true },
    { to: '/admin/departments', label: 'Departments', icon: <Building2 size={18} /> },
    { to: '/admin/users', label: 'User Management', icon: <Users size={18} /> },
    { to: '/admin/sfs-guidelines', label: 'SFS Guidelines', icon: <BookOpen size={18} /> },
    { to: '/rules', label: 'Rule Management', icon: <Settings size={18} />, featureKey: 'global_rules' },
  ]

  const ruleItems = [
    { to: '/rules', label: 'Rule Management', icon: <Settings size={18} />, featureKey: 'global_rules' },
  ]

  const guidelineItems = [
    { to: '/sfs', label: 'SFS Guidelines', icon: <BookOpen size={18} />, featureKey: 'sfs_guidelines' },
  ]

  const operationItems = [
    { to: '/assess', label: 'Run Assessment', icon: <Search size={18} />, featureKey: 'run_assessment' },
    { to: '/decisions', label: 'Decisions', icon: <CheckSquare size={18} />, featureKey: 'decisions' },
  ]

  const showRuleManagement = isAdmin || hasFeature('global_rules')
  const showGuidelines = hasFeature('sfs_guidelines')
  const showOperations = isAdmin || ['run_assessment', 'decisions'].some(k => hasFeature(k))

  return (
    <aside className="w-56 bg-slate-900 flex flex-col py-4 shrink-0 overflow-hidden">
      <nav className="flex-1 space-y-1 px-2 overflow-y-auto">
        {isAdmin ? (
          <>
            <div className="px-2 mb-2">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Navigation</h2>
            </div>
            {adminItems.map((item) => <NavItem key={item.to} item={item} />)}
            {showOperations && (
              <>
                <SectionLabel>Operations</SectionLabel>
                {operationItems.map((item) => <NavItem key={item.to} item={item} />)}
              </>
            )}
          </>
        ) : featuresLoading ? (
          <>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse bg-slate-700 rounded h-4 w-3/4 mb-2 mx-2" />
            ))}
          </>
        ) : (
          <>
            <div className="px-2 mb-2">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Navigation</h2>
            </div>
            <NavItem item={{ to: '/dashboard', label: 'Home', icon: <Home size={18} />, end: true }} />
            {showGuidelines && guidelineItems.map((item) => <NavItem key={item.to} item={item} />)}
            {showRuleManagement && ruleItems.filter((item) => hasFeature(item.featureKey)).map((item) => <NavItem key={item.to} item={item} />)}
            {showOperations && (
              <>
                <SectionLabel>Operations</SectionLabel>
                {operationItems.filter((item) => hasFeature(item.featureKey)).map((item) => <NavItem key={item.to} item={item} />)}
              </>
            )}
          </>
        )}
      </nav>

      {/* App version at bottom */}
      <div className="px-4 mt-auto pt-2">
        <p className="text-xs text-slate-600">v1.0.0</p>
      </div>
    </aside>
  )
}
