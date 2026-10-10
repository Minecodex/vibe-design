import type { WheelEvent } from 'react'

export function handleScrollableWheel(event: Pick<WheelEvent<HTMLElement>, 'ctrlKey' | 'stopPropagation'>) {
  if (event.ctrlKey) {
    return
  }

  event.stopPropagation()
}
