import React from 'react'
import { useRuleDetail } from '../../hooks/useRules'
import { ExternalLink, Edit2 } from 'lucide-react'
import LoadingSpinner from '../shared/LoadingSpinner'

const CATEGORY_CONFIG = {
  income: { label: 'Income', bg: 'bg-green-100', text: 'text-green-800' },
  bank_statements: { label: 'Bank Statements', bg: 'bg-blue-100', text: 'text-blue-800' },
  proof_of_debts: { label: 'Proof of Debts', bg: 'bg-indigo-100', text: 'text-indigo-800' },
  creditor_specific: { label: 'Creditor Specific', bg: 'bg-purple-100', text: 'text-purple-800' },
  hmrc: { label: 'HMRC', bg: 'bg-amber-100', text: 'text-amber-800' },
  vehicle: { label: 'Vehicle', bg: 'bg-orange-100', text: 'text-orange-800' },
  flags: { label: 'Flags', bg: 'bg-red-100', text: 'text-red-800' },
  other: { label: 'Other', bg: 'bg-gray-100', text: 'text-gray-800' },
}

const getCategoryConfig = (cat) => CATEGORY_CONFIG[cat] ?? { label: cat, bg: 'bg-gray-100', text: 'text-gray-800' }

export default function RuleDetailDrawer({ ruleKey, isOpen, onClose, onEdit, isAdmin }) {
  const { data: rule, isLoading, error } = useRuleDetail(ruleKey, isOpen)

  if (!isOpen || !ruleKey) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 z-40 transition-opacity" onClick={onClose} />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-2xl bg-white shadow-xl z-50 
                    flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">{rule?.name || 'Loading...'}</h2>
            <p className="text-[10px] font-mono text-gray-400 mt-0.5">{rule?.rule_key}</p>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button 
                onClick={() => {
                  onEdit(rule)
                  onClose()
                }}
                className="p-2 rounded-md text-blue-600 hover:text-blue-800 hover:bg-blue-50 transition-colors"
                title="Edit rule"
              >
                <Edit2 size={16} />
              </button>
            )}
            <button 
              onClick={onClose}
              className="p-2 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              aria-label="Close drawer"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {isLoading ? (
            <div className="py-20 flex justify-center">
              <LoadingSpinner message="Loading rule details…" />
            </div>
          ) : error ? (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              Could not load rule details. Please try again.
            </div>
          ) : rule ? (
            <div className="space-y-6">
              {/* Metadata */}
              <div className="grid grid-cols-2 gap-4 pb-4 border-b">
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Criteria Set</label>
                  <div className="text-sm font-medium text-gray-700">{rule.criteria_set}</div>
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Severity</label>
                  <div className="text-sm font-medium text-gray-700 capitalize">{rule.severity.replace('_', ' ')}</div>
                </div>
                {rule.category && (
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Category</label>
                    <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded border ${getCategoryConfig(rule.category).bg} ${getCategoryConfig(rule.category).text}`}>
                      {getCategoryConfig(rule.category).label}
                    </span>
                  </div>
                )}
                {rule.threshold_value != null && (
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Threshold</label>
                    <div className="text-sm font-mono font-medium text-gray-700">{rule.threshold_value}</div>
                  </div>
                )}
              </div>

              {/* Description */}
              {rule.description && (
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Description</label>
                  <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded border border-gray-200">
                    {rule.description}
                  </p>
                </div>
              )}

              {/* Example Case */}
              {rule.example_case && (
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Example Case</label>
                  <p className="text-sm text-gray-700 leading-relaxed bg-blue-50 p-3 rounded border border-blue-200">
                    {rule.example_case}
                  </p>
                </div>
              )}

              {/* Implementation Notes */}
              {rule.implementation_notes && (
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Implementation Notes</label>
                  <p className="text-sm text-gray-700 leading-relaxed bg-amber-50 p-3 rounded border border-amber-200">
                    {rule.implementation_notes}
                  </p>
                </div>
              )}

              {/* Messages */}
              <div className="grid grid-cols-1 gap-4">
                {rule.rejection_message && (
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Rejection Message</label>
                    <p className="text-sm text-red-700 leading-relaxed bg-red-50 p-3 rounded border border-red-200">
                      {rule.rejection_message}
                    </p>
                  </div>
                )}
                {rule.flag_message && (
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Flag Message</label>
                    <p className="text-sm text-amber-700 leading-relaxed bg-amber-50 p-3 rounded border border-amber-200">
                      {rule.flag_message}
                    </p>
                  </div>
                )}
              </div>

              {/* Creditor Information */}
              {rule.is_creditor_specific && (
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                  <div className="text-xs font-semibold text-purple-900 mb-2">Creditor Specific Rule</div>
                  {rule.applies_to_creditors && rule.applies_to_creditors.length > 0 && (
                    <div>
                      <label className="block text-[10px] font-semibold text-purple-700 uppercase tracking-wider mb-1">Applies To:</label>
                      <div className="flex flex-wrap gap-2">
                        {rule.applies_to_creditors.map((creditor, idx) => (
                          <span key={idx} className="inline-block px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded border border-purple-300">
                            {creditor}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Related Rules */}
              {rule.related_rules && rule.related_rules.length > 0 && (
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Related Rules</label>
                  <div className="flex flex-wrap gap-2">
                    {rule.related_rules.map((relatedKey, idx) => (
                      <button
                        key={idx}
                        className="px-2.5 py-1.5 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded hover:bg-blue-100 transition-colors inline-flex items-center gap-1"
                      >
                        {relatedKey}
                        <ExternalLink size={12} className="opacity-50" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Dependencies */}
              {rule.depends_on_rules && rule.depends_on_rules.length > 0 && (
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Dependencies</label>
                  <div className="space-y-1">
                    {rule.depends_on_rules.map((depKey, idx) => (
                      <div key={idx} className="text-sm text-gray-600 flex items-center gap-2 px-2 py-1 bg-gray-50 rounded border border-gray-200">
                        <span className="text-gray-400">→</span>
                        <span className="font-mono text-xs">{depKey}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* References */}
              {rule.references && rule.references.length > 0 && (
                <div>
                  <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">References</label>
                  <ul className="space-y-1">
                    {rule.references.map((ref, idx) => (
                      <li key={idx} className="text-xs text-gray-600 flex items-start gap-2">
                        <span className="text-gray-400 mt-1">•</span>
                        <span className="text-gray-600">{ref}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Review Info */}
              <div className="border-t pt-4 text-xs text-gray-500 space-y-1">
                {rule.last_reviewed && (
                  <div>
                    <span className="font-semibold">Last Reviewed:</span> {new Date(rule.last_reviewed).toLocaleDateString()}
                  </div>
                )}
                {rule.review_notes && (
                  <div>
                    <span className="font-semibold">Review Notes:</span> {rule.review_notes}
                  </div>
                )}
                {rule.last_updated && (
                  <div>
                    <span className="font-semibold">Last Updated:</span> {new Date(rule.last_updated).toLocaleDateString()}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </>
  )
}
