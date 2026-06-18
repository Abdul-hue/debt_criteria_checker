import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useRules, usePatchRule } from '../../hooks/useRules'
import LoadingSpinner from '../shared/LoadingSpinner'
import RuleEditDrawer from './RuleEditDrawer'
import RuleDetailDrawer from './RuleDetailDrawer'
import {
  Search,
  ChevronDown,
  ChevronUp,
  Pencil,
  Eye,
  ExternalLink,
  Power
} from 'lucide-react'

const RULE_META = { 
  "TIG-05": { 
    title: "Wage Slip Required", 
    description: "Employment income must be supported by at least one payslip per employer. This verifies declared income before the IVA can proceed.", 
  }, 
  "TIG-10": { 
    title: "Debt Evidence Verification", 
    description: "Every unsecured debt of £1,000 or more must have a linked and verified creditor statement or letter. Unverified debts cannot be included in the IVA proposal.", 
  }, 
  "TIG-11": { 
    title: "Bank Statement Required", 
    description: "At least one valid bank statement is required to verify income, expenditure, and identify any antecedent transactions before a proposal can be submitted.", 
  }, 
  "TIG-13": { 
    title: "Previous IVA — Termination Report Needed", 
    description: "Where a client has had a previous IVA, a termination report must be uploaded and reviewed. This ensures any previous failure reasons are fully understood.", 
  }, 
  "TIG-16": { 
    title: "Property Equity Review", 
    description: "Where a client owns property, equity must be assessed. Significant equity may prevent an IVA from being the appropriate solution.", 
  }, 
  "TIG-21.1": { 
    title: "Link Financial — SFS Guidelines", 
    description: "Link Financial has specific requirements under the Mid SFS guidelines. These must be confirmed as applied before the case proceeds.", 
  }, 
  "WATCH-22.2": { 
    title: "Debt Repayable Without IVA", 
    description: "WATCH representatives reject cases where the client's disposable income could repay all unsecured debt within 6 years (72 months) without an IVA arrangement.", 
  }, 
  "WATCH-22.8": { 
    title: "Client Age — End-of-Term Risk", 
    description: "Where a client is aged 80 or over at the expected IVA completion date, WATCH flags a risk that the arrangement may not complete.", 
  }, 
  "WATCH-22.12": { 
    title: "Previous IVA — Consistency Check", 
    description: "Where a previous IVA exists, income, expenditure, assets and liabilities must be consistent with the previous proposal, or a written explanation must be provided for any material differences.", 
  }, 
}

const CATEGORIES = [
  "Income", "Bank", "Proof", "Creditor", "HMRC", "Vehicle", "Flags", "Other"
]

const SEVERITY_MAP = {
  hard_block: { label: 'Hard Block', color: 'bg-red-100 text-red-700 border-red-200', bar: 'bg-red-500' },
  flag: { label: 'Flag', color: 'bg-amber-100 text-amber-700 border-amber-200', bar: 'bg-amber-500' },
  info: { label: 'Info', color: 'bg-blue-100 text-blue-700 border-blue-200', bar: 'bg-blue-500' },
  pass: { label: 'Pass', color: 'bg-emerald-100 text-emerald-700 border-emerald-200', bar: 'bg-emerald-500' }
}

const CRITERIA_MAP = {
  TIG: { color: 'bg-blue-100 text-blue-700' },
  WATCH: { color: 'bg-purple-100 text-purple-700' },
  TIX: { color: 'bg-emerald-100 text-emerald-700' },
  EVOLVE: { color: 'bg-amber-100 text-amber-700' }
}

