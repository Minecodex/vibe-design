import { createBrowserRouter, Navigate } from 'react-router-dom'
import { PrivateRoute } from './PrivateRoute'
import { HomeRouteGuard } from './HomeRouteGuard'
import { MainLayout } from '@/components/common/MainLayout'
import { LoginPage } from '@/pages/LoginPage'
import { UserDetailPage } from '@/pages/dashboard/UserPage/UserDetailPage'
import { SettingsPage } from '@/pages/dashboard/SettingsPage'
import { ProvidersPage } from '@/pages/dashboard/ProvidersPage'
import { ProjectsPage } from '@/pages/dashboard/ProjectsPage'
import { ChatHomePage } from '@/pages/dashboard/HomeHarnessAgent'
import { CanvasPage } from '@/pages/dashboard/CanvasPage'
import { ShareViewPage } from '@/pages/dashboard/ShareViewPage'
import { AssetsPage } from '@/pages/dashboard/Assets'
import { ReferenceGalleryPage } from '@/pages/dashboard/ReferenceGallery'

const devOnlyRoutes = import.meta.env.DEV
  ? [
    {
      path: '/__canvas-perf',
      lazy: async () => {
        const { CanvasPerfHarnessPage } = await import('@/pages/dashboard/CanvasPage/components/CanvasPerfHarnessPage')
        return { Component: CanvasPerfHarnessPage }
      },
    },
    {
      path: '/__style-demo',
      lazy: async () => {
        const { StyleDemoPage } = await import('@/pages/StyleDemoPage')
        return { Component: StyleDemoPage }
      },
    },
  ]
  : []

export const router = createBrowserRouter([
  ...devOnlyRoutes,
  {
    path: '/',
    element: <LoginPage />,
  },
  {
    path: '/share/:token',
    element: <ShareViewPage />,
  },
  {
    path: '/canvas/:id',
    element: (
      <PrivateRoute>
        <CanvasPage />
      </PrivateRoute>
    ),
  },
  {
    path: '/dashboard',
    element: (
      <PrivateRoute>
        <MainLayout />
      </PrivateRoute>
    ),
    children: [
      { index: true, element: <Navigate to="projects" replace /> },
      { path: 'home', element: <HomeRouteGuard><ChatHomePage /></HomeRouteGuard> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'assets', element: <AssetsPage /> },
      { path: 'reference-gallery', element: <ReferenceGalleryPage /> },
      { path: 'users/:id', element: <UserDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'providers', element: <ProvidersPage /> },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
