import { QueryClient, QueryCache } from '@tanstack/react-query'

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      // Check error?.response?.status === 401
      if (error?.response?.status === 401) {
        // Dispatch 'auth:logout' DOM event on 401 responses
        const event = new CustomEvent('auth:logout')
        window.dispatchEvent(event)
      }
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
      gcTime: 10 * 60 * 1000, // TanStack Query v5 uses gcTime, not cacheTime
    },
  },
})

export default queryClient
