import { useEffect, useMemo, useState } from 'react'
import { getCurrentUser, login as loginRequest, logout as logoutRequest } from '../services/criteriaService.js'

export function useAuth() {
  const [user, setUser] = useState(() => getCurrentUser())

  useEffect(() => {
    const currentUser = getCurrentUser()
    setUser(currentUser)
  }, [])

  const isAuthenticated = useMemo(() => Boolean(user), [user])
  const isAdmin = useMemo(() => Boolean(user?.is_staff), [user])

  const login = async (username, password) => {
    const loggedUser = await loginRequest(username, password)
    setUser(loggedUser)
    return loggedUser
  }

  const logout = () => {
    logoutRequest()
    setUser(null)
  }

  return { user, isAuthenticated, isAdmin, login, logout }
}
