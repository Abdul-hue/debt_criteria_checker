import { Component } from 'react'
import Layout from './Layout.jsx'

/**
 * ErrorBoundary component catches errors in child components
 * and displays a fallback UI
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
    }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by ErrorBoundary:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      const fallbackUI = (
        <div className="max-w-md mx-auto mt-20">
          <div className="bg-white border border-red-200 rounded-lg p-6 shadow-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                <span className="text-red-600 text-xl font-bold">!</span>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">An unexpected error occurred</h2>
            </div>
            
            <p className="text-sm text-gray-600 mb-6">
              {this.state.error?.message || 'Something went wrong. Please try again.'}
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => window.location.reload()}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded transition-colors font-medium text-sm"
              >
                Reload Page
              </button>
              <button
                onClick={() => window.location.href = '/login'}
                className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 px-4 rounded transition-colors font-medium text-sm"
              >
                Go to Login
              </button>
            </div>
          </div>
        </div>
      )

      // Wrap the fallback in the <Layout /> shell if possible
      // This works if the error happened inside a page component
      return (
        <Layout>
          {fallbackUI}
        </Layout>
      )
    }

    return this.props.children
  }
}
