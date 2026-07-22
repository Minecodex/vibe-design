import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanvasControllerMarks } from './hooks/useCanvasController.marks'
import { useChatStore } from '@/store/canvasAgentStore'

const { analyzeElement } = vi.hoisted(() => ({
  analyzeElement: vi.fn(),
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    analyzeElement,
  },
}))

describe('useCanvasControllerMarks', () => {
  beforeEach(() => {
    analyzeElement.mockReset()
    useChatStore.setState({
      modelPreferences: {
        auto: false,
        multimodal_model: 'claude-opus-4-7',
        multimodal_provider: 'builtin',
      },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses the active multimodal model for mark analysis even when balance is zero', async () => {
    analyzeElement.mockResolvedValue({ data: { labels: ['apple'] } })
    const updateMarks = vi.fn((updater) => updater([]))
    const setIsChatSidebarOpen = vi.fn()
    const { result } = renderHook(() =>
      useCanvasControllerMarks({
        t: (_key: string, fallback?: string) => fallback ?? _key,
        user: { balance_cents: 0 },
        updateMarks,
        isChatSidebarOpen: false,
        setIsChatSidebarOpen,
        markIdCounter: { current: 0 },
      }),
    )

    vi.spyOn(document, 'querySelector').mockReturnValue({
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 200, height: 100 }),
    } as HTMLImageElement)

    await act(async () => {
      result.current.addMark(
        { id: 'image-1', url: '/image.png' },
        { clientX: 50, clientY: 25 } as React.MouseEvent,
      )
      await Promise.resolve()
    })

    expect(analyzeElement).toHaveBeenCalledWith({
      image_url: '/image.png',
      relative_x: 0.25,
      relative_y: 0.25,
      language: 'zh',
      model_name: 'claude-opus-4-7',
      provider_code: 'builtin',
    })
    expect(setIsChatSidebarOpen).toHaveBeenCalledWith(true)
  })
})
