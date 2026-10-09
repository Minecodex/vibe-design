import type { CanvasWorkspaceItemLayerProps } from './canvasRenderContracts'
import React from 'react'
import type { CanvasItem } from '@/api/endpoints/projects'
import { canvasRenderFixture } from '@/store/testing/canvasRenderFixture'
import type { CanvasWorkspaceCanvasAreaProps } from './CanvasWorkspaceCanvasArea'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CanvasWorkspaceCanvasArea,
} from './CanvasWorkspaceCanvasArea'
import { CANVAS_CLIPBOARD_MIME } from '../canvasClipboard'
import { getClipboardImageFile } from '../clipboardImage'

vi.mock('./CanvasSceneLayer', () => ({
  CanvasSceneLayer: ({ onReadyChange }: { onReadyChange?: (ready: boolean) => void }) => {
    React.useEffect(() => {
      onReadyChange?.(true)
    }, [onReadyChange])
    return <div data-testid="scene-layer" />
  },
}))

vi.mock('./CanvasWorkspaceGroupLayer', () => ({
  CanvasWorkspaceGroupLayer: () => <div data-testid="group-layer" />,
}))

vi.mock('./CanvasBrushDraftPreview', () => ({
  CanvasBrushDraftPreview: () => <div data-testid="brush-preview" />,
}))

vi.mock('./CanvasWorkspaceMultiSelectToolbar', () => ({
  CanvasWorkspaceMultiSelectToolbar: () => null,
}))

vi.mock('./CanvasWorkspaceItemLayer', () => ({
  CanvasWorkspaceItemLayer: (props: CanvasWorkspaceItemLayerProps & {
    onHoverImageDetailEnter?: (itemId: string) => void
    onHoverImageDetailLeave?: () => void
  }) => {
    const item = props.canvasItems[0]
    return (
      <div
        id={`item-${item.id}`}
        data-testid="hover-target"
        data-canvas-item-id={item.id}
        data-active-preview-item-id={props.activeVideoPreviewItemId ?? ''}
        onMouseDown={(event) => {
          event.stopPropagation()
          props.handleItemMouseDown?.(event, item.id)
        }}
        onMouseEnter={() => props.onHoverImageDetailEnter?.(item.id)}
        onMouseLeave={() => props.onHoverImageDetailLeave?.()}
      >
        {item.id}:{props.useWebGLRenderer ? props.renderSnapshot?.overlayNodes?.map((node) => node.id).join(',') : 'dom'}
        {props.imageAnchoredImageDraft?.sourceImageItemId === item.id && (
          <textarea data-testid="anchored-image-prompt" />
        )}
      </div>
    )
  },
}))

vi.mock('./CanvasWorkspaceFloatingPanels', () => ({
  CanvasWorkspaceFloatingPanels: ({
    hoverImageDetailItem,
    hoverImageDetailPanelPosition,
    hoverImageDetailSourceRect,
  }: { hoverImageDetailItem?: Pick<CanvasItem, 'id'> | null; hoverImageDetailPanelPosition?: { left: number; top: number } | null; hoverImageDetailSourceRect?: { width: number; height: number } | null }) => (
    <div>
      <div data-testid="hover-item-id">{hoverImageDetailItem?.id ?? 'none'}</div>
      <div data-testid="hover-panel-left">{hoverImageDetailPanelPosition?.left ?? 'none'}</div>
      <div data-testid="hover-source-width">{hoverImageDetailSourceRect?.width ?? 'none'}</div>
      <div data-testid="hover-source-height">{hoverImageDetailSourceRect?.height ?? 'none'}</div>
    </div>
  ),
}))

vi.mock('../generationTaskSnapshot', () => ({
  fetchCanvasGenerationTaskSnapshot: vi.fn(),
}))

