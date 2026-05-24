// NOTE: CreditorEditDrawer and RuleEditDrawer can be refactored to use this in a future cleanup pass
import React, { useEffect } from 'react'
import { X } from 'lucide-react'

/**
 * EditDrawer component
 * A generic reusable slide-in panel for editing records
 */
export default function EditDrawer({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  width = 'max-w-xl',
}) {
  // Handle Escape key to close
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      window.addEventListener('keydown', handleEscape)
      // Prevent body scroll when drawer is open
      document.body.style.overflow = 'hidden'
    }
    return () => {
      window.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  return (
    <div 
      className={`fixed inset-0 z-50 flex justify-end transition-visibility duration-300 ${isOpen ? 'visible' : 'invisible'}`}
    >
      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Panel */}
      <div
        className={`relative w-full sm:${width} bg-white shadow-2xl flex flex-col h-full transform transition-transform duration-200 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100 shrink-0">
          <div>
            <h2 id="drawer-title" className="text-xl font-bold text-slate-900 uppercase tracking-tight">
              {title}
            </h2>
            {subtitle && <p className="mt-1 text-sm text-slate-500 font-medium">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
            aria-label="Close drawer"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Body (Scrollable) */}
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </div>
    </div>
  )
}
