import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CanvasItem } from '@/api/endpoints/projects'
import { useCanvasProjectSync } from './useCanvasProjectSync'

const { getProject, updateProject, listAssets } = vi.hoisted(() => ({
  getProject: vi.fn(), updateProject: vi.fn(), listAssets: vi.fn(),
}))
vi.mock('@/api/endpoints/projects', () => ({ projectsApi: { get: getProject, update: updateProject } }))
vi.mock('@/api/endpoints/assets', () => ({ assetsApi: { list: listAssets } }))

const image: CanvasItem = { id: 'image-1', type: 'image', url: '/image.png', x: 0, y: 0 }

function argumentsForProject() {
  return {
    id: 7, isGuest: false, canvasItems: [image], canvasItemsLoaded: true,
    setCanvasItemsLoaded: vi.fn(), setTitle: vi.fn(), initializeState: vi.fn(),
    updateCanvasItems: vi.fn(), buildCanvasMeta: () => ({ id: 'global_state' }),
    loadPersistedGeneratorMeta: vi.fn(), withReferenceImages: () => ({}), onStale: vi.fn(),
  }
}

describe('canvas project synchronization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProject.mockReset().mockResolvedValue({ data: { title: 'Project', canvas_revision: 3, canvas_data: [image] } })
    updateProject.mockReset().mockResolvedValue({ data: { canvas_revision: 4 } })
    listAssets.mockReset().mockResolvedValue({ data: [] })
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('loads project data and preserves deletion markers from global metadata', async () => {
    const args = argumentsForProject()
    const meta = { ...image, id: 'global_state', deletedAgentMediaKeys: ['deleted-1'] }
    getProject.mockResolvedValueOnce({ data: { title: 'Loaded', canvas_revision: 3, canvas_data: [meta, image] } })
    const { result } = renderHook(() => useCanvasProjectSync(args))

    await waitFor(() => expect(args.initializeState).toHaveBeenCalledWith([image], []))
    expect(args.setTitle).toHaveBeenCalledWith('Loaded')
    expect(args.loadPersistedGeneratorMeta).toHaveBeenCalledWith(meta)
    expect(result.current.deletedAgentMediaKeys).toEqual(['deleted-1'])
    expect(updateProject).not.toHaveBeenCalled()
  })

  it('does not save an empty snapshot after the initial request fails', async () => {
    const args = argumentsForProject()
    getProject.mockRejectedValueOnce(new Error('load failed'))
    const { result, rerender } = renderHook(({ items }) => useCanvasProjectSync({ ...args, canvasItems: items }), {
      initialProps: { items: [image] },
    })
    await waitFor(() => expect(args.initializeState).toHaveBeenCalledWith([], []))
    expect(args.setCanvasItemsLoaded).toHaveBeenCalledWith(true)
    vi.useFakeTimers()
    act(() => result.current.trackedUpdateCanvasItems([]))
    rerender({ items: [] })
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(updateProject).not.toHaveBeenCalled()
  })

  it('autosaves an edit against the loaded revision with the latest snapshot', async () => {
    const args = argumentsForProject()
    const { result, rerender } = renderHook(({ items }) => useCanvasProjectSync({ ...args, canvasItems: items }), {
      initialProps: { items: [image] },
    })
    await waitFor(() => expect(args.initializeState).toHaveBeenCalled())
    vi.useFakeTimers()
    const edited = [{ ...image, x: 120 }]
    act(() => result.current.trackedUpdateCanvasItems(edited))
    rerender({ items: edited })
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(updateProject).toHaveBeenCalledWith(7, {
      canvas_base_revision: 3,
      canvas_data: [...edited, { id: 'global_state', deletedAgentMediaKeys: [] }],
    })
  })

  it('blocks edits after a newer server revision and resumes after an explicit refresh', async () => {
    const args = argumentsForProject()
    const { result } = renderHook(() => useCanvasProjectSync(args))
    await waitFor(() => expect(args.initializeState).toHaveBeenCalled())
    getProject.mockResolvedValue({ data: { title: 'Updated', canvas_revision: 5, canvas_data: [image] } })
    act(() => window.dispatchEvent(new Event('focus')))
    await waitFor(() => expect(result.current.isCanvasStale).toBe(true))
    expect(args.onStale).toHaveBeenCalledOnce()
    act(() => result.current.trackedUpdateCanvasItems([]))
    expect(args.updateCanvasItems).not.toHaveBeenCalled()
    await act(() => result.current.refreshCanvasFromServer())
    expect(result.current.isCanvasStale).toBe(false)
    act(() => result.current.trackedUpdateCanvasItems([image]))
    expect(args.updateCanvasItems).toHaveBeenCalledWith([image], undefined)
  })
})
