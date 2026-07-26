import React, { useState, useRef, useCallback } from 'react'
import CaseSearch from '../components/assess/CaseSearch'
import CriteriaReport from '../components/criteria/CriteriaReport'
import EmptyState from '../components/shared/EmptyState'
import { useAssessCase } from '../hooks/useAssessCase'
import { isPrivateParkingOperator, creditorRowKey } from '../lib/dmpRowSelections'
import { Search } from 'lucide-react'

// Case-level DMP checklist fields (Part 4 of the Aryza-only DMP redesign) —
// the 6 checkboxes with no reliable per-creditor signal. Kept in sync with
// DMP_CASE_LEVEL_CHECKLIST_FIELDS in debt_app/views/criteria_views.py.
const DEFAULT_DMP_CHECKLIST = {
  current_gas_bill: false,
  current_electric_bill: false,
  previous_gas_provider_debt: false,
  previous_electric_provider_debt: false,
  current_phone_contract: false,
  lost_right_to_pay_instalments: false,
  // HMRC VAT — hmrc_debt_has_vat is the parent tick (only offered when the last
  // assessment result's hmrc_is_creditor is true); hmrc_previous_year_vat is the
  // only one that drives behaviour (forces recommended_solution to DMP).
  hmrc_debt_has_vat: false,
  hmrc_previous_year_vat: false,
}

/**
 * AssessPage component
 * Main page for running and viewing criteria assessments
 */
