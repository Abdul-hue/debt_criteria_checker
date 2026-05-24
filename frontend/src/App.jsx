import React, { Suspense } from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import PrivateRoute from './components/PrivateRoute.jsx'
import AdminRoute from './components/AdminRoute.jsx'
import LoginPage from './pages/LoginPage.jsx'
import LoadingSpinner from './components/shared/LoadingSpinner.jsx'
import { useAuth } from './context/AuthContext.jsx'

// Lazy-loaded page components
const AssessPage = React.lazy(() => import('./pages/AssessPage.jsx'))
const RulesPage = React.lazy(() => import('./pages/RulesPage.jsx'))
const UserManagementPage = React.lazy(() => import('./pages/UserManagementPage.jsx'))
const AdminDashboard = React.lazy(() => import('./pages/admin/AdminDashboard.jsx'))
const DecisionsPage = React.lazy(() => import('./pages/admin/DecisionsPage.jsx'))

/**
 * LayoutWrapper - wraps Layout with Outlet as children
 */
function LayoutWrapper() {
  return (
    <Layout>
      <Outlet />
    </Layout>
  )
}

/**
 * RootRedirect — sends admins to /admin, assessors to /assess
 */
function RootRedirect() {
  const { isAdmin, isLoading, token } = useAuth()

  if (isLoading) return <LoadingSpinner fullScreen />
  if (!token) return <Navigate to="/login" replace />
  return <Navigate to={isAdmin ? '/admin' : '/assess'} replace />
}

/**
 * App component
 * Sets up React Router v6 with public and private routes
 */
function App() {
  return (
    <Routes>
      {/* Public route: Login */}
      <Route path="/login" element={<LoginPage />} />

      {/* Root redirect — role-aware */}
      <Route path="/" element={<RootRedirect />} />

      {/* Private routes */}
      <Route element={<PrivateRoute />}>
        <Route element={<LayoutWrapper />}>

          {/* Assess page */}
          <Route
            path="/assess"
            element={
              <Suspense fallback={<LoadingSpinner fullScreen />}>
                <AssessPage />
              </Suspense>
            }
          />

          {/* Rules page */}
          <Route
            path="/rules"
            element={
              <Suspense fallback={<LoadingSpinner fullScreen />}>
                <RulesPage />
              </Suspense>
            }
          />

          {/* Admin-only routes */}
          <Route element={<AdminRoute />}>

            {/* Admin Dashboard */}
            <Route
              path="/admin"
              element={
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <AdminDashboard />
                </Suspense>
              }
            />

            {/* User Management */}
            <Route
              path="/admin/users"
              element={
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <UserManagementPage />
                </Suspense>
              }
            />

            {/* Redirects for removed pages */}
            <Route path="/admin/applications" element={<Navigate to="/assess" replace />} />
            <Route path="/admin/evidence" element={<Navigate to="/assess" replace />} />
            <Route path="/admin/voters" element={<Navigate to="/assess" replace />} />

            {/* Decisions (read-only + delete) */}
            <Route
              path="/admin/decisions"
              element={
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <DecisionsPage />
                </Suspense>
              }
            />

          </Route>
        </Route>
      </Route>

      {/* Catch-all: redirect to root (which will role-redirect) */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
