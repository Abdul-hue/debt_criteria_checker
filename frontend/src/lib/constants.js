export const REPRESENTATIVES = ['WATCH', 'TIX', 'EVOLVE', 'EVERYDAY_LOANS', 'NONE']

export const CREDITOR_STATUSES = [
  'ACCEPT',
  'REJECT',
  'WILL_CONSIDER',
  'DO_NOT_VOTE',
  'CONDITIONAL_VOTER',
  'UNKNOWN',
]

export const SEVERITY_LEVELS = ['hard_block', 'flag', 'info']

export const CRITERIA_SETS = ['TIG', 'WATCH', 'TIX', 'EVOLVE']

export const TOKEN_KEY = 'debt_assessment_token'

export const DEFAULT_STALE_TIME = 5 * 60 * 1000

// Legacy support (if needed)
export const RULE_SEVERITIES = SEVERITY_LEVELS
export const STORAGE_KEY = TOKEN_KEY

export const DEBT_TYPES = [
  'credit_card',
  'personal_loan',
  'overdraft',
  'catalogue',
  'store_card',
  'hp',
  'mortgage',
  'council_tax',
  'pcn',
  'housing_benefit',
  'utility',
  'mobile',
  'rent',
  'unknown',
]

export const OVERALL_STATUSES = {
  BLOCKED: 'blocked',
  FLAGGED: 'flagged',
  PASS: 'pass',
}

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
