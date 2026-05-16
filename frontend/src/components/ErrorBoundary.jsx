import { Component } from 'react'

/**
 * ErrorBoundary — Catches rendering errors in child components.
 *
 * Prevents the entire app from crashing with a white screen when a
 * child component throws during rendering (e.g., from null/undefined
 * access on unexpected API data).
 *
 * Usage: Wrap the app or sections with <ErrorBoundary>...</ErrorBoundary>
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg border border-red-900 bg-gray-900 p-6 text-center">
          <span className="text-3xl">⚠️</span>
          <h2 className="mt-3 text-lg font-semibold text-red-400">
            Something went wrong
          </h2>
          <p className="mt-2 text-sm text-gray-400">
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <button
            onClick={this.handleReset}
            className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer"
          >
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary