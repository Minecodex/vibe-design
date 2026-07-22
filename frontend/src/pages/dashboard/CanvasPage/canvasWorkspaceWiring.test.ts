import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')
const workspaceSource = readFileSync(
  resolve(currentDir, 'components', 'CanvasWorkspace.tsx'),
  'utf8',
)
const readComponentIfExists = (name: string) => {
  const componentPath = resolve(currentDir, 'components', name)

  return existsSync(componentPath) ? readFileSync(componentPath, 'utf8') : ''
}
const canvasAreaSource = readComponentIfExists('CanvasWorkspaceCanvasArea.tsx')
const floatingPanelsSource = readComponentIfExists('CanvasWorkspaceFloatingPanels.tsx')
const bottomBarSource = readComponentIfExists('CanvasWorkspaceBottomBar.tsx')
const staleOverlaySource = readComponentIfExists('CanvasStaleOverlay.tsx')
const mediaRenderItemSource = readComponentIfExists('CanvasWorkspaceMediaRenderItem.tsx')
const viewportHookSource = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasController.viewport.tsx'),
  'utf8',
)
const wheelCameraSource = readFileSync(
  resolve(currentDir, 'canvasWheelCamera.ts'),
  'utf8',
)
const topBarSource = readFileSync(
  resolve(currentDir, 'components', 'CanvasTopBar.tsx'),
  'utf8',
)
const topBarUsageMatch = source.match(/<CanvasTopBar[\s\S]*?\/>/)
const topBarUsageSource = topBarUsageMatch?.[0] ?? ''
const workspaceUsageMatch = source.match(/<CanvasWorkspace[\s\S]*?\/>/)
const workspaceUsageSource = workspaceUsageMatch?.[0] ?? ''

