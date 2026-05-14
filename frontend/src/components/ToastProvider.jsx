import * as ToastPrimitive from '@radix-ui/react-toast'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const ToastContext = createContext(null)

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((type, title, description) => {
    const id = crypto.randomUUID()
    setToasts((current) => [
      ...current,
      { id, type, title, description },
    ])
  }, [])

  const removeToast = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const value = useMemo(() => ({
    success: (message) => addToast('success', 'Success', message),
    error: (message) => addToast('error', 'Error', message),
  }), [addToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastPrimitive.Provider swipeDirection="right">
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            open
            onOpenChange={(open) => !open && removeToast(toast.id)}
            className="max-w-sm rounded-lg border bg-white border-[#e5e7eb] p-4 shadow-sm"
          >
            <ToastPrimitive.Title className="text-sm font-semibold text-[#111827]">
              {toast.title}
            </ToastPrimitive.Title>
            <ToastPrimitive.Description asChild>
              <div className="mt-1 text-sm text-[#6b7280]">{toast.description}</div>
            </ToastPrimitive.Description>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed right-4 bottom-4 z-50 flex w-[320px] flex-col gap-2" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  )
}

export const useToast = () => {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within ToastProvider')
  return context
}
