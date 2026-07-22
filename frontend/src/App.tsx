import { RouterProvider } from 'react-router-dom'
import { router } from '@/router'
import { useIsDarkMode } from '@/hooks/useTheme'
import { Toaster } from 'sonner'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '@/store/authStore'
import { useAppConfigStore } from '@/store/appConfigStore'
import { getLocalizedAppName } from '@/config/brand'

function App() {
  const isDark = useIsDarkMode()
  const fetchDeployType = useAuthStore((s) => s.fetchDeployType)
  const fetchPublicConfig = useAppConfigStore((s) => s.fetchPublicConfig)
  const appName = useAppConfigStore((s) => s.appName)
  const appNameEn = useAppConfigStore((s) => s.appNameEn)
  const { i18n } = useTranslation()

  useEffect(() => {
    fetchDeployType()
    fetchPublicConfig()
  }, [fetchDeployType, fetchPublicConfig])

  useEffect(() => {
    document.title = getLocalizedAppName(i18n.language, { appName, appNameEn })
  }, [appName, appNameEn, i18n.language])

  return (
    <>
      <RouterProvider router={router} />
      <Toaster
        theme={isDark ? 'dark' : 'light'}
        position="top-center"
        richColors
        closeButton
      />
    </>
  )
}

export default App