describe('CanvasPage CanvasWorkspace wiring', () => {
  it('keeps controller state and actions that CanvasWorkspace reads', () => {
    expect(source).toContain('setActiveDropdown,')
    expect(source).toContain('selectionBox,')
    expect(source).toContain('setMediaResizeState,')
    expect(source).toContain('openImageAnchoredVideoDraft,')
    expect(source).toContain('imageAnchoredImageDraft,')
    expect(source).toContain('openImageAnchoredImageDraft,')
    expect(source).toContain('handleGenerateAnchoredImage,')
    expect(source).toContain('handleCanvasPaste,')
    expect(source).toContain('chatAppendMentionRequest,')
    expect(source).toContain('const handleAppendImageMentionToChat = (itemId: string) => {')

    expect(source).toContain('setActiveDropdown={setActiveDropdown}')
    expect(source).toContain('selectionBox={selectionBox}')
    expect(source).toContain('setMediaResizeState={setMediaResizeState}')
    expect(source).toContain('openImageAnchoredVideoDraft={openImageAnchoredVideoDraft}')
    expect(source).toContain('imageAnchoredImageDraft={imageAnchoredImageDraft}')
    expect(source).toContain('openImageAnchoredImageDraft={openImageAnchoredImageDraft}')
    expect(source).toContain('handleGenerateAnchoredImage={handleGenerateAnchoredImage}')
    expect(source).toContain('handleCanvasPaste={handleCanvasPaste}')
    expect(source).toContain('handleAppendImageMentionToChat={handleAppendImageMentionToChat}')
  })

  it('destructures every runtime prop that the workspace body reads directly', () => {
    expect(workspaceSource).toContain('setActiveDropdown,')
    expect(workspaceSource).toContain('selectionBox,')
    expect(workspaceSource).toContain('setMediaResizeState,')
    expect(workspaceSource).toContain('openImageAnchoredVideoDraft,')
    expect(workspaceSource).toContain('imageAnchoredImageDraft,')
    expect(workspaceSource).toContain('openImageAnchoredImageDraft,')
    expect(workspaceSource).toContain('handleGenerateAnchoredImage,')
    expect(workspaceSource).toContain('handleAppendImageMentionToChat,')
  })

  it('keeps clipboard image paste wired from the controller into the canvas area', () => {
    expect(source).toContain('handleCanvasPaste,')
    expect(source).toContain('clipboardItems,')
    expect(source).toContain('clipboardSource,')
    expect(workspaceUsageSource).toContain('handleCanvasPaste={handleCanvasPaste}')
    expect(workspaceUsageSource).toContain('clipboardItems={clipboardItems}')
    expect(workspaceUsageSource).toContain('clipboardSource={clipboardSource}')
    expect(workspaceSource).toContain('<CanvasWorkspaceCanvasArea {...props} />')
  })

  it('composes the split workspace layers from dedicated subcomponents', () => {
    expect(workspaceSource).toContain('CanvasWorkspaceCanvasArea')
    expect(workspaceSource).toContain('CanvasWorkspaceBottomBar')
    expect(canvasAreaSource).toContain('CanvasWorkspaceGroupLayer')
    expect(canvasAreaSource).toContain('CanvasWorkspaceItemLayer')
    expect(canvasAreaSource).toContain('CanvasWorkspaceFloatingPanels')
  })

  it('renders the stale overlay at the page root so it covers the agent sidebar too', () => {
    expect(source).toContain('import { CanvasStaleOverlay }')
    expect(source).toContain('{isCanvasStale && (')
    expect(source).toContain('<CanvasStaleOverlay')
    expect(source.indexOf('<ChatSidebar')).toBeLessThan(source.indexOf('<CanvasStaleOverlay'))
    expect(workspaceSource).not.toContain('canvas.stale_overlay.description')
    expect(staleOverlaySource).toContain('zIndex: 2147483647')
  })

  it('renders zoom controls in the bottom-left workspace toolbar instead of the top bar', () => {
    expect(topBarUsageSource).not.toContain('zoom={zoom}')
    expect(topBarUsageSource).not.toContain('zoomIn={zoomIn}')
    expect(topBarUsageSource).not.toContain('zoomOut={zoomOut}')

    expect(topBarSource).not.toContain('zoom: number')
    expect(topBarSource).not.toContain('zoomIn: () => void')
    expect(topBarSource).not.toContain('zoomOut: () => void')

    expect(workspaceSource).toContain('zoomIn,')
    expect(workspaceSource).toContain('zoomOut,')
    expect(bottomBarSource).toContain("{Math.round(zoom)}%")
  })

  it('keeps the video duration dropdown scrollable with a 200px height cap', () => {
    const durationMarker = "{isDurationDropdownOpen && ("
    const durationStart = mediaRenderItemSource.indexOf(durationMarker)

    expect(durationStart).toBeGreaterThan(-1)

    const durationSnippet = mediaRenderItemSource.slice(durationStart, durationStart + 1200)

    expect(durationSnippet).toContain('onWheel={handleScrollableWheel}')
    expect(durationSnippet).toContain('maxHeight: 200')
  })

  it('keeps the generator precision control in the split media render component', () => {
    expect(mediaRenderItemSource).toContain("t('canvas.generator.resolution_label'")
    expect(mediaRenderItemSource).toContain("t('canvas.generator.resolution_prefix'")
    expect(mediaRenderItemSource).toContain("type: isImageGroup ? 'res' : 'video_res'")
  })

  it('closes the right-click context menu when left-clicking the media item again', () => {
    expect(mediaRenderItemSource).toContain('onClick={(e) => {')
    expect(mediaRenderItemSource).toContain('setContextMenu(null)')
    expect(mediaRenderItemSource).toContain('setActiveContextMenuItem(null)')
    expect(readComponentIfExists('CanvasWorkspaceItemLayer.tsx')).toContain('setContextMenu(null)')
  })

  it('moves overlay-style workspace UI into the floating panel component', () => {
    expect(floatingPanelsSource).toContain('projectedGuides.length > 0')
    expect(floatingPanelsSource).toContain('selectionBox && (')
    expect(floatingPanelsSource).not.toContain('CanvasBrushDraftPreview')
    expect(canvasAreaSource).toContain('CanvasBrushDraftPreview')
  })

  it('routes canvas content transforms through the shared viewport helper', () => {
    expect(canvasAreaSource).not.toContain("from '../canvasViewportTransform'")
    expect(canvasAreaSource).not.toContain('getCanvasViewportTransform(offset, zoom)')
    expect(canvasAreaSource).not.toContain('transform:')
  })

  it('routes wheel viewport updates through the shared camera helper', () => {
    expect(viewportHookSource).not.toContain('createViewportFrameApplier')
    expect(viewportHookSource).not.toContain('createDeferredViewportStateSync')
    expect(viewportHookSource).not.toContain('wheelFrameApplierRef')
    expect(viewportHookSource).not.toContain('wheelStateSyncRef')
    expect(viewportHookSource).toContain('createCanvasWheelCameraScheduler')
    expect(wheelCameraSource).toContain('camera.setCamera(')
    expect(wheelCameraSource).toContain("camera.commitCamera('wheel-idle')")
    expect(viewportHookSource).not.toContain('setOffset(newOffset)')
  })
})
