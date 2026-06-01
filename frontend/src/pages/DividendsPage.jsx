import DividendsList from '../components/rules/DividendsList'

export default function DividendsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-slate-800 mb-1">Dividends</h1>
      <p className="text-slate-500 text-sm mb-6">Rule Management / Dividends</p>
      <DividendsList />
    </div>
  )
}
