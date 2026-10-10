import { describe, expect, it, vi } from 'vitest'

import { handleScrollableWheel } from './scrollableWheel'

describe('handleScrollableWheel', () => {
  it('stops propagation and lets the browser handle normal dropdown scrolling', () => {
    const preventDefault = vi.fn()
    const stopPropagation = vi.fn()
    const currentTarget = { scrollTop: 20 }
    const event = {
      ctrlKey: false,
      deltaY: 15,
      preventDefault,
      stopPropagation,
      currentTarget,
      nativeEvent: { cancelable: true },
    }

    handleScrollableWheel(event)

    expect(preventDefault).not.toHaveBeenCalled()
    expect(stopPropagation).toHaveBeenCalledTimes(1)
    expect(currentTarget.scrollTop).toBe(20)
  })

  it('also avoids preventDefault for passive wheel events so the browser does not warn', () => {
    const preventDefault = vi.fn()
    const stopPropagation = vi.fn()
    const currentTarget = { scrollTop: 20 }
    const event = {
      ctrlKey: false,
      deltaY: 15,
      preventDefault,
      stopPropagation,
      currentTarget,
      nativeEvent: { cancelable: false },
    }

    handleScrollableWheel(event)

    expect(preventDefault).not.toHaveBeenCalled()
    expect(stopPropagation).toHaveBeenCalledTimes(1)
    expect(currentTarget.scrollTop).toBe(20)
  })

  it('does nothing for ctrl-wheel so zoom gestures can keep working elsewhere', () => {
    const preventDefault = vi.fn()
    const stopPropagation = vi.fn()
    const event = {
      ctrlKey: true,
      deltaY: 15,
      preventDefault,
      stopPropagation,
      currentTarget: { scrollTop: 20 },
      nativeEvent: { cancelable: true },
    }

    handleScrollableWheel(event)

    expect(preventDefault).not.toHaveBeenCalled()
    expect(stopPropagation).not.toHaveBeenCalled()
  })
})
