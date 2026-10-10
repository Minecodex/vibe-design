import { useCallback, useEffect, useRef, useState } from 'react'
import { assetsApi, type AssetRead } from '@/api/endpoints/assets'
import { projectsApi, isCanvasItemRecord, type CanvasItem, type CanvasDataRecord, type ProjectRead } from '@/api/endpoints/projects'
import { normalizeAgentGeneratedMediaItems, normalizeDeletedAgentMediaKeys } from '../agentGeneratedMedia'
import { normalizeReferenceImages } from '../generatorCapabilities'
import { normalizeTextCanvasItem } from '../textTypography'
import {
  CANVAS_REVISION_BROADCAST_CHANNEL, applyAgentPatchCanvasRevisionSync,
  broadcastCanvasRevision, normalizeCanvasRevision,
} from '../canvasRevision'
import { useCanvasSaver } from './useCanvasSaver'

type CanvasProjectData = Pick<ProjectRead, 'title' | 'canvas_data' | 'canvas_revision'>
type CanvasUpdater = CanvasItem[] | ((items: CanvasItem[]) => CanvasItem[])
interface CanvasUpdateOptions { skipHistory?: boolean }
interface CanvasProjectSyncArgs {
  id?: string | number
  isGuest: boolean
  guestProject?: CanvasProjectData | null
  canvasItems: CanvasItem[]
  canvasItemsLoaded: boolean
  setCanvasItemsLoaded: (loaded: boolean) => void
  setTitle: (title: string) => void
  updateCanvasItems: (updater: CanvasUpdater, options?: CanvasUpdateOptions) => void
  initializeState: (items: CanvasItem[], marks: []) => void
  buildCanvasMeta: () => Record<string, unknown>
  loadPersistedGeneratorMeta: (meta: CanvasDataRecord) => void
  withReferenceImages: (images: string[]) => Partial<CanvasItem>
  onStale: () => void
}

function mergeServerCanvasMediaUrls(localItems: CanvasItem[], serverItems?: CanvasItem[]) {
  if (!Array.isArray(serverItems) || serverItems.length === 0) return localItems
  const serverUrlById = new Map(
    serverItems
      .filter((item: CanvasItem) => item?.id && typeof item.url === 'string' && item.url)
      .map((item: CanvasItem) => [String(item.id), item.url]),
  )
  if (serverUrlById.size === 0) return localItems

  let changed = false
  const nextItems = localItems.map((item: CanvasItem) => {
    const serverUrl = serverUrlById.get(String(item?.id || ''))
    if (!serverUrl || item.url === serverUrl) return item
    changed = true
    return { ...item, url: serverUrl }
  })
  return changed ? nextItems : localItems
}

