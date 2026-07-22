import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuthStore } from '@/store/authStore'
import { canAccessHomeAgent } from '@/utils/licenseAccess'

export function HomeRouteGuard({ children }: { children: ReactNode }) {
  const licenseEdition = useAuthStore((state) => state.licenseEdition)

  if (!canAccessHomeAgent(licenseEdition)) {
    return <Navigate to="/dashboard/projects" replace />
  }

  return <>{children}</>
}
