import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import LoadingSpinner from './shared/LoadingSpinner.jsx'

/**
 * AdminRoute wraps routes that require the admin role.
 * - Not authenticated → redirect to /login
 * - Authenticated but not admin → redirect to /assess with reason state
 * - Authenticated and admin → render child routes
 */
export default function AdminRoute() {
  const { token, isAdmin, isLoading } = useAuth()

  if (isLoading) {
    return <LoadingSpinner fullScreen />
  }

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (!isAdmin) {
    return <Navigate to="/assess" replace state={{ reason: 'insufficient_permissions' }} />
  }

  return <Outlet />
}
