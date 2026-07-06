import { useState, useMemo } from 'react'
import { useAuth } from '../context/AuthContext'
import { useFeatureAccess } from '../hooks/useFeatureAccess'
import { useDepartment } from '../hooks/useDepartment'
import CreditorsList from '../components/rules/CreditorsList'
import RulesList from '../components/rules/RulesList'
import CouncilsList from '../components/rules/CouncilsList'
import CountyCouncilsList from '../components/rules/CountyCouncilsList'
import DividendsList from '../components/rules/DividendsList'
import GeneralCreditorsList from '../components/rules/GeneralCreditorsList'

const ALL_TABS = [
  { id: 'general',        label: 'General Creditors',   featureKey: 'general_creditors' },
  { id: 'creditors',      label: 'Which Representative', featureKey: 'representative_creditors' },
  { id: 'rules',          label: 'Global Rules',         featureKey: 'global_rules' },
  { id: 'councils',       label: 'Councils',             featureKey: 'councils' },
  { id: 'county_councils',label: 'County Councils',      featureKey: 'councils' },
  { id: 'dividends',      label: 'Dividends',            featureKey: 'dividends' },
]

export default function RulesPage() {
  const { isAdmin } = useAuth()
  const { hasFeature } = useFeatureAccess()
  const { data: myDepartment } = useDepartment()

  const visibleTabs = useMemo(
    () => ALL_TABS.filter(tab => isAdmin || hasFeature(tab.featureKey)),
    [isAdmin, hasFeature]
  )

  const [activeTab, setActiveTab] = useState(() => visibleTabs[0]?.id ?? null)

  // Keep activeTab valid if visible tabs change (e.g. after features load)
  const resolvedTab = visibleTabs.find(t => t.id === activeTab)
    ? activeTab
    : (visibleTabs[0]?.id ?? null)

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Rule Management</h1>
        {!isAdmin && myDepartment && (
          <div className="flex flex-col items-end gap-0.5">
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700 border border-blue-200">
              Viewing as: {myDepartment.name}
            </span>
            {myDepartment.description && (
              <span className="text-[11px] text-gray-400 max-w-xs text-right truncate" title={myDepartment.description}>
                {myDepartment.description}
              </span>
            )}
          </div>
        )}
      </div>

      {visibleTabs.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
          No rule management sections are available for your department.
        </div>
      ) : (
        <>
          {/* Tab bar */}
          <div className="flex gap-1 border-b border-gray-200 mb-6">
            {visibleTabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  resolvedTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content — only the active tab mounts, so no API call for hidden tabs */}
          <div className="mt-4">
            {resolvedTab === 'general'   && <GeneralCreditorsList />}
            {resolvedTab === 'creditors' && <CreditorsList />}
            {resolvedTab === 'rules'     && <RulesList />}
            {resolvedTab === 'councils'  && <CouncilsList />}
            {resolvedTab === 'county_councils' && <CountyCouncilsList />}
            {resolvedTab === 'dividends' && <DividendsList />}
          </div>
        </>
      )}
    </div>
  )
}
