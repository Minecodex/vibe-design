import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const hooksDir = resolve(currentDir, 'hooks')
const controllerSource = readFileSync(resolve(hooksDir, 'useCanvasController.tsx'), 'utf8')
const viewportSource = readFileSync(resolve(hooksDir, 'useCanvasController.viewport.tsx'), 'utf8')
const workspaceSource = readFileSync(resolve(currentDir, 'components', 'CanvasWorkspace.tsx'), 'utf8')
const itemLayerPath = resolve(currentDir, 'components', 'CanvasWorkspaceItemLayer.tsx')
const itemLayerSource = existsSync(itemLayerPath)
  ? readFileSync(itemLayerPath, 'utf8')
  : ''
const mediaRenderItemPath = resolve(currentDir, 'components', 'CanvasWorkspaceMediaRenderItem.tsx')
const mediaRenderItemSource = existsSync(mediaRenderItemPath)
  ? readFileSync(mediaRenderItemPath, 'utf8')
  : ''

describe('useCanvasController interaction wiring', () => {
  it('passes drag updates through the viewport hook wiring', () => {
    expect(viewportSource).toMatch(/const\s*\{[\s\S]*updateCanvasItems[\s\S]*\}\s*=\s*args/)
  })

  it('debounces canvas persistence so grouping and movement survive refresh', () => {
    expect(controllerSource).toContain('const timer = setTimeout(() => {')
    expect(controllerSource).toContain('void saveCanvasItems(latestCanvasItemsRef.current, {}, { dirtyEpoch: canvasDirtyEpochRef.current })')
    expect(controllerSource).toContain('isCanvasStaleRef.current')
    expect(controllerSource).toContain('}, 1000)')
  })

  it('returns the stale-aware canvas updater to page-level integrations', () => {
    expect(controllerSource).toContain('const trackedUpdateCanvasItems = useCallback')
    expect(controllerSource).toContain('if (isCanvasStaleRef.current) return')
    expect(controllerSource).toContain('updateCanvasItems: trackedUpdateCanvasItems')
  })

  it('skips autosave for the initial restored canvas until a user edit occurs', () => {
    expect(controllerSource).toContain('const hasHydratedCanvasRef = useRef(false)')
    expect(controllerSource).toContain('const canvasDirtyEpochRef = useRef(0)')
    expect(controllerSource).toContain('const persistedCanvasDirtyEpochRef = useRef(0)')
    expect(controllerSource).toContain('if (!hasHydratedCanvasRef.current) {')
    expect(controllerSource).toContain('hasHydratedCanvasRef.current = true')
    expect(controllerSource).toContain('if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return')
  })

  it('applies agent canvas patches through a skip-history non-dirty path', () => {
    expect(controllerSource).toContain('const applyAgentCanvasItems = useCallback')
    expect(controllerSource).toContain('confirmedCanvasItemsRef.current = nextItems')
    expect(controllerSource).toContain('updateCanvasItems((current: any[]) => {')
    expect(controllerSource).toContain('}, { skipHistory: true })')
    expect(readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')).toContain('applyAgentCanvasItems,')
  })

  it('does not let an older save response downgrade a newer agent canvas revision', () => {
    expect(controllerSource).toContain('const currentRevision = canvasRevisionRef.current')
    expect(controllerSource).toContain('if (revision < currentRevision) {')
    expect(controllerSource).toContain('return')
  })

  it('separates hand-tool and visibility shortcuts so shift+ctrl+y does not trigger hand mode or redo', () => {
    expect(viewportSource).toContain("if (event.key === 'h' || event.key === 'H') setActiveTool('hand')")
    expect(viewportSource).toContain("if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'y') {")
    expect(viewportSource).toContain("if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'y') {")
    expect(readFileSync(resolve(currentDir, 'contextMenu.ts'), 'utf8')).toContain('Shift + Ctrl + Y')
  })

  it('supports holding space for a temporary hand tool without replacing the h shortcut', () => {
    expect(viewportSource).toContain('const temporaryHandToolRef = useRef(false)')
    expect(viewportSource).toContain('const temporaryHandToolRestoreRef = useRef<string | null>(null)')
    expect(viewportSource).toContain("if (event.code === 'Space' && !event.repeat) {")
    expect(viewportSource).toContain("temporaryHandToolRestoreRef.current = activeToolRef.current")
    expect(viewportSource).toContain("setActiveTool('hand')")
    expect(viewportSource).toContain("if (event.code === 'Space' && temporaryHandToolRef.current) {")
    expect(viewportSource).toContain('setActiveTool(restoreTool)')
    expect(viewportSource).toContain('const resetTemporaryHandTool = () => {')
  })

  it('keeps failed anchored video tasks selectable even when their generator panel stays hidden', () => {
    expect(viewportSource).not.toContain("if (isHoverOnlyFailedVideoTask(item)) return")
    expect(viewportSource).not.toContain("if (isHoverOnlyFailedVideoTask(item)) return false")
    expect(mediaRenderItemSource).not.toContain('if (isHoverOnlyFailedVideo) return')
    expect(mediaRenderItemSource).toContain("shouldShowGeneratorControlPanel(item, { isHoverOnlyFailedVideo })")
    expect(itemLayerSource).toContain('CanvasWorkspaceMediaRenderItem')
    expect(workspaceSource).toContain('CanvasWorkspaceCanvasArea')
  })

  it('lets escape close anchored image and video panels through the viewport keyboard handler', () => {
    expect(controllerSource).toContain('imageAnchoredImageDraft,')
    expect(controllerSource).toContain('cancelImageAnchoredImageDraft: generatorsController.cancelImageAnchoredImageDraft')
    expect(viewportSource).toContain('if (imageAnchoredImageDraft && event.key === \'Escape\') {')
    expect(viewportSource).toContain('cancelImageAnchoredImageDraft(false)')
    expect(viewportSource).toContain('if (imageAnchoredVideoDraft && event.key === \'Escape\') {')
    expect(viewportSource).toContain('cancelImageAnchoredVideoDraft(false)')
  })

  it('lets escape close image info, text redraw, crop, and spatial angle overlays', () => {
    expect(controllerSource).toContain('imageDetailItemId,')
    expect(controllerSource).toContain('handleCloseImageDetails: mediaController.handleCloseImageDetails')
    expect(controllerSource).toContain('textRedrawState,')
    expect(controllerSource).toContain('handleCancelTextRedraw: mediaController.handleCancelTextRedraw')
    expect(controllerSource).toContain('cropState,')
    expect(controllerSource).toContain('setCropState,')
    expect(controllerSource).toContain('spatialAngleSession: generatorsController.spatialAngleSession')
    expect(controllerSource).toContain('handleCancelSpatialAngle: generatorsController.handleCancelSpatialAngle')
    expect(viewportSource).toContain('if (imageDetailItemId && event.key === \'Escape\') {')
    expect(viewportSource).toContain('handleCloseImageDetails()')
    expect(viewportSource).toContain('if (textRedrawState && event.key === \'Escape\') {')
    expect(viewportSource).toContain('handleCancelTextRedraw()')
    expect(viewportSource).toContain('if (cropState && event.key === \'Escape\') {')
    expect(viewportSource).toContain('setCropState(null)')
    expect(viewportSource).toContain('if (spatialAngleSession && event.key === \'Escape\') {')
    expect(viewportSource).toContain('handleCancelSpatialAngle(false)')
  })

  it('supports both Delete and Backspace for deleting selected canvas items', () => {
    expect(viewportSource).toContain("if ((event.key === 'Delete' || event.key === 'Backspace') && selectedItems.length > 0) {")
    expect(viewportSource).toContain("handleContextMenuAction('delete')")
  })

  it('keeps Ctrl+C handling in keydown and also listens for native copy as a fallback', () => {
    expect(viewportSource).toContain("if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {")
    expect(viewportSource).toContain("document.execCommand('copy')")
    expect(viewportSource).toContain("window.addEventListener('copy', handleCopy)")
    expect(viewportSource).toContain("window.removeEventListener('copy', handleCopy)")
    expect(viewportSource).toContain("handleContextMenuAction('copy')")
    expect(viewportSource).toContain('writeCanvasClipboardMarkerToClipboardData')
  })

  it('builds shared item lookup indexes once in the controller and passes them into the viewport hook', () => {
    expect(controllerSource).toContain('const itemIndex = useMemo(() => new Map(')
    expect(controllerSource).toContain('const groupChildrenIndex = useMemo(() => {')
    expect(controllerSource).toContain('itemIndex,')
    expect(controllerSource).toContain('groupChildrenIndex,')
    expect(viewportSource).toContain('itemIndex,')
    expect(viewportSource).toContain('groupChildrenIndex,')
  })

  it('uses indexed canvas lookups for drag setup and marquee selection hot paths', () => {
    expect(viewportSource).toContain("const item = itemIndex.get(itemId)")
    expect(viewportSource).toContain("const childIds = groupChildrenIndex.get(item.id) || []")
    expect(viewportSource).toContain('const selectionCandidateItems = visibleSelectableItemsRef.current')
  })

  it('routes hand-tool panning through the camera hot path and commits on interaction end', () => {
    expect(viewportSource).toContain('if (!_isPanning) return')
    expect(viewportSource).toContain('camera.panToOffset(newOffset)')
    expect(viewportSource).toContain("camera.commitCamera('pan-end')")
    expect(viewportSource).not.toContain('setOffset(newOffset)')
  })

  it('precomputes base guide candidates in the controller and filters them for each drag interaction', () => {
    expect(controllerSource).toContain('const baseGuideCandidates = useMemo(() => collectGuideCandidates(')
    expect(controllerSource).toContain('const baseGuideCandidateBuckets = useMemo(')
    expect(controllerSource).toContain('baseGuideCandidates,')
    expect(controllerSource).toContain('baseGuideCandidateBuckets,')
    expect(viewportSource).toContain('baseGuideCandidateBuckets,')
    expect(viewportSource).toContain('baseGuideCandidates,')
    expect(viewportSource).toContain('const candidates = filterGuideCandidateBuckets(baseGuideCandidateBuckets, movingIds)')
    expect(viewportSource).toContain('resolveActiveGuidesFromBuckets(draggedBounds, candidates, getGuideThresholdInCanvas(_zoom))')
  })

  it('precomputes stationary group hit candidates and uses a shared drag preview helper during move frames', () => {
    expect(viewportSource).toContain('const groupHitCandidatesRef = useRef<any[]>([])')
    expect(viewportSource).toContain('const currentItems = canvasItemsRef.current')
    expect(viewportSource).toContain("groupHitCandidatesRef.current = currentItems.filter((canvasItem: any) => (")
    expect(viewportSource).toContain("canvasItem.type === 'group' && !movingIds.has(canvasItem.id)")
    expect(viewportSource).toContain('const { items: nextItems, draggedBounds } = applyDragPreview({')
    expect(viewportSource).toContain('groupHitCandidates: groupHitCandidatesRef.current,')
    expect(viewportSource).toContain('interactionPreviewRef.current.apply(')
    expect(viewportSource).not.toContain('const draggedBounds = getDraggedBounds(movingIds, nextItems, getItemDims)')
    expect(viewportSource).toContain('groupHitCandidatesRef.current = []')
  })

  it('keeps drag and resize move frames on transient DOM previews until mouseup commit', () => {
    expect(viewportSource).toContain('createCanvasInteractionPreviewController')
    expect(viewportSource).toContain('applyBrushResizePreview')
    expect(viewportSource).toContain('applyMediaResizePreview')
    expect(viewportSource).toContain('applyGroupResizePreview')
    expect(viewportSource).toContain('applyDragPreview')
    expect(viewportSource).toContain('const previewItems = interactionPreviewRef.current.getLatestItems()')
    expect(viewportSource).toContain('updateCanvasItems((prev: any[]) => prev.map((item) => previewById.get(item.id) || item))')
  })

  it('imports getDraggedBounds before using it during drag start guide setup', () => {
    expect(viewportSource).toContain('getDraggedBounds,')
    expect(viewportSource).toContain('const draggedBounds = getDraggedBounds(movingIds, currentItems, getItemDims)')
  })

  it('hoists item-layer selection and dropdown membership outside the per-item render body', () => {
    expect(itemLayerSource).toContain('const selectedItemIdSet = useMemo(() => new Set(selectedItems), [selectedItems])')
    expect(itemLayerSource).toContain('const activeDropdownState = useMemo(() => ({')
    expect(itemLayerSource).toContain('const viewportBounds = useMemo(() => getCanvasViewportCullBounds({')
    expect(itemLayerSource).toContain('isCanvasItemVisibleInViewport(item, {')
    expect(itemLayerSource).toContain('selectedItemIdSet.has(item.id)')
    expect(itemLayerSource).toContain('activeDropdownState.itemId === item.id')
  })
})
