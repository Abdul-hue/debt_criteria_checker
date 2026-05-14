export default function ErrorCard({ message }) {
  return (
    <div className="rounded-3xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900">
      <p className="font-semibold">Error</p>
      <p className="mt-1">{message}</p>
    </div>
  )
}