export default function RulesList() {
  const navigate = useNavigate()
  const { token } = useAuth()
  const { data: rules, isLoading, error } = useRules()
  const { mutate: patchRule, isPending: isToggling } = usePatchRule()
  const [togglingKey, setTogglingKey] = useState(null)

  function handleToggle(e, rule) {
    e.stopPropagation()
    setTogglingKey(rule.rule_key)
    patchRule(
      { ruleKey: rule.rule_key, is_active: !rule.is_active },
      { onSettled: () => setTogglingKey(null) }
    )
  }
  
  const [search, setSearch] = useState('')
  const [criteriaFilter, setCriteriaFilter] = useState([])
  const [severityFilter, setSeverityFilter] = useState([])
  const [categoryFilter, setCategoryFilter] = useState([])
  const [expandedRule, setExpandedRule] = useState(null)
  const [editTarget, setEditTarget] = useState(null)
  const [detailTarget, setDetailTarget] = useState(null)
  const [ruleHistory, setRuleHistory] = useState({})

  async function fetchRuleHistory(rule_key) {
    setRuleHistory(prev => ({
      ...prev,
      [rule_key]: { loading: true }
    }))
    try {
      const res = await fetch(
        `/api/v1/criteria/rules/${rule_key}/history/`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      const data = await res.json()
      setRuleHistory(prev => ({
        ...prev,
        [rule_key]: { loading: false, data }
      }))
    } catch {
      setRuleHistory(prev => ({
        ...prev,
        [rule_key]: { loading: false, error: true }
      }))
    }
  }

  const filteredRules = useMemo(() => {
    if (!rules) return []
    return rules.filter(r => {
      const matchesSearch = !search || 
        r.name.toLowerCase().includes(search.toLowerCase()) || 
        r.rule_key.toLowerCase().includes(search.toLowerCase())
      const matchesCriteria = criteriaFilter.length === 0 || criteriaFilter.includes(r.criteria_set)
      const matchesSeverity = severityFilter.length === 0 || severityFilter.includes(r.severity)
      const matchesCategory = categoryFilter.length === 0 || (r.category && categoryFilter.includes(r.category))
      return matchesSearch && matchesCriteria && matchesSeverity && matchesCategory
    })
  }, [rules, search, criteriaFilter, severityFilter, categoryFilter])

  const stats = useMemo(() => {
    if (!rules) return {}
    const counts = {
      TIG: 0, WATCH: 0, TIX: 0, EVOLVE: 0,
      hard_block: 0, flag: 0, info: 0
    }
    rules.forEach(r => {
      if (counts[r.criteria_set] !== undefined) counts[r.criteria_set]++
      if (counts[r.severity] !== undefined) counts[r.severity]++
    })
    return counts
  }, [rules])

  if (isLoading) return <div className="py-20"><LoadingSpinner message="Loading global rules…" /></div>
  if (error) return <div className="p-4 bg-red-50 text-red-700 rounded-lg">Error loading rules.</div>

  const toggleFilter = (filter, setFilter, val) => {
    setFilter(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])
  }

  return (
    <div className="space-y-6 font-sans">
      {/* HEADER ROW */}
      <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
        <span className="text-gray-900 font-bold">{rules.length} rules</span>
        <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">• {stats.TIG} TIG</span>
        <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">• {stats.WATCH} Watch</span>
        <span className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">• {stats.TIX} TIX</span>
        <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">• {stats.EVOLVE} Evolve</span>
        <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full">• {stats.hard_block} Hard Block</span>
        <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">• {stats.flag} Flag</span>
        <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">• {stats.info} Info</span>
      </div>

      {/* FILTER ROW */}
      <div className="space-y-3 bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest min-w-[80px]">Criteria set:</span>
          <div className="flex gap-2">
            {Object.keys(CRITERIA_MAP).map(s => (
              <button
                key={s}
                onClick={() => toggleFilter(criteriaFilter, setCriteriaFilter, s)}
                className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all ${
                  criteriaFilter.includes(s) ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest min-w-[80px]">Severity:</span>
          <div className="flex gap-2">
            {['hard_block', 'flag', 'info'].map(s => (
              <button
                key={s}
                onClick={() => toggleFilter(severityFilter, setSeverityFilter, s)}
                className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all ${
                  severityFilter.includes(s) ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                }`}
              >
                {SEVERITY_MAP[s].label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest min-w-[80px]">Category:</span>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map(c => (
              <button
                key={c}
                onClick={() => toggleFilter(categoryFilter, setCategoryFilter, c)}
                className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all ${
                  categoryFilter.includes(c) ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* SEARCH BAR */}
      <div className="relative group">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-gray-900 transition-colors" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by rule name or key…"
          className="w-full pl-11 pr-4 py-3 bg-white border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-gray-900/5 focus:border-gray-900 transition-all text-sm"
        />
      </div>

      {/* RULE TABLE */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        {/* Table Header */}
        <div className="grid grid-cols-[1fr_120px_140px_120px_90px_40px] gap-4 px-6 py-3 border-b border-gray-50 text-[10px] font-bold text-gray-400 uppercase tracking-widest">
          <div>Rule Name</div>
          <div>Criteria Set</div>
          <div>Severity</div>
          <div>Category</div>
          <div>Status</div>
          <div></div>
        </div>

        {/* Table Rows */}
        <div className="divide-y divide-gray-50">
          {filteredRules.map(rule => {
            const isExpanded = expandedRule === rule.rule_key
            const sev = SEVERITY_MAP[rule.severity] || SEVERITY_MAP.info
            const cri = CRITERIA_MAP[rule.criteria_set] || { color: 'bg-gray-100 text-gray-600' }
            const meta = RULE_META[rule.rule_key] || { description: "No description available." }
            const isActive = rule.is_active !== false

            return (
              <div key={rule.rule_key} className={`transition-colors ${!isActive ? 'opacity-50' : ''}`}>
                <div 
                  onClick={() => {
                    const nextState = isExpanded ? null : rule.rule_key;
                    setExpandedRule(nextState);
                    if (nextState && !ruleHistory[rule.rule_key]) {
                      fetchRuleHistory(rule.rule_key);
                    }
                  }}
                  className="grid grid-cols-[1fr_120px_140px_120px_90px_40px] gap-4 px-6 py-4 items-center cursor-pointer hover:bg-gray-50/50 transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-[3px] h-6 rounded-full ${sev.bar}`} />
                    <div className="flex flex-col">
                      <span className="text-sm font-semibold text-gray-900">{rule.name}</span>
                      <span className="text-[10px] font-bold text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded w-fit mt-1">{rule.rule_key}</span>
                    </div>
                  </div>
                  <div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${cri.color}`}>
                      {rule.criteria_set}
                    </span>
                  </div>
                  <div>
                    <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider ${sev.color}`}>
                      {sev.label}
                    </span>
                  </div>
                  <div className="text-xs text-gray-600 font-medium">
                    {rule.category || 'Other'}
                  </div>
                  {/* Status toggle */}
                  <div onClick={e => handleToggle(e, rule)}>
                    <button
                      disabled={togglingKey === rule.rule_key}
                      className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-bold border transition-all
                        ${togglingKey === rule.rule_key ? 'opacity-50 cursor-wait' : 'cursor-pointer'}
                        ${isActive
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                          : 'bg-gray-100 text-gray-500 border-gray-200 hover:bg-gray-200'
                        }`}
                    >
                      <Power className="w-3 h-3" />
                      {isActive ? 'Active' : 'Disabled'}
                    </button>
                  </div>
                  <div className="flex justify-end">
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400 group-hover:text-gray-600" />}
                  </div>
                </div>

                {/* Expanded Panel */}
                <div className={`overflow-hidden transition-all duration-300 bg-gray-50/50 ${isExpanded ? 'max-h-[500px] border-t border-gray-100' : 'max-h-0'}`}>
                  <div className="p-6 grid grid-cols-3 gap-8">
                    {/* Column 1: Rule Details */}
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Rule Details</h4>
                      <div className="space-y-3">
                        {rule.threshold !== null && (
                          <div>
                            <span className="text-xs text-gray-500">Threshold:</span>
                            <span className="ml-2 text-xs font-bold text-gray-900">
                              {typeof rule.threshold === 'number' && rule.rule_key.includes('WATCH-22.2') ? `${rule.threshold} months` : rule.threshold}
                            </span>
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">Status:</span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600'}`}>
                            {isActive ? 'Active' : 'Inactive'}
                          </span>
                        </div>
                        <button 
                          onClick={(e) => { e.stopPropagation(); setEditTarget(rule); }}
                          className="flex items-center gap-2 text-xs font-bold text-gray-900 hover:text-blue-600 transition-colors"
                        >
                          <Pencil className="w-3 h-3" /> Edit Configuration
                        </button>
                      </div>
                    </div>

                    {/* Column 2: What This Rule Checks */}
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">What This Rule Checks</h4>
                      <p className="text-sm text-gray-600 leading-relaxed">
                        {meta.description}
                      </p>
                    </div>

                    {/* Column 3: Recent Case Activity */}
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Recent Case Activity</h4>
                      <div className="space-y-2">
                        {(() => {
                          const hist = ruleHistory[rule.rule_key]
                          if (!hist || hist.loading) {
                            return (
                              <>
                                <div className="h-3 w-24 bg-gray-200 animate-pulse rounded" />
                                <div className="h-3 w-16 bg-gray-200 animate-pulse rounded mt-1" />
                              </>
                            )
                          }
                          if (hist.error) {
                            return <span className="text-xs text-red-500">Could not load history</span>
                          }
                          if (hist.data) {
                            const { last_triggered, times_triggered_30d, latest_case_id } = hist.data
                            
                            let lastTriggeredEl = null
                            if (!last_triggered) {
                              lastTriggeredEl = <span className="text-xs text-gray-400">— Never triggered</span>
                            } else {
                              const dt = new Date(last_triggered)
                              const diffMs = new Date() - dt
                              const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
                              
                              if (diffDays <= 7) {
                                lastTriggeredEl = <span className="text-xs text-green-600">{diffDays} days ago</span>
                              } else if (diffDays <= 30) {
                                lastTriggeredEl = <span className="text-xs text-amber-600">{diffDays} days ago</span>
                              } else {
                                const formatted = dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
                                lastTriggeredEl = <span className="text-xs text-gray-500">{formatted}</span>
                              }
                            }

                            let timesTriggeredEl = null
                            if (times_triggered_30d === 0) {
                              timesTriggeredEl = <span className="text-xs text-gray-400">0</span>
                            } else if (times_triggered_30d <= 5) {
                              timesTriggeredEl = <span className="text-xs text-amber-600">{times_triggered_30d}</span>
                            } else {
                              timesTriggeredEl = <span className="text-xs text-red-500">{times_triggered_30d}</span>
                            }

                            return (
                              <div className="space-y-2">
                                <div className="flex flex-col">
                                  <span className="text-xs text-gray-400">Last triggered:</span>
                                  {lastTriggeredEl}
                                </div>
                                <div className="flex flex-col">
                                  <span className="text-xs text-gray-400">Times triggered (30d):</span>
                                  {timesTriggeredEl}
                                </div>
                                <div className="pt-1">
                                  {latest_case_id ? (
                                    <button 
                                      className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                                      onClick={() => navigate('/assess', { state: { prefill: latest_case_id } })}
                                    >
                                      View in latest case →
                                    </button>
                                  ) : (
                                    <span className="text-xs text-gray-400">No cases on record</span>
                                  )}
                                </div>
                              </div>
                            )
                          }
                          return null
                        })()}
                      </div>
                    </div>
                  </div>
                  
                  {/* Expanded Footer Buttons */}
                  <div className="px-6 pb-6 flex gap-3">
                    <button 
                      onClick={(e) => { e.stopPropagation(); setEditTarget(rule); }}
                      className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs font-bold text-gray-600 hover:bg-white hover:border-gray-900 hover:text-gray-900 transition-all"
                    >
                      Edit Rule
                    </button>
                    <button 
                      onClick={(e) => { e.stopPropagation(); setDetailTarget(rule); }}
                      className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs font-bold text-gray-600 hover:bg-white hover:border-gray-900 hover:text-gray-900 transition-all"
                    >
                      View Rule
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Drawers */}
      {editTarget && (
        <RuleEditDrawer 
          rule={editTarget} 
          isOpen={!!editTarget} 
          onClose={() => setEditTarget(null)} 
        />
      )}
      {detailTarget && (
        <RuleDetailDrawer 
          rule={detailTarget} 
          isOpen={!!detailTarget} 
          onClose={() => setDetailTarget(null)} 
        />
      )}
    </div>
  )
}
