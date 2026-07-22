import { describe, expect, it, vi } from 'vitest'

import {
  isHomeChatNearBottom,
  isHomeChatNearTop,
  restoreHomeChatScrollAnchor,
  scrollHomeChatToBottom,
} from './useHomeChatMessageScroll'

function createScrollContainer(overrides: Partial<HTMLElement> = {}) {
  return {
    clientHeight: 400,
    scrollHeight: 1000,
    scrollTop: 0,
    scrollTo: vi.fn(),
    ...overrides,
  } as unknown as HTMLElement
}

describe('home chat message scrolling', () => {
  it('detects the top loading threshold without treating the middle as the top', () => {
    expect(isHomeChatNearTop(createScrollContainer({ scrollTop: 80 }))).toBe(true)
    expect(isHomeChatNearTop(createScrollContainer({ scrollTop: 81 }))).toBe(false)
  })

  it('detects whether appended messages should keep following the bottom', () => {
    expect(isHomeChatNearBottom(createScrollContainer({ scrollTop: 520 }))).toBe(true)
    expect(isHomeChatNearBottom(createScrollContainer({ scrollTop: 519 }))).toBe(false)
  })

  it('positions a conversation at the latest message through the actual scroller', () => {
    const container = createScrollContainer()

    scrollHomeChatToBottom(container, 'auto')

    expect(container.scrollTo).toHaveBeenCalledWith({
      top: 1000,
      behavior: 'auto',
    })
  })

  it('preserves the visible anchor after older messages are prepended', () => {
    const container = createScrollContainer({
      scrollHeight: 1400,
      scrollTop: 120,
    })

    restoreHomeChatScrollAnchor(container, 1000, 120)

    expect(container.scrollTop).toBe(520)
  })
})
