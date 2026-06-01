import CouncilsList from '../components/rules/CouncilsList'

export default function CouncilsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-slate-800 mb-1">Councils</h1>
      <p className="text-slate-500 text-sm mb-6">Rule Management / Councils</p>
      <CouncilsList />
    </div>
  )
}
