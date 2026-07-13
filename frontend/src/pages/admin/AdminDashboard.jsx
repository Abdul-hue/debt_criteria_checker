import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import CrmSyncHistoryPanel from '../../components/dashboard/CrmSyncHistoryPanel'
import TodaySyncReportPanel from '../../components/dashboard/TodaySyncReportPanel'
import {
  Users,
  FileText,
  Shield,
  CheckSquare,
  Settings,
  Building2,
  ChevronRight,
  Table2,
} from 'lucide-react'

/**
 * Fetch the count from a paginated list endpoint.
 * Returns the `count` field (total number of records).
 */
function useModelCount(queryKey, url) {
  return useQuery({
    queryKey,
    queryFn: async () => {
      const { data } = await api.get(url)
      return typeof data.count === 'number' ? data.count : (data.results ?? data).length
    },
    staleTime: 60 * 1000,
  })
}

const ACCENTS = {
  navy: { border: 'border-t-brand-navy', chip: 'bg-slate-100 text-brand-navy', hoverText: 'group-hover:text-brand-navy' },
  slate: { border: 'border-t-slate-500', chip: 'bg-slate-100 text-slate-600', hoverText: 'group-hover:text-slate-700' },
  gold: { border: 'border-t-brand-gold', chip: 'bg-amber-50 text-brand-gold', hoverText: 'group-hover:text-brand-gold' },
  forest: { border: 'border-t-emerald-800', chip: 'bg-emerald-50 text-emerald-800', hoverText: 'group-hover:text-emerald-800' },
  burgundy: { border: 'border-t-brand-red', chip: 'bg-rose-50 text-brand-red', hoverText: 'group-hover:text-brand-red' },
}

function DashboardCard({ title, icon: Icon, accent = 'navy', count, changeTo }) {
  const style = ACCENTS[accent] || ACCENTS.navy
  return (
    <Link
      to={changeTo}
      className={`group bg-white rounded-lg border border-slate-200 border-t-4 ${style.border} p-5 shadow-sm hover:shadow-md transition-all duration-200`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2.5 rounded-md ${style.chip}`}>
          <Icon className="w-5 h-5" />
        </div>
        {count !== undefined && (
          <span className="text-2xl font-display font-bold text-brand-navy tracking-tight">
            {count === null ? <LoadingSpinner size="sm" /> : count}
          </span>
        )}
      </div>
      <div>
        <h3 className={`text-sm font-semibold text-slate-800 ${style.hoverText} transition-colors`}>{title}</h3>
        <div className="flex items-center gap-1 mt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400 group-hover:text-slate-600">
          Manage Resources
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

export default function AdminDashboard() {
  const users = useModelCount(['users-count'], '/api/v1/criteria/users/?page_size=1')
  const applications = useModelCount(['applications-count'], '/api/v1/criteria/applications/?page_size=1')
  const creditors = useModelCount(['creditors-count'], '/api/v1/criteria/creditors/?page_size=1')
  const decisions = useModelCount(['decisions-count'], '/api/v1/criteria/assess/history/?page_size=1')
  const rules = useModelCount(['rules-count'], '/api/v1/criteria/rules/?page_size=1')
  const councils = useModelCount(['councils-count'], '/api/v1/criteria/councils/?page_size=1')
  const sfsGuidelines = useModelCount(['sfs-guidelines-count'], '/api/v1/criteria/sfs/guidelines/?page_size=1')

  return (
    <div className="p-8 max-w-7xl mx-auto min-h-screen bg-slate-50/50">
      {/* Page header */}
      <div className="mb-10 rounded-xl bg-brand-navy overflow-hidden shadow-sm">
        <div className="h-1 w-full bg-gradient-to-r from-brand-navy via-brand-gold to-brand-red" />
        <div className="px-8 py-7 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold text-white tracking-tight">System Control</h1>
            <p className="mt-1.5 text-slate-300 font-medium">
              Global administration and data management console.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-white bg-white/10 border border-white/20 px-3.5 py-1.5 rounded-full">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
            System Operational
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">

        {/* Auth section */}
        <SectionHeading>Access Control</SectionHeading>
        <DashboardCard
          title="User Accounts"
          icon={Users}
          accent="gold"
          count={users.isLoading ? null : (users.data ?? '?')}
          changeTo="/admin/users"
        />

        {/* Debt Criteria Application section */}
        <SectionHeading>Core Engine Data</SectionHeading>
        <DashboardCard
          title="Case Applications"
          icon={FileText}
          accent="navy"
          count={applications.isLoading ? null : (applications.data ?? '?')}
          changeTo="/admin/applications"
        />
        <DashboardCard
          title="Creditor Rules"
          icon={Building2}
          accent="slate"
          count={creditors.isLoading ? null : (creditors.data ?? '?')}
          changeTo="/rules"
        />
        <DashboardCard
          title="Decision Logs"
          icon={CheckSquare}
          accent="forest"
          count={decisions.isLoading ? null : (decisions.data ?? '?')}
          changeTo="/admin/decisions"
        />
        <DashboardCard
          title="Global Thresholds"
          icon={Settings}
          accent="slate"
          count={rules.isLoading ? null : (rules.data ?? '?')}
          changeTo="/rules"
        />
        <DashboardCard
          title="Council Settings"
          icon={Shield}
          accent="navy"
          count={councils.isLoading ? null : (councils.data ?? '?')}
          changeTo="/rules"
        />
        <DashboardCard
          title="SFS Expenditure Guidelines"
          icon={Table2}
          accent="gold"
          count={sfsGuidelines.isLoading ? null : (sfsGuidelines.data ?? '?')}
          changeTo="/admin/sfs-guidelines"
        />

        <SectionHeading>CRM Vote Sync</SectionHeading>
        <TodaySyncReportPanel />
        <CrmSyncHistoryPanel />
      </div>
    </div>
  )
}
