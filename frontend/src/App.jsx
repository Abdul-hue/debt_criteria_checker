import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth.jsx'
import Layout from './components/Layout.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import Login from './pages/Login.jsx'
import CriteriaLookup from './pages/criteria/CriteriaLookup.jsx'
import DecisionHistory from './pages/criteria/DecisionHistory.jsx'
import RulesAdmin from './pages/criteria/RulesAdmin.jsx'
import CreditorAdmin from './pages/criteria/CreditorAdmin.jsx'

function App() {
  const { isAuthenticated } = useAuth()

  return (
    <div className="min-h-screen bg-[#f9fafb] text-[#111827]">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/criteria" element={<CriteriaLookup />} />
            <Route element={<ProtectedRoute adminOnly />}>
              <Route path="/criteria/history" element={<DecisionHistory />} />
              <Route path="/criteria/admin/rules" element={<RulesAdmin />} />
              <Route path="/criteria/admin/creditors" element={<CreditorAdmin />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<Navigate to={isAuthenticated ? '/criteria' : '/login'} replace />} />
      </Routes>
    </div>
  )
}

export default App
