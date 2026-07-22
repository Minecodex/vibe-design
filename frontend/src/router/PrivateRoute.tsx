import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { storage } from '@/utils/storage'

interface PrivateRouteProps {
  children: React.ReactNode
}

export function PrivateRoute({ children }: PrivateRouteProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const location = useLocation()

  // Check for stale auth state: persisted isAuthenticated but no actual token
  const token = storage.getToken()
  if (isAuthenticated && !token) {
    useAuthStore.setState({ user: null, isAuthenticated: false, error: null })
    return <Navigate to="/?login=true" state={{ from: location }} replace />
  }

  if (!isAuthenticated) {
    return <Navigate to="/?login=true" state={{ from: location }} replace />
  }

  return <>{children}</>
}
