import { useState } from 'react'
import { assessCase } from '../../services/criteriaService.js'
import ErrorCard from '../../components/shared/ErrorCard.jsx'
import Spinner from '../../components/shared/Spinner.jsx'
import DecisionResult from './DecisionResult.jsx'

export default function CriteriaLookup() {
  const [aryzaReference, setAryzaReference] = useState('')
  const [clientName, setClientName] = useState('')
  const [decision, setDecision] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError(null)
    setDecision(null)
    setLoading(true)

    try {
      const result = await assessCase(aryzaReference.trim(), clientName.trim())
      setDecision(result)
    } catch (err) {
      setError('Unable to fetch assessment. Please verify the reference and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-200 bg-[#f8fafc] p-8 shadow-sm">
        <div className="mb-4">
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-500">Criteria Lookup</p>
          <h2 className="mt-3 text-3xl font-semibold text-slate-900">Assess a case in real time</h2>
          <p className="mt-2 text-sm text-slate-600">Enter the Aryza reference and optional client name to review the latest decision from the criteria engine.</p>
        </div>

        {error && <ErrorCard message={error} />}

        <form className="grid gap-4 sm:grid-cols-[1fr_1fr]" onSubmit={handleSubmit}>
          <label className="block text-sm font-semibold text-slate-700">
            Aryza Reference
            <input
              required
              value={aryzaReference}
              onChange={(event) => setAryzaReference(event.target.value.toUpperCase())}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="ABCD1234"
            />
          </label>

          <label className="block text-sm font-semibold text-slate-700">
            Client name
            <input
              value={clientName}
              onChange={(event) => setClientName(event.target.value)}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="Optional client name"
            />
          </label>

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex w-full items-center justify-center rounded-3xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {loading ? <Spinner /> : 'Run assessment'}
            </button>
          </div>
        </form>
      </div>

      {decision && (
        <>
          {console.log('API result:', decision)}
          <DecisionResult result={decision} applicationId={aryzaReference} />
        </>
      )}
    </div>
  )
}
