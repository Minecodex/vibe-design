import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CanvasWorkspaceFloatingPanels } from './CanvasWorkspaceFloatingPanels'

function renderFloatingPanels(selectedSingleItem: any, overrides: Record<string, any> = {}) {
  const handleRetryFailedGeneration = vi.fn()

  const view = render(
    <CanvasWorkspaceFloatingPanels
      imageDetailItem={null}
      imageDetailData={null}
      imageDetailPanelPosition={null}
      isDark={false}
      t={(_key: string, fallback?: string) => fallback ?? _key}
      handleCloseImageDetails={vi.fn()}
      textRedrawState={null}
      textRedrawPanelPosition={null}
      TEXT_REDRAW_PANEL_TOKENS={{}}
      handleChangeTextRedrawSegment={vi.fn()}
      handleCancelTextRedraw={vi.fn()}
      handleSubmitTextRedraw={vi.fn()}
      selectedSingleItem={selectedSingleItem}
      selectedSingleItemRect={{ left: 40, top: 80, width: 240, height: 160 }}
      selectedSingleItemCanvasRect={{ left: 24, top: 48, width: 240, height: 160 }}
      activeTool="select"
      cropState={null}
      shouldShowImageToolbar={() => false}
      imageAnchoredImageDraft={null}
      imageAnchoredVideoDraft={null}
      openImageAnchoredImageDraft={vi.fn()}
      openImageAnchoredVideoDraft={vi.fn()}
      handleOpenHDUpscale={vi.fn()}
      handleOpenCutout={vi.fn()}
      handleOpenImageErase={vi.fn()}
      handleOpenTextRedraw={vi.fn()}
      handleOpenSpatialAngle={vi.fn()}
      handleOpenCropPanel={vi.fn()}
      handleDeleteCanvasImage={vi.fn()}
      handleOpenImageDetails={vi.fn()}
      handleRetryFailedGeneration={handleRetryFailedGeneration}
      shouldRenderSelectedMeta={false}
      selectedSingleItemViewportWidth={0}
      selectedIsImageGroup={false}
      editingNameId={null}
      updateItem={vi.fn()}
      setEditingNameId={vi.fn()}
      selectedIsGenerator
      formatDimensionLabel={vi.fn(() => '')}
      selectedSingleItemWidth={240}
      selectedSingleItemHeight={160}
      projectedGuides={[]}
      selectionBox={null}
      {...overrides}
    />,
  )

  return { ...view, handleRetryFailedGeneration }
}

function createImageDetailProps(overrides: Record<string, any> = {}) {
  return {
    imageDetailItem: { id: 'img-1', type: 'image', asset_origin: 'local_upload' },
    imageDetailData: {
      creatorName: 'Alice',
      creatorAvatar: null,
      fileFormat: 'PNG',
      imageSize: '1.50 MB',
      updatedAt: '2026/4/16 12:00:00',
      generationMeta: null,
    },
    imageDetailPanelPosition: { left: 40, top: 60, width: 360, height: 220 },
    ...overrides,
  }
}

describe('CanvasWorkspaceFloatingPanels', () => {
  it('shows a retry button for selected task-backed failed generator cards', () => {
    const { handleRetryFailedGeneration } = renderFloatingPanels({
      id: 'failed-generator-1',
      type: 'image_generator',
      status: 'failed',
      task_id: 42,
      failure_kind: 'task_failed',
    })

    fireEvent.click(screen.getByText('重新生成'))

    expect(handleRetryFailedGeneration).toHaveBeenCalledWith('failed-generator-1')
  })

  it('does not show a retry button for internal-error failed generator cards', () => {
    renderFloatingPanels({
      id: 'internal-error-generator-1',
      type: 'image_generator',
      status: 'failed',
      failure_kind: 'internal_failed',
    })

    expect(screen.queryByText('重新生成')).not.toBeInTheDocument()
  })

  it('anchors the selected-item floating stack using canvas-local coordinates', () => {
    const { container } = renderFloatingPanels(
      { id: 'image-1', type: 'image', status: 'completed', name: 'Sample' },
      {
        shouldRenderSelectedMeta: true,
        selectedSingleItemViewportWidth: 240,
        selectedIsGenerator: false,
        formatDimensionLabel: vi.fn(() => '240 x 160'),
      },
    )

    const floatingStack = container.querySelector('div[style*="transform: translate(-50%, -100%)"]') as HTMLDivElement | null
    expect(floatingStack).toBeTruthy()
    expect(floatingStack?.style.left).toBe('144px')
    expect(floatingStack?.style.top).toBe('40px')
    expect(floatingStack?.id).toBe('canvas-screen-preview-image-1')
    expect(floatingStack?.dataset.canvasPreviewScale).toBe('1')
  })

  it('does not allow renaming a generating media item from the selected meta panel', () => {
    const setEditingNameId = vi.fn()

    renderFloatingPanels(
      {
        id: 'video-generator-1',
        type: 'video_generator',
        status: 'generating',
        name: 'video',
      },
      {
        shouldRenderSelectedMeta: true,
        selectedSingleItemViewportWidth: 240,
        selectedIsGenerator: true,
        selectedIsImageGroup: false,
        setEditingNameId,
      },
    )

    fireEvent.click(screen.getByText('canvas.generator.video_title'))

    expect(setEditingNameId).not.toHaveBeenCalled()
  })

  it('keeps renaming available for completed selected media items', () => {
    const setEditingNameId = vi.fn()

    renderFloatingPanels(
      {
        id: 'image-1',
        type: 'image',
        status: 'completed',
        name: 'Sample',
      },
      {
        shouldRenderSelectedMeta: true,
        selectedSingleItemViewportWidth: 240,
        selectedIsGenerator: false,
        setEditingNameId,
      },
    )

    fireEvent.click(screen.getByText('Sample'))

    expect(setEditingNameId).toHaveBeenCalledWith('image-1')
  })

  it('keeps the close button on the click-open image detail card', () => {
    renderFloatingPanels(
      { id: 'image-1', type: 'image', status: 'completed', name: 'Sample' },
      createImageDetailProps(),
    )

    expect(screen.getByRole('button')).toBeInTheDocument()
  })
})
