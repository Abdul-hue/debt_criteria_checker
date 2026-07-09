import React, { useState, useMemo } from 'react'
import { 
  ChevronDown, 
  ChevronUp, 
  X, 
  Lightbulb, 
  CheckCircle2, 
  AlertCircle, 
  Info,
  Check
} from 'lucide-react'

const REPRESENTATIVE_META = { 
  "WATCH": { 
    label: "WATCH", 
    fullName: "WATCH Debt Solutions", 
    color: "purple", 
    chipClass: "bg-purple-100 text-purple-800 border border-purple-200", 
    description: "This case is governed by WATCH creditor " + 
      "criteria. WATCH-specific rules apply in addition to " + 
      "standard TIG requirements.", 
  }, 
  "TIG": { 
    label: "TIG", 
    fullName: "Trust IVA Group", 
    color: "blue", 
    chipClass: "bg-blue-100 text-blue-800 border border-blue-200", 
    description: "This case is governed by TIG criteria. " + 
      "Standard TIG rules apply.", 
  }, 
  "TIX": { 
    label: "TIX", 
    fullName: "TIX Representative", 
    color: "teal", 
    chipClass: "bg-teal-100 text-teal-800 border border-teal-200", 
    description: "This case is governed by TIX criteria.", 
  }, 
  "EVOLVE": { 
    label: "EVOLVE", 
    fullName: "Evolve", 
    color: "amber", 
    chipClass: "bg-amber-100 text-amber-800 border border-amber-200", 
    description: "This case is governed by EVOLVE criteria.", 
  }, 
  "NONE": { 
    label: "No Representative", 
    fullName: "No Representative Detected", 
    color: "gray", 
    chipClass: "bg-gray-100 text-gray-600 border border-gray-200", 
    description: "No creditor representative was detected " + 
      "for this case.", 
  }, 
}

const formatCurrency = (val) => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(val || 0)
const formatPence = (val) => `${(val || 0).toFixed(2)}p`

const STATUS_CHIP = {
  'ACCEPT':           'bg-emerald-100 text-emerald-700',
  'REJECT':           'bg-red-100 text-red-700',
  'UNKNOWN':          'bg-blue-100 text-blue-700',
  'REVIEW':           'bg-amber-100 text-amber-700',
  'WILL_CONSIDER':    'bg-amber-100 text-amber-700',
  'DO_NOT_VOTE':      'bg-gray-100 text-gray-600',
  'CONDITIONAL_VOTER':'bg-blue-100 text-blue-700',
}

const STATUS_LABEL = {
  'ACCEPT':           'Accept',
  'REJECT':           'Reject',
  'UNKNOWN':          'Unidentified',
  'REVIEW':           'Needs Review',
  'WILL_CONSIDER':    'Will Consider',
  'DO_NOT_VOTE':      'Does Not Vote',
  'CONDITIONAL_VOTER':'Case by Case',
}

const STATUS_DEFAULT_REASON = {
  'ACCEPT':           'No conditions or restrictions apply — this creditor is expected to accept the proposal.',
  'REJECT':           'This creditor has indicated it will reject this proposal based on the case criteria.',
  'WILL_CONSIDER':    'This creditor will consider the proposal subject to conditions or modifications.',
  'DO_NOT_VOTE':      'This creditor does not participate in the creditor vote.',
  'CONDITIONAL_VOTER':'This creditor votes case by case — outcome depends on specific case factors.',
  'UNKNOWN':          'This creditor has no matching record in our database.',
}

