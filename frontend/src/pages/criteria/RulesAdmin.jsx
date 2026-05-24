import { useEffect, useState, useMemo } from 'react'
import * as Switch from '@radix-ui/react-switch'
import * as Tabs from '@radix-ui/react-tabs'
import * as Accordion from '@radix-ui/react-accordion'
import * as Dialog from '@radix-ui/react-dialog'
import { getRulesByCriteriaSet, updateRule, createRule } from '../../services/criteriaService.js'
import ErrorCard from '../../components/shared/ErrorCard.jsx'
import Spinner from '../../components/shared/Spinner.jsx'
import { ChevronDownIcon, MagnifyingGlassIcon, PlusIcon, Cross2Icon } from '@radix-ui/react-icons'

const CRITERIA_SETS = ['TIG', 'WATCH', 'TIX', 'EVOLVE']

export default function RulesAdmin() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeSet, setActiveSet] = useState('TIG')
  
  // Search and Filter State
  const [searchQuery, setSearchQuery] = useState('')
  const [severityFilter, setSeverityFilter] = useState('all')

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [newRule, setNewRule] = useState({
    rule_key: '',
    rule_name: '',
    criteria_set: 'TIG',
    category: '',
    severity: 'flag',
    is_active: true,
    threshold_value: '',
    description: '',
    rejection_message: '',
    flag_message: ''
  })

  const fetchRules = async (criteriaSet) => {
    setLoading(true)
    setError(null)
    try {
      const response = await getRulesByCriteriaSet(criteriaSet)
      // If the API doesn't filter, we filter here just in case:
      const filteredResponse = response.filter(r => r.criteria_set === criteriaSet)
      setRules(filteredResponse.length > 0 ? filteredResponse : response)
    } catch {
      setError('Unable to load rule configuration. Please try again later.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRules(activeSet)
  }, [activeSet])

  const handleToggle = async (ruleKey, isActive) => {
    const updatedRules = rules.map((rule) => (rule.rule_key === ruleKey ? { ...rule, is_active: isActive } : rule))
    setRules(updatedRules)
    try {
      await updateRule(ruleKey, { is_active: isActive })
    } catch {
      setError('Unable to update rule status. Please try again.')
      fetchRules(activeSet)
    }
  }

  const handleThreshold = async (ruleKey, threshold_value) => {
    const updatedRules = rules.map((rule) => (rule.rule_key === ruleKey ? { ...rule, threshold_value } : rule))
    setRules(updatedRules)
    try {
      await updateRule(ruleKey, { threshold_value })
    } catch {
      setError('Unable to update rule threshold. Please try again.')
      fetchRules(activeSet)
    }
  }

  const handleCreateRule = async (e) => {
    e.preventDefault()
    try {
      const payload = {
        ...newRule,
        threshold_value: newRule.threshold_value ? Number(newRule.threshold_value) : null
      }
      await createRule(payload)
      setIsModalOpen(false)
      fetchRules(activeSet)
      setNewRule({
        rule_key: '', rule_name: '', criteria_set: activeSet, category: '', severity: 'flag',
        is_active: true, threshold_value: '', description: '', rejection_message: '', flag_message: ''
      })
    } catch (err) {
      setError('Unable to create new rule. Ensure rule key is unique.')
    }
  }

  // Filter rules by search query and severity
  const filteredRules = useMemo(() => {
    return rules.filter(rule => {
      const matchesSearch = rule.rule_name?.toLowerCase().includes(searchQuery.toLowerCase()) || 
                            rule.rule_key?.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesSeverity = severityFilter === 'all' || rule.severity === severityFilter
      return matchesSearch && matchesSeverity
    })
  }, [rules, searchQuery, severityFilter])

  // Group rules by category
  const rulesByCategory = useMemo(() => {
    const grouped = {}
    filteredRules.forEach(rule => {
      const cat = rule.category || 'Uncategorized'
      if (!grouped[cat]) grouped[cat] = []
      grouped[cat].push(rule)
    })
    return grouped
  }, [filteredRules])

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'hard_block': return 'bg-red-100 text-red-800 border-red-200'
      case 'flag': return 'bg-amber-100 text-amber-800 border-amber-200'
      case 'info': return 'bg-blue-100 text-blue-800 border-blue-200'
      default: return 'bg-slate-100 text-slate-800 border-slate-200'
    }
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Header Section */}
      <div className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-900 to-slate-800 p-8 shadow-lg text-white flex justify-between items-center">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-400">Rules admin</p>
          <h2 className="mt-3 text-3xl font-semibold">Criteria Rules Management</h2>
          <p className="mt-2 text-sm text-slate-300">Configure global engine rules, thresholds, and metadata.</p>
        </div>
        
        {/* Register New Rule Button */}
        <Dialog.Root open={isModalOpen} onOpenChange={setIsModalOpen}>
          <Dialog.Trigger asChild>
            <button className="flex items-center gap-2 rounded-full bg-indigo-500 hover:bg-indigo-600 px-6 py-3 text-sm font-semibold text-white transition shadow-md">
              <PlusIcon className="w-5 h-5" />
              Register New Rule
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40" />
            <Dialog.Content className="fixed top-1/2 left-1/2 max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-3xl bg-white p-8 shadow-2xl z-50 overflow-y-auto">
              <div className="flex justify-between items-center mb-6">
                <Dialog.Title className="text-2xl font-semibold text-slate-900">Register New Rule</Dialog.Title>
                <Dialog.Close asChild>
                  <button className="text-slate-400 hover:text-slate-600"><Cross2Icon className="w-6 h-6" /></button>
                </Dialog.Close>
              </div>
              <form onSubmit={handleCreateRule} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Rule Key</label>
                    <input required value={newRule.rule_key} onChange={e => setNewRule({...newRule, rule_key: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" placeholder="e.g. TIG-99" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Rule Name</label>
                    <input required value={newRule.rule_name} onChange={e => setNewRule({...newRule, rule_name: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" placeholder="Short display name" />
                  </div>
                </div>
                
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Criteria Set</label>
                    <select value={newRule.criteria_set} onChange={e => setNewRule({...newRule, criteria_set: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm bg-white">
                      {CRITERIA_SETS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Severity</label>
                    <select value={newRule.severity} onChange={e => setNewRule({...newRule, severity: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm bg-white">
                      <option value="hard_block">Hard Block</option>
                      <option value="flag">Flag</option>
                      <option value="info">Info</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Threshold Value</label>
                    <input type="number" step="0.01" value={newRule.threshold_value} onChange={e => setNewRule({...newRule, threshold_value: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm" placeholder="Optional" />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1">Category</label>
                  <input value={newRule.category} onChange={e => setNewRule({...newRule, category: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm" placeholder="e.g. Income, HMRC, etc." />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1">Description</label>
                  <textarea rows="3" required value={newRule.description} onChange={e => setNewRule({...newRule, description: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm" placeholder="Full rule explanation" />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Rejection Message</label>
                    <textarea rows="2" value={newRule.rejection_message} onChange={e => setNewRule({...newRule, rejection_message: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm" placeholder="Displayed to user on rejection" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1">Flag Message</label>
                    <textarea rows="2" value={newRule.flag_message} onChange={e => setNewRule({...newRule, flag_message: e.target.value})} className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm" placeholder="Displayed to user as warning" />
                  </div>
                </div>

                <div className="pt-4 flex justify-end gap-3 border-t border-slate-100">
                  <Dialog.Close asChild>
                    <button type="button" className="rounded-full px-5 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100 transition">Cancel</button>
                  </Dialog.Close>
                  <button type="submit" className="rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition">Save Rule</button>
                </div>
              </form>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>

      {error && <ErrorCard message={error} />}

      {/* Main Content Area */}
      <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        
        {/* Navigation Tabs */}
        <Tabs.Root value={activeSet} onValueChange={setActiveSet} className="w-full">
          <Tabs.List className="flex border-b border-slate-200 bg-slate-50 px-6 pt-4">
            {CRITERIA_SETS.map((set) => (
              <Tabs.Trigger
                key={set}
                value={set}
                className={`pb-4 px-6 text-sm font-bold uppercase tracking-wider transition-all border-b-2 
                  ${activeSet === set ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'}`}
              >
                {set} Rules
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <Tabs.Content value={activeSet} className="p-8">
            
            {/* Search and Filters */}
            <div className="flex gap-4 mb-8">
              <div className="relative flex-1">
                <MagnifyingGlassIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input 
                  type="text" 
                  placeholder="Search rules by ID or name..." 
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 py-3 pl-12 pr-4 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-slate-50 hover:bg-white transition"
                />
              </div>
              <select 
                value={severityFilter} 
                onChange={e => setSeverityFilter(e.target.value)}
                className="rounded-2xl border border-slate-200 px-6 py-3 text-sm font-medium bg-slate-50 hover:bg-white transition focus:border-indigo-500 outline-none"
              >
                <option value="all">All Severities</option>
                <option value="hard_block">Hard Block</option>
                <option value="flag">Flag</option>
                <option value="info">Info</option>
              </select>
            </div>

            {loading ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                <Spinner />
                <p className="mt-4 font-medium">Loading {activeSet} rules...</p>
              </div>
            ) : filteredRules.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 py-20 text-center text-slate-500">
                <p className="font-medium text-lg">No matching rules found in {activeSet}.</p>
                <p className="text-sm mt-1">Try adjusting your search or filters.</p>
              </div>
            ) : (
              <Accordion.Root type="multiple" className="space-y-6">
                {Object.entries(rulesByCategory).map(([category, catRules]) => (
                  <Accordion.Item key={category} value={category} className="rounded-2xl border border-slate-200 overflow-hidden bg-white shadow-sm">
                    <Accordion.Header>
                      <Accordion.Trigger className="flex w-full items-center justify-between bg-slate-50 px-6 py-4 transition hover:bg-slate-100 group">
                        <div className="flex items-center gap-3">
                          <h3 className="text-lg font-semibold text-slate-900 capitalize">{category.replace(/_/g, ' ')}</h3>
                          <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-bold text-slate-600">{catRules.length}</span>
                        </div>
                        <ChevronDownIcon className="w-5 h-5 text-slate-400 transition-transform duration-300 group-data-[state=open]:rotate-180" />
                      </Accordion.Trigger>
                    </Accordion.Header>
                    
                    <Accordion.Content className="overflow-hidden data-[state=closed]:animate-slideUp data-[state=open]:animate-slideDown">
                      <div className="divide-y divide-slate-100 p-6 space-y-6">
                        {catRules.map((rule) => (
                          <div key={rule.rule_key} className="pt-6 first:pt-0">
                            
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between mb-4">
                              <div>
                                <div className="flex items-center gap-3 mb-1">
                                  <span className="font-mono text-xs font-bold px-2 py-1 bg-slate-100 rounded text-slate-600 border border-slate-200">
                                    {rule.rule_key}
                                  </span>
                                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border uppercase tracking-wider ${getSeverityColor(rule.severity)}`}>
                                    {rule.severity.replace('_', ' ')}
                                  </span>
                                </div>
                                <h4 className="text-xl font-bold text-slate-900">{rule.rule_name || rule.rule_key}</h4>
                                <p className="mt-2 text-sm text-slate-600 leading-relaxed max-w-3xl">{rule.description || 'No description provided.'}</p>
                              </div>

                              <div className="flex items-center gap-4 bg-slate-50 p-3 rounded-xl border border-slate-100 shrink-0">
                                <label className="flex items-center gap-3 text-sm font-semibold text-slate-700 cursor-pointer">
                                  <Switch.Root
                                    checked={rule.is_active}
                                    onCheckedChange={(checked) => handleToggle(rule.rule_key, checked)}
                                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${rule.is_active ? 'bg-indigo-600' : 'bg-slate-300'}`}
                                  >
                                    <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${rule.is_active ? 'translate-x-5' : 'translate-x-0'}`} />
                                  </Switch.Root>
                                  {rule.is_active ? 'Active' : 'Inactive'}
                                </label>
                              </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 bg-slate-50 p-4 rounded-xl border border-slate-100">
                              <div>
                                <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Threshold / Limit</label>
                                <input
                                  type="number"
                                  value={rule.threshold_value ?? ''}
                                  onChange={(event) => handleThreshold(rule.rule_key, Number(event.target.value || 0))}
                                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                                  placeholder="No threshold"
                                />
                              </div>
                              
                              {rule.rejection_message && (
                                <div className="lg:col-span-2">
                                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Rejection Message</label>
                                  <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-sm text-red-800">
                                    {rule.rejection_message}
                                  </div>
                                </div>
                              )}

                              {rule.flag_message && !rule.rejection_message && (
                                <div className="lg:col-span-2">
                                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Flag / Warning Message</label>
                                  <div className="rounded-lg bg-amber-50 border border-amber-100 p-3 text-sm text-amber-800">
                                    {rule.flag_message}
                                  </div>
                                </div>
                              )}

                              {rule.implementation_notes && (
                                <div className="lg:col-span-3">
                                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Implementation Notes</label>
                                  <div className="rounded-lg bg-slate-100 border border-slate-200 p-3 text-sm text-slate-700 italic">
                                    {rule.implementation_notes}
                                  </div>
                                </div>
                              )}

                              {rule.is_creditor_specific && (
                                <div className="lg:col-span-3 flex flex-wrap items-center gap-2 mt-2">
                                  <span className="px-2 py-1 bg-indigo-100 text-indigo-800 text-xs font-bold uppercase tracking-wider rounded border border-indigo-200">Creditor Specific Rule</span>
                                  {rule.applies_to_creditors && rule.applies_to_creditors.map(c => (
                                    <span key={c} className="px-2 py-1 bg-white border border-slate-300 text-slate-700 text-xs font-semibold rounded shadow-sm">{c}</span>
                                  ))}
                                </div>
                              )}
                            </div>

                          </div>
                        ))}
                      </div>
                    </Accordion.Content>
                  </Accordion.Item>
                ))}
              </Accordion.Root>
            )}
          </Tabs.Content>
        </Tabs.Root>

      </div>
    </div>
  )
}
