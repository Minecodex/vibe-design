import { useEffect, useRef, useState } from 'react'

type UseProjectCardVisibilityOptions = {
  disabled?: boolean
  resetKey?: string
  rootMargin?: string
}

export function useProjectCardVisibility<T extends Element>({
  disabled = false,
  resetKey,
  rootMargin = '240px 0px',
}: UseProjectCardVisibilityOptions = {}) {
  const ref = useRef<T | null>(null)
  const [isActive, setIsActive] = useState(disabled)

  useEffect(() => {
    setIsActive(disabled)
  }, [disabled, resetKey])

  useEffect(() => {
    if (disabled) {
      setIsActive(true)
      return
    }

    if (isActive) {
      return
    }

    const target = ref.current
    if (!target) {
      return
    }

    if (typeof IntersectionObserver === 'undefined') {
      setIsActive(true)
      return
    }

    const observer = new IntersectionObserver(
      entries => {
        const [entry] = entries
        if (entry?.isIntersecting) {
          setIsActive(true)
          observer.disconnect()
        }
      },
      {
        root: null,
        rootMargin,
      }
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [disabled, isActive, resetKey, rootMargin])

  return { isActive, ref }
}
