export default function Spinner({ size = 20 }) {
  return (
    <div className="inline-flex items-center justify-center">
      <svg className="h-5 w-5 animate-spin text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
        <path d="M22 12a10 10 0 0 1-10 10" strokeLinecap="round" />
      </svg>
    </div>
  )
}
