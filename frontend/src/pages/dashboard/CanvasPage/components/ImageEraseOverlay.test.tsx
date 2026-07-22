import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import type { ImageEraseSession } from '../types'

import { ImageEraseOverlay } from './ImageEraseOverlay'

function buildSession(overrides: Partial<ImageEraseSession> = {}): ImageEraseSession {
  return {
    tool: 'erase',
    itemId: 'image-1',
    imageUrl: 'https://example.com/source.png',
    displayWidth: 320,
    displayHeight: 180,
    sourceWidth: 960,
    sourceHeight: 540,
    mode: 'brush',
    brushSize: 24,
    history: [{ maskDataUrl: null }],
    future: [],
    isSubmitting: false,
    hasMask: false,
    ...overrides,
  }
}

function renderOverlay(extraWrapper?: (node: React.ReactNode) => React.ReactNode) {
  const overlay = (
    <ImageEraseOverlay
      session={buildSession()}
      tool="erase"
      isDark={false}
      onCancel={() => {}}
      onConfirm={() => {}}
      onUndo={() => {}}
      onRedo={() => {}}
      onChangeMode={() => {}}
      onChangeBrushSize={() => {}}
      canvasRef={{ current: null }}
      previewRect={null}
    />
  )

  return render(extraWrapper ? extraWrapper(overlay) : overlay)
}

describe('ImageEraseOverlay', () => {
  test('renders erase tool buttons and brush size slider', () => {
    renderOverlay()

    expect(screen.getByRole('button', { name: 'canvas.tools.brush' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'canvas.tools.rect' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'canvas.tools.segment' })).not.toBeInTheDocument()
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })

  test('cancels on escape', () => {
    const onCancel = vi.fn()

    render(
      <ImageEraseOverlay
        session={buildSession()}
        tool="erase"
        isDark={false}
        onCancel={onCancel}
        onConfirm={() => {}}
        onUndo={() => {}}
        onRedo={() => {}}
        onChangeMode={() => {}}
        onChangeBrushSize={() => {}}
        canvasRef={{ current: null }}
        previewRect={null}
      />,
    )

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  test('keeps plain wheel events inside the toolbar', () => {
    const onWheel = vi.fn()
    const { container } = renderOverlay(node => <div onWheel={onWheel}>{node}</div>)

    const toolbar = container.querySelector('.nowheel')
    expect(toolbar).not.toBeNull()

    fireEvent.wheel(toolbar!, { deltaY: 120 })

    expect(onWheel).not.toHaveBeenCalled()
  })

  test('allows ctrl + wheel to bubble so canvas zoom can handle it', () => {
    const onWheel = vi.fn()
    const { container } = renderOverlay(node => <div onWheel={onWheel}>{node}</div>)

    const toolbar = container.querySelector('.nowheel')
    expect(toolbar).not.toBeNull()

    fireEvent.wheel(toolbar!, { deltaY: 120, ctrlKey: true })

    expect(onWheel).toHaveBeenCalledTimes(1)
  })

  test('uses cutout-specific confirm copy when editing cutouts', () => {
    render(
      <ImageEraseOverlay
        session={buildSession({ hasMask: true })}
        tool="cutout"
        isDark={false}
        onCancel={() => {}}
        onConfirm={() => {}}
        onUndo={() => {}}
        onRedo={() => {}}
        onChangeMode={() => {}}
        onChangeBrushSize={() => {}}
        canvasRef={{ current: null }}
        previewRect={null}
      />,
    )

    expect(screen.getByRole('button', { name: '生成抠图' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'canvas.generate_1' })).not.toBeInTheDocument()
  })
  test('keeps rect selection available for cutout mode', () => {
    render(
      <ImageEraseOverlay
        session={buildSession({ hasMask: true })}
        tool="cutout"
        isDark={false}
        onCancel={() => {}}
        onConfirm={() => {}}
        onUndo={() => {}}
        onRedo={() => {}}
        onChangeMode={() => {}}
        onChangeBrushSize={() => {}}
        canvasRef={{ current: null }}
        previewRect={null}
      />,
    )

    expect(screen.getByRole('button', { name: 'canvas.tools.rect' })).toBeInTheDocument()
  })

  test('keeps the original slider for cutout brush mode', () => {
    render(
      <ImageEraseOverlay
        session={buildSession({ hasMask: true, mode: 'brush' })}
        tool="cutout"
        isDark={false}
        onCancel={() => {}}
        onConfirm={() => {}}
        onUndo={() => {}}
        onRedo={() => {}}
        onChangeMode={() => {}}
        onChangeBrushSize={() => {}}
        canvasRef={{ current: null }}
        previewRect={null}
      />,
    )

    expect(screen.getByRole('slider')).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })
})
