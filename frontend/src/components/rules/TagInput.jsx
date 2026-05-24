import React, { useState } from 'react'

/**
 * Custom tag input component for trading_names
 */
export default function TagInput({ value = [], onChange, disabled = false }) {
  const [inputValue, setInputValue] = useState('')

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      const trimmed = inputValue.trim().replace(/,$/, '')
      if (trimmed && !value.includes(trimmed)) {
        onChange([...value, trimmed])
      }
      setInputValue('')
    } else if (e.key === 'Backspace' && inputValue === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className={`flex flex-wrap gap-1.5 p-2 border rounded-md min-h-[40px] 
                    focus-within:ring-2 focus-within:ring-blue-400 focus-within:border-blue-400 
                    ${disabled ? 'bg-gray-50 border-gray-200' : 'bg-white border-gray-300'}`}>
      {value.map(tag => (
        <span key={tag} 
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-800 
                         text-xs font-medium rounded-full">
          {tag}
          {!disabled && (
            <button type="button" onClick={() => onChange(value.filter(t => t !== tag))} 
                    className="hover:text-blue-600 focus:outline-none" aria-label={`Remove ${tag}`}>
              ×
            </button>
          )}
        </span>
      ))}
      {!disabled && (
        <input 
          type="text" 
          value={inputValue} 
          onChange={e => setInputValue(e.target.value)} 
          onKeyDown={handleKeyDown} 
          className="flex-1 min-w-[120px] outline-none text-sm text-gray-700 bg-transparent" 
          placeholder={value.length === 0 ? 'Type and press Enter or comma to add…' : ''} 
        />
      )}
    </div>
  )
}
