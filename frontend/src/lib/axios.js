import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const STORAGE_KEY = 'debt_assessment_token'

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

// Response interceptor: handle 401 errors
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear token from localStorage
      localStorage.removeItem(STORAGE_KEY)

      // Dispatch custom DOM event for AuthContext to react without circular import
      window.dispatchEvent(new Event('auth:logout'))
    }
    return Promise.reject(error)
  }
)

export default axiosInstance
export { STORAGE_KEY }
