export const CRITERIA_ENGINE_ERRORS = {
  CASE_NOT_FOUND:   "This case could not be found. Please check the reference and try again.",
  INCOMPLETE_DATA:  "Some required information is missing from this case. Please review the case details.",
  ENGINE_ERROR:     "The assessment engine encountered an unexpected error. Please try again or contact support.",
  UNAUTHORISED:     "Your session has expired. Please log in again.",
  NETWORK_ERROR:    "Could not reach the server. Please check your connection and try again.",
  UNKNOWN:          "An unexpected error occurred. Please try again.",
}

/**
 * Maps HTTP status codes or network errors to CRITERIA_ENGINE_ERRORS
 * @param {Error} error - The axios error object
 * @returns {Object} Typed error object { code, message, raw }
 */
export function mapCriteriaError(error) {
  let code = 'UNKNOWN'
  
  if (!error.response) {
    code = 'NETWORK_ERROR'
  } else {
    switch (error.response.status) {
      case 404:
        code = 'CASE_NOT_FOUND'
        break
      case 422:
        code = 'INCOMPLETE_DATA'
        break
      case 401:
        code = 'UNAUTHORISED'
        break
      case 500:
        code = 'ENGINE_ERROR'
        break
      default:
        code = 'UNKNOWN'
    }
  }

  return {
    code,
    message: CRITERIA_ENGINE_ERRORS[code] || CRITERIA_ENGINE_ERRORS.UNKNOWN,
    raw: error
  }
}
