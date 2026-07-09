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
    accent: 'navy',
    route: '/assess',
  },
  general_creditors: {
    label: 'Creditors (General)',
    icon: Building2,
    accent: 'slate',
    route: '/rules',
  },
  representative_creditors: {
    label: 'Creditors (Rep.)',
    icon: Users,
    accent: 'gold',
    route: '/rules',
  },
  global_rules: {
    label: 'Global Rules',
    icon: Shield,
    accent: 'forest',
    route: '/rules',
  },
  councils: {
    label: 'Councils',
    icon: Landmark,
    accent: 'gold',
    route: '/rules',
  },
  dividends: {
    label: 'Dividends',
    icon: DollarSign,
    accent: 'forest',
    route: '/rules',
  },
  evidence: {
    label: 'Evidence',
    icon: Paperclip,
    accent: 'burgundy',
    route: '/evidence',
  },
  decisions: {
    label: 'Decisions',
    icon: CheckSquare,
    accent: 'navy',
    route: '/decisions',
  },
  sfs_guidelines: {
    label: 'SFS Guidelines',
    icon: Table2,
    accent: 'burgundy',
    route: '/sfs',
  },
}

const ACCENTS = {
  navy: { border: 'border-t-brand-navy', chip: 'bg-slate-100 text-brand-navy', hoverText: 'group-hover:text-brand-navy' },
  slate: { border: 'border-t-slate-500', chip: 'bg-slate-100 text-slate-600', hoverText: 'group-hover:text-slate-700' },
  gold: { border: 'border-t-brand-gold', chip: 'bg-amber-50 text-brand-gold', hoverText: 'group-hover:text-brand-gold' },
  forest: { border: 'border-t-emerald-800', chip: 'bg-emerald-50 text-emerald-800', hoverText: 'group-hover:text-emerald-800' },
  burgundy: { border: 'border-t-brand-red', chip: 'bg-rose-50 text-brand-red', hoverText: 'group-hover:text-brand-red' },
}

function DashboardCard({ title, icon: Icon, accent, count, isLoading, route }) {
  const style = ACCENTS[accent] || ACCENTS.navy
  return (
    <Link
      to={route}
      className={`group bg-white rounded-lg border border-slate-200 border-t-4 ${style.border} p-5 shadow-sm hover:shadow-md transition-all duration-200`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2.5 rounded-md ${style.chip}`}>
          <Icon className="w-5 h-5" />
        </div>
        {isLoading ? (
          <div className="w-12 h-7 animate-pulse bg-slate-200 rounded" />
        ) : (
          <span className="text-2xl font-display font-bold text-brand-navy tracking-tight">
            {count ?? '—'}
          </span>
        )}
      </div>
      <div>
        <h3 className={`text-sm font-semibold text-slate-800 ${style.hoverText} transition-colors`}>
          {title}
        </h3>
        <div className="flex items-center gap-1 mt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 group-hover:text-slate-600">
          View
          <ChevronRight className="w-3 h-3 transition-transform group-hover:translate-x-1" />
        </div>
      </div>
    </Link>
  )
}

function SectionHeading({ children }) {
  return (
    <div className="col-span-full mb-2 mt-6 first:mt-0 flex items-center gap-3">
      <h2 className="text-[11px] font-bold text-slate-500 uppercase tracking-[0.2em]">{children}</h2>
      <div className="h-px flex-1 bg-slate-200" />
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
      <div className="mb-10 rounded-xl bg-brand-navy overflow-hidden shadow-sm">
        <div className="h-1 w-full bg-gradient-to-r from-brand-navy via-brand-gold to-brand-red" />
        <div className="px-8 py-7 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold text-white tracking-tight">
              Welcome, {displayName}
            </h1>
            <p className="mt-1.5 text-slate-300 font-medium">
              Here's an overview of your department access and available tools.
            </p>
          </div>

          {/* Department badge */}
          {deptLoading ? (
            <div className="w-36 h-9 animate-pulse bg-white/10 rounded-full" />
          ) : department ? (
            <div className="flex items-center gap-2 text-sm font-semibold text-white bg-white/10 border border-white/20 px-3.5 py-1.5 rounded-full">
              <div className="w-2 h-2 rounded-full bg-brand-gold flex-shrink-0" />
              {department.name}
            </div>
          ) : null}
        </div>
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
                  accent={config.accent}
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
                    className="bg-brand-navy hover:bg-slate-800 text-white text-sm px-4 py-2 rounded-md font-medium transition-colors flex items-center gap-2 border border-transparent hover:border-brand-gold/40"
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
