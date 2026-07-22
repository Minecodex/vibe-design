import { useCallback, useRef } from 'react'
import type { MutableRefObject } from 'react'

import { projectsApi } from '@/api/endpoints/projects'

import { createCoalescingRunner } from '../canvasSaveQueue'
import {
  isCanvasRevisionConflictError,
  normalizeCanvasRevision,
} from '../canvasRevision'

interface UseCanvasSaverArgs {
  id: string | number | undefined
  isGuest: boolean
  canvasItemsLoaded: boolean
  canvasLoadFailed: boolean
  buildCanvasMeta: () => Record<string, any>
  deletedAgentMediaKeys: string[]
  canvasRevisionRef: MutableRefObject<number>
  isCanvasStaleRef: MutableRefObject<boolean>
  getDirtyEpoch?: () => number
  onRevisionSaved: (revision: number, savedItems: any[], serverItems: any[] | undefined, meta: CanvasSaveMeta) => void
  onRevisionConflict: (revision?: number) => void
  onObsoleteRevisionConflict?: (meta: CanvasObsoleteSaveConflict) => void
}

export interface CanvasSaveMeta {
  baseRevision: number
  dirtyEpoch: number
}

export interface CanvasSaveOptions {
  dirtyEpoch?: number
}

interface CanvasSavePayload extends CanvasSaveMeta {
  items: any[]
  metaOverrides: Record<string, any>
}

interface CanvasObsoleteSaveConflict extends CanvasSaveMeta {
  conflictRevision: number
}

/**
 * Returns a `saveCanvasItems(items, metaOverrides?)` that persists the full canvas snapshot,
 * serialized and coalesced so concurrent generation-event saves cannot arrive out of order
 * and drop a just-added item (defects D3/D4). See `createCoalescingRunner`.
 */
export function useCanvasSaver({
  id,
  isGuest,
  canvasItemsLoaded,
  canvasLoadFailed,
  buildCanvasMeta,
  deletedAgentMediaKeys,
  canvasRevisionRef,
  isCanvasStaleRef,
  getDirtyEpoch,
  onRevisionSaved,
  onRevisionConflict,
  onObsoleteRevisionConflict,
}: UseCanvasSaverArgs) {
  // Read the latest meta / project id at flush time even though the runner is created once.
  const performSaveRef = useRef<(payload: CanvasSavePayload) => Promise<void>>(
    async () => {},
  )
  performSaveRef.current = async (payload: CanvasSavePayload) => {
    if (isCanvasStaleRef.current) return
    const meta = {
      ...(buildCanvasMeta() as any),
      deletedAgentMediaKeys,
      ...payload.metaOverrides,
    }
    const response = await projectsApi.update(Number(id), {
      canvas_data: [...payload.items, meta],
      canvas_base_revision: payload.baseRevision,
    })
    const serverItems = Array.isArray(response.data.canvas_data)
      ? response.data.canvas_data.filter((item: any) => item?.id !== 'global_state')
      : undefined
    onRevisionSaved(
      normalizeCanvasRevision(response.data.canvas_revision),
      payload.items,
      serverItems,
      {
        baseRevision: payload.baseRevision,
        dirtyEpoch: payload.dirtyEpoch,
      },
    )
  }

  const runnerRef = useRef<((payload: CanvasSavePayload) => Promise<void>) | null>(null)
  if (!runnerRef.current) {
    runnerRef.current = createCoalescingRunner(
      (payload) => performSaveRef.current(payload),
      (error, payload) => {
        if (isCanvasRevisionConflictError(error)) {
          const rawRevision = (error as any)?.response?.data?.detail?.canvas_revision
          const revision = rawRevision === undefined ? undefined : normalizeCanvasRevision(rawRevision)
          const currentRevision = normalizeCanvasRevision(canvasRevisionRef.current)
          if (
            revision !== undefined
            && payload.baseRevision < revision
            && currentRevision >= revision
          ) {
            onObsoleteRevisionConflict?.({
              baseRevision: payload.baseRevision,
              dirtyEpoch: payload.dirtyEpoch,
              conflictRevision: revision,
            })
            return
          }
          onRevisionConflict(revision)
          return
        }
        console.error('Failed to save project data:', error)
      },
    )
  }

  return useCallback(
    async (
      currentItems: any[],
      metaOverrides: Record<string, any> = {},
      options: CanvasSaveOptions = {},
    ) => {
      if (!id || isGuest || !canvasItemsLoaded || canvasLoadFailed || isCanvasStaleRef.current) return
      await runnerRef.current?.({
        items: currentItems,
        metaOverrides,
        baseRevision: normalizeCanvasRevision(canvasRevisionRef.current),
        dirtyEpoch: options.dirtyEpoch ?? getDirtyEpoch?.() ?? 0,
      })
    },
    [canvasItemsLoaded, canvasLoadFailed, getDirtyEpoch, id, isGuest],
  )
}
