import GeneralCreditorsList from '../components/rules/GeneralCreditorsList'

export default function CreditorGeneralPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-slate-800 mb-1">Creditors (General)</h1>
      <p className="text-slate-500 text-sm mb-6">Rule Management / General Creditors</p>
      <GeneralCreditorsList />
    </div>
  )
}
