import { CREDITOR_STATUSES, RULE_SEVERITIES, CRITERIA_SETS } from './constants'

/**
 * Format pence as a readable string: 3000 -> "30.00p"
 */
export const formatPence = (pence) => {
  try {
    const num = parseFloat(pence)
    if (isNaN(num)) return '0.00p'
    return `${(num / 100).toFixed(2)}p`
  } catch {
    return '0.00p'
  }
}

/**
 * Format a decimal as a percentage: 0.75 -> "75%"
 */
export const formatPercent = (value) => {
  try {
    const num = parseFloat(value)
    if (isNaN(num)) return '0%'
    return `${Math.round(num * 100)}%`
  } catch {
    return '0%'
  }
}

/**
 * Format a number as months: 6 -> "6 months"
 */
export const formatMonths = (n) => {
  const num = parseInt(n, 10)
  if (isNaN(num)) return '0 months'
  return `${num} ${num === 1 ? 'month' : 'months'}`
}

/**
 * Get human-readable label for creditor status
 */
export const statusLabel = (status) => {
  const labels = {
    ACCEPT: 'Accept',
    REJECT: 'Reject',
    WILL_CONSIDER: 'Will Consider',
    DO_NOT_VOTE: 'Do Not Vote',
    CONDITIONAL_VOTER: 'Conditional Voter',
    UNKNOWN: 'Unknown',
  }
  return labels[status] || status || 'Unknown'
}

/**
 * Get human-readable label for rule severity
 */
export const severityLabel = (severity) => {
  const labels = {
    hard_block: 'Hard Block',
    flag: 'Flag',
    info: 'Info',
  }
  return labels[severity] || severity
}

/**
 * Get human-readable label for criteria set
 */
export const criteriaSetLabel = (set) => {
  const labels = {
    TIG: 'TIG',
    WATCH: 'Watch',
    TIX: 'TIX',
    EVOLVE: 'Evolve',
  }
  return labels[set] || set
}

/**
 * Format a value as currency (£12,345.67)
 */
export const formatCurrency = (value) => {
  try {
    const num = parseFloat(value)
    if (isNaN(num)) return '£0.00'
    return `£${num.toLocaleString('en-GB', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
  } catch {
    return '£0.00'
  }
}

/**
 * Get Tailwind color class for status
 */
export const statusColour = (status) => {
  const colours = {
    ACCEPT: 'text-green-600 bg-green-50',
    REJECT: 'text-red-600 bg-red-50',
    WILL_CONSIDER: 'text-amber-600 bg-amber-50',
    DO_NOT_VOTE: 'text-gray-600 bg-gray-100',
    CONDITIONAL_VOTER: 'text-purple-600 bg-purple-50',
    UNKNOWN: 'text-gray-400 bg-gray-50',
  }
  return colours[status] || 'text-gray-600 bg-gray-50'
}
