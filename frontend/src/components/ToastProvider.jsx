import { createContext, useCallback, useMemo, useState, useContext } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react'

export const ToastContext = createContext(null)

const toastTypeStyles = {
  success: {
    bg: 'bg-green-600',
    icon: CheckCircle,
  },
  error: {
    bg: 'bg-red-600',
    icon: XCircle,
  },
  warning: {
    bg: 'bg-amber-600',
    icon: AlertTriangle,
  },
  info: {
    bg: 'bg-blue-600',
    icon: Info,
  },
}

function Toast({ id, type, title, message, onRemove }) {
  const { bg, icon: IconComponent } = toastTypeStyles[type]

  return (
    <div
      className={`${bg} flex items-start gap-3 p-4 rounded-lg shadow-lg text-white w-80 animate-in slide-in-from-right fade-in`}
    >
      <IconComponent size={20} className="mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm">{title}</p>
        <p className="text-sm opacity-90 mt-1">
          {typeof message === 'string' 
            ? message 
            : message?.message ?? String(message)}
        </p>
      </div>
      <button
        onClick={() => onRemove(id)}
        className="flex-shrink-0 hover:opacity-75 transition-opacity mt-0.5"
      >
        <X size={16} />
      </button>
    </div>
  )
}

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([])

  const removeToast = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const addToast = useCallback(
    (type, title, message, duration = 4000) => {
      const id = crypto.randomUUID()
      setToasts((current) => {
        const updated = [...current, { id, type, title, message, duration }]
        return updated.slice(-5)
      })

      setTimeout(() => {
        removeToast(id)
      }, duration)
    },
    [removeToast]
  )

  const value = useMemo(
    () => ({
      addToast,
    }),
    [addToast]
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto">
            <Toast {...toast} onRemove={removeToast} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within ToastProvider')
  return context
}