function createBaseProps(overrides: Partial<CanvasWorkspaceCanvasAreaProps> = {}): CanvasWorkspaceCanvasAreaProps {
  const canvasRef = React.createRef<HTMLDivElement>()
  const canvasContentRef = React.createRef<HTMLDivElement>()
  const WebGLStageTestDouble = ({
    nodes,
    isInteracting,
    onReadyChange,
    onFallback,
  }: {
    nodes: NonNullable<CanvasWorkspaceItemLayerProps['renderSnapshot']>['nodes']
    isInteracting?: boolean
    onReadyChange?: (ready: boolean) => void
    onFallback?: () => void
  }) => {
    React.useEffect(() => {
      onReadyChange?.(true)
    }, [onReadyChange])
    return (
      <button
        data-testid="webgl-stage"
        data-interacting={String(Boolean(isInteracting))}
        onClick={() => onFallback?.()}
        type="button"
      >
        {nodes.map((node) => node.id).join(',')}
      </button>
    )
  }

  return {
    ...canvasRenderFixture({ id: 'img-1', type: 'image', url: '', x: 20, y: 30 }),
    interactionPreview: undefined,
    imageDetailData: null, imageDetailPanelPosition: null,
    handleCloseImageDetails: vi.fn(), textRedrawState: null, textRedrawPanelPosition: null,
    TEXT_REDRAW_PANEL_TOKENS: { panelRadius: 24, panelPadding: 20 },
    handleChangeTextRedrawSegment: vi.fn(), handleCancelTextRedraw: vi.fn(), handleSubmitTextRedraw: vi.fn(),
    selectedSingleItem: null, selectedSingleItemRect: null, selectedSingleItemCanvasRect: null,
    shouldShowImageToolbar: () => false, openImageAnchoredImageDraft: vi.fn(), openImageAnchoredVideoDraft: vi.fn(),
    handleOpenHDUpscale: vi.fn(), handleOpenCutout: vi.fn(), handleOpenImageErase: vi.fn(), handleOpenTextRedraw: vi.fn(),
    handleOpenSpatialAngle: vi.fn(), handleOpenCropPanel: vi.fn(), handleDeleteCanvasImage: vi.fn(), handleOpenImageDetails: vi.fn(),
    handleRetryFailedGeneration: vi.fn(), shouldRenderSelectedMeta: false, selectedSingleItemViewportWidth: 0,
    selectedIsImageGroup: false, editingNameId: null, setEditingNameId: vi.fn(), selectedIsGenerator: false,
    formatDimensionLabel: () => '', selectedSingleItemWidth: 0, selectedSingleItemHeight: 0, projectedGuides: [], selectionBox: null,
    setResizingGroupId: vi.fn(), handleUngroup: vi.fn(), setMultiSelectToolsOpen: vi.fn(), multiSelectToolsOpen: null,
    setGroupBackgroundColor: vi.fn(), handleCreateGroup: vi.fn(), handleMergeLayers: vi.fn(), handleAlign: vi.fn(),
    handleAutoArrange: vi.fn(), handleSpacing: vi.fn(), handleContextMenuAction: vi.fn(),
    canvasRef,
    canvasContentRef,
    canvasItems: [
      {
        id: 'img-1',
        type: 'image',
        url: 'https://example.com/image.png',
        x: 20,
        y: 30,
        width: 100,
        height: 80,
        z_index: 1,
        asset_origin: 'local_upload',
        created_at: '2026-04-16T12:00:00Z',
        creator_name: 'Alice',
      },
    ],
    imageDetailItemId: null,
    imageDetailItem: null,
    updateItem: vi.fn(),
    handleMouseDown: vi.fn(),
    handleMouseMove: vi.fn(),
    handleMouseUp: vi.fn(),
    setContextMenu: vi.fn(),
    setSelectedItems: vi.fn(),
    setActiveContextMenuItem: vi.fn(),
    handleCanvasClick: vi.fn(),
    isPanning: false,
    activeTool: 'select',
    MARK_CURSOR: 'crosshair',
    offset: { x: 0, y: 0 },
    zoom: 100,
    isWheeling: false,
    brushDraft: null,
    marks: [],
    selectedItems: [],
    cropState: null,
    textRedrawExtractingItemIds: new Set<string>(),
    isDark: false,
    getItemDims: vi.fn((item: CanvasItem) => ({ width: item.width ?? 0, height: item.height ?? 0 })),
    webGLStageComponent: WebGLStageTestDouble,
    ...overrides,
  }
}

