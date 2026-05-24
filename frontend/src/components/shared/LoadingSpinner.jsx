/**
 * LoadingSpinner component
 * @param {string} size - Size of spinner: sm | md | lg (default: md)
 * @param {boolean} fullScreen - Whether to show as full-screen overlay (default: false)
 */
export default function LoadingSpinner({ size = 'md', fullScreen = false }) {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  }

  const spinnerContent = (
    <svg
      className={`${sizeClasses[size]} animate-spin text-slate-600`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      role="status"
      aria-label="Loading"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )

  if (fullScreen) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-white/80 backdrop-blur-sm z-50">
        <div className="flex items-center justify-center">{spinnerContent}</div>
      </div>
    )
  }

  return <div className="flex items-center justify-center p-4">{spinnerContent}</div>
}
