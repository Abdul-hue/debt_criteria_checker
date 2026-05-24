import axios from 'axios'
import api from '../lib/axios'
import { mapCriteriaError } from '../utils/errorMessages'

const API_BASE = '/api'
const CRITERIA_BASE = '/api/v1/criteria'

const apiClient = axios.create({
  headers: { 'Content-Type': 'application/json' },
})

let isRefreshing = false
let pendingRequests = []

const getAccessToken = () => localStorage.getItem('criteria_access_token')
const getRefreshToken = () => localStorage.getItem('criteria_refresh_token')

const setTokens = (access, refresh) => {
  localStorage.setItem('criteria_access_token', access)
  localStorage.setItem('criteria_refresh_token', refresh)
  const payload = parseJwt(access)
  localStorage.setItem('criteria_user', JSON.stringify(payload || { username: payload?.username }))
}

const clearAuth = () => {
  localStorage.removeItem('criteria_access_token')
  localStorage.removeItem('criteria_refresh_token')
  localStorage.removeItem('criteria_user')
}

const redirectToLogin = () => {
  clearAuth()
  window.location.href = '/login'
}

const parseJwt = (token) => {
  if (!token) return null
  try {
    const [, payload] = token.split('.')
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decodeURIComponent(escape(decoded)))
  } catch (error) {
    return null
  }
}

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      if (!isRefreshing) {
        isRefreshing = true
        const refreshToken = getRefreshToken()
        if (!refreshToken) {
          logout()
          return Promise.reject(error)
        }
        try {
          const response = await axios.post(`${API_BASE}/token/refresh/`, { refresh: refreshToken })
          const access = response.data.access
          localStorage.setItem('criteria_access_token', access)
          const payload = parseJwt(access)
          if (payload) {
            localStorage.setItem('criteria_user', JSON.stringify(payload))
          }
          pendingRequests.forEach((callback) => callback(access))
          pendingRequests = []
          return apiClient(originalRequest)
        } catch (refreshError) {
          redirectToLogin()
          return Promise.reject(refreshError)
        } finally {
          isRefreshing = false
        }
      }
      return new Promise((resolve) => {
        pendingRequests.push((accessToken) => {
          originalRequest.headers.Authorization = `Bearer ${accessToken}`
          resolve(apiClient(originalRequest))
        })
      })
    }
    return Promise.reject(error)
  },
)

export const login = async (username, password) => {
  const response = await axios.post(`${API_BASE}/token/`, { username, password })
  const { access, refresh } = response.data
  setTokens(access, refresh)
  return getCurrentUser()
}

export const logout = () => {
  redirectToLogin()
}

export const getCurrentUser = () => {
  const json = localStorage.getItem('criteria_user')
  if (!json) return null
  try {
    return JSON.parse(json)
  } catch {
    return null
  }
}

export const assessCase = async (aryzaReference, clientName) => {
  const response = await apiClient.post(`${CRITERIA_BASE}/assess/`, {
    aryza_reference: aryzaReference,
    client_name: clientName || '',
  })
  return response.data
}

export const getHistory = async (params) => {
  const response = await apiClient.get(`${CRITERIA_BASE}/assess/history/`, { params })
  return response.data
}

export const getHistoryDetail = async (id) => {
  const response = await apiClient.get(`${CRITERIA_BASE}/assess/history/${id}/`)
  return response.data
}

export const getCreditors = async (params) => {
  const response = await apiClient.get(`${CRITERIA_BASE}/creditors/`, { params })
  return response.data
}

export const updateCreditor = async (id, data) => {
  const response = await apiClient.put(`${CRITERIA_BASE}/creditors/${id}/`, data)
  return response.data
}

export const getRules = async () => {
  const response = await apiClient.get(`${CRITERIA_BASE}/rules/?include=full`)
  return response.data
}

export const getRulesByCriteriaSet = async (criteriaSet) => {
  const response = await apiClient.get(`${CRITERIA_BASE}/rules/?criteria_set=${criteriaSet}&include=full`)
  return response.data
}

export const createRule = async (data) => {
  const response = await apiClient.post(`${CRITERIA_BASE}/rules/`, data)
  return response.data
}

export const updateRule = async (ruleKey, data) => {
  const response = await apiClient.put(`${CRITERIA_BASE}/rules/${ruleKey}/`, data)
  return response.data
}

/**
 * Sends a request to evaluate a specific case against the criteria engine.
 * @param {string|number} caseId - The ID of the application/case to evaluate
 * @returns {Promise<Object>} The parsed response data on success
 * @throws {Object} Typed error object on failure
 */
export const evaluateCase = async (caseId) => {
  try {
    const response = await api.post(`${CRITERIA_BASE}/cases/${caseId}/evaluate`)
    return response.data
  } catch (error) {
    throw mapCriteriaError(error)
  }
}

/**
 * Fetches the evaluation history for a specific case.
 * @param {string|number} caseId - The ID of the application/case
 * @param {number} page - The page number for pagination
 * @returns {Promise<Object>} The paginated history results
 * @throws {Object} Typed error object on failure
 */
export const getEvaluationHistory = async (caseId, page = 1) => {
  try {
    const response = await api.get(`${CRITERIA_BASE}/cases/${caseId}/evaluations?page=${page}`)
    return response.data
  } catch (error) {
    throw mapCriteriaError(error)
  }
}
