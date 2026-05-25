import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
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

function DashboardCard({ title, icon: Icon, iconColor, count, changeTo }) {
  return (
    <Link 
      to={changeTo}
      className="group bg-white rounded-xl border border-slate-200 p-5 hover:border-slate-300 hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2.5 rounded-lg ${iconColor} group-hover:scale-110 transition-transform duration-200`}>
          <Icon className="w-5 h-5" />
        </div>
        {count !== undefined && (
          <span className="text-2xl font-bold text-slate-900 tracking-tight">
            {count === null ? <LoadingSpinner size="sm" /> : count}
          </span>
        )}
      </div>
      <div>
        <h3 className="text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors">{title}</h3>
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
    <div className="col-span-full mb-2 mt-6 first:mt-0">
      <h2 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">{children}</h2>
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
      <div className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">System Control</h1>
          <p className="mt-1 text-slate-500 font-medium">
            Global administration and data management console.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-semibold text-slate-400 bg-white border border-slate-200 px-4 py-2 rounded-full shadow-sm">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          System Operational
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">

        {/* Auth section */}
        <SectionHeading>Access Control</SectionHeading>
        <DashboardCard
          title="User Accounts"
          icon={Users}
          iconColor="bg-purple-50 text-purple-600"
          count={users.isLoading ? null : (users.data ?? '?')}
          changeTo="/admin/users"
        />

        {/* Debt Criteria Application section */}
        <SectionHeading>Core Engine Data</SectionHeading>
        <DashboardCard
          title="Case Applications"
          icon={FileText}
          iconColor="bg-blue-50 text-blue-600"
          count={applications.isLoading ? null : (applications.data ?? '?')}
          changeTo="/admin/applications"
        />
        <DashboardCard
          title="Creditor Rules"
          icon={Building2}
          iconColor="bg-cyan-50 text-cyan-600"
          count={creditors.isLoading ? null : (creditors.data ?? '?')}
          changeTo="/rules"
        />
        <DashboardCard
          title="Decision Logs"
          icon={CheckSquare}
          iconColor="bg-emerald-50 text-emerald-600"
          count={decisions.isLoading ? null : (decisions.data ?? '?')}
          changeTo="/admin/decisions"
        />
        <DashboardCard
          title="Global Thresholds"
          icon={Settings}
          iconColor="bg-slate-100 text-slate-600"
          count={rules.isLoading ? null : (rules.data ?? '?')}
          changeTo="/rules"
        />
        <DashboardCard
          title="Council Settings"
          icon={Shield}
          iconColor="bg-indigo-50 text-indigo-600"
          count={councils.isLoading ? null : (councils.data ?? '?')}
          changeTo="/rules"
        />
        <DashboardCard
          title="SFS Expenditure Guidelines"
          icon={Table2}
          iconColor="bg-amber-50 text-amber-600"
          count={sfsGuidelines.isLoading ? null : (sfsGuidelines.data ?? '?')}
          changeTo="/admin/sfs-guidelines"
        />
      </div>
    </div>
  )
}
