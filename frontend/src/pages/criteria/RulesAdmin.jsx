import { useEffect, useState } from 'react'
import * as Switch from '@radix-ui/react-switch'
import * as Tabs from '@radix-ui/react-tabs'
import { getRules, updateRule } from '../../services/criteriaService.js'
import ErrorCard from '../../components/shared/ErrorCard.jsx'
import Spinner from '../../components/shared/Spinner.jsx'

const tabRoutes = [
  { value: 'active', label: 'Active rules' },
  { value: 'inactive', label: 'Inactive rules' },
]

export default function RulesAdmin() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('active')

  const fetchRules = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getRules()
      setRules(response)
    } catch {
      setError('Unable to load rule configuration. Please try again later.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRules()
  }, [])

  const handleToggle = async (ruleKey, isActive) => {
    const updatedRules = rules.map((rule) => (rule.key === ruleKey ? { ...rule, is_active: isActive } : rule))
    setRules(updatedRules)
    try {
      await updateRule(ruleKey, { is_active: isActive })
    } catch {
      setError('Unable to update rule status. Please try again.')
      fetchRules()
    }
  }

  const handleThreshold = async (ruleKey, threshold_value) => {
    const updatedRules = rules.map((rule) => (rule.key === ruleKey ? { ...rule, threshold_value } : rule))
    setRules(updatedRules)
    try {
      await updateRule(ruleKey, { threshold_value })
    } catch {
      setError('Unable to update rule threshold. Please try again.')
      fetchRules()
    }
  }

  const visibleRules = rules.filter((rule) => (activeTab === 'active' ? rule.is_active : !rule.is_active))

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-200 bg-[#f8fafc] p-8 shadow-sm">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-500">Rules admin</p>
          <h2 className="mt-3 text-3xl font-semibold text-slate-900">Review and update engine rules</h2>
          <p className="mt-2 text-sm text-slate-600">Toggle rule activation, adjust thresholds, and verify the governance configuration.</p>
        </div>
      </div>

      {error && <ErrorCard message={error} />}

      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <Tabs.Root value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <Tabs.List className="flex flex-wrap gap-3">
            {tabRoutes.map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className={`rounded-3xl px-5 py-3 text-sm font-semibold transition ${activeTab === tab.value ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <Tabs.Content value={activeTab} className="space-y-6">
            {loading ? (
              <div className="rounded-3xl border border-dashed border-slate-200 p-12 text-center text-slate-500">
                <Spinner />
                <p className="mt-4">Loading rule set...</p>
              </div>
            ) : visibleRules.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-slate-200 p-12 text-center text-slate-500">No matching rules found.</div>
            ) : (
              <div className="space-y-4">
                {visibleRules.map((rule) => {
                  const booleanRule = rule.threshold_value === 0 && rule.severity !== 'hard_block'
                  return (
                    <div key={rule.key} className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <h3 className="text-lg font-semibold text-slate-900">{rule.text || rule.key}</h3>
                          <p className="mt-2 text-sm text-slate-600">Severity: {rule.severity}</p>
                        </div>
                        <div className="flex items-center gap-4">
                          <label className="flex items-center gap-3 text-sm font-semibold text-slate-700">
                            <Switch.Root
                              checked={rule.is_active}
                              onCheckedChange={(checked) => handleToggle(rule.key, checked)}
                              className="relative inline-flex h-[28px] w-[52px] shrink-0 cursor-pointer rounded-full border border-slate-300 bg-slate-200 transition focus:outline-none focus:ring-2 focus:ring-slate-400"
                            >
                              <span className={`block h-[24px] w-[24px] translate-x-1 rounded-full bg-white shadow-sm transition ${rule.is_active ? 'translate-x-7' : ''}`} />
                            </Switch.Root>
                            Active
                          </label>
                        </div>
                      </div>

                      <div className="mt-6 grid gap-4 sm:grid-cols-2">
                        <div>
                          <label className="block text-sm font-semibold text-slate-700">Threshold</label>
                          {booleanRule ? (
                            <div className="mt-3 rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">—</div>
                          ) : (
                            <input
                              type="number"
                              value={rule.threshold_value ?? ''}
                              onChange={(event) => handleThreshold(rule.key, Number(event.target.value || 0))}
                              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
                            />
                          )}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-slate-700">Last updated</p>
                          <p className="mt-3 text-sm text-slate-600">{rule.last_updated || '—'}</p>
                          <p className="mt-2 text-sm text-slate-500">By {rule.updated_by || '—'}</p>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Tabs.Content>
        </Tabs.Root>
      </div>
    </div>
  )
}
