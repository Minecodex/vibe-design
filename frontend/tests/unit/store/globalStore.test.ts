import { describe, it, expect, beforeEach } from 'vitest'
import { useGlobalStore } from '@/store/globalStore'

describe('globalStore', () => {
    beforeEach(() => {
        useGlobalStore.setState({
            sidebarCollapsed: false,
            theme: 'light',
        })
    })

    it('should have initial state', () => {
        const state = useGlobalStore.getState()
        expect(state.sidebarCollapsed).toBe(false)
        expect(state.theme).toBe('light')
    })

    it('should toggle sidebar', () => {
        useGlobalStore.getState().toggleSidebar()
        expect(useGlobalStore.getState().sidebarCollapsed).toBe(true)

        useGlobalStore.getState().toggleSidebar()
        expect(useGlobalStore.getState().sidebarCollapsed).toBe(false)
    })

    it('should set sidebar collapsed', () => {
        useGlobalStore.getState().setSidebarCollapsed(true)
        expect(useGlobalStore.getState().sidebarCollapsed).toBe(true)

        useGlobalStore.getState().setSidebarCollapsed(false)
        expect(useGlobalStore.getState().sidebarCollapsed).toBe(false)
    })

    it('should set theme', () => {
        useGlobalStore.getState().setTheme('dark')
        expect(useGlobalStore.getState().theme).toBe('dark')

        useGlobalStore.getState().setTheme('light')
        expect(useGlobalStore.getState().theme).toBe('light')
    })
})
