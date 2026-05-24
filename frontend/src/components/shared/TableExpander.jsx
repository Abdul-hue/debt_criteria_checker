import React from 'react'

/**
 * TableExpander component
 * A reusable toggle button used to expand/collapse individual table rows.
 * 
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the row is expanded
 * @param {function} props.onClick - Click handler
 * @param {string} props.label - Screen-reader label
 */
const TableExpander = ({ isOpen, onClick, label }) => {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      aria-expanded={isOpen}
      className="flex items-center justify-center w-6 h-6 rounded 
                 text-gray-400 hover:text-gray-600 hover:bg-gray-100 
                 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400"
    >
      {isOpen ? "▾" : "▸"}
    </button>
  )
}

export default TableExpander