describe('CanvasWorkspaceCanvasArea', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      headers: { get: () => '1024' },
      blob: async () => new Blob(['x'.repeat(1024)]),
    })))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('does not open image details when hovering a canvas image', () => {
    const props = createBaseProps()
    render(<CanvasWorkspaceCanvasArea {...props} />)

    const canvas = props.canvasRef.current as HTMLDivElement
    const target = screen.getByTestId('hover-target') as HTMLDivElement

    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 800,
      height: 600,
      right: 800,
      bottom: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    target.getBoundingClientRect = () => ({
      left: 40,
      top: 60,
      width: 100,
      height: 80,
      right: 140,
      bottom: 140,
      x: 40,
      y: 60,
      toJSON: () => ({}),
    })

    fireEvent.mouseEnter(target)
    expect(screen.getByTestId('hover-item-id').textContent).toBe('none')
    expect(screen.getByTestId('hover-panel-left').textContent).toBe('none')
    expect(screen.getByTestId('hover-source-width').textContent).toBe('none')
    expect(screen.getByTestId('hover-source-height').textContent).toBe('none')
  })

  it('extracts the first image file from clipboard data', () => {
    const file = new File(['image'], 'paste.png', { type: 'image/png' })
    const clipboardData = {
      files: [file],
      items: [],
    }

    const result = getClipboardImageFile(clipboardData as unknown as ClipboardEvent['clipboardData'])

    expect(result).toBe(file)
  })

  it('routes pasted clipboard images through the canvas paste handler', () => {
    const handleCanvasPaste = vi.fn()
    const props = createBaseProps({ handleCanvasPaste })
    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const file = new File(['image'], 'paste.png', { type: 'image/png' })

    fireEvent.paste(view.container.firstChild as Element, {
      clipboardData: {
        files: [file],
        items: [],
      },
    })

    expect(handleCanvasPaste).toHaveBeenCalledTimes(1)
    expect(handleCanvasPaste).toHaveBeenCalledWith(file)
  })

  it('mounts the WebGL stage by default and keeps selected image visuals in WebGL while providing DOM overlay nodes', () => {
    const props = createBaseProps({
      canvasItems: [
        {
          id: 'plain-image',
          type: 'image',
          url: 'https://example.com/plain.png',
          x: 20,
          y: 30,
          width: 100,
          height: 80,
          z_index: 1,
        },
        {
          id: 'selected-image',
          type: 'image',
          url: 'https://example.com/selected.png',
          x: 120,
          y: 130,
          width: 100,
          height: 80,
          z_index: 2,
        },
      ],
      selectedItems: ['selected-image'],
    })

    render(<CanvasWorkspaceCanvasArea {...props} />)

    expect(screen.getByTestId('webgl-stage').textContent).toBe('plain-image,selected-image')
    expect(screen.getByTestId('hover-target').textContent).toContain('selected-image')
    expect(screen.getByTestId('hover-target').textContent).not.toContain('plain-image,')
  })

  it('keeps large stable image sets in WebGL and limits the DOM overlay to active items', () => {
    const canvasItems: CanvasItem[] = Array.from({ length: 1000 }, (_, index) => ({
      id: `image-${index}`,
      type: 'image',
      url: `https://example.com/image-${index}.png`,
      x: (index % 50) * 120,
      y: Math.floor(index / 50) * 100,
      width: 100,
      height: 80,
      z_index: index,
    }))
    const props = createBaseProps({
      canvasItems,
      selectedItems: ['image-0'],
    })

    render(<CanvasWorkspaceCanvasArea {...props} />)

    const webglIds = screen.getByTestId('webgl-stage').textContent?.split(',').filter(Boolean) ?? []
    expect(webglIds.length).toBeGreaterThan(0)
    expect(webglIds.length).toBeLessThan(1000)
    expect(webglIds).toContain('image-1')
    expect(webglIds).toContain('image-0')
    expect(screen.getByTestId('hover-target').textContent).toContain('image-0')
  })

  it('switches a hovered WebGL video back to the DOM overlay for playback controls', () => {
    const props = createBaseProps({
      canvasItems: [
        {
          id: 'video-1',
          type: 'video',
          url: 'https://example.com/video.mp4',
          x: 0,
          y: 0,
          width: 160,
          height: 90,
          z_index: 1,
        },
      ],
      canvasCamera: {
        getCamera: () => ({ zoom: 100, offset: { x: 0, y: 0 } }),
      },
    })

    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const canvas = props.canvasRef.current as HTMLDivElement
    Object.defineProperty(canvas, 'clientWidth', { configurable: true, value: 1000 })
    Object.defineProperty(canvas, 'clientHeight', { configurable: true, value: 800 })
    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 1000,
      height: 800,
      right: 1000,
      bottom: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    expect(screen.getByTestId('webgl-stage').textContent).toBe('video-1')

    fireEvent.mouseMove(view.container.firstChild as Element, {
      clientX: 560,
      clientY: 445,
    })

    expect(screen.getByTestId('webgl-stage').textContent).toBe('video-1')
    expect(screen.getByTestId('hover-target').textContent).toContain('video-1')
    expect(screen.getByTestId('hover-target')).toHaveAttribute('data-active-preview-item-id', 'video-1')

    fireEvent.mouseMove(screen.getByTestId('hover-target'), {
      clientX: 561,
      clientY: 446,
    })

    expect(screen.getByTestId('hover-target')).toHaveAttribute('data-active-preview-item-id', 'video-1')
  })

  it('keeps other images in WebGL when an anchored image draft panel is open', () => {
    const props = createBaseProps({
      canvasItems: [
        {
          id: 'source-image',
          type: 'image',
          url: 'https://example.com/source.png',
          x: 0,
          y: 0,
          width: 100,
          height: 80,
          z_index: 1,
        },
        {
          id: 'other-image',
          type: 'image',
          url: 'https://example.com/other.png',
          x: 140,
          y: 0,
          width: 100,
          height: 80,
          z_index: 2,
        },
      ],
      selectedItems: ['source-image'],
      imageAnchoredImageDraft: { sourceImageUrl: '', prompt: '', model_name: '', provider_code: '', aspect_ratio: '1:1', resolution: '1K', reference_images: [],  sourceImageItemId: 'source-image' },
    })

    render(<CanvasWorkspaceCanvasArea {...props} />)

    expect(screen.getByTestId('webgl-stage').textContent).toBe('source-image,other-image')
    expect(screen.getByTestId('hover-target').textContent).toContain('source-image')
    expect(screen.getByTestId('hover-target').textContent).not.toContain('other-image')
  })

  it('uses the DOM scene renderer when the renderer override requests DOM fallback', () => {
    vi.stubEnv('VITE_CANVAS_RENDERER', 'dom')
    const props = createBaseProps()

    render(<CanvasWorkspaceCanvasArea {...props} />)

    expect(screen.getByTestId('scene-layer')).toBeInTheDocument()
    expect(screen.queryByTestId('webgl-stage')).not.toBeInTheDocument()
  })

  it('routes clicks on WebGL-rendered items through snapshot hit testing', () => {
    const setSelectedItems = vi.fn()
    const props = createBaseProps({
      setSelectedItems,
      canvasItems: [
        {
          id: 'plain-image',
          type: 'image',
          url: 'https://example.com/plain.png',
          x: 0,
          y: 0,
          width: 100,
          height: 80,
          z_index: 1,
        },
      ],
      canvasCamera: {
        getCamera: () => ({ zoom: 100, offset: { x: 0, y: 0 } }),
      },
    })

    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    screen.getByTestId('webgl-stage')
    const canvas = props.canvasRef.current as HTMLDivElement
    Object.defineProperty(canvas, 'clientWidth', { configurable: true, value: 1000 })
    Object.defineProperty(canvas, 'clientHeight', { configurable: true, value: 800 })
    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 1000,
      height: 800,
      right: 1000,
      bottom: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    fireEvent.click(view.container.firstChild as Element, {
      clientX: 550,
      clientY: 440,
    })

    expect(setSelectedItems).toHaveBeenCalledWith(['plain-image'])
  })

  it('lets the hand tool pan the canvas over WebGL-rendered groups', () => {
    const handleMouseDown = vi.fn()
    const handleItemMouseDown = vi.fn()
    const props = createBaseProps({
      activeTool: 'hand',
      handleMouseDown,
      handleItemMouseDown,
      canvasItems: [
        { url: '', 
          id: 'group-1',
          type: 'group',
          x: 0,
          y: 0,
          width: 300,
          height: 200,
          z_index: 1,
        },
      ],
      canvasCamera: {
        getCamera: () => ({ zoom: 100, offset: { x: 0, y: 0 } }),
      },
    })

    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const canvas = props.canvasRef.current as HTMLDivElement
    Object.defineProperty(canvas, 'clientWidth', { configurable: true, value: 1000 })
    Object.defineProperty(canvas, 'clientHeight', { configurable: true, value: 800 })
    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 1000,
      height: 800,
      right: 1000,
      bottom: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    fireEvent.mouseDown(view.container.firstChild as Element, {
      clientX: 550,
      clientY: 450,
      button: 0,
    })

    expect(handleMouseDown).toHaveBeenCalledTimes(1)
    expect(handleItemMouseDown).not.toHaveBeenCalled()
  })

  it('passes interaction state into the WebGL stage for LOD decisions', () => {
    const props = createBaseProps({
      isPanning: true,
      isWheeling: false,
      canvasItems: [
        {
          id: 'plain-image',
          type: 'image',
          url: 'https://example.com/plain.png',
          x: 0,
          y: 0,
          width: 100,
          height: 80,
          z_index: 1,
        },
      ],
    })

    render(<CanvasWorkspaceCanvasArea {...props} />)

    expect(screen.getByTestId('webgl-stage').getAttribute('data-interacting')).toBe('true')
  })

  it('falls back to the DOM scene renderer when the WebGL stage reports a failure', () => {
    const props = createBaseProps({
      canvasItems: [
        {
          id: 'plain-image',
          type: 'image',
          url: 'https://example.com/plain.png',
          x: 0,
          y: 0,
          width: 100,
          height: 80,
          z_index: 1,
        },
      ],
    })

    render(<CanvasWorkspaceCanvasArea {...props} />)
    fireEvent.click(screen.getByTestId('webgl-stage'))

    expect(screen.getByTestId('scene-layer')).toBeInTheDocument()
  })

  it('pastes an external/OS image even when a stale internal canvas copy intent exists (regression)', () => {
    // Regression: once a user copied something inside the canvas, the sticky
    // clipboardSource='internal' flag used to permanently route every paste to
    // the internal duplicate path, so an image copied from the OS / a web page
    // could never be pasted into the canvas until a page refresh. The live
    // clipboard image must win over the stale internal intent.
    const handleCanvasPaste = vi.fn()
    const handleContextMenuAction = vi.fn()
    const props = createBaseProps({
      handleCanvasPaste,
      handleContextMenuAction,
      clipboardItems: [{ url: '',  id: 'copied-image', type: 'image', x: 10, y: 20 }],
      clipboardSource: 'internal',
    })
    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const catcher = view.container.querySelector('[data-canvas-clipboard-catcher="true"]') as HTMLElement
    const file = new File(['image'], 'paste.png', { type: 'image/png' })

    fireEvent.paste(catcher, {
      clipboardData: {
        files: [file],
        items: [],
      },
    })

    expect(handleCanvasPaste).toHaveBeenCalledTimes(1)
    expect(handleCanvasPaste).toHaveBeenCalledWith(file)
    expect(handleContextMenuAction).not.toHaveBeenCalledWith('paste')
  })

  it('routes native paste events with the canvas clipboard marker through internal canvas paste', () => {
    const handleCanvasPaste = vi.fn()
    const handleContextMenuAction = vi.fn()
    const props = createBaseProps({
      handleCanvasPaste,
      handleContextMenuAction,
    })
    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const catcher = view.container.querySelector('[data-canvas-clipboard-catcher="true"]') as HTMLElement

    fireEvent.paste(catcher, {
      clipboardData: {
        files: [],
        items: [],
        types: [CANVAS_CLIPBOARD_MIME],
      },
    })

    expect(handleContextMenuAction).toHaveBeenCalledWith('paste')
    expect(handleCanvasPaste).not.toHaveBeenCalled()
  })

  it('focuses the hidden clipboard catcher before item mouse handlers stop propagation so canvas shortcuts stay active after selecting an element', () => {
    const props = createBaseProps()
    render(
      <div>
        <input data-testid="editor" />
        <CanvasWorkspaceCanvasArea {...props} />
      </div>,
    )

    const input = screen.getByTestId('editor') as HTMLInputElement
    input.focus()
    expect(document.activeElement).toBe(input)

    const target = screen.getByTestId('hover-target')
    fireEvent.mouseDown(target)

    expect((document.activeElement as HTMLElement | null)?.getAttribute('data-canvas-clipboard-catcher')).toBe('true')
  })

  it('preserves focus for protected agent text selection instead of stealing it back to the clipboard catcher', () => {
    const props = createBaseProps()
    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const canvas = view.container.firstChild as HTMLDivElement
    const catcher = view.container.querySelector('[data-canvas-clipboard-catcher="true"]') as HTMLElement
    const protectedText = document.createElement('div')

    protectedText.setAttribute('data-canvas-text-selectable', 'true')
    protectedText.tabIndex = 0
    protectedText.textContent = 'Selected agent text'
    canvas.appendChild(protectedText)

    catcher.focus()
    expect(document.activeElement).toBe(catcher)

    protectedText.focus()
    expect(document.activeElement).toBe(protectedText)

    fireEvent.mouseDown(protectedText)

    expect(document.activeElement).toBe(protectedText)
  })

  it('routes window-level paste events through the canvas paste handler when an image is present', () => {
    const handleCanvasPaste = vi.fn()
    const props = createBaseProps({ handleCanvasPaste })
    render(<CanvasWorkspaceCanvasArea {...props} />)
    const file = new File(['image'], 'wechat-paste.png', { type: 'image/png' })
    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true }) as Event & {
      clipboardData: DataTransfer
    }

    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        files: [file],
        items: [],
      },
    })

    window.dispatchEvent(pasteEvent)

    expect(handleCanvasPaste).toHaveBeenCalledTimes(1)
    expect(handleCanvasPaste).toHaveBeenCalledWith(file)
  })

  it('routes window-level paste events through internal canvas paste when the hidden clipboard catcher is focused', () => {
    const handleCanvasPaste = vi.fn()
    const handleContextMenuAction = vi.fn()
    const props = createBaseProps({
      handleCanvasPaste,
      handleContextMenuAction,
      clipboardItems: [{ url: '',  id: 'group-1', type: 'group', x: 10, y: 20 }],
      clipboardSource: 'internal',
    })
    const view = render(<CanvasWorkspaceCanvasArea {...props} />)
    const catcher = view.container.querySelector('[data-canvas-clipboard-catcher="true"]') as HTMLDivElement
    catcher.focus()
    expect(document.activeElement).toBe(catcher)

    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true }) as Event & {
      clipboardData: DataTransfer
    }

    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        files: [],
        items: [],
        types: [],
      },
    })

    window.dispatchEvent(pasteEvent)

    expect(handleContextMenuAction).toHaveBeenCalledWith('paste')
    expect(handleCanvasPaste).not.toHaveBeenCalled()
  })

  it('ignores window-level image paste when an editable element is focused', () => {
    const handleCanvasPaste = vi.fn()
    const props = createBaseProps({ handleCanvasPaste })
    render(
      <div>
        <input data-testid="editor" />
        <CanvasWorkspaceCanvasArea {...props} />
      </div>,
    )

    const input = screen.getByTestId('editor') as HTMLInputElement
    input.focus()
    const file = new File(['image'], 'wechat-paste.png', { type: 'image/png' })
    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true }) as Event & {
      clipboardData: DataTransfer
    }

    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        files: [file],
        items: [],
      },
    })

    input.dispatchEvent(pasteEvent)

    expect(handleCanvasPaste).not.toHaveBeenCalled()
  })

  it('lets anchored image prompt textareas handle text paste after a canvas copy intent exists', () => {
    const handleCanvasPaste = vi.fn()
    const handleContextMenuAction = vi.fn()
    const props = createBaseProps({
      handleCanvasPaste,
      handleContextMenuAction,
      selectedItems: ['img-1'],
      clipboardItems: [{ url: '',  id: 'img-1', type: 'image', x: 20, y: 30 }],
      clipboardSource: 'internal',
      imageAnchoredImageDraft: { sourceImageUrl: '', prompt: '', model_name: '', provider_code: '', aspect_ratio: '1:1', resolution: '1K', reference_images: [],  sourceImageItemId: 'img-1' },
    })
    render(<CanvasWorkspaceCanvasArea {...props} />)

    const prompt = screen.getByTestId('anchored-image-prompt') as HTMLTextAreaElement
    prompt.focus()

    fireEvent.paste(prompt, {
      clipboardData: {
        files: [],
        items: [],
        types: ['text/plain'],
        getData: (type: string) => (type === 'text/plain' ? 'make the shirt linen white' : ''),
      },
    })

    expect(handleContextMenuAction).not.toHaveBeenCalledWith('paste')
    expect(handleCanvasPaste).not.toHaveBeenCalled()
  })
})
