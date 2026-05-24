import React, { useState } from 'react'
import CaseSearch from '../components/assess/CaseSearch'
import CriteriaReport from '../components/criteria/CriteriaReport'
import EmptyState from '../components/shared/EmptyState'
import { Search } from 'lucide-react'

/**
 * AssessPage component
 * Main page for running and viewing criteria assessments
 */
export default function AssessPage() {
  const [assessmentResult, setAssessmentResult] = useState(null)

  const handleResult = (data) => {
    setAssessmentResult(data)
  }

  const handleError = (message) => {
    // Error is handled via toast inside CaseSearch
    console.error('Assessment error:', message)
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Panel: Search & Trigger (fixed width, scrollable if needed) */}
      <div className="w-72 h-full flex-shrink-0 border-r border-slate-200 bg-white">
        <CaseSearch onResult={handleResult} onError={handleError} />
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
            />
          </div>
        )}
      </div>
    </div>
  )
}
