import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { jwtDecode } from 'jwt-decode'
import axiosInstance, { STORAGE_KEY, REFRESH_KEY } from '../lib/axios.js'

const AuthContext = createContext(null)

// Extract role string from decoded JWT payload.
// Reads payload.role first; falls back to is_admin/is_staff booleans for older tokens.
function extractRole(decoded) {
  if (decoded.role) return decoded.role
  return decoded.is_admin || decoded.is_staff ? 'admin' : 'assessor'
}

export function AuthProvider({ children }) {
  const [state, setState] = useState({
    user: null,
    token: null,
    role: null,
    isLoading: true,
  })

  useEffect(() => {
    const initializeAuth = () => {
      const token = localStorage.getItem(STORAGE_KEY)
      if (token) {
        try {
          const decoded = jwtDecode(token)
          if (decoded.exp && decoded.exp > Date.now() / 1000) {
            setState({
              user: decoded,
              token,
              role: extractRole(decoded),
              isLoading: false,
            })
          } else {
            localStorage.removeItem(STORAGE_KEY)
            localStorage.removeItem(REFRESH_KEY)
            setState((prev) => ({ ...prev, isLoading: false }))
          }
        } catch (error) {
          console.error('Failed to decode token:', error)
          localStorage.removeItem(STORAGE_KEY)
          localStorage.removeItem(REFRESH_KEY)
          setState((prev) => ({ ...prev, isLoading: false }))
        }
      } else {
        setState((prev) => ({ ...prev, isLoading: false }))
      }
    }

    initializeAuth()
  }, [])

  // Listen for auth:logout DOM event (fired by Axios interceptor on refresh failure)
  useEffect(() => {
    const handleLogout = () => {
      setState({
        user: null,
        token: null,
        role: null,
        isLoading: false,
      })
    }

    window.addEventListener('auth:logout', handleLogout)
    return () => window.removeEventListener('auth:logout', handleLogout)
  }, [])

  const login = useCallback(async (email, password) => {
    try {
      const response = await axiosInstance.post('/api/token/', {
        email,
        password,
      })
      const { access, refresh } = response.data
      localStorage.setItem(STORAGE_KEY, access)
      if (refresh) {
        localStorage.setItem(REFRESH_KEY, refresh)
      }
      const decoded = jwtDecode(access)
      setState({
        user: decoded,
        token: access,
        role: extractRole(decoded),
        isLoading: false,
      })
      return decoded
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setState({
      user: null,
      token: null,
      role: null,
      isLoading: false,
    })
  }, [])

  // isAdmin is derived, not stored, so it stays consistent with role at all times
  const isAdmin = state.role === 'admin'

  return (
    <AuthContext.Provider
      value={{
        ...state,
        isAdmin,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
