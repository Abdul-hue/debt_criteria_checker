import React, { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { ruleSchema } from '../../schemas/ruleSchema'
import { usePatchRule } from '../../hooks/useRules'
import { useToast } from '../../hooks/useToast'
import Spinner from '../shared/Spinner'
import { X } from 'lucide-react'

const CATEGORY_OPTIONS = [
  { value: 'income', label: 'Income' },
  { value: 'bank_statements', label: 'Bank Statements' },
  { value: 'proof_of_debts', label: 'Proof of Debts' },
  { value: 'creditor_specific', label: 'Creditor Specific' },
  { value: 'hmrc', label: 'HMRC' },
  { value: 'vehicle', label: 'Vehicle' },
  { value: 'flags', label: 'Flags' },
  { value: 'other', label: 'Other' },
]

/**
 * Slide-in panel for viewing and editing a global rule
 */
export default function RuleEditDrawer({ rule, isOpen, onClose, readOnly }) {
  const toast = useToast()
  const patchRule = usePatchRule()
  const [creditorInput, setCreditorInput] = useState('')
  const [relatedRulesInput, setRelatedRulesInput] = useState('')
  const [dependsOnInput, setDependsOnInput] = useState('')
  const [referencesInput, setReferencesInput] = useState('')

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
    watch,
    setValue,
  } = useForm({
    resolver: zodResolver(ruleSchema),
  })

  const appliesTo = watch('applies_to_creditors') || []
  const relatedRules = watch('related_rules') || []
  const dependsOn = watch('depends_on_rules') || []
  const references = watch('references') || []
  const isCreditorSpecific = watch('is_creditor_specific') || false

  // Reset form when rule changes or drawer opens
  useEffect(() => {
    if (rule && isOpen) {
      reset({
        is_active: rule.is_active,
        severity: rule.severity,
        threshold_value: rule.threshold_value,
        description: rule.description || '',
        implementation_notes: rule.implementation_notes || '',
        category: rule.category || '',
        example_case: rule.example_case || '',
        rejection_message: rule.rejection_message || '',
        flag_message: rule.flag_message || '',
        is_creditor_specific: rule.is_creditor_specific || false,
        applies_to_creditors: rule.applies_to_creditors || [],
        references: rule.references || [],
        execution_order: rule.execution_order || null,
        depends_on_rules: rule.depends_on_rules || [],
        related_rules: rule.related_rules || [],
        last_reviewed: rule.last_reviewed || '',
        review_notes: rule.review_notes || '',
      })
    }
  }, [rule, isOpen, reset])

  const addCreditor = () => {
    if (creditorInput.trim()) {
      const newList = [...appliesTo, creditorInput.trim()]
      setValue('applies_to_creditors', newList)
      setCreditorInput('')
    }
  }

  const removeCreditor = (idx) => {
    setValue('applies_to_creditors', appliesTo.filter((_, i) => i !== idx))
  }

  const addRelatedRule = () => {
    if (relatedRulesInput.trim()) {
      const newList = [...relatedRules, relatedRulesInput.trim()]
      setValue('related_rules', newList)
      setRelatedRulesInput('')
    }
  }

  const removeRelatedRule = (idx) => {
    setValue('related_rules', relatedRules.filter((_, i) => i !== idx))
  }

  const addDependsOn = () => {
    if (dependsOnInput.trim()) {
      const newList = [...dependsOn, dependsOnInput.trim()]
      setValue('depends_on_rules', newList)
      setDependsOnInput('')
    }
  }

  const removeDependsOn = (idx) => {
    setValue('depends_on_rules', dependsOn.filter((_, i) => i !== idx))
  }

  const addReference = () => {
    if (referencesInput.trim()) {
      const newList = [...references, referencesInput.trim()]
      setValue('references', newList)
      setReferencesInput('')
    }
  }

  const removeReference = (idx) => {
    setValue('references', references.filter((_, i) => i !== idx))
  }

  if (!isOpen || !rule) return null

  const onSubmit = (data) => {
    if (readOnly) return

    patchRule.mutate(
      { ruleKey: rule.rule_key, ...data },
      {
        onSuccess: () => {
          toast.success('Success', 'Rule updated successfully')
          onClose()
        },
        onError: (err) => {
          toast.error('Error', err?.response?.data?.detail ?? 'Failed to update rule')
        },
      }
    )
  }

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
            <h2 className="text-lg font-semibold text-gray-800">Edit Rule</h2>
            <p className="text-[10px] font-mono text-gray-400 mt-0.5">{rule.rule_key} / {rule.name}</p>
          </div>
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

        {/* Body */}
        <form id="rule-form" onSubmit={handleSubmit(onSubmit)} className="flex-1 overflow-y-auto px-6 py-5">
          {readOnly && (
            <div className="mb-6 p-2.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700">
              View only — admin access required to edit rule settings.
            </div>
          )}

          <div className="space-y-6">
            {/* ─ Core Configuration ─ */}
            <fieldset disabled={readOnly} className="space-y-3 border-b pb-4">
              <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Core Configuration</h3>
              
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-gray-700">Active Status</label>
                <input 
                  type="checkbox" 
                  {...register('is_active')} 
                  className="w-4 h-4 accent-blue-600 cursor-pointer disabled:cursor-not-allowed" 
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Severity Level</label>
                <select 
                  {...register('severity')} 
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
                >
                  <option value="hard_block">Hard Block</option>
                  <option value="flag">Flag</option>
                  <option value="info">Info</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Category</label>
                <select 
                  {...register('category')} 
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50 disabled:text-gray-500"
                >
                  <option value="">Select category...</option>
                  {CATEGORY_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Threshold Value</label>
                <input 
                  type="number" 
                  step="any"
                  {...register('threshold_value', { 
                    setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseFloat(v) 
                  })} 
                  placeholder="Enter threshold (if applicable)..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Execution Order</label>
                <input 
                  type="number" 
                  {...register('execution_order', { 
                    setValueAs: v => (v === '' || v === null || isNaN(v)) ? null : parseInt(v) 
                  })} 
                  placeholder="Order of evaluation (if applicable)..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>
            </fieldset>

            {/* ─ Documentation ─ */}
            <fieldset disabled={readOnly} className="space-y-3 border-b pb-4">
              <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Documentation</h3>
              
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Description</label>
                <textarea 
                  rows={3}
                  {...register('description')} 
                  placeholder="What does this rule do? When should it apply?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Example Case</label>
                <textarea 
                  rows={2}
                  {...register('example_case')} 
                  placeholder="Real-world scenario where this rule applies..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Implementation Notes</label>
                <textarea 
                  rows={2}
                  {...register('implementation_notes')} 
                  placeholder="Technical details about how this rule is implemented..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Rejection Message</label>
                <textarea 
                  rows={2}
                  {...register('rejection_message')} 
                  placeholder="User-facing message when rule causes rejection..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Flag Message</label>
                <textarea 
                  rows={2}
                  {...register('flag_message')} 
                  placeholder="User-facing message when rule triggers a flag..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>
            </fieldset>

            {/* ─ Creditor Information ─ */}
            <fieldset disabled={readOnly} className="space-y-3 border-b pb-4">
              <div className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  {...register('is_creditor_specific')} 
                  className="w-3.5 h-3.5 accent-purple-600 cursor-pointer disabled:cursor-not-allowed" 
                />
                <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Creditor Specific Rule</h3>
              </div>
              
              {isCreditorSpecific && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-2">Applies To Creditors</label>
                  <div className="flex gap-2 mb-2">
                    <input 
                      type="text" 
                      value={creditorInput}
                      onChange={(e) => setCreditorInput(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && (addCreditor(), e.preventDefault())}
                      placeholder="Add creditor name..."
                      className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-400"
                    />
                    <button 
                      type="button"
                      onClick={addCreditor}
                      className="px-3 py-2 text-sm font-medium bg-purple-100 text-purple-700 rounded-md hover:bg-purple-200"
                    >
                      Add
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {appliesTo.map((creditor, idx) => (
                      <span key={idx} className="inline-flex items-center gap-2 px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded border border-purple-300">
                        {creditor}
                        <button
                          type="button"
                          onClick={() => removeCreditor(idx)}
                          className="text-purple-600 hover:text-purple-800"
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </fieldset>

            {/* ─ References & Links ─ */}
            <fieldset disabled={readOnly} className="space-y-3 border-b pb-4">
              <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">References & Links</h3>
              
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-2">Related Rules</label>
                <div className="flex gap-2 mb-2">
                  <input 
                    type="text" 
                    value={relatedRulesInput}
                    onChange={(e) => setRelatedRulesInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && (addRelatedRule(), e.preventDefault())}
                    placeholder="e.g., TIG-01, TIG-02..."
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                  <button 
                    type="button"
                    onClick={addRelatedRule}
                    className="px-3 py-2 text-sm font-medium bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {relatedRules.map((ruleKey, idx) => (
                    <span key={idx} className="inline-flex items-center gap-2 px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded border border-blue-300 font-mono">
                      {ruleKey}
                      <button
                        type="button"
                        onClick={() => removeRelatedRule(idx)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-2">Rule Dependencies</label>
                <div className="flex gap-2 mb-2">
                  <input 
                    type="text" 
                    value={dependsOnInput}
                    onChange={(e) => setDependsOnInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && (addDependsOn(), e.preventDefault())}
                    placeholder="e.g., TIG-01, TIG-02..."
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                  <button 
                    type="button"
                    onClick={addDependsOn}
                    className="px-3 py-2 text-sm font-medium bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {dependsOn.map((ruleKey, idx) => (
                    <span key={idx} className="inline-flex items-center gap-2 px-2 py-1 bg-blue-50 text-blue-800 text-xs rounded border border-blue-200 font-mono">
                      {ruleKey}
                      <button
                        type="button"
                        onClick={() => removeDependsOn(idx)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-2">Documentation References</label>
                <div className="flex gap-2 mb-2">
                  <input 
                    type="text" 
                    value={referencesInput}
                    onChange={(e) => setReferencesInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && (addReference(), e.preventDefault())}
                    placeholder="e.g., TIG_Criteria.md line 45..."
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                  <button 
                    type="button"
                    onClick={addReference}
                    className="px-3 py-2 text-sm font-medium bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200"
                  >
                    Add
                  </button>
                </div>
                <div className="space-y-1">
                  {references.map((ref, idx) => (
                    <div key={idx} className="inline-flex items-center gap-2 px-2 py-1 bg-blue-50 text-blue-800 text-xs rounded border border-blue-200 w-full">
                      <span className="flex-1 truncate">{ref}</span>
                      <button
                        type="button"
                        onClick={() => removeReference(idx)}
                        className="text-blue-600 hover:text-blue-800 flex-shrink-0"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </fieldset>

            {/* ─ Review ─ */}
            <fieldset disabled={readOnly} className="space-y-3">
              <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Review</h3>
              
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Last Reviewed Date</label>
                <input 
                  type="date" 
                  {...register('last_reviewed')} 
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">Review Notes</label>
                <textarea 
                  rows={2}
                  {...register('review_notes')} 
                  placeholder="Notes from the last review..."
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:bg-gray-50"
                />
              </div>
            </fieldset>
          </div>
        </form>

        {/* Footer */}
        {!readOnly && (
          <div className="px-6 py-4 border-t flex justify-end gap-2 bg-gray-50">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              Cancel
            </button>
            <button
              type="submit"
              form="rule-form"
              disabled={patchRule.isPending}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {patchRule.isPending && <Spinner className="w-4 h-4 mr-2" />}
              Save Changes
            </button>
          </div>
        )}
      </div>
    </>
  )
}
