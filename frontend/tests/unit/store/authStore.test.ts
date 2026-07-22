import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '@/store/authStore'

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    })
    localStorage.clear()
  })

  it('initial state should be unauthenticated', () => {
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
    expect(state.error).toBeNull()
  })

  it('login should set user and isAuthenticated', async () => {
    await useAuthStore.getState().login({
      account: 'test@example.com',
      password: 'Test1234!',
    })

    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.user?.email).toBe('test@example.com')
    expect(state.error).toBeNull()
  })

  it('logout should clear user state', async () => {
    useAuthStore.setState({ user: { id: 1, email: 'test@example.com', username: 'test', role: 'user', is_active: true }, isAuthenticated: true })

    await useAuthStore.getState().logout()

    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  it('clearError should reset error', () => {
    useAuthStore.setState({ error: 'some error' })
    useAuthStore.getState().clearError()
    expect(useAuthStore.getState().error).toBeNull()
  })

  it('fetchDeployType should store license status from health response', async () => {
    await useAuthStore.getState().fetchDeployType()

    const state = useAuthStore.getState()
    expect(state.deployType).toBe('private')
    expect(state.licenseExpired).toBe(false)
    expect(state.licenseExpiresAt).toBe('2099-12-31T23:59:59+08:00')
  })
})
