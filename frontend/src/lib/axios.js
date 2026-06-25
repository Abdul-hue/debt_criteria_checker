import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const STORAGE_KEY = 'debt_assessment_token'
const REFRESH_KEY = 'debt_assessment_refresh_token'

const axiosInstance = axios.create({
  baseURL: API_BASE,
})

// Request interceptor: add Authorization header if token exists
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem(STORAGE_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Token refresh state
let isRefreshing = false
let pendingQueue = []

const processQueue = (error, token = null) => {
  pendingQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  pendingQueue = []
}

// Response interceptor: attempt token refresh on 401 before logging out
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = localStorage.getItem(REFRESH_KEY)

      if (!refreshToken) {
        localStorage.removeItem(STORAGE_KEY)
        window.dispatchEvent(new Event('auth:logout'))
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject })
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return axiosInstance(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const response = await axios.post(`${API_BASE}/api/token/refresh/`, {
          refresh: refreshToken,
        })
        const newAccess = response.data.access
        localStorage.setItem(STORAGE_KEY, newAccess)
        axiosInstance.defaults.headers.common.Authorization = `Bearer ${newAccess}`
        processQueue(null, newAccess)
        originalRequest.headers.Authorization = `Bearer ${newAccess}`
        return axiosInstance(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        localStorage.removeItem(STORAGE_KEY)
        localStorage.removeItem(REFRESH_KEY)
        window.dispatchEvent(new Event('auth:logout'))
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default axiosInstance
export { STORAGE_KEY, REFRESH_KEY }
