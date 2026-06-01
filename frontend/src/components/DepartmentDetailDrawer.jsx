import { useState, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDepartments,
  useDepartmentRules,
  useDepartmentCreditors,
  useDepartmentCouncils,
  useDepartmentFeatures,
  useDepartmentPermissions,
  useToggleDepartmentRule,
  useToggleDepartmentCreditor,
  useToggleDepartmentCouncil,
  useToggleDepartmentFeature,
  useSetDepartmentPermission,
} from '../hooks/useDepartments'
import { useUsers, useUpdateUserDepartment } from '../hooks/useUsers'
import { useToast } from '../hooks/useToast'
import { extractErrorMessage } from '../lib/errorHandler'
import api from '../lib/axios'
import LoadingSpinner from './shared/LoadingSpinner'
import DepartmentFormDrawer from './DepartmentFormDrawer'
import {
  Pencil, Search, ChevronDown, ChevronRight, Loader2, Users, X,
  Shield, Landmark, PieChart, Calculator, Play, ClipboardList,
  FileText, UserCog, Building,
} from 'lucide-react'

const GROUP_ORDER = ['TIG', 'WATCH', 'TIX', 'EVOLVE']

const CRITERIA_COLORS = {
  TIG: 'bg-blue-100 text-blue-700',
  WATCH: 'bg-amber-100 text-amber-700',
  TIX: 'bg-purple-100 text-purple-700',
  EVOLVE: 'bg-emerald-100 text-emerald-700',
}

const SEVERITY_STYLES = {
  hard_block: 'bg-red-100 text-red-700 border border-red-200',
  flag: 'bg-amber-100 text-amber-700 border border-amber-200',
  info: 'bg-blue-100 text-blue-700 border border-blue-200',
  soft_block: 'bg-orange-100 text-orange-700 border border-orange-200',
  warning: 'bg-amber-100 text-amber-700 border border-amber-200',
}

const SEVERITY_LABELS = {
  hard_block: 'Hard Block',
  flag: 'Flag',
  info: 'Info',
  soft_block: 'Soft Block',
  warning: 'Warning',
}

const STATUS_STYLES = {
  ACCEPT: 'bg-green-100 text-green-700',
  REJECT: 'bg-red-100 text-red-700',
  REFERRED: 'bg-amber-100 text-amber-700',
  WATCH: 'bg-blue-100 text-blue-700',
  WILL_CONSIDER: 'bg-amber-100 text-amber-700',
  DO_NOT_VOTE: 'bg-slate-100 text-slate-600',
  CONDITIONAL_VOTER: 'bg-purple-100 text-purple-700',
}

const REP_STYLES = {
  TIG: 'bg-blue-100 text-blue-700 border border-blue-200',
  WATCH: 'bg-amber-100 text-amber-700 border border-amber-200',
  TIX: 'bg-purple-100 text-purple-700 border border-purple-200',
  EVOLVE: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
  General: 'bg-slate-100 text-slate-600 border border-slate-200',
  EVERYDAY_LOANS: 'bg-orange-100 text-orange-700 border border-orange-200',
  NONE: 'bg-slate-100 text-slate-500',
}

const TABS = [
  { id: 'features', label: 'Feature Access' },
  { id: 'permissions', label: 'Permissions' },
  { id: 'rules', label: 'Rules Visibility' },
  { id: 'creditors', label: 'Creditors Visibility' },
  { id: 'councils', label: 'Councils Visibility' },
  { id: 'users', label: 'Users' },
]

const FEATURE_DEFS = [
  { key: 'general_creditors', label: 'General Creditors', description: 'Standard creditor rules', icon: Users },
  { key: 'representative_creditors', label: 'Representative Creditors', description: 'WATCH/TIX/EVOLVE rules', icon: Building },
  { key: 'global_rules', label: 'Global Rules', description: 'System-wide IVA criteria', icon: Shield },
  { key: 'councils', label: 'Councils', description: 'Council voting rules', icon: Landmark },
  { key: 'dividends', label: 'Dividends', description: 'Dividend criteria per creditor', icon: PieChart },
  { key: 'sfs_guidelines', label: 'SFS Guidelines', description: 'Expenditure guidelines', icon: Calculator },
  { key: 'run_assessment', label: 'Run Assessment', description: 'Execute case criteria engine', icon: Play },
  { key: 'decisions', label: 'Decisions', description: 'View assessment history', icon: ClipboardList },
  { key: 'evidence', label: 'Evidence', description: 'Evidence ledger', icon: FileText },
  { key: 'user_management', label: 'User Management', description: 'Manage system users', icon: UserCog },
]

