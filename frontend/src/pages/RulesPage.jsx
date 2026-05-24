import { useState } from 'react'
import CreditorsList from '../components/rules/CreditorsList'
import RulesList from '../components/rules/RulesList'
import CouncilsList from '../components/rules/CouncilsList'
import DividendsList from '../components/rules/DividendsList'
import GeneralCreditorsList from '../components/rules/GeneralCreditorsList'

const TABS = [
  { id: 'general',   label: 'General Creditors' },
  { id: 'creditors', label: 'Which Representative' },
  { id: 'rules',     label: 'Global Rules' },
  { id: 'councils',  label: 'Councils' },
  { id: 'dividends', label: 'Dividends' },
]

/**
 * Rules Management page with tabbed navigation
 */
export default function RulesPage() {
  const [activeTab, setActiveTab] = useState('general')

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Rule Management</h1>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200 mb-6">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="mt-4">
        {activeTab === 'general' && <GeneralCreditorsList />}

        {activeTab === 'creditors' && <CreditorsList />}

        {activeTab === 'rules' && <RulesList />}

        {activeTab === 'councils' && <CouncilsList />}

        {activeTab === 'dividends' && <DividendsList />}
      </div>
    </div>
  )
}
