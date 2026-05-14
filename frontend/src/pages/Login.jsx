import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import ErrorCard from '../components/shared/ErrorCard.jsx'
import Spinner from '../components/shared/Spinner.jsx'

export default function Login() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (isAuthenticated) {
    return <Navigate to="/criteria" replace />
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError(null)

    try {
      await login(username, password)
      toast.success('You are signed in successfully.')
      navigate('/criteria')
    } catch (err) {
      setError('Unable to sign in. Please check your credentials and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f3f4f6] px-4 py-10">
      <div className="w-full max-w-md rounded-[2rem] border border-slate-200 bg-white p-10 shadow-lg">
        <div className="mb-8 text-center">
          <p className="text-sm uppercase tracking-[0.28em] text-slate-500">Criteria Engine</p>
          <h1 className="mt-4 text-3xl font-semibold text-slate-900">Sign in to continue</h1>
          <p className="mt-3 text-sm text-slate-500">Access the assessment dashboard and administration tools.</p>
        </div>

        {error && <ErrorCard message={error} />}

        <form className="space-y-5" onSubmit={handleSubmit}>
          <label className="block text-sm font-semibold text-slate-700">
            Username
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="Enter your username"
              autoComplete="username"
            />
          </label>

          <label className="block text-sm font-semibold text-slate-700">
            Password
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-3 block w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
              placeholder="Enter your password"
              type="password"
              autoComplete="current-password"
            />
          </label>

          <button
            type="submit"
            className="inline-flex w-full items-center justify-center rounded-3xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={loading}
          >
            {loading ? <Spinner /> : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
