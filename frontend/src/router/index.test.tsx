import { isValidElement, type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./PrivateRoute', () => ({
  PrivateRoute: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock('./HomeRouteGuard', () => ({
  HomeRouteGuard: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/common/MainLayout', () => ({
  MainLayout: () => <Outlet />,
}))

vi.mock('@/pages/LoginPage', () => ({
  LoginPage: () => <div>login-page</div>,
}))

vi.mock('@/pages/ActivationPage', () => ({
  ActivationPage: () => <div>activation-page</div>,
}))

vi.mock('@/pages/dashboard/UserPage/UserDetailPage', () => ({
  UserDetailPage: () => <div>user-detail-page</div>,
}))

vi.mock('@/pages/dashboard/SettingsPage', () => ({
  SettingsPage: () => <div>settings-page</div>,
}))

vi.mock('@/pages/dashboard/ProvidersPage', () => ({
  ProvidersPage: () => <div>providers-page</div>,
}))

vi.mock('@/pages/dashboard/ProjectsPage', () => ({
  ProjectsPage: () => <div>projects-page</div>,
}))

vi.mock('@/pages/dashboard/HomeHarnessAgent', () => ({
  ChatHomePage: () => <div>home-page</div>,
}))

vi.mock('@/pages/dashboard/CanvasPage', () => ({
  CanvasPage: () => <div>canvas-page</div>,
}))

vi.mock('@/pages/dashboard/ShareViewPage', () => ({
  ShareViewPage: () => <div>share-view-page</div>,
}))

vi.mock('@/pages/dashboard/Assets', () => ({
  AssetsPage: () => <div>assets-page</div>,
}))

import { router } from './index'

describe('router', () => {
  it('redirects /dashboard to /dashboard/projects', () => {
    const dashboardRoute = router.routes.find((route) => route.path === '/dashboard')
    const dashboardIndexRoute = dashboardRoute?.children?.find((route) => route.index)

    const element = dashboardIndexRoute && 'element' in dashboardIndexRoute ? dashboardIndexRoute.element : undefined
    expect(isValidElement(element) ? element.props : null).toMatchObject({
      to: 'projects',
      replace: true,
    })
  })
})
