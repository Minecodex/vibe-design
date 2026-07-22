import type { WheelEvent } from 'react'

export function handleScrollableWheel(event: WheelEvent<HTMLElement>) {
  if (event.ctrlKey) {
    return
  }

  event.stopPropagation()
}
