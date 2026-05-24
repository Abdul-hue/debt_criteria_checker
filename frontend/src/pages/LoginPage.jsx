import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from 'react-router-dom'
import { loginSchema } from '../schemas/authSchema.js'
import { useAuth } from '../context/AuthContext.jsx'
import LoadingSpinner from '../components/shared/LoadingSpinner.jsx'

/**
 * LoginPage component
 * Displays a login form with email/password fields
 * Handles authentication and redirects on success
 */
export default function LoginPage() {
  const navigate = useNavigate()
  const { token, login, isAdmin } = useAuth()
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Redirect if already logged in
  useEffect(() => {
    if (token) {
      navigate(isAdmin ? '/admin' : '/assess', { replace: true })
    }
  }, [token, isAdmin, navigate])

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    try {
      const decoded = await login(data.email, data.password)
      const role = decoded?.role || (decoded?.is_admin || decoded?.is_staff ? 'admin' : 'assessor')
      navigate(role === 'admin' ? '/admin' : '/assess', { replace: true })
    } catch (err) {
      setError('Invalid credentials. Please try again.')
      console.error('Login failed:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        {/* Logo/Title */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">IVA Criteria Assessment Engine</h1>
          <p className="text-slate-600 mt-2">Creditor Assessment & Decision Tool</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Email Field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1">
              Email
            </label>
            <input
              {...register('email')}
              type="email"
              id="email"
              placeholder="admin@test.com"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
            {errors.email && <p className="text-red-600 text-sm mt-1">{errors.email.message}</p>}
          </div>

          {/* Password Field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              {...register('password')}
              type="password"
              id="password"
              placeholder="••••••••"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
            {errors.password && <p className="text-red-600 text-sm mt-1">{errors.password.message}</p>}
          </div>

          {/* Error Message */}
          {error && <div className="text-red-600 text-sm bg-red-50 p-3 rounded">{error}</div>}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-slate-800 text-white py-2 px-4 rounded-md hover:bg-slate-700 disabled:bg-slate-400 disabled:cursor-not-allowed transition-colors font-medium flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <>
                <LoadingSpinner size="sm" />
                <span>Signing in...</span>
              </>
            ) : (
              'Sign In'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