const FEATURE_SECTIONS = [
  {
    label: 'Rule Management',
    keys: ['general_creditors', 'representative_creditors', 'global_rules', 'councils', 'dividends', 'sfs_guidelines'],
  },
  {
    label: 'Operations',
    keys: ['run_assessment', 'decisions', 'evidence', 'user_management'],
  },
]

function ToggleSwitch({ checked, onChange, disabled }) {
  return (
    <label className="relative inline-flex items-center cursor-pointer shrink-0">
      <input
        type="checkbox"
        className="sr-only peer"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <div className="w-9 h-5 bg-slate-200 peer-focus:ring-2 peer-focus:ring-slate-400 rounded-full peer peer-checked:bg-slate-700 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4 peer-disabled:opacity-50 peer-disabled:cursor-not-allowed" />
    </label>
  )
}

function SummaryBar({ count, total, label }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="bg-slate-100 border border-slate-200 rounded-xl px-4 py-3 mb-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm text-slate-700 font-medium">
          {count} of {total} {label}
        </span>
        <span className="text-xs text-slate-400">{pct}%</span>
      </div>
      <div className="bg-slate-300 rounded-full h-1.5">
        <div
          className="bg-slate-600 h-1.5 rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function SearchInput({ value, onChange, placeholder, resultCount, totalCount }) {
  return (
    <div className="mb-3">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-white border border-slate-200 rounded-xl pl-8 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-400 transition-colors"
        />
      </div>
      {value && (
        <p className="text-xs text-slate-400 mt-1 ml-1">
          Showing {resultCount} of {totalCount}
        </p>
      )}
    </div>
  )
}

function BulkActionsBar({ onEnableAll, onDisableAll, loading, disabled = false }) {
  const isDisabled = !!loading || disabled
  return (
    <div className="flex items-center gap-2 mb-4">
      <button
        onClick={onEnableAll}
        disabled={isDisabled}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading === 'enable' && <Loader2 size={12} className="animate-spin" />}
        Enable All
      </button>
      <button
        onClick={onDisableAll}
        disabled={isDisabled}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading === 'disable' && <Loader2 size={12} className="animate-spin" />}
        Disable All
      </button>
    </div>
  )
}