export function useCanvasProjectSync({
  id, isGuest, guestProject, canvasItems, canvasItemsLoaded, setCanvasItemsLoaded,
  setTitle, updateCanvasItems, initializeState, buildCanvasMeta,
  loadPersistedGeneratorMeta, withReferenceImages, onStale,
}: CanvasProjectSyncArgs) {
  const [projectAssets, setProjectAssets] = useState<Record<number, AssetRead>>({})
  const [deletedAgentMediaKeys, setDeletedAgentMediaKeys] = useState<string[]>([])
  const [canvasLoadFailed, setCanvasLoadFailed] = useState(false)
  const [isCanvasStale, setIsCanvasStale] = useState(false)
  const [isRefreshingCanvas, setIsRefreshingCanvas] = useState(false)
  const hasHydratedCanvasRef = useRef(false)
  const canvasDirtyEpochRef = useRef(0)
  const persistedCanvasDirtyEpochRef = useRef(0)
  const canvasRevisionRef = useRef(0)
  const isCanvasStaleRef = useRef(false)
  const canvasStaleRevisionRef = useRef<number | null>(null)
  const confirmedCanvasItemsRef = useRef<CanvasItem[]>([])
  const latestCanvasItemsRef = useRef<CanvasItem[]>([])
  const saveCanvasItemsRef = useRef<ReturnType<typeof useCanvasSaver> | null>(null)
  useEffect(() => {
    latestCanvasItemsRef.current = canvasItems
  }, [canvasItems])

  const markCanvasAsEdited = useCallback(() => {
    if (!hasHydratedCanvasRef.current) return
    if (isCanvasStaleRef.current) return
    canvasDirtyEpochRef.current += 1
  }, [])

  const trackedUpdateCanvasItems = useCallback((updater: CanvasUpdater, options?: CanvasUpdateOptions) => {
    if (isCanvasStaleRef.current) return
    markCanvasAsEdited()
    updateCanvasItems(updater, options)
  }, [markCanvasAsEdited, updateCanvasItems])

  // Serialized + coalesced canvas autosave (defects D3/D4) lives in its own hook module.
  const markCanvasRevisionSaved = useCallback((revision: number, savedItems: CanvasItem[], serverItems?: CanvasItem[], saveMeta?: { dirtyEpoch?: number }) => {
    const currentRevision = canvasRevisionRef.current
    const savedDirtyEpoch = saveMeta?.dirtyEpoch ?? 0
    if (saveMeta?.dirtyEpoch !== undefined) {
      persistedCanvasDirtyEpochRef.current = Math.max(
        persistedCanvasDirtyEpochRef.current,
        saveMeta.dirtyEpoch,
      )
    }
    const normalizedItems = mergeServerCanvasMediaUrls(savedItems, serverItems)
    if (revision < currentRevision) {
      if (normalizedItems !== savedItems) {
        confirmedCanvasItemsRef.current = mergeServerCanvasMediaUrls(confirmedCanvasItemsRef.current, serverItems)
        updateCanvasItems((current: CanvasItem[]) => {
          const mergedItems = mergeServerCanvasMediaUrls(current, serverItems)
          latestCanvasItemsRef.current = mergedItems
          return mergedItems
        }, { skipHistory: true })
      }
      return
    }

    canvasRevisionRef.current = revision
    confirmedCanvasItemsRef.current = normalizedItems
    if (savedDirtyEpoch >= canvasDirtyEpochRef.current) {
      latestCanvasItemsRef.current = normalizedItems
    }
    if (normalizedItems !== savedItems) {
      updateCanvasItems((current: CanvasItem[]) => {
        const mergedItems = mergeServerCanvasMediaUrls(current, serverItems)
        latestCanvasItemsRef.current = mergedItems
        return mergedItems
      }, { skipHistory: true })
    }
    if (id && !isGuest) {
      broadcastCanvasRevision(Number(id), revision)
    }
  }, [id, isGuest, updateCanvasItems])

  const applyAgentCanvasItems = useCallback((updater: CanvasUpdater) => {
    if (isCanvasStaleRef.current) return
    updateCanvasItems((current: CanvasItem[]) => {
      const nextItems = typeof updater === 'function' ? updater(current) : updater
      latestCanvasItemsRef.current = nextItems
      confirmedCanvasItemsRef.current = nextItems
      return nextItems
    }, { skipHistory: true })
  }, [updateCanvasItems])

  const syncCanvasRevisionFromAgentPatch = useCallback((revision: number, options?: { resolveStale?: boolean }) => {
    const next = applyAgentPatchCanvasRevisionSync({
      currentRevision: canvasRevisionRef.current,
      isStale: isCanvasStaleRef.current,
      staleRevision: canvasStaleRevisionRef.current,
    }, revision, options)
    if (!next.revisionChanged && !next.staleCleared) return
    canvasRevisionRef.current = next.currentRevision
    isCanvasStaleRef.current = next.isStale
    canvasStaleRevisionRef.current = next.staleRevision
    if (next.staleCleared) {
      setIsCanvasStale(false)
    }
    if (id && !isGuest) {
      broadcastCanvasRevision(Number(id), next.currentRevision)
    }
  }, [id, isGuest])

  const markCanvasStale = useCallback((revision?: number) => {
    if (revision !== undefined) {
      canvasRevisionRef.current = Math.max(canvasRevisionRef.current, revision)
      canvasStaleRevisionRef.current = normalizeCanvasRevision(revision)
    } else {
      canvasStaleRevisionRef.current = null
    }
    isCanvasStaleRef.current = true
    setIsCanvasStale(true)
    onStale()
  }, [onStale])

  const saveCanvasItems = useCanvasSaver({
    id,
    isGuest,
    canvasItemsLoaded,
    canvasLoadFailed,
    buildCanvasMeta,
    deletedAgentMediaKeys,
    canvasRevisionRef,
    isCanvasStaleRef,
    getDirtyEpoch: () => canvasDirtyEpochRef.current,
    onRevisionSaved: markCanvasRevisionSaved,
    onObsoleteRevisionConflict: () => {
      if (isCanvasStaleRef.current) return
      if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return
      void saveCanvasItemsRef.current?.(
        latestCanvasItemsRef.current,
        {},
        { dirtyEpoch: canvasDirtyEpochRef.current },
      )
    },
    onRevisionConflict: (revision) => {
      updateCanvasItems(confirmedCanvasItemsRef.current)
      markCanvasStale(revision)
    },
  })
  saveCanvasItemsRef.current = saveCanvasItems

  const loadProjectAssets = useCallback(async () => {
    if (!id || isGuest) {
      setProjectAssets({})
      return
    }

    try {
      const res = await assetsApi.list(Number(id))
      const nextAssets = res.data.reduce((acc: Record<number, AssetRead>, asset: AssetRead) => {
        acc[asset.id] = asset
        return acc
      }, {})
      setProjectAssets(nextAssets)
    } catch (error) {
      console.error('Failed to load project assets:', error)
    }
  }, [id, isGuest])

  const loadCanvasProjectData = useCallback((data: CanvasProjectData, options: { clearStale?: boolean } = {}) => {
    hasHydratedCanvasRef.current = false
    canvasDirtyEpochRef.current = 0
    persistedCanvasDirtyEpochRef.current = 0
    setCanvasLoadFailed(false)
    setTitle(data.title)
    const revision = normalizeCanvasRevision(data.canvas_revision)
    canvasRevisionRef.current = revision
    if (options.clearStale) {
      isCanvasStaleRef.current = false
      canvasStaleRevisionRef.current = null
      setIsCanvasStale(false)
    }
    let nextItems: CanvasItem[] = []
    if (Array.isArray(data.canvas_data) && data.canvas_data.length > 0) {
      const meta = data.canvas_data.find(item => item.id === 'global_state')
      if (meta) {
        loadPersistedGeneratorMeta(meta)
        setDeletedAgentMediaKeys(normalizeDeletedAgentMediaKeys('deletedAgentMediaKeys' in meta ? meta.deletedAgentMediaKeys : undefined))
      } else {
        setDeletedAgentMediaKeys([])
      }
      nextItems = normalizeAgentGeneratedMediaItems(
        data.canvas_data
          .filter(isCanvasItemRecord),
      )
        .map((item: CanvasItem) => ({
          ...(item.type === 'text' ? normalizeTextCanvasItem(item) : item),
          ...withReferenceImages(normalizeReferenceImages(item)),
        }))
      initializeState(nextItems, [])
    } else {
      initializeState([], [])
      setDeletedAgentMediaKeys([])
    }
    confirmedCanvasItemsRef.current = nextItems
    latestCanvasItemsRef.current = nextItems
    hasHydratedCanvasRef.current = true
    setCanvasItemsLoaded(true)
  }, [initializeState, loadPersistedGeneratorMeta, setCanvasItemsLoaded, setTitle, withReferenceImages])

  const refreshCanvasFromServer = useCallback(async () => {
    if (!id || isGuest) return
    setIsRefreshingCanvas(true)
    try {
      const res = await projectsApi.get(Number(id))
      loadCanvasProjectData(res.data, { clearStale: true })
      void loadProjectAssets()
    } catch (error) {
      console.error('Failed to refresh canvas:', error)
    } finally {
      setIsRefreshingCanvas(false)
    }
  }, [id, isGuest, loadCanvasProjectData, loadProjectAssets])

  useEffect(() => {
    if (isGuest && guestProject) {
      loadCanvasProjectData(guestProject, { clearStale: true })
    } else if (id && !isGuest) {
      projectsApi.get(Number(id)).then((res) => {
        loadCanvasProjectData(res.data, { clearStale: true })
        void loadProjectAssets()
      }).catch(() => {
        hasHydratedCanvasRef.current = false
        canvasDirtyEpochRef.current = 0
        persistedCanvasDirtyEpochRef.current = 0
        initializeState([], [])
        setDeletedAgentMediaKeys([])
        setCanvasLoadFailed(true)
        setCanvasItemsLoaded(true)
      })
    }
  }, [guestProject, id, isGuest, initializeState, loadCanvasProjectData, loadProjectAssets, setCanvasItemsLoaded])

  useEffect(() => {
    if (isGuest || !canvasItemsLoaded || !id || canvasLoadFailed || isCanvasStaleRef.current) return
    if (!hasHydratedCanvasRef.current) {
      hasHydratedCanvasRef.current = true
      return
    }
    if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return
    const timer = setTimeout(() => {
      if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return
      void saveCanvasItems(latestCanvasItemsRef.current, {}, { dirtyEpoch: canvasDirtyEpochRef.current })
    }, 1000)
    return () => clearTimeout(timer)
  }, [canvasItems, canvasItemsLoaded, canvasLoadFailed, id, isGuest, saveCanvasItems])

  useEffect(() => {
    isCanvasStaleRef.current = isCanvasStale
  }, [isCanvasStale])

  useEffect(() => {
    if (!id || isGuest || typeof BroadcastChannel === 'undefined') return
    const projectId = Number(id)
    const channel = new BroadcastChannel(CANVAS_REVISION_BROADCAST_CHANNEL)
    channel.onmessage = (event) => {
      const message = event.data || {}
      if (Number(message.projectId) !== projectId) return
      const incomingRevision = normalizeCanvasRevision(message.canvasRevision)
      if (incomingRevision > canvasRevisionRef.current) {
        markCanvasStale(incomingRevision)
      }
    }
    return () => channel.close()
  }, [id, isGuest, markCanvasStale])

  useEffect(() => {
    if (!id || isGuest) return
    let inFlight = false
    const checkRevision = async () => {
      if (inFlight || isCanvasStaleRef.current) return
      inFlight = true
      try {
        const res = await projectsApi.get(Number(id))
        const incomingRevision = normalizeCanvasRevision(res.data.canvas_revision)
        if (incomingRevision > canvasRevisionRef.current) {
          markCanvasStale(incomingRevision)
        }
      } catch {
        // Keep the current editable state on transient revision probe failures.
      } finally {
        inFlight = false
      }
    }
    const handleFocus = () => {
      void checkRevision()
    }
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void checkRevision()
      }
    }
    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [id, isGuest, markCanvasStale])

  return {
    projectAssets, setProjectAssets, deletedAgentMediaKeys, setDeletedAgentMediaKeys,
    latestCanvasItemsRef, trackedUpdateCanvasItems, applyAgentCanvasItems,
    saveCanvasItems, isCanvasStale, isCanvasStaleRef, isRefreshingCanvas,
    refreshCanvasFromServer, syncCanvasRevisionFromAgentPatch, loadProjectAssets,
  }
}