export default function AssessPage() {
  const [assessmentResult, setAssessmentResult] = useState(null)
  const [lastRunParams, setLastRunParams] = useState(null) // { aryza_reference, credit_report_id }
  const [dmpChecklist, setDmpChecklist] = useState(DEFAULT_DMP_CHECKLIST)
  // Per-creditor-row DMP dropdown selections, keyed by a stable row key
  // (creditor_name + debt_type_normalised) -> selection value string.
  const [creditorRowSelections, setCreditorRowSelections] = useState({})

  const { runAssessment: recalculate } = useAssessCase()

  // Request sequencing for recalculation — a rapid sequence of dropdown
  // changes fires one POST each with no server-side ordering guarantee, so
  // whichever response lands LAST would otherwise overwrite state, even if
  // it was requested BEFORE a later change. Every call here aborts the
  // previous in-flight request and stamps an incrementing sequence number;
  // a response is only applied if it's still the latest request when it
  // resolves — a superseded request's response (abort error or a late
  // success that lost the abort race) is silently discarded.
  const recalcSeqRef = useRef(0)
  const recalcAbortRef = useRef(null)
  const [isRecalculating, setIsRecalculating] = useState(false)

  const runRecalculation = useCallback((payload) => {
    recalcAbortRef.current?.abort()
    const controller = new AbortController()
    recalcAbortRef.current = controller
    const seq = ++recalcSeqRef.current

    setIsRecalculating(true)
    recalculate(
      { ...payload, signal: controller.signal },
      {
        onSuccess: (data) => {
          if (seq !== recalcSeqRef.current) return // stale — a newer request has already superseded this one
          setAssessmentResult(data)
          setIsRecalculating(false)
        },
        onError: (error) => {
          if (seq !== recalcSeqRef.current) return // superseded (likely our own abort) — ignore
          setIsRecalculating(false)
          console.error('Recalculation failed:', error)
        },
      }
    )
  }, [recalculate])

  const handleResult = (data, creditReportId) => {
    setAssessmentResult(data)
    const runParams = { aryza_reference: data.aryza_reference, credit_report_id: creditReportId }
    setLastRunParams(runParams)

    // Clear any stale VAT ticks from a previous (different) case — the parent
    // "HMRC Debt has VAT" checkbox is disabled/hidden when this case has no
    // HMRC creditor, but the underlying state would otherwise silently carry a
    // previous case's hmrc_previous_year_vat=true into this unrelated one and
    // force it to DMP. Left untouched when hmrc_is_creditor is true so a tick
    // made just before a recalculation isn't wiped.
    if (!data.hmrc_is_creditor) {
      setDmpChecklist((prev) => ({ ...prev, hmrc_debt_has_vat: false, hmrc_previous_year_vat: false }))
    }

    // Pre-select "Private" for PCN rows matching a known private-parking
    // operator (Part 3.3) — still overridable per-row. A fresh assessment
    // otherwise clears any row selections made against the previous
    // creditor list.
    const defaults = {}
    ;(data.creditor_positions || []).forEach((c) => {
      if (c.debt_type_normalised === 'pcn' && isPrivateParkingOperator(c.creditor_name || c.original_aryza_name)) {
        defaults[creditorRowKey(c)] = { debt_type_normalised: 'pcn', value: 'private' }
      }
    })
    setCreditorRowSelections(defaults)

    if (Object.keys(defaults).length > 0) {
      runRecalculation({
        aryza_reference: runParams.aryza_reference,
        credit_report_id: runParams.credit_report_id,
        dmp_checklist: dmpChecklist,
        creditor_rows: Object.values(defaults),
      })
    }
  }

  const handleError = (message) => {
    // Error is handled via toast inside CaseSearch
    console.error('Assessment error:', message)
  }

  const handleRowSelectionChange = (rowKey, debtTypeNormalised, value) => {
    const next = { ...creditorRowSelections, [rowKey]: { debt_type_normalised: debtTypeNormalised, value } }
    setCreditorRowSelections(next)
    if (!lastRunParams) return
    runRecalculation({
      aryza_reference: lastRunParams.aryza_reference,
      credit_report_id: lastRunParams.credit_report_id,
      dmp_checklist: dmpChecklist,
      creditor_rows: Object.values(next).filter((r) => r.value),
    })
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Panel: Search & Trigger (fixed width, scrollable if needed) */}
      <div className="w-72 h-full flex-shrink-0 border-r border-slate-200 bg-white">
        <CaseSearch
          onResult={handleResult}
          onError={handleError}
          dmpChecklist={dmpChecklist}
          onDmpChecklistChange={setDmpChecklist}
          hmrcIsCreditor={assessmentResult ? !!assessmentResult.hmrc_is_creditor : null}
        />
      </div>

      {/* Right Panel: Results (fills width, scrollable) */}
      <div className="flex-1 overflow-y-auto bg-slate-50">
        {assessmentResult === null ? (
          <div className="h-full flex items-center justify-center p-12">
            <div className="max-w-md text-center">
              <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-200">
                <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-slate-900 mb-2">Run Case Assessment</h3>
                <p className="text-slate-500 text-sm leading-relaxed">
                  Enter an Aryza case reference and click <strong>Run Assessment</strong> to see the full IVA eligibility criteria check.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="max-w-5xl mx-auto p-8">
            {/* Header info for the assessment */}
            <div className="mb-6 flex items-baseline justify-between">
              <div>
                <h1 className="text-2xl font-bold text-slate-900">Run Case Assessment</h1>
                <p className="text-slate-500 mt-1">Enter an Aryza case reference to run the full IVA eligibility criteria check</p>
              </div>
              {assessmentResult.client_name && (
                <div className="text-right">
                  <span className="text-sm font-medium text-slate-500">Showing results for:</span>
                  <h2 className="text-lg font-bold text-slate-900">
                    {assessmentResult.client_name} <span className="text-slate-400 font-normal">(Ref: {assessmentResult.application_id || assessmentResult.aryza_reference})</span>
                  </h2>
                </div>
              )}
            </div>

            {/* The main report component */}
            <CriteriaReport
              result={assessmentResult}
              dividendAnalysis={assessmentResult.dividend_analysis}
              majorityAnalysis={assessmentResult.majority_analysis}
              creditorRowSelections={creditorRowSelections}
              onRowSelectionChange={handleRowSelectionChange}
              isRecalculating={isRecalculating}
            />
          </div>
        )}
      </div>
    </div>
  )
}
