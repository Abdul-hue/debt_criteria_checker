import React from 'react'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import LoadingSpinner from './LoadingSpinner'

/**
 * ConfirmDialog component
 * A generic modal confirmation dialog
 */
export default function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  loading = false,
}) {
  const getVariantStyles = () => {
    switch (variant) {
      case 'danger':
        return 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
      case 'warning':
        return 'bg-amber-500 hover:bg-amber-600 focus:ring-amber-400'
      default:
        return 'bg-slate-900 hover:bg-slate-800 focus:ring-slate-700'
    }
  }

  return (
    <AlertDialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm transition-opacity" />
        <AlertDialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl focus:outline-none"
          role="alertdialog"
        >
          <AlertDialog.Title className="text-lg font-semibold text-slate-900">
            {title}
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-3 text-sm text-slate-500 leading-relaxed">
            {message}
          </AlertDialog.Description>

          <div className="mt-6 flex justify-end gap-3">
            <AlertDialog.Cancel asChild>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 transition-colors disabled:opacity-50"
                disabled={loading}
              >
                {cancelLabel}
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault()
                  onConfirm()
                }}
                disabled={loading}
                className={`inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 transition-colors disabled:opacity-50 ${getVariantStyles()}`}
              >
                {loading ? (
                  <>
                    <LoadingSpinner size="sm" />
                    <span className="ml-2">Processing...</span>
                  </>
                ) : (
                  confirmLabel
                )}
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
