import CreditorsList from '../components/rules/CreditorsList'

export default function CreditorRepPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-slate-800 mb-1">Creditors (Representative)</h1>
      <p className="text-slate-500 text-sm mb-6">Rule Management / Which Representative</p>
      <CreditorsList />
    </div>
  )
}