const RuleCard = ({ rule, isExpanded, onToggle, creditorPositions = [] }) => {
  const meta = { 
    title: rule.title || rule.rule_id, 
    description: rule.description || rule.message, 
    action: rule.action || null, 
  }
  
  const severity = rule.severity || 'pass'
  
  const styles = {
    hard_block: {
      bg: 'bg-block-red',
      border: 'border-block-red-border',
      chip: 'bg-brand-navy text-white',
      label: 'HARD BLOCK',
      icon: <X className="w-4 h-4 text-red-600" />
    },
    flag: {
      bg: 'bg-flag-amber',
      border: 'border-flag-amber-border',
      chip: 'bg-brand-navy text-white',
      label: 'FLAG',
      icon: <AlertCircle className="w-4 h-4 text-amber-600" />
    },
    pass: {
      bg: 'bg-pass-green',
      border: 'border-pass-green-border',
      chip: 'bg-emerald-600 text-white',
      label: 'PASS',
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-600" />
    }
  }[severity] || {
    bg: 'bg-info-blue',
    border: 'border-info-blue-border',
    chip: 'bg-brand-navy text-white',
    label: 'INFO',
    icon: <Info className="w-4 h-4 text-blue-600" />
  }

  // Creditor List Extraction for TIG-10
  const renderCreditorList = () => {
    if (rule.rule_id !== 'TIG-10') return null

    const creditors = rule.creditors
    if (!creditors || creditors.length === 0) return null

    const REP_CHIP = {
      'WATCH': 'bg-blue-50 text-blue-600 border-blue-100',
      'TIX': 'bg-indigo-50 text-indigo-600 border-indigo-100',
      'EVOLVE': 'bg-teal-50 text-teal-600 border-teal-100',
      'EVERYDAY_LOANS': 'bg-orange-50 text-orange-600 border-orange-100',
      'NONE': 'bg-gray-50 text-gray-400 border-gray-100',
    }

    const totalBalance = creditors.reduce((sum, c) => sum + (typeof c.balance === 'number' ? c.balance : 0), 0)

    return (
      <div className="mt-4 border border-gray-100 rounded-lg overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-50 text-gray-400 uppercase text-[10px] tracking-widest font-bold">
            <tr>
              <th className="px-4 py-3 w-full">Creditor</th>
              <th className="px-4 py-3 w-20 whitespace-nowrap">Rep</th>
              <th className="px-4 py-3 w-32 text-right whitespace-nowrap">Balance</th>
              <th className="px-4 py-3 w-28 text-center whitespace-nowrap">Type</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {creditors.map((c, i) => {
              const balanceFormatted = typeof c.balance === 'number'
                ? c.balance.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                : c.balance
              const rep = (c.representative || 'NONE').toUpperCase().trim()
              const repChipClass = REP_CHIP[rep] || 'bg-gray-50 text-gray-400 border-gray-100'
              const rawType = (c.debt_type || '').toLowerCase()
              const debtType = rawType.replace(/_/g, ' ')
              const TYPE_CHIP = {
                'credit_card':    'bg-blue-50 text-blue-700 border border-blue-200',
                'catalogue':      'bg-purple-50 text-purple-700 border border-purple-200',
                'personal_loan':  'bg-amber-50 text-amber-700 border border-amber-200',
                'unsecured_loan': 'bg-amber-50 text-amber-700 border border-amber-200',
                'overdraft':      'bg-orange-50 text-orange-700 border border-orange-200',
                'store_card':     'bg-pink-50 text-pink-700 border border-pink-200',
                'utility':        'bg-teal-50 text-teal-700 border border-teal-200',
                'council_tax':    'bg-red-50 text-red-700 border border-red-200',
                'mobile':         'bg-cyan-50 text-cyan-700 border border-cyan-200',
                'rent':           'bg-green-50 text-green-700 border border-green-200',
              }
              const typeChipClass = TYPE_CHIP[rawType] || 'bg-gray-50 text-gray-500 border border-gray-200'

              return (
                <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">{c.original_aryza_name || c.creditor_name || c.name}</span>
                      {c.matched_in_db
                        ? <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-tight bg-green-50 text-green-700 border border-green-200">Matched</span>
                        : <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-tight bg-gray-100 text-gray-500 border border-gray-200">Unmatched</span>}
                    </div>
                    {(c.original_aryza_name && c.creditor_name && c.creditor_name !== c.original_aryza_name) ? (
                      <div className="text-xs text-gray-400 mt-0.5">Matched: {c.creditor_name}</div>
                    ) : (c.credit_report_name && (
                      <div className="text-xs text-gray-400 mt-0.5">{c.credit_report_name}</div>
                    ))}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-tight ${repChipClass}`}>
                      {rep === 'EVERYDAY_LOANS' ? 'EV-LOANS' : rep}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600">£{balanceFormatted}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold capitalize tracking-wide ${typeChipClass}`}>
                      {debtType || '—'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-gray-200 bg-gray-50">
              <td colSpan="2" className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Total
              </td>
              <td className="px-4 py-3 text-right font-semibold text-sm text-gray-900">
                {formatCurrency(totalBalance)}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    )
  }

  if (severity === 'pass' && !isExpanded) {
    return (
      <div 
        onClick={onToggle}
        className={`bg-white border border-gray-100 border-l-4 ${styles.border} rounded-xl p-5 cursor-pointer hover:shadow-md transition-all duration-200 flex items-center justify-between group`}
      >
        <div className="flex items-center gap-3">
          {styles.icon}
          <span className="text-sm font-bold text-gray-900">{meta.title}</span>
          <span className="text-sm text-gray-500 truncate max-w-md">— {rule.message}</span>
        </div>
        <ChevronDown className="w-5 h-5 text-gray-400 group-hover:text-gray-600 transition-transform" />
      </div>
    )
  }

  return (
    <div 
      className={`bg-white border border-gray-100 border-l-4 ${styles.border} rounded-xl p-5 shadow-sm transition-all duration-200`}
    >
      <div className="flex justify-between items-start cursor-pointer" onClick={onToggle}>
        <div className="flex gap-4">
          <div className="flex flex-col items-center gap-1">
            <div className={`px-2 py-1 rounded text-[10px] font-bold tracking-widest ${styles.chip}`}>
              {rule.rule_id}
            </div>
            <div className="text-[10px] font-bold text-gray-400 tracking-tighter uppercase">{styles.label}</div>
          </div>
          <div>
            <h3 className="text-base font-bold text-gray-900">{meta.title}</h3>
            <p className="text-sm text-gray-500 mt-0.5">{rule.message}</p>
          </div>
        </div>
        <ChevronUp className={`w-5 h-5 text-gray-400 transition-transform ${isExpanded ? '' : 'rotate-180'}`} />
      </div>

      <div className={`overflow-hidden transition-all duration-300 ${isExpanded ? 'max-h-[1000px] mt-6' : 'max-h-0'}`}>
        <div className="space-y-6">
          <section>
            <div className="flex items-center gap-2 mb-3">
              <div className="h-px bg-gray-100 flex-1" />
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">What this rule checks</span>
              <div className="h-px bg-gray-100 flex-1" />
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600 leading-relaxed">
              {meta.description}
            </div>
          </section>

          {renderCreditorList()}

          {(rule.threshold !== null || rule.actual_value !== null) && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px bg-gray-100 flex-1" />
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Values</span>
                <div className="h-px bg-gray-100 flex-1" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                {rule.threshold !== null && (
                  <div>
                    <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-1">Required</label>
                    <div className="text-sm font-semibold text-gray-900">
                      {typeof rule.threshold === 'number' && rule.rule_id.includes('WATCH-22.2') ? `${rule.threshold} months` : (typeof rule.threshold === 'object' ? JSON.stringify(rule.threshold) : rule.threshold)}
                    </div>
                  </div>
                )}
                {rule.actual_value !== null && (
                  <div>
                    <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-1">Actual</label>
                    <div className="text-sm font-semibold text-gray-900">
                      {typeof rule.actual_value === 'number' ? rule.actual_value.toFixed(2) : (typeof rule.actual_value === 'object' ? JSON.stringify(rule.actual_value) : rule.actual_value)}
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {meta.action && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px bg-gray-100 flex-1" />
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                  {severity === 'flag' ? 'Advisory' : 'Action Required'}
                </span>
                <div className="h-px bg-gray-100 flex-1" />
              </div>
              <div className={`${severity === 'flag' ? 'bg-amber-50 text-amber-700' : 'bg-info-blue text-blue-700'} rounded-lg p-3 flex items-center gap-2 text-sm font-medium`}>
                <span className="text-lg">→</span>
                {meta.action}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

export default function CriteriaReport({ result }) {
  const hard_blocks = result?.hard_blocks || []
  const flags = result?.flags || []
  const passed = result?.passed || []
  const total = hard_blocks.length + flags.length + passed.length

  const [statusPopup, setStatusPopup] = useState(null)
  const [activeTab, setActiveTab] = useState(hard_blocks.length > 0 ? 'failed' : 'all')
  const [expandedRules, setExpandedRules] = useState(() => {
    const expanded = {}
    if (activeTab === 'failed') hard_blocks.forEach(r => { expanded[r.rule_id] = true })
    if (activeTab === 'flagged') flags.forEach(r => { expanded[r.rule_id] = true })
    return expanded
  })
  const outcomesTally = statusPopup?.creditor ? {
    approved: statusPopup.creditor.outcomes_approved || 0,
    disapproved: statusPopup.creditor.outcomes_disapproved || 0,
    total: statusPopup.creditor.outcomes_total || 0,
  } : null

  const handleTabChange = (tab) => {
    setActiveTab(tab)
    const expanded = {}
    if (tab === 'failed') hard_blocks.forEach(r => { expanded[r.rule_id] = true })
    if (tab === 'flagged') flags.forEach(r => { expanded[r.rule_id] = true })
    // For 'all' and 'passed', keep collapsed by default
    setExpandedRules(expanded)
  }

  const toggleRule = (id) => {
    setExpandedRules(prev => ({ ...prev, [id]: !prev[id] }))
  }

  const filteredResults = useMemo(() => {
    if (activeTab === 'failed') return hard_blocks
    if (activeTab === 'flagged') return flags
    if (activeTab === 'passed') return passed
    return [...hard_blocks, ...flags, ...passed]
  }, [activeTab, hard_blocks, flags, passed])

  const solutionStyles = {
    IVA: 'border-emerald-400 bg-emerald-50 text-emerald-800',
    DMP: 'border-blue-400 bg-blue-50 text-blue-800',
    NON_IVA: 'border-blue-400 bg-blue-50 text-blue-800',
    IVA_NOT_VIABLE: 'border-red-400 bg-red-50 text-red-800',
    IVA_VIABLE: 'border-emerald-400 bg-emerald-50 text-emerald-800',
    IVA_WITH_CONDITIONS: 'border-emerald-400 bg-emerald-50 text-emerald-800',
    REVIEW_REQUIRED: 'border-amber-400 bg-amber-50 text-amber-800',
    BREATHING_SPACE: 'border-amber-400 bg-amber-50 text-amber-800',
    UNCLEAR: 'border-gray-400 bg-gray-50 text-gray-800'
  }

  const solutionDescriptions = {
    IVA_NOT_VIABLE: "Based on this client's income and debt level, a Debt Management Plan is the most suitable alternative to an IVA.",
    IVA: "This client appears eligible for an IVA based on the criteria assessed.",
    DMP: "A Debt Management Plan is recommended for this client's current situation.",
    BREATHING_SPACE: "A temporary stay of action is recommended to provide relief."
  }

  const solutionLabelMap = {
    'IVA_VIABLE': 'IVA Recommended',
    'IVA_WITH_CONDITIONS': 'IVA with Conditions',
    'IVA_NOT_VIABLE': 'Debt Management Plan',
    'REVIEW_REQUIRED': 'Review Required',
    'DMP': 'Debt Management Plan',
    'BREATHING_SPACE': 'Breathing Space',
    'UNCLEAR': 'Inconclusive — Manual Review Needed'
  }

  // Handle recommended_solution being either a string (legacy/direct) or a rich object (standard)
  const solutionObj = result?.recommended_solution
  const solutionCode = typeof solutionObj === 'object' ? (solutionObj?.code || 'IVA') : (solutionObj || 'IVA')
  const solutionLabel = typeof solutionObj === 'object' 
    ? (solutionObj?.label || solutionCode) 
    : (solutionLabelMap[solutionCode] || solutionCode)
  
  const solutionRationale = typeof solutionObj === 'object' && solutionObj?.rationale
    ? solutionObj.rationale
    : (solutionDescriptions[solutionCode] || "Based on the assessment, this is the most suitable path forward.")

  const isBlocked = hard_blocks.length > 0
  const isAchievable = result?.majority_analysis?.achievable === true
  const estDividend = result?.dividend_analysis?.estimated_pence || 0

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 font-sans text-gray-600">
      {/* SECTION A — CLIENT HEADER CARD */}
      <div className="bg-white rounded-2xl shadow-md border border-gray-100 overflow-hidden">
        <div className="h-1 w-full bg-gradient-to-r from-brand-navy via-brand-gold to-brand-red" />
        <div className="p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
        <div className="space-y-3">
          <h1 className="font-display text-3xl font-bold text-brand-navy tracking-tight">
            {result?.client_name || 'Theresa Topp'}
          </h1>
          <p className="text-sm text-gray-400">
            Aryza Ref: {result?.aryza_reference || '324991'} • Assessed {new Date(result?.evaluated_at).toLocaleDateString()}
          </p>
          <div className="space-y-1">
            <div className="text-xs uppercase tracking-widest text-gray-400">REPRESENTATIVES DETECTED</div>
            <div className="flex flex-col gap-2">
              {((result?.representatives_detected && result.representatives_detected.length > 0) 
                ? result.representatives_detected 
                : ["NONE"]
              ).map((entry, idx) => {
                const meta = REPRESENTATIVE_META[entry] ?? REPRESENTATIVE_META["NONE"]
                return (
                  <div key={idx} className="flex flex-col">
                    <div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${meta.chipClass}`}>
                        {meta.label}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{meta.description}</p>
                  </div>
                )
              })}
            </div>
          </div>
          {result?.overall_status === 'BLOCKED' && (
            <div className="inline-flex items-center gap-1.5 bg-red-100 text-red-700 border border-red-200 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-widest">
              <X className="w-3.5 h-3.5" />
              BLOCKED
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-3 w-full md:w-auto">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Recommended Solution</span>
          <div className={`rounded-xl border-2 px-4 py-3 flex items-center gap-2 min-w-[200px] ${solutionStyles[solutionCode] || solutionStyles.IVA}`}>
            <Lightbulb className="w-5 h-5" />
            <span className="text-lg font-bold">{solutionLabel}</span>
          </div>
          <p className="text-xs text-right text-gray-500 max-w-[280px] leading-relaxed">
            {solutionRationale}
          </p>
        </div>
        </div>
      </div>

      {/* SECTION B — KEY METRICS ROW */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
        <div className="rounded-xl bg-white shadow-sm border border-gray-100 border-t-4 border-t-brand-navy p-4">
          <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-1 flex items-center gap-1.5">
            Total Debt
            <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider bg-slate-100 text-brand-navy border border-slate-200">
              Unsecured
            </span>
          </label>
          <div className="font-display text-2xl font-bold text-brand-navy">{formatCurrency(result?.total_unsecured_debt)}</div>
          {result?.total_secured_debt > 0 && (
            <p className="text-[10px] text-gray-400 mt-1">
              + {formatCurrency(result.total_secured_debt)} secured (excluded)
            </p>
          )}
        </div>
        <div className="rounded-xl bg-white shadow-sm border border-gray-100 border-t-4 border-t-brand-gold p-4">
          <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-1">Disposable Income</label>
          <div className="font-display text-2xl font-bold text-brand-navy">{formatCurrency(result?.disposable_income)}</div>
        </div>
        <div className="rounded-xl shadow-sm border p-4 bg-white border-gray-100 border-t-4 border-t-emerald-800">
          <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-1">Est. Dividend</label>
          <div className="font-display text-2xl font-bold text-brand-navy">{formatPence(estDividend)}</div>
          {result?.dividend_analysis && (
            <div className="mt-2">
              {result.dividend_analysis.below_min?.length > 0 ? (
                <div className="text-xs text-amber-600">
                  Below minimum for: {result.dividend_analysis.below_min.map(b => typeof b === 'object' ? b.creditor_name : b).join(', ')}
                </div>
              ) : (
                <div className="text-xs text-green-600">All creditors satisfied</div>
              )}
            </div>
          )}
        </div>
        <div className={`rounded-xl shadow-sm border p-4 bg-white border-gray-100 border-t-4 ${isAchievable ? 'border-t-emerald-800' : 'border-t-brand-red'}`}>
          <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-1">Majority</label>
          <div className="flex items-center gap-2">
            {isAchievable ? (
              <Check className="w-6 h-6 text-emerald-600 stroke-[3]" />
            ) : (
              <X className="w-6 h-6 text-brand-red stroke-[3]" />
            )}
            <div className="font-display text-2xl font-bold text-brand-navy">{isAchievable ? 'Yes' : 'No'}</div>
          </div>
          {result?.majority_analysis && (
            <div className="mt-2 space-y-0.5">
              <div className="text-xs text-gray-500">
                75% threshold: £{new Intl.NumberFormat('en-GB').format(Math.round(result.majority_analysis.threshold || 0))}
              </div>
              <div className="text-xs text-gray-500">
                Voting debt: £{new Intl.NumberFormat('en-GB').format(Math.round(result.majority_analysis.voting_debt || 0))}
              </div>
              {result.majority_analysis.achievable ? (
                <div className="text-xs font-medium text-green-600">Majority Achievable</div>
              ) : (
                <div className="text-xs font-medium text-brand-red">
                  Shortfall: £{new Intl.NumberFormat('en-GB').format(Math.round(result.majority_analysis.shortfall || 0))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* CASE SUMMARY section */}
      <div className="mt-8 space-y-6">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 border-t-4 border-t-brand-navy p-6">
          <h2 className="text-sm font-bold text-brand-navy uppercase tracking-wide mb-4">Creditor Positions</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-4 pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide w-full">Creditor</th>
                  <th className="px-4 pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-right whitespace-nowrap">Balance</th>
                  <th className="px-4 pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-right whitespace-nowrap">CR Balance</th>
                  <th className="px-4 py-3 text-right text-xs text-gray-500 font-medium uppercase tracking-wide">Match</th>
                  <th className="px-4 pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-right whitespace-nowrap">CR Status</th>
                  <th className="px-4 pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-right whitespace-nowrap">Missed Pmts (3m)</th>
                  <th className="px-4 pb-3 text-xs font-medium text-gray-500 uppercase tracking-wide text-center whitespace-nowrap">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {(result?.creditor_positions || []).map((creditor, idx) => {
                  // CR Balance: stored in pence, display as £
                  const crBalPounds = creditor.cr_balance != null ? creditor.cr_balance / 100 : null

                  return (
                    <tr key={idx}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900">
                            {creditor.cr_raw_name || creditor.original_aryza_name || creditor.creditor_name || creditor.display_name || creditor.name}
                          </span>
                          {creditor.type_code && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-tight bg-cyan-50 text-cyan-600 border border-cyan-100">
                              {creditor.type_code}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {(() => {
                            const REP_CHIP = {
                              'WATCH': 'bg-blue-50 text-blue-600 border-blue-100',
                              'TIX': 'bg-indigo-50 text-indigo-600 border-indigo-100',
                              'EVOLVE': 'bg-teal-50 text-teal-600 border-teal-100',
                              'EVERYDAY_LOANS': 'bg-orange-50 text-orange-600 border-orange-100',
                            }
                            const rep = (creditor.representative || 'NONE').toUpperCase().trim()
                            if (rep !== 'NONE' && REP_CHIP[rep]) {
                              return (
                                <span className={`px-1.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-tight ${REP_CHIP[rep]}`}>
                                  {rep === 'EVERYDAY_LOANS' ? 'EV-LOANS' : rep}
                                </span>
                              )
                            }
                            return null
                          })()}
                        </div>
                      </td>
                      {/* Balance — Aryza */}
                      <td className="px-4 py-3 text-sm text-gray-700 text-right">
                        {formatCurrency(creditor.balance)}
                      </td>
                      {/* CR Balance */}
                      <td className="px-4 py-3 text-sm text-gray-700 text-right">
                        {crBalPounds != null
                          ? new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(crBalPounds)
                          : <span className="text-gray-300">—</span>}
                      </td>
                      {/* Match */}
                      <td className="px-4 py-3 text-sm text-right">
                        {creditor.cr_balance != null ? (
                          Math.abs((creditor.cr_balance / 100) - creditor.balance) < 0.01 ? (
                            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700 border border-green-200">Matched</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700 border border-red-200">Mismatch</span>
                          )
                        ) : <span className="text-gray-300">—</span>}
                      </td>
                      {/* CR Status */}
                      <td className="px-4 py-3 text-sm text-gray-700 text-right">
                        {creditor.cr_account_status || creditor.cr_account_status_subjective ? (
                          <span>
                            {creditor.cr_account_status || ''}
                            {creditor.cr_account_status && creditor.cr_account_status_subjective ? ' / ' : ''}
                            {creditor.cr_account_status_subjective || ''}
                          </span>
                        ) : <span className="text-gray-300">—</span>}
                      </td>
                      {/* Missed Pmts 3m */}
                      <td className="px-4 py-3 text-sm text-gray-700 text-right">
                        {creditor.cr_missed_payments_3m != null
                          ? creditor.cr_missed_payments_3m
                          : <span className="text-gray-300">—</span>}
                      </td>
                      {/* Status badge */}
                      <td className="px-4 py-3 text-center">
                        {(() => {
                          const statusKey = (creditor.effective_status || '').toUpperCase().trim()
                          const chipClass = STATUS_CHIP[statusKey] || 'bg-gray-100 text-gray-500'
                          return (
                            <button
                              onClick={() => setStatusPopup({ creditor, idx })}
                              className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider cursor-pointer hover:opacity-80 transition-opacity ${chipClass}`}
                              title="Click for details"
                            >
                              {STATUS_LABEL[statusKey] || statusKey || 'UNKNOWN'}
                            </button>
                          )
                        })()}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan="7" className="px-4 pt-4 pb-1 text-right">
                    <span className="font-semibold text-sm text-gray-500 mr-2">Total Unsecured Debt:</span>
                    <span className="font-semibold text-sm text-gray-900">
                      {formatCurrency(
                        (result?.creditor_positions || [])
                          .filter(c => !c.is_secured)
                          .reduce((sum, c) => sum + (c.balance || 0), 0)
                      )}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>

      {/* SECTION C — FILTER TAB BAR */}
      <div className="flex flex-wrap gap-2 mt-8 mb-6">
        <button 
          onClick={() => handleTabChange('all')}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-all duration-200 ${
            activeTab === 'all' ? 'bg-brand-navy text-white shadow-md' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          All Results ({total})
        </button>
        <button 
          onClick={() => handleTabChange('failed')}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-all duration-200 ${
            activeTab === 'failed' ? 'bg-red-600 text-white shadow-md' : 'bg-red-50 text-red-700 hover:bg-red-100'
          }`}
        >
          Not Qualifying ({hard_blocks.length})
        </button>
        <button 
          onClick={() => handleTabChange('flagged')}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-all duration-200 ${
            activeTab === 'flagged' ? 'bg-amber-500 text-white shadow-md' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'
          }`}
        >
          Needs Review ({flags.length})
        </button>
        <button 
          onClick={() => handleTabChange('passed')}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-all duration-200 ${
            activeTab === 'passed' ? 'bg-emerald-600 text-white shadow-md' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
          }`}
        >
          Requirements Met ({passed.length})
        </button>
      </div>

      {/* SECTION D — RULE CARDS */}
      <div className="space-y-4">
        {filteredResults.map((rule, idx) => (
          <RuleCard
            key={`${rule.rule_id}-${idx}`}
            rule={rule}
            isExpanded={expandedRules[rule.rule_id]}
            onToggle={() => toggleRule(rule.rule_id)}
            creditorPositions={result?.creditor_positions || []}
          />
        ))}
        {filteredResults.length === 0 && (
          <div className="text-center py-12 bg-gray-50 rounded-2xl border border-dashed border-gray-200">
            <p className="text-gray-400 font-medium">No results found in this category.</p>
          </div>
        )}
      </div>

      {/* STATUS REASON POPUP */}
      {statusPopup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          onClick={() => setStatusPopup(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-gray-200 p-6 max-w-md w-full mx-4"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="text-base font-bold text-gray-900">
                  {statusPopup.creditor.original_aryza_name || statusPopup.creditor.creditor_name}
                </div>
                {statusPopup.creditor.original_aryza_name && statusPopup.creditor.creditor_name &&
                  statusPopup.creditor.creditor_name !== statusPopup.creditor.original_aryza_name && (
                    <div className="text-xs text-gray-400 mt-0.5">
                      Matched: {statusPopup.creditor.creditor_name}
                    </div>
                  )}
              </div>
              <button
                onClick={() => setStatusPopup(null)}
                className="text-gray-400 hover:text-gray-600 transition-colors ml-4 flex-shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Status badge + rep */}
            <div className="flex items-center gap-2 mb-4">
              {(() => {
                const statusKey = (statusPopup.creditor.effective_status || '').toUpperCase().trim()
                const chipClass = STATUS_CHIP[statusKey] || 'bg-gray-100 text-gray-500'
                return (
                  <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${chipClass}`}>
                    {STATUS_LABEL[statusKey] || statusKey || 'UNKNOWN'}
                  </span>
                )
              })()}
              {statusPopup.creditor.representative && statusPopup.creditor.representative !== 'NONE' && (
                <span className="px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tight bg-blue-50 text-blue-600 border border-blue-100">
                  {statusPopup.creditor.representative}
                </span>
              )}
            </div>

            {outcomesTally && (outcomesTally.total > 0) && (
              <div className="mt-2 text-xs text-gray-500">
                <span className="text-green-600 font-semibold">{outcomesTally.approved} approved</span>
                {' · '}
                <span className="text-red-500 font-semibold">{outcomesTally.disapproved} disapproved</span>
                {' · '}
                {outcomesTally.total} submitted
              </div>
            )}

            {/* Reason */}
            <div className="bg-gray-50 rounded-xl px-4 py-3 text-sm text-gray-700 leading-relaxed">
              {statusPopup.creditor.reason ||
                STATUS_DEFAULT_REASON[(statusPopup.creditor.effective_status || '').toUpperCase()] ||
                'No additional information available.'}
            </div>

            {/* Checks run on this case */}
            {(() => {
              const statusKey = (statusPopup.creditor.effective_status || '').toUpperCase().trim()
              const findings = statusPopup.creditor.findings || []
              const isUnidentified = statusKey === 'UNKNOWN' &&
                findings.every(f => f.code === 'CREDITOR-UNKNOWN')

              if (isUnidentified) {
                return (
                  <div className="mt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
                        Checks run on this case
                      </span>
                      <div className="flex-1 h-px bg-gray-100" />
                    </div>
                    <div className="flex items-start gap-2.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-xs text-blue-800">
                      <span className="mt-0.5 font-bold text-sm leading-none text-blue-500">i</span>
                      <span className="leading-snug">
                        This creditor has no matching record in our database, so no criteria checks apply.
                      </span>
                    </div>
                  </div>
                )
              }

              return findings.length > 0 && (
              <div className="mt-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
                    Checks run on this case
                  </span>
                  <div className="flex-1 h-px bg-gray-100" />
                  <span className="text-[11px] text-gray-400">
                    {findings.filter(f => f.severity === 'pass').length} passed
                    {' · '}
                    {findings.filter(f => f.code.endsWith('-REJECT')).length} failed
                    {' · '}
                    {findings.filter(f => !f.severity?.match(/pass/) && !f.code.endsWith('-REJECT')).length} flagged
                  </span>
                </div>
                <div className="space-y-2">
                  {(() => {
                    const sorted = [...(statusPopup.creditor.findings || [])].sort((a, b) => {
                      const sa = a.code.endsWith('-REJECT') ? 0 : a.severity === 'pass' ? 2 : 1;
                      const sb = b.code.endsWith('-REJECT') ? 0 : b.severity === 'pass' ? 2 : 1;
                      return sa - sb;
                    });

                    return sorted.map((f, i) => {
                      const isReject    = f.code.endsWith('-REJECT');
                      const isDoNotVote = f.code.endsWith('-DO_NOT_VOTE');
                      const isPass      = f.severity === 'pass';

                      const chipClasses = isReject
                        ? 'bg-red-50 border-red-200 text-red-800'
                        : isDoNotVote
                        ? 'bg-gray-50 border-gray-200 text-gray-600'
                        : isPass
                        ? 'bg-green-50 border-green-200 text-green-800'
                        : 'bg-amber-50 border-amber-200 text-amber-800';

                      const iconClasses = isReject
                        ? 'text-red-500'
                        : isDoNotVote
                        ? 'text-gray-400'
                        : isPass
                        ? 'text-green-500'
                        : 'text-amber-500';

                      const icon = isReject ? '✕' : isPass ? '✓' : '!';

                      return (
                        <div
                          key={i}
                          className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-xs ${chipClasses}`}
                        >
                          <span className={`mt-0.5 font-bold text-sm leading-none ${iconClasses}`}>
                            {icon}
                          </span>
                          <div className="flex flex-col gap-0.5 min-w-0">
                            <span className="font-semibold tracking-wide uppercase text-[10px] opacity-70">
                              {f.code}
                            </span>
                            <span className="leading-snug">{f.reason}</span>
                          </div>
                        </div>
                      );
                    });
                  })()}
                </div>
              </div>
              )
            })()}

            {/* Balance */}
            <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
              <span>Balance</span>
              <span className="font-semibold text-gray-800">{formatCurrency(statusPopup.creditor.balance)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
