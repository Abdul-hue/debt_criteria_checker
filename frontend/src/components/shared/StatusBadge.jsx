import React from 'react'
import clsx from 'clsx'

/**
 * Maps status strings to Tailwind classes
 */
const statusMap = {
  ACCEPT: {
    bg: 'bg-green-100',
    text: 'text-green-800',
    border: 'border-green-200',
  },
  REJECT: {
    bg: 'bg-red-100',
    text: 'text-red-800',
    border: 'border-red-200',
  },
  WILL_CONSIDER: {
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    border: 'border-amber-200',
  },
  DO_NOT_VOTE: {
    bg: 'bg-gray-100',
    text: 'text-gray-600',
    border: 'border-gray-200',
  },
  CONDITIONAL_VOTER: {
    bg: 'bg-purple-100',
    text: 'text-purple-800',
    border: 'border-purple-200',
  },
  UNKNOWN: {
    bg: 'bg-white',
    text: 'text-gray-500',
    border: 'border-gray-300',
  },
  blocked: {
    bg: 'bg-red-600',
    text: 'text-white',
    border: 'border-transparent',
  },
  BLOCKED: {
    bg: 'bg-red-600',
    text: 'text-white',
    border: 'border-transparent',
  },
  flagged: {
    bg: 'bg-amber-500',
    text: 'text-white',
    border: 'border-transparent',
  },
  FLAGGED: {
    bg: 'bg-amber-500',
    text: 'text-white',
    border: 'border-transparent',
  },
  pass: {
    bg: 'bg-green-600',
    text: 'text-white',
    border: 'border-transparent',
  },
  PASS: {
    bg: 'bg-green-600',
    text: 'text-white',
    border: 'border-transparent',
  },
  hard_block: {
    bg: 'bg-red-100',
    text: 'text-red-700',
    border: 'border-red-300',
  },
  flag: {
    bg: 'bg-amber-100',
    text: 'text-amber-700',
    border: 'border-amber-300',
  },
  info: {
    bg: 'bg-blue-100',
    text: 'text-blue-700',
    border: 'border-blue-300',
  },
}

/**
 * Helper to get status label (human readable)
 */
export const statusLabel = (status) => {
  return status || 'UNKNOWN'
}

/**
 * Helper to get status colour classes
 */
export const statusColour = (status) => {
  return statusMap[status] || statusMap.UNKNOWN
}

/**
 * StatusBadge component
 * Displays a coloured badge based on status
 */
export default function StatusBadge({ status, size = 'md' }) {
  const config = statusColour(status)
  
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 rounded',
    md: 'text-sm px-2.5 py-1 rounded-md',
    lg: 'text-base px-4 py-1.5 rounded-md font-semibold',
  }

  return (
    <span
      className={clsx(
        'inline-flex items-center font-medium border',
        config.bg,
        config.text,
        config.border,
        sizeClasses[size]
      )}
    >
      {statusLabel(status)}
    </span>
  )
}
