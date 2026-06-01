import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Play,
  Building2,
  Users,
  Shield,
  Landmark,
  DollarSign,
  Paperclip,
  CheckSquare,
  Table2,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext.jsx'
import { useFeatureAccess } from '../hooks/useFeatureAccess.js'
import { useDepartment } from '../hooks/useDepartment.js'
import api from '../lib/axios'

function useModelCount(queryKey, url) {
  return useQuery({
    queryKey,
    queryFn: async () => {
      const { data } = await api.get(url)
      return typeof data.count === 'number' ? data.count : (data.results ?? data).length
    },
    staleTime: 60 * 1000,
    retry: false,
  })
}

const FEATURE_CONFIG = {
  run_assessment: {
    label: 'Run Assessment',
    icon: Play,
    iconColor: 'bg-indigo-50 text-indigo-600',
    route: '/assess',
  },
  general_creditors: {
    label: 'Creditors (General)',
    icon: Building2,
    iconColor: 'bg-blue-50 text-blue-600',
    route: '/rules',
  },
  representative_creditors: {
    label: 'Creditors (Rep.)',
    icon: Users,
    iconColor: 'bg-purple-50 text-purple-600',
    route: '/rules',
  },
  global_rules: {
    label: 'Global Rules',
    icon: Shield,
    iconColor: 'bg-emerald-50 text-emerald-600',
    route: '/rules',
  },
  councils: {
    label: 'Councils',
    icon: Landmark,
    iconColor: 'bg-amber-50 text-amber-600',
    route: '/rules',
  },
  dividends: {
    label: 'Dividends',
    icon: DollarSign,
    iconColor: 'bg-green-50 text-green-600',
    route: '/rules',
  },
  evidence: {
    label: 'Evidence',
    icon: Paperclip,
    iconColor: 'bg-rose-50 text-rose-600',
    route: '/evidence',
  },
  decisions: {
    label: 'Decisions',
    icon: CheckSquare,
    iconColor: 'bg-sky-50 text-sky-600',
    route: '/decisions',
  },
  sfs_guidelines: {
    label: 'SFS Guidelines',
    icon: Table2,
    iconColor: 'bg-violet-50 text-violet-600',
    route: '/sfs',
  },
}

function DashboardCard({ title, icon: Icon, iconColor, count, isLoading, route }) {
  return (
    <Link
      to={route}
      className="group bg-white rounded-xl border border-slate-200 p-5 hover:border-slate-300 hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2.5 rounded-lg ${iconColor} group-hover:scale-110 transition-transform duration-200`}>
          <Icon className="w-5 h-5" />
        </div>
        {isLoading ? (
          <div className="w-12 h-7 animate-pulse bg-slate-200 rounded" />
        ) : (
          <span className="text-2xl font-bold text-slate-900 tracking-tight">
            {count ?? '—'}
          </span>
        )}
      </div>
      <div>
        <h3 className="text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
          {title}
        </h3>
        <div className="flex items-center gap-1 mt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 group-hover:text-slate-600">
          Go to Page
          <ChevronRight className="w-3 h-3 transition-transform group-hover:translate-x-1" />
        </div>
      </div>
    </Link>
  )
}

function SectionHeading({ children }) {
  return (
    <div className="col-span-full mb-2 mt-6 first:mt-0">
      <h2 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">{children}</h2>
    </div>
  )
}

export default function DepartmentDashboard() {
  const { user } = useAuth()
  const { hasFeature, isLoading: featuresLoading } = useFeatureAccess()
  const { data: department, isLoading: deptLoading } = useDepartment()

  // All counts fetched in parallel — hooks cannot be conditional
  const assessQuery    = useModelCount(['dept-assess-count'],    '/api/v1/criteria/assess/?page_size=1')
  const creditorsQuery = useModelCount(['dept-creditors-count'], '/api/v1/criteria/creditors/?page_size=1')
  const rulesQuery     = useModelCount(['dept-rules-count'],     '/api/v1/criteria/rules/?page_size=1')
  const councilsQuery  = useModelCount(['dept-councils-count'],  '/api/v1/criteria/councils/?page_size=1')
  const dividendsQuery = useModelCount(['dept-dividends-count'], '/api/v1/criteria/creditors/?has_dividend=true&page_size=1')
  const evidenceQuery  = useModelCount(['dept-evidence-count'],  '/api/v1/criteria/evidence/?page_size=1')
  const sfsQuery       = useModelCount(['dept-sfs-count'],       '/api/v1/criteria/sfs/guidelines/?page_size=1')

  const countMap = {
    run_assessment:           assessQuery,
    general_creditors:        creditorsQuery,
    representative_creditors: creditorsQuery,
    global_rules:             rulesQuery,
    councils:                 councilsQuery,
    dividends:                dividendsQuery,
    evidence:                 evidenceQuery,
    decisions:                assessQuery,
    sfs_guidelines:           sfsQuery,
  }

  const displayName = user?.first_name || user?.username || 'User'
  const accessibleFeatures = Object.keys(FEATURE_CONFIG).filter(key => hasFeature(key))

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen bg-slate-50/50">
      {/* Page header */}
      <div className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
            Welcome, {displayName}
          </h1>
          <p className="mt-1 text-slate-500 font-medium">
            Here's an overview of your department access and available tools.
          </p>
        </div>

        {/* Department badge */}
        {deptLoading ? (
          <div className="w-36 h-9 animate-pulse bg-slate-200 rounded-full" />
        ) : department ? (
          <div className="flex items-center gap-2 text-sm font-semibold text-indigo-700 bg-indigo-50 border border-indigo-100 px-3 py-1 rounded-full">
            <div className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0" />
            {department.name}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">

        {/* Feature access cards */}
        {!featuresLoading && accessibleFeatures.length > 0 && (
          <>
            <SectionHeading>Your Access</SectionHeading>
            {accessibleFeatures.map(key => {
              const config = FEATURE_CONFIG[key]
              const q = countMap[key]
              return (
                <DashboardCard
                  key={key}
                  title={config.label}
                  icon={config.icon}
                  iconColor={config.iconColor}
                  count={q.isError ? '—' : q.data}
                  isLoading={q.isLoading}
                  route={config.route}
                />
              )
            })}
          </>
        )}

        {/* Quick navigation */}
        {!featuresLoading && accessibleFeatures.length > 0 && (
          <>
            <SectionHeading>Quick Links</SectionHeading>
            <div className="col-span-full flex flex-wrap gap-3">
              {accessibleFeatures.map(key => {
                const config = FEATURE_CONFIG[key]
                const Icon = config.icon
                return (
                  <Link
                    key={key}
                    to={config.route}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
                  >
                    <Icon className="w-4 h-4" />
                    {config.label}
                  </Link>
                )
              })}
            </div>
          </>
        )}

      </div>
    </div>
  )
}
