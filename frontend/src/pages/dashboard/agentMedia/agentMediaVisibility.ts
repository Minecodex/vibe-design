import { useEffect, useRef, useState } from 'react'

export function useAgentViewportReady(loadMode: 'viewport' | 'immediate' = 'viewport') {
  const ref = useRef<HTMLElement | null>(null)
  const [ready, setReady] = useState(loadMode === 'immediate')

  useEffect(() => {
    if (loadMode === 'immediate') {
      setReady(true)
      return
    }
    const element = ref.current
    if (!element) {
      return
    }
    if (typeof IntersectionObserver === 'undefined') {
      setReady(true)
      return
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting || entry.intersectionRatio > 0)) {
        setReady(true)
        observer.disconnect()
      }
    }, { rootMargin: '800px 0px' })
    observer.observe(element)
    return () => observer.disconnect()
  }, [loadMode])

  return { ref, ready }
}
