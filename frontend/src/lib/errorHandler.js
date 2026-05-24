/**
 * Error handling utilities for consistent API error handling
 */

/**
 * Returns a human-readable message from an Axios error response
 */
export function extractErrorMessage(error) {
  if (!error) return 'An unknown error occurred'

  // 1. Check for explicit error detail from backend (Django REST Framework style)
  if (error.response?.data?.detail) {
    return error.response.data.detail
  }

  // 2. Check for message field
  if (error.response?.data?.message) {
    return error.response.data.message
  }

  // 3. Check if the response data itself is a string
  if (typeof error.response?.data === 'string' && error.response.data.length < 200) {
    return error.response.data
  }

  // 4. Handle specific HTTP status codes if no message provided
  if (error.response?.status) {
    switch (error.response.status) {
      case 400: return 'Invalid request data'
      case 401: return 'Your session has expired. Please log in again.'
      case 403: return 'You do not have permission to perform this action.'
      case 404: return 'The requested resource was not found.'
      case 500: return 'Server error. Please try again later.'
      default: return `Error: ${error.response.statusText || error.response.status}`
    }
  }

  // 5. Handle network errors (no response)
  if (error.request) {
    return 'Network error. Please check your internet connection.'
  }

  // 6. Fallback to standard error message
  return error.message || 'An unexpected error occurred'
}

/**
 * Returns true if error.response.status === 401
 */
export function isAuthError(error) {
  return error?.response?.status === 401
}

/**
 * Returns true if error.response.status === 404
 */
export function isNotFoundError(error) {
  return error?.response?.status === 404
}

/**
 * Returns true if error.response.status === 400
 */
export function isValidationError(error) {
  return error?.response?.status === 400
}
