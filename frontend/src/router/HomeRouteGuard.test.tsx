import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

const authStoreState = {
  licenseEdition: 'flagship' as 'flagship' | 'premium' | null,
}

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authStoreState) => unknown) =>
    selector ? selector(authStoreState) : authStoreState,
}))

import { HomeRouteGuard } from './HomeRouteGuard'

describe('HomeRouteGuard', () => {
  it('renders children for flagship edition', () => {
    authStoreState.licenseEdition = 'flagship'

    render(
      <MemoryRouter initialEntries={['/dashboard/home']}>
        <Routes>
          <Route
            path="/dashboard/home"
            element={(
              <HomeRouteGuard>
                <div>home-page</div>
              </HomeRouteGuard>
            )}
          />
          <Route path="/dashboard/projects" element={<div>projects-page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('home-page')).toBeInTheDocument()
  })

  it('redirects premium edition away from home', () => {
    authStoreState.licenseEdition = 'premium'

    render(
      <MemoryRouter initialEntries={['/dashboard/home']}>
        <Routes>
          <Route
            path="/dashboard/home"
            element={(
              <HomeRouteGuard>
                <div>home-page</div>
              </HomeRouteGuard>
            )}
          />
          <Route path="/dashboard/projects" element={<div>projects-page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('projects-page')).toBeInTheDocument()
    expect(screen.queryByText('home-page')).not.toBeInTheDocument()
  })
})
