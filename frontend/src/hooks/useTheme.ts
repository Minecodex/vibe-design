import { useEffect, useState } from 'react'
import { useGlobalStore } from '@/store/globalStore'

export function useIsDarkMode() {
  const theme = useGlobalStore((state) => state.theme)
  const [systemIsDark, setSystemIsDark] = useState(
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemIsDark(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  const isDark = theme === 'system' ? systemIsDark : theme === 'dark'

  // Sync dark class on <html> for Tailwind CSS dark mode
  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
  }, [isDark])

  return isDark
}
