import React from 'react'
import { Inbox } from 'lucide-react'

/**
 * EmptyState component
 * Displays a centred empty state display when no data is available
 */
export default function EmptyState({
  icon = <Inbox className="w-12 h-12 text-slate-300" />,
  title,
  message,
  action,
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {/* Icon */}
      <div className="mb-4 flex items-center justify-center">
        {icon}
      </div>

      {/* Title */}
      <h3 className="text-lg font-semibold text-slate-900">
        {title}
      </h3>

      {/* Message */}
      {message && (
        <p className="mt-2 text-sm text-slate-500 max-w-sm mx-auto">
          {message}
        </p>
      )}

      {/* Action CTA */}
      {action && (
        <div className="mt-6">
          {action}
        </div>
      )}
    </div>
  )
}
