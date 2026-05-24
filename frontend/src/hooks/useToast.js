import { useContext } from 'react'
import { ToastContext } from '../components/ToastProvider.jsx'

/**
 * useToast hook
 * Provides convenience methods for showing different toast types
 */
export function useToast() {
  const ctx = useContext(ToastContext)

  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider')
  }

  return {
    success: (title, message) => ctx.addToast('success', title, message),
    error: (title, message) => ctx.addToast('error', title, message),
    warning: (title, message) => ctx.addToast('warning', title, message),
    info: (title, message) => ctx.addToast('info', title, message),
  }
}
