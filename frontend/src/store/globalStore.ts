import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

interface GlobalState {
  sidebarCollapsed: boolean
  theme: 'light' | 'dark' | 'system'
  dismissedBalanceAlert: boolean
}

interface GlobalActions {
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setTheme: (theme: 'light' | 'dark' | 'system') => void
  setDismissedBalanceAlert: (dismissed: boolean) => void
}

export const useGlobalStore = create<GlobalState & GlobalActions>()(
  devtools(
    persist(
      (set) => ({
        sidebarCollapsed: false,
        theme: 'system',
        dismissedBalanceAlert: false,

        toggleSidebar: () =>
          set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
        setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
        setTheme: (theme) => set({ theme }),
        setDismissedBalanceAlert: (dismissed) => set({ dismissedBalanceAlert: dismissed }),
      }),
      {
        name: 'global-storage-v2',
      }
    ),
    { name: 'GlobalStore' }
  )
)