function GroupHeader({ groupKey, colorClass, count, visibleCount, isCollapsed, onToggleCollapse, searchActive, gLoading, bulkLoading, onEnable, onDisable }) {
  return (
    <div className="bg-slate-100 rounded-lg px-4 py-2.5 mb-2 flex items-center gap-2">
      <button
        onClick={onToggleCollapse}
        disabled={searchActive}
        className="flex items-center gap-2 flex-1 min-w-0 disabled:cursor-default"
      >
        {isCollapsed
          ? <ChevronRight size={14} className="text-slate-400 shrink-0" />
          : <ChevronDown size={14} className="text-slate-400 shrink-0" />
        }
        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${colorClass}`}>
          {groupKey}
        </span>
        <span className="text-xs text-slate-400">{count}</span>
        <span className="bg-white border border-slate-200 text-xs px-2 py-0.5 rounded-full text-slate-600">
          {visibleCount} visible
        </span>
      </button>
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={onEnable}
          disabled={!!gLoading || !!bulkLoading}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs text-emerald-700 bg-emerald-100 rounded-md hover:bg-emerald-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {gLoading === 'enable' && <Loader2 size={10} className="animate-spin" />}
          Enable
        </button>
        <button
          onClick={onDisable}
          disabled={!!gLoading || !!bulkLoading}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs text-slate-600 bg-slate-100 rounded-md hover:bg-slate-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {gLoading === 'disable' && <Loader2 size={10} className="animate-spin" />}
          Disable
        </button>
      </div>
    </div>
  )
}

function RulesTab({ deptId }) {
  const queryClient = useQueryClient()
  const { data: rules, isLoading } = useDepartmentRules(deptId)
  const toggleRule = useToggleDepartmentRule(deptId)
  const toast = useToast()
  const [local, setLocal] = useState([])
  const [search, setSearch] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState(new Set())
  const [bulkLoading, setBulkLoading] = useState(null)
  const [groupLoading, setGroupLoading] = useState({})
  const initialized = useRef(false)

  useEffect(() => {
    if (!rules) return
    setLocal(rules)
    if (!initialized.current) {
      initialized.current = true
      const grouped = {}
      rules.forEach((r) => {
        const key = r.criteria_set || 'Other'
        if (!grouped[key]) grouped[key] = []
        grouped[key].push(r)
      })
      const collapsed = new Set(
        Object.entries(grouped)
          .filter(([, gr]) => gr.every((r) => !r.is_visible))
          .map(([key]) => key)
      )
      setCollapsedGroups(collapsed)
    }
  }, [rules])

  if (isLoading) return <LoadingSpinner />

  const grouped = local.reduce((acc, r) => {
    const key = r.criteria_set || 'Other'
    if (!acc[key]) acc[key] = []
    acc[key].push(r)
    return acc
  }, {})

  const sortedGroupKeys = [
    ...GROUP_ORDER.filter((g) => grouped[g]),
    ...Object.keys(grouped).filter((g) => !GROUP_ORDER.includes(g)),
  ]

  const lowerSearch = search.toLowerCase()
  const filteredGrouped = sortedGroupKeys.reduce((acc, key) => {
    const items = search
      ? grouped[key].filter(
          (r) =>
            r.rule_name?.toLowerCase().includes(lowerSearch) ||
            r.rule_key?.toLowerCase().includes(lowerSearch)
        )
      : grouped[key]
    if (items.length > 0) acc[key] = items
    return acc
  }, {})

  const totalCount = local.length
  const filteredCount = Object.values(filteredGrouped).flat().length
  const visibleTotal = local.filter((r) => r.is_visible).length
  const anyGroupLoading = Object.values(groupLoading).some(Boolean)

  const handleToggle = (rule_key, currentVisible) => {
    const newVisible = !currentVisible
    setLocal((prev) => prev.map((r) => (r.rule_key === rule_key ? { ...r, is_visible: newVisible } : r)))
    toggleRule.mutate(
      { rule_key, is_visible: newVisible },
      {
        onError: () => {
          setLocal((prev) => prev.map((r) => (r.rule_key === rule_key ? { ...r, is_visible: currentVisible } : r)))
          toast.error('Error', 'Failed to update rule visibility')
        },
      }
    )
  }

  const handleBulkToggle = async (targetRules, is_visible) => {
    const snapshot = [...local]
    const targetKeys = new Set(targetRules.map((r) => r.rule_key))
    setLocal((l) => l.map((r) => (targetKeys.has(r.rule_key) ? { ...r, is_visible } : r)))
    setBulkLoading(is_visible ? 'enable' : 'disable')
    try {
      await Promise.all(
        targetRules.map((r) =>
          api.post(`/api/v1/criteria/departments/${deptId}/rules/toggle/`, { rule_key: r.rule_key, is_visible })
        )
      )
      queryClient.invalidateQueries({ queryKey: ['department-rules', deptId] })
    } catch {
      setLocal(snapshot)
      toast.error('Error', 'Failed to update rules')
    } finally {
      setBulkLoading(null)
    }
  }

  const handleGroupToggle = async (groupKey, groupRules, is_visible) => {
    const snapshot = [...local]
    const groupRuleKeys = new Set(groupRules.map((r) => r.rule_key))
    setLocal((l) => l.map((r) => (groupRuleKeys.has(r.rule_key) ? { ...r, is_visible } : r)))
    setGroupLoading((curr) => ({ ...curr, [groupKey]: is_visible ? 'enable' : 'disable' }))
    try {
      await Promise.all(
        groupRules.map((r) =>
          api.post(`/api/v1/criteria/departments/${deptId}/rules/toggle/`, { rule_key: r.rule_key, is_visible })
        )
      )
      queryClient.invalidateQueries({ queryKey: ['department-rules', deptId] })
    } catch {
      setLocal(snapshot)
      toast.error('Error', 'Failed to update group rules')
    } finally {
      setGroupLoading((curr) => ({ ...curr, [groupKey]: null }))
    }
  }

  const toggleGroupCollapse = (groupKey) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(groupKey)) next.delete(groupKey)
      else next.add(groupKey)
      return next
    })
  }

  return (
    <div>
      <SummaryBar count={visibleTotal} total={totalCount} label="rules visible" />
      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder="Search rules by name or key..."
        resultCount={filteredCount}
        totalCount={totalCount}
      />
      <BulkActionsBar
        onEnableAll={() => handleBulkToggle(local, true)}
        onDisableAll={() => handleBulkToggle(local, false)}
        loading={bulkLoading}
        disabled={anyGroupLoading}
      />
      <div className="space-y-3">
        {Object.entries(filteredGrouped).map(([groupKey, groupItems]) => {
          const allGroupRules = grouped[groupKey] || []
          const visibleCount = allGroupRules.filter((r) => r.is_visible).length
          const isCollapsed = collapsedGroups.has(groupKey) && !search
          const gLoading = groupLoading[groupKey]

          return (
            <div key={groupKey}>
              <GroupHeader
                groupKey={groupKey}
                colorClass={CRITERIA_COLORS[groupKey] || 'bg-slate-100 text-slate-600'}
                count={`${allGroupRules.length} rules`}
                visibleCount={visibleCount}
                isCollapsed={isCollapsed}
                onToggleCollapse={() => toggleGroupCollapse(groupKey)}
                searchActive={!!search}
                gLoading={gLoading}
                bulkLoading={bulkLoading}
                onEnable={() => handleGroupToggle(groupKey, allGroupRules, true)}
                onDisable={() => handleGroupToggle(groupKey, allGroupRules, false)}
              />

              {!isCollapsed && (
                <div className="space-y-1.5 pt-1">
                  {groupItems.map((rule) => (
                    <div
                      key={rule.rule_key}
                      className={`flex items-center gap-3 rounded-xl border shadow-sm p-4 transition-all duration-200 ${
                        rule.is_visible
                          ? 'border-slate-200 border-l-4 border-l-emerald-500 bg-emerald-50/30 hover:shadow-md hover:border-slate-300'
                          : 'border-slate-200 border-l-4 border-l-slate-300 bg-slate-50 opacity-55'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-slate-800">{rule.rule_name}</span>
                          <span className="bg-slate-100 text-slate-600 font-mono text-xs px-2 py-0.5 rounded">
                            {rule.rule_key}
                          </span>
                        </div>
                      </div>
                      {rule.action_type && (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${SEVERITY_STYLES[rule.action_type] || 'bg-slate-100 text-slate-600'}`}>
                          {SEVERITY_LABELS[rule.action_type] || rule.action_type}
                        </span>
                      )}
                      <ToggleSwitch
                        checked={rule.is_visible}
                        onChange={() => handleToggle(rule.rule_key, rule.is_visible)}
                        disabled={toggleRule.isPending || !!bulkLoading || !!groupLoading[groupKey]}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CreditorsTab({ deptId }) {
  const queryClient = useQueryClient()
  const { data: creditors, isLoading } = useDepartmentCreditors(deptId)
  const toggleCreditor = useToggleDepartmentCreditor(deptId)
  const toast = useToast()
  const [local, setLocal] = useState([])
  const [search, setSearch] = useState('')
  const [bulkLoading, setBulkLoading] = useState(null)
  const [collapsedGroups, setCollapsedGroups] = useState(new Set())
  const [groupLoading, setGroupLoading] = useState({})

  useEffect(() => {
    if (creditors) setLocal(creditors)
  }, [creditors])

  if (isLoading) return <LoadingSpinner />

  const lowerSearch = search.toLowerCase()
  const filtered = search
    ? local.filter((c) => c.name?.toLowerCase().includes(lowerSearch))
    : local

  const grouped = filtered.reduce((acc, c) => {
    const key = c.representative && c.representative !== 'NONE' ? c.representative : 'General'
    if (!acc[key]) acc[key] = []
    acc[key].push(c)
    return acc
  }, {})

  const repOrder = ['TIG', 'WATCH', 'TIX', 'EVOLVE', 'EVERYDAY_LOANS', 'General']
  const sortedGroupKeys = [
    ...repOrder.filter((g) => grouped[g]),
    ...Object.keys(grouped).filter((g) => !repOrder.includes(g)),
  ]

  const allGrouped = local.reduce((acc, c) => {
    const key = c.representative && c.representative !== 'NONE' ? c.representative : 'General'
    if (!acc[key]) acc[key] = []
    acc[key].push(c)
    return acc
  }, {})

  const visibleTotal = local.filter((c) => c.is_visible).length

  const handleToggle = (creditor_id, currentVisible) => {
    const newVisible = !currentVisible
    setLocal((prev) => prev.map((c) => (c.id === creditor_id ? { ...c, is_visible: newVisible } : c)))
    toggleCreditor.mutate(
      { creditor_id, is_visible: newVisible },
      {
        onError: () => {
          setLocal((prev) => prev.map((c) => (c.id === creditor_id ? { ...c, is_visible: currentVisible } : c)))
          toast.error('Error', 'Failed to update creditor visibility')
        },
      }
    )
  }

  const handleBulkToggle = async (is_visible) => {
    const snapshot = [...local]
    setLocal((l) => l.map((c) => ({ ...c, is_visible })))
    setBulkLoading(is_visible ? 'enable' : 'disable')
    try {
      await Promise.all(
        snapshot.map((c) =>
          api.post(`/api/v1/criteria/departments/${deptId}/creditors/toggle/`, { creditor_id: c.id, is_visible })
        )
      )
      queryClient.invalidateQueries({ queryKey: ['department-creditors', deptId] })
    } catch {
      setLocal(snapshot)
      toast.error('Error', 'Failed to update creditors')
    } finally {
      setBulkLoading(null)
    }
  }

  const handleGroupToggle = async (groupKey, groupItems, is_visible) => {
    const snapshot = [...local]
    const ids = new Set(groupItems.map((c) => c.id))
    setLocal((l) => l.map((c) => (ids.has(c.id) ? { ...c, is_visible } : c)))
    setGroupLoading((curr) => ({ ...curr, [groupKey]: is_visible ? 'enable' : 'disable' }))
    try {
      await Promise.all(
        groupItems.map((c) =>
          api.post(`/api/v1/criteria/departments/${deptId}/creditors/toggle/`, { creditor_id: c.id, is_visible })
        )
      )
      queryClient.invalidateQueries({ queryKey: ['department-creditors', deptId] })
    } catch {
      setLocal(snapshot)
      toast.error('Error', 'Failed to update group creditors')
    } finally {
      setGroupLoading((curr) => ({ ...curr, [groupKey]: null }))
    }
  }

  const toggleGroupCollapse = (groupKey) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(groupKey)) next.delete(groupKey)
      else next.add(groupKey)
      return next
    })
  }

  if (local.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">No creditors found.</p>
  }

  return (
    <div>
      <SummaryBar count={visibleTotal} total={local.length} label="creditors visible" />
      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder="Search creditors..."
        resultCount={filtered.length}
        totalCount={local.length}
      />
      <BulkActionsBar
        onEnableAll={() => handleBulkToggle(true)}
        onDisableAll={() => handleBulkToggle(false)}
        loading={bulkLoading}
        disabled={Object.values(groupLoading).some(Boolean)}
      />
      <div className="space-y-3">
        {sortedGroupKeys.map((groupKey) => {
          const groupItems = grouped[groupKey] || []
          const allGroupItems = allGrouped[groupKey] || []
          const visibleCount = allGroupItems.filter((c) => c.is_visible).length
          const isCollapsed = collapsedGroups.has(groupKey) && !search
          const gLoading = groupLoading[groupKey]

          return (
            <div key={groupKey}>
              <GroupHeader
                groupKey={groupKey}
                colorClass={REP_STYLES[groupKey] || 'bg-slate-100 text-slate-600 border border-slate-200'}
                count={`${allGroupItems.length} creditors`}
                visibleCount={visibleCount}
                isCollapsed={isCollapsed}
                onToggleCollapse={() => toggleGroupCollapse(groupKey)}
                searchActive={!!search}
                gLoading={gLoading}
                bulkLoading={bulkLoading}
                onEnable={() => handleGroupToggle(groupKey, allGroupItems, true)}
                onDisable={() => handleGroupToggle(groupKey, allGroupItems, false)}
              />

              {!isCollapsed && (
                <div className="space-y-1.5 pt-1">
                  {groupItems.map((c) => (
                    <div
                      key={c.id}
                      className={`flex items-center gap-3 rounded-xl border shadow-sm p-4 transition-all duration-200 ${
                        c.is_visible
                          ? 'border-slate-200 border-l-4 border-l-emerald-500 bg-emerald-50/30 hover:shadow-md hover:border-slate-300'
                          : 'border-slate-200 border-l-4 border-l-slate-300 bg-slate-50 opacity-55'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-slate-800">{c.name}</span>
                          {c.representative && c.representative !== 'NONE' && (
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${REP_STYLES[c.representative] || 'bg-slate-100 text-slate-500'}`}>
                              {c.representative}
                            </span>
                          )}
                          {c.status && (
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${STATUS_STYLES[c.status] || 'bg-slate-100 text-slate-600'}`}>
                              {c.status}
                            </span>
                          )}
                        </div>
                        {c.parent_group && (
                          <p className="text-xs text-slate-400 italic mt-0.5 truncate">{c.parent_group}</p>
                        )}
                      </div>
                      <ToggleSwitch
                        checked={c.is_visible}
                        onChange={() => handleToggle(c.id, c.is_visible)}
                        disabled={toggleCreditor.isPending || !!bulkLoading || !!groupLoading[groupKey]}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CouncilsTab({ deptId }) {
  const queryClient = useQueryClient()
  const { data: councils, isLoading } = useDepartmentCouncils(deptId)
  const toggleCouncil = useToggleDepartmentCouncil(deptId)
  const toast = useToast()
  const [local, setLocal] = useState([])
  const [search, setSearch] = useState('')
  const [bulkLoading, setBulkLoading] = useState(null)

  useEffect(() => {
    if (councils) setLocal(councils)
  }, [councils])

  if (isLoading) return <LoadingSpinner />

  const lowerSearch = search.toLowerCase()
  const filtered = search
    ? local.filter((c) => c.name?.toLowerCase().includes(lowerSearch))
    : local

  const visibleTotal = local.filter((c) => c.is_visible).length

  const handleToggle = (council_id, currentVisible) => {
    const newVisible = !currentVisible
    setLocal((prev) => prev.map((c) => (c.id === council_id ? { ...c, is_visible: newVisible } : c)))
    toggleCouncil.mutate(
      { council_id, is_visible: newVisible },
      {
        onError: () => {
          setLocal((prev) => prev.map((c) => (c.id === council_id ? { ...c, is_visible: currentVisible } : c)))
          toast.error('Error', 'Failed to update council visibility')
        },
      }
    )
  }

  const handleBulkToggle = async (is_visible) => {
    const snapshot = [...local]
    setLocal((l) => l.map((c) => ({ ...c, is_visible })))
    setBulkLoading(is_visible ? 'enable' : 'disable')
    try {
      await Promise.all(
        snapshot.map((c) =>
          api.post(`/api/v1/criteria/departments/${deptId}/councils/toggle/`, { council_id: c.id, is_visible })
        )
      )
      queryClient.invalidateQueries({ queryKey: ['department-councils', deptId] })
    } catch {
      setLocal(snapshot)
      toast.error('Error', 'Failed to update councils')
    } finally {
      setBulkLoading(null)
    }
  }

  if (local.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">No councils found.</p>
  }

  return (
    <div>
      <SummaryBar count={visibleTotal} total={local.length} label="councils visible" />
      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder="Search councils..."
        resultCount={filtered.length}
        totalCount={local.length}
      />
      <BulkActionsBar
        onEnableAll={() => handleBulkToggle(true)}
        onDisableAll={() => handleBulkToggle(false)}
        loading={bulkLoading}
      />
      <div className="space-y-1.5">
        {filtered.map((c) => (
          <div
            key={c.id}
            className={`flex items-center gap-3 rounded-xl border shadow-sm p-4 transition-all duration-200 ${
              c.is_visible
                ? 'border-slate-200 border-l-4 border-l-emerald-500 bg-emerald-50/30 hover:shadow-md hover:border-slate-300'
                : 'border-slate-200 border-l-4 border-l-slate-300 bg-slate-50 opacity-55'
            }`}
          >
            <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-slate-800">{c.name}</span>
              {c.status && (
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${STATUS_STYLES[c.status] || 'bg-slate-100 text-slate-600'}`}>
                  {c.status}
                </span>
              )}
            </div>
            <ToggleSwitch
              checked={c.is_visible}
              onChange={() => handleToggle(c.id, c.is_visible)}
              disabled={toggleCouncil.isPending || !!bulkLoading}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

function FeaturesTab({ deptId }) {
  const { data: features, isLoading } = useDepartmentFeatures(deptId)
  const toggleFeature = useToggleDepartmentFeature(deptId)
  const toast = useToast()
  const [local, setLocal] = useState([])

  useEffect(() => {
    if (features) setLocal(features)
  }, [features])

  if (isLoading) return <LoadingSpinner />

  const handleToggle = (feature_key, currentEnabled) => {
    const newEnabled = !currentEnabled
    setLocal((prev) => prev.map((f) => (f.feature_key === feature_key ? { ...f, is_enabled: newEnabled } : f)))
    toggleFeature.mutate(
      { feature_key, is_enabled: newEnabled },
      {
        onError: () => {
          setLocal((prev) => prev.map((f) => (f.feature_key === feature_key ? { ...f, is_enabled: currentEnabled } : f)))
          toast.error('Error', 'Failed to update feature access')
        },
      }
    )
  }

  const featureMap = local.reduce((acc, f) => {
    acc[f.feature_key] = f.is_enabled
    return acc
  }, {})

  const enabledCount = FEATURE_DEFS.filter((def) =>
    featureMap[def.key] !== undefined ? featureMap[def.key] : true
  ).length

  return (
    <div>
      <SummaryBar count={enabledCount} total={FEATURE_DEFS.length} label="features enabled" />
      {FEATURE_SECTIONS.map((section) => {
        const sectionDefs = FEATURE_DEFS.filter((d) => section.keys.includes(d.key))
        return (
          <div key={section.label} className="mb-6">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
              {section.label}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {sectionDefs.map((def) => {
                const is_enabled = featureMap[def.key] !== undefined ? featureMap[def.key] : true
                const Icon = def.icon
                return (
                  <div
                    key={def.key}
                    className={`flex items-start gap-3 rounded-xl border shadow-sm p-4 transition-all duration-200 ${
                      is_enabled
                        ? 'border-slate-200 border-l-4 border-l-slate-500 bg-white hover:shadow-md hover:border-slate-300'
                        : 'border-slate-200 border-l-4 border-l-slate-300 bg-slate-50 opacity-55'
                    }`}
                  >
                    <div className="bg-slate-100 text-slate-600 p-2 rounded-lg shrink-0">
                      <Icon size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-slate-800 text-sm">{def.label}</p>
                      <p className="text-sm text-slate-500">{def.description}</p>
                    </div>
                    <ToggleSwitch
                      checked={is_enabled}
                      onChange={() => handleToggle(def.key, is_enabled)}
                      disabled={toggleFeature.isPending}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function UsersTab({ department }) {
  const { data: users = [] } = useUsers()
  const { data: departments = [] } = useDepartments()
  const { mutateAsync: updateUserDept, isPending } = useUpdateUserDepartment()
  const toast = useToast()
  const [reassignTarget, setReassignTarget] = useState(null)

  const deptUsers = users.filter((u) => u.department?.id === department.id)
  const otherDepts = departments.filter((d) => d.id !== department.id && d.is_active)

  const handleReassign = async (userId, newDeptId) => {
    if (!newDeptId) return
    try {
      await updateUserDept({ userId, department_id: parseInt(newDeptId, 10) })
      toast.success('User reassigned', 'Department updated successfully.')
      setReassignTarget(null)
    } catch (err) {
      toast.error('Reassign failed', extractErrorMessage(err))
    }
  }

  const getInitials = (user) => {
    if (user.first_name && user.last_name) {
      return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase()
    }
    return ((user.username || user.email || '?')[0] || '?').toUpperCase()
  }

  const getAvatarColor = (role) => {
    if (role === 'admin') return 'bg-purple-100 text-purple-700'
    if (role === 'assessor') return 'bg-blue-100 text-blue-700'
    return 'bg-slate-100 text-slate-600'
  }

  if (deptUsers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-3">
          <Users size={20} className="text-slate-400" />
        </div>
        <p className="text-sm font-medium text-slate-600 mb-1">No users assigned to this department yet.</p>
        <p className="text-xs text-slate-400">Assign users via User Management →</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {deptUsers.map((u) => (
        <div
          key={u.id}
          className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 hover:shadow-md hover:border-slate-300 transition-all duration-200"
        >
          <div className="flex items-start gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold shrink-0 ${getAvatarColor(u.role)}`}>
              {getInitials(u)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-slate-800">
                  {u.first_name && u.last_name ? `${u.first_name} ${u.last_name}` : u.username}
                </span>
                {u.role && (
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
                    u.role === 'admin'
                      ? 'bg-purple-100 text-purple-700 border-purple-200'
                      : u.role === 'assessor'
                      ? 'bg-blue-100 text-blue-700 border-blue-200'
                      : 'bg-slate-100 text-slate-600 border-slate-200'
                  }`}>
                    {u.role.charAt(0).toUpperCase() + u.role.slice(1)}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-400 truncate mt-0.5">{u.email}</p>
              {u.department?.name && (
                <span className="inline-block mt-1 text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                  {u.department.name}
                </span>
              )}
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-100">
            {reassignTarget === u.id ? (
              <div className="flex items-center gap-2">
                <select
                  onChange={(e) => handleReassign(u.id, e.target.value)}
                  disabled={isPending}
                  defaultValue=""
                  className="flex-1 text-sm border border-slate-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-50"
                >
                  <option value="" disabled>Select department...</option>
                  {otherDepts.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
                <button
                  onClick={() => setReassignTarget(null)}
                  className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setReassignTarget(u.id)}
                className="text-sm text-slate-500 hover:text-slate-800 underline transition-colors"
              >
                Reassign
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function PermissionsTab({ deptId }) {
  const { data: permissions, isLoading, refetch } = useDepartmentPermissions(deptId)
  const setPermission = useSetDepartmentPermission(deptId)
  const toast = useToast()
  const [local, setLocal] = useState([])

  useEffect(() => {
    if (permissions && permissions.length > 0) {
      setLocal(permissions)
    }
  }, [permissions])

  if (isLoading) return <LoadingSpinner />

  const handlePermissionChange = (feature_key, newLevel) => {
    const oldLevel = local.find(p => p.feature_key === feature_key)?.permission_level
    
    setLocal((prev) =>
      prev.map((p) => (p.feature_key === feature_key ? { ...p, permission_level: newLevel } : p))
    )
    
    setPermission.mutate(
      { feature_key, permission_level: newLevel },
      {
        onError: () => {
          setLocal((prev) =>
            prev.map((p) => (p.feature_key === feature_key ? { ...p, permission_level: oldLevel } : p))
          )
          toast.error('Error', 'Failed to update permission level')
        },
        onSuccess: () => {
          toast.success('Success', `Permission level updated to ${newLevel}`)
        },
      }
    )
  }

  const PERMISSION_FEATURES = [
    { key: 'general_creditors', label: 'General Creditors', icon: Users },
    { key: 'representative_creditors', label: 'Representative Creditors', icon: Building },
    { key: 'global_rules', label: 'Global Rules', icon: Shield },
    { key: 'councils', label: 'Councils', icon: Landmark },
    { key: 'dividends', label: 'Dividends', icon: PieChart },
    { key: 'sfs_guidelines', label: 'SFS Guidelines', icon: Calculator },
  ]

  return (
    <div>
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
        <p className="text-sm text-blue-900">
          <strong>Permission Levels:</strong> Control whether departments have <strong>READ</strong> (view-only) or <strong>WRITE</strong> (edit, create, delete) access to each feature.
        </p>
      </div>

      <div className="space-y-3">
        {PERMISSION_FEATURES.map((feature) => {
          const permission = local.find(p => p.feature_key === feature.key)
          const level = permission?.permission_level || 'READ'
          const Icon = feature.icon

          return (
            <div
              key={feature.key}
              className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 hover:shadow-md transition-all duration-200"
            >
              <div className="bg-slate-100 text-slate-600 p-2 rounded-lg shrink-0">
                <Icon size={18} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-800 text-sm">{feature.label}</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {level === 'READ' ? 'View-only access' : 'Full access (view, edit, create, delete)'}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <select
                  value={level}
                  onChange={(e) => handlePermissionChange(feature.key, e.target.value)}
                  disabled={setPermission.isPending}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
                    level === 'WRITE'
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                      : 'bg-slate-100 border-slate-200 text-slate-700'
                  } focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  <option value="READ">READ</option>
                  <option value="WRITE">WRITE</option>
                </select>
                {setPermission.isPending && <Loader2 size={14} className="animate-spin text-slate-400" />}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DepartmentDetailDrawer({ department, isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('features')
  const [editOpen, setEditOpen] = useState(false)

  useEffect(() => {
    if (isOpen) setActiveTab('features')
  }, [isOpen, department?.id])

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      window.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      window.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  if (!department) return null

  return (
    <>
      <div className={`fixed inset-0 z-50 flex justify-end transition-visibility duration-300 ${isOpen ? 'visible' : 'invisible'}`}>
        {/* Backdrop */}
        <div
          className={`fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
          onClick={onClose}
          aria-hidden="true"
        />

        {/* Drawer Panel */}
        <div
          className={`relative w-full sm:max-w-3xl bg-slate-50 shadow-2xl flex flex-col h-full transform transition-transform duration-200 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby="dept-drawer-title"
        >
          {/* Gradient Header + Tab Bar */}
          <div className="bg-gradient-to-r from-slate-800 to-slate-700 px-6 pt-5 shrink-0">
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1 min-w-0 pr-3">
                <h2 id="dept-drawer-title" className="text-xl font-bold text-white truncate">
                  {department.name}
                </h2>
                <code className="text-white/70 text-xs font-mono mt-1 inline-block bg-white/10 rounded px-2 py-0.5">
                  /{department.slug}
                </code>
                {department.description && (
                  <p className="text-white/80 text-sm mt-1 line-clamp-2">{department.description}</p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium text-white border border-white/30 bg-white/10">
                  <span className={`w-1.5 h-1.5 rounded-full ${department.is_active ? 'bg-emerald-300' : 'bg-slate-400'}`} />
                  {department.is_active ? 'Active' : 'Inactive'}
                </span>
                <button
                  onClick={() => setEditOpen(true)}
                  className="inline-flex items-center gap-1.5 text-xs text-white border border-white/30 rounded-lg px-3 py-1.5 hover:bg-white/10 transition-colors"
                >
                  <Pencil size={12} />
                  Edit
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                  aria-label="Close drawer"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Pill Tab Bar */}
            <div className="flex gap-1 overflow-x-auto pb-2 scrollbar-none">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all duration-150 ${
                    activeTab === tab.id
                      ? 'bg-white text-slate-800 shadow-sm'
                      : 'text-white/70 hover:text-white hover:bg-white/10'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Scrollable Content */}
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-4xl mx-auto px-6 py-5">
              {activeTab === 'features' && <FeaturesTab deptId={department.id} />}
              {activeTab === 'permissions' && <PermissionsTab deptId={department.id} />}
              {activeTab === 'rules' && <RulesTab deptId={department.id} />}
              {activeTab === 'creditors' && <CreditorsTab deptId={department.id} />}
              {activeTab === 'councils' && <CouncilsTab deptId={department.id} />}
              {activeTab === 'users' && <UsersTab department={department} />}
            </div>
          </div>
        </div>
      </div>

      <DepartmentFormDrawer
        isOpen={editOpen}
        onClose={() => setEditOpen(false)}
        department={department}
      />
    </>
  )
}
