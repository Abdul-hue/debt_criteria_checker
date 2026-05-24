import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import LoadingSpinner from './shared/LoadingSpinner.jsx'

/**
 * PrivateRoute component wraps protected routes
 * Shows loading spinner while auth is initializing
 * Redirects to /login if no token
 * Otherwise renders the child route
 */
export default function PrivateRoute() {
  const { token, isLoading } = useAuth()

  if (isLoading) {
    return <LoadingSpinner fullScreen />
  }

  if (!token) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
