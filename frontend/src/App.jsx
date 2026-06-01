import React, { Suspense } from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import PrivateRoute from './components/PrivateRoute.jsx'
import AdminRoute from './components/AdminRoute.jsx'
import LoginPage from './pages/LoginPage.jsx'
import LoadingSpinner from './components/shared/LoadingSpinner.jsx'
import { useAuth } from './context/AuthContext.jsx'
import { useFeatureAccess } from './hooks/useFeatureAccess.js'

// Lazy-loaded page components
const AssessPage = React.lazy(() => import('./pages/AssessPage.jsx'))
const RulesPage = React.lazy(() => import('./pages/RulesPage.jsx'))
const UserManagementPage = React.lazy(() => import('./pages/UserManagementPage.jsx'))
const AdminDashboard = React.lazy(() => import('./pages/admin/AdminDashboard.jsx'))
const DecisionsPage = React.lazy(() => import('./pages/admin/DecisionsPage.jsx'))
const SFSGuidelinesPage = React.lazy(() => import('./pages/admin/SFSGuidelinesPage.jsx'))
const DepartmentPage = React.lazy(() => import('./pages/DepartmentPage.jsx'))
const NoAccessPage = React.lazy(() => import('./pages/NoAccessPage.jsx'))
const DepartmentDashboard = React.lazy(() => import('./pages/DepartmentDashboard.jsx'))
const CreditorGeneralPage = React.lazy(() => import('./pages/CreditorGeneralPage.jsx'))
const CreditorRepPage = React.lazy(() => import('./pages/CreditorRepPage.jsx'))
const CouncilsPage = React.lazy(() => import('./pages/CouncilsPage.jsx'))
const DividendsPage = React.lazy(() => import('./pages/DividendsPage.jsx'))
const EvidencePage = React.lazy(() => import('./pages/EvidencePage.jsx'))

/**
 * FeatureRoute — redirects to /no-access if the user's department
 * does not have the required feature enabled. Admins always pass.
 */
function FeatureRoute({ featureKey, children }) {
  const { hasFeature, isLoading } = useFeatureAccess()
  const { isAdmin } = useAuth()
  if (isAdmin) return children
  if (isLoading) return <LoadingSpinner fullScreen />
  if (!hasFeature(featureKey)) return <Navigate to="/no-access" replace />
  return children
}

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
 * RootRedirect — sends admins to /admin, all other authenticated users to /dashboard
 */
function RootRedirect() {
  const { isAdmin, isLoading, token } = useAuth()

  if (isLoading) return <LoadingSpinner fullScreen />
  if (!token) return <Navigate to="/login" replace />
  if (isAdmin) return <Navigate to="/admin" replace />
  return <Navigate to="/dashboard" replace />
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

          {/* Assess page — gated by run_assessment feature */}
          <Route
            path="/assess"
            element={
              <FeatureRoute featureKey="run_assessment">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <AssessPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Rules page — gated by global_rules feature */}
          <Route
            path="/rules"
            element={
              <FeatureRoute featureKey="global_rules">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <RulesPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Decisions page — gated by decisions feature */}
          <Route
            path="/decisions"
            element={
              <FeatureRoute featureKey="decisions">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <DecisionsPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* SFS Guidelines — gated by sfs_guidelines feature */}
          <Route
            path="/sfs"
            element={
              <FeatureRoute featureKey="sfs_guidelines">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <SFSGuidelinesPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Creditors (General) — gated by general_creditors feature */}
          <Route
            path="/creditors"
            element={
              <FeatureRoute featureKey="general_creditors">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <CreditorGeneralPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Creditors (Representative) — gated by representative_creditors feature */}
          <Route
            path="/creditors/rep"
            element={
              <FeatureRoute featureKey="representative_creditors">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <CreditorRepPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Councils — gated by councils feature */}
          <Route
            path="/councils"
            element={
              <FeatureRoute featureKey="councils">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <CouncilsPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Dividends — gated by dividends feature */}
          <Route
            path="/dividends"
            element={
              <FeatureRoute featureKey="dividends">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <DividendsPage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Evidence — gated by evidence feature */}
          <Route
            path="/evidence"
            element={
              <FeatureRoute featureKey="evidence">
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <EvidencePage />
                </Suspense>
              </FeatureRoute>
            }
          />

          {/* Department Dashboard — always accessible to authenticated non-admins */}
          <Route
            path="/dashboard"
            element={
              <Suspense fallback={<LoadingSpinner fullScreen />}>
                <DepartmentDashboard />
              </Suspense>
            }
          />

          {/* No access page */}
          <Route
            path="/no-access"
            element={
              <Suspense fallback={<LoadingSpinner fullScreen />}>
                <NoAccessPage />
              </Suspense>
            }
          />

          {/* Legacy redirect */}
          <Route path="/unauthorized" element={<Navigate to="/no-access" replace />} />

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

            {/* SFS Expenditure Guidelines */}
            <Route
              path="/admin/sfs-guidelines"
              element={
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <SFSGuidelinesPage />
                </Suspense>
              }
            />

            {/* Departments */}
            <Route
              path="/admin/departments"
              element={
                <Suspense fallback={<LoadingSpinner fullScreen />}>
                  <DepartmentPage />
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
