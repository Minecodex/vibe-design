import { canvasItem, projectRead } from '@/store/testing/canvasStateFixtures'
import { httpResponse } from '@/store/testing/harnessStateFixtures'
import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { projectsApi } from '@/api/endpoints/projects'

import { useCanvasSaver } from './hooks/useCanvasSaver'

vi.mock('@/api/endpoints/projects', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/endpoints/projects')>(),
  projectsApi: {
    update: vi.fn(),
  },
}))

describe('useCanvasSaver revision handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends canvas_base_revision and stores the returned revision', async () => {
    vi.mocked(projectsApi.update).mockResolvedValueOnce(httpResponse({ data: projectRead({ canvas_revision: 4 }) }))
    const onRevisionSaved = vi.fn()
    const onRevisionConflict = vi.fn()
    const canvasRevisionRef = { current: 3 }
    const isCanvasStaleRef = { current: false }

    const { result } = renderHook(() => useCanvasSaver({
      id: 7,
      isGuest: false,
      canvasItemsLoaded: true,
      canvasLoadFailed: false,
      buildCanvasMeta: () => ({ id: 'global_state' }),
      deletedAgentMediaKeys: [],
      canvasRevisionRef,
      isCanvasStaleRef,
      onRevisionSaved,
      onRevisionConflict,
    }))

    await act(async () => {
      await result.current([canvasItem({ id: 'item-1' })])
    })

    expect(projectsApi.update).toHaveBeenCalledWith(7, {
      canvas_data: [canvasItem({ id: 'item-1' }), { id: 'global_state', deletedAgentMediaKeys: [] }],
      canvas_base_revision: 3,
    })
    expect(onRevisionSaved).toHaveBeenCalledWith(
      4,
      [canvasItem({ id: 'item-1' })],
      undefined,
      { baseRevision: 3, dirtyEpoch: 0 },
    )
    expect(onRevisionConflict).not.toHaveBeenCalled()
  })

  it('passes normalized canvas items returned by the server', async () => {
    vi.mocked(projectsApi.update).mockResolvedValueOnce(httpResponse({ data: projectRead({
        canvas_revision: 4,
        canvas_data: [
          canvasItem({ id: 'item-1', url: '/api/v1/uploads/canvas/7/source.png' }),
          { id: 'global_state', deletedAgentMediaKeys: [] },
        ],
      }) }))
    const onRevisionSaved = vi.fn()

    const { result } = renderHook(() => useCanvasSaver({
      id: 7,
      isGuest: false,
      canvasItemsLoaded: true,
      canvasLoadFailed: false,
      buildCanvasMeta: () => ({ id: 'global_state' }),
      deletedAgentMediaKeys: [],
      canvasRevisionRef: { current: 3 },
      isCanvasStaleRef: { current: false },
      onRevisionSaved,
      onRevisionConflict: vi.fn(),
    }))

    await act(async () => {
      await result.current([canvasItem({ id: 'item-1', url: '/api/v1/uploads/canvas/1/source.png' })])
    })

    expect(onRevisionSaved).toHaveBeenCalledWith(
      4,
      [canvasItem({ id: 'item-1', url: '/api/v1/uploads/canvas/1/source.png' })],
      [canvasItem({ id: 'item-1', url: '/api/v1/uploads/canvas/7/source.png' })],
      { baseRevision: 3, dirtyEpoch: 0 },
    )
  })

  it('captures the base revision when the save is enqueued', async () => {
    let resolveSave: ((value: Awaited<ReturnType<typeof projectsApi.update>>) => void) | null = null
    vi.mocked(projectsApi.update).mockImplementationOnce(() => new Promise((resolve) => {
      resolveSave = resolve
    }))
    const canvasRevisionRef = { current: 3 }

    const { result } = renderHook(() => useCanvasSaver({
      id: 7,
      isGuest: false,
      canvasItemsLoaded: true,
      canvasLoadFailed: false,
      buildCanvasMeta: () => ({ id: 'global_state' }),
      deletedAgentMediaKeys: [],
      canvasRevisionRef,
      isCanvasStaleRef: { current: false },
      onRevisionSaved: vi.fn(),
      onRevisionConflict: vi.fn(),
    }))

    const savePromise = act(async () => {
      const pending = result.current([canvasItem({ id: 'item-1' })])
      canvasRevisionRef.current = 9
      resolveSave?.(httpResponse({ data: projectRead({ canvas_revision: 4 }) }))
      await pending
    })
    await savePromise

    expect(projectsApi.update).toHaveBeenCalledWith(7, {
      canvas_data: [canvasItem({ id: 'item-1' }), { id: 'global_state', deletedAgentMediaKeys: [] }],
      canvas_base_revision: 3,
    })
  })

  it('reports revision conflicts without throwing to callers', async () => {
    vi.mocked(projectsApi.update).mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: { canvas_revision: 8 } },
      },
    })
    const onRevisionSaved = vi.fn()
    const onRevisionConflict = vi.fn()

    const { result } = renderHook(() => useCanvasSaver({
      id: 7,
      isGuest: false,
      canvasItemsLoaded: true,
      canvasLoadFailed: false,
      buildCanvasMeta: () => ({ id: 'global_state' }),
      deletedAgentMediaKeys: [],
      canvasRevisionRef: { current: 3 },
      isCanvasStaleRef: { current: false },
      onRevisionSaved,
      onRevisionConflict,
    }))

    await act(async () => {
      await result.current([canvasItem({ id: 'item-1' })])
    })

    expect(onRevisionConflict).toHaveBeenCalledWith(8)
    expect(onRevisionSaved).not.toHaveBeenCalled()
  })

  it('treats a conflict at an already-synced agent revision as an obsolete save', async () => {
    const canvasRevisionRef = { current: 3 }
    vi.mocked(projectsApi.update).mockImplementationOnce(async () => {
      canvasRevisionRef.current = 8
      throw {
        response: {
          status: 409,
          data: { detail: { canvas_revision: 8 } },
        },
      }
    })
    const onRevisionConflict = vi.fn()
    const onObsoleteRevisionConflict = vi.fn()

    const { result } = renderHook(() => useCanvasSaver({
      id: 7,
      isGuest: false,
      canvasItemsLoaded: true,
      canvasLoadFailed: false,
      buildCanvasMeta: () => ({ id: 'global_state' }),
      deletedAgentMediaKeys: [],
      canvasRevisionRef,
      isCanvasStaleRef: { current: false },
      getDirtyEpoch: () => 5,
      onRevisionSaved: vi.fn(),
      onRevisionConflict,
      onObsoleteRevisionConflict,
    }))

    await act(async () => {
      await result.current([canvasItem({ id: 'item-1' })])
    })

    expect(onObsoleteRevisionConflict).toHaveBeenCalledWith({
      baseRevision: 3,
      dirtyEpoch: 5,
      conflictRevision: 8,
    })
    expect(onRevisionConflict).not.toHaveBeenCalled()
  })

  it('does not save while the canvas is stale', async () => {
    const { result } = renderHook(() => useCanvasSaver({
      id: 7,
      isGuest: false,
      canvasItemsLoaded: true,
      canvasLoadFailed: false,
      buildCanvasMeta: () => ({ id: 'global_state' }),
      deletedAgentMediaKeys: [],
      canvasRevisionRef: { current: 3 },
      isCanvasStaleRef: { current: true },
      onRevisionSaved: vi.fn(),
      onRevisionConflict: vi.fn(),
    }))

    await act(async () => {
      await result.current([canvasItem({ id: 'item-1' })])
    })

    expect(projectsApi.update).not.toHaveBeenCalled()
  })
})
