import { fireEvent, render, screen } from '@testing-library/react'
import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useCanvasCamera } from './hooks/useCanvasCamera'

function CameraHarness({
  onCommitOffset,
  onCommitZoom,
}: {
  onCommitOffset: (offset: { x: number; y: number }) => void
  onCommitZoom: (zoom: number) => void
}) {
  const contentRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef(100)
  const offsetRef = useRef({ x: 0, y: 0 })
  const [zoom, setZoomState] = useState(100)
  const [offset, setOffsetState] = useState({ x: 0, y: 0 })
  const setZoom = (nextZoom: number) => {
    onCommitZoom(nextZoom)
    setZoomState(nextZoom)
  }
  const setOffset = (nextOffset: { x: number; y: number }) => {
    onCommitOffset(nextOffset)
    setOffsetState(nextOffset)
  }
  const camera = useCanvasCamera({
    canvasContentRef: contentRef,
    zoom,
    setZoom,
    zoomRef,
    offset,
    setOffset,
    offsetRef,
  })

  return (
    <>
      <div data-testid="content" ref={contentRef} />
      <button type="button" onClick={() => camera.panToOffset({ x: 40, y: -12 })}>pan</button>
      <button type="button" onClick={() => camera.commitCamera('pan-end')}>commit</button>
      <button type="button" onClick={() => camera.setCamera({ zoom: 80, offset: { x: 8, y: 16 } }, { commit: true, reason: 'zoom-button' })}>zoom</button>
    </>
  )
}

describe('useCanvasCamera', () => {
  it('updates the DOM transform during pan without committing React state until requested', () => {
    const onCommitOffset = vi.fn()
    const onCommitZoom = vi.fn()
    render(<CameraHarness onCommitOffset={onCommitOffset} onCommitZoom={onCommitZoom} />)

    onCommitOffset.mockClear()
    onCommitZoom.mockClear()
    fireEvent.click(screen.getByText('pan'))

    expect(screen.getByTestId('content')).toHaveStyle({
      transform: 'translate(-50%, -50%) translate(40px, -12px) scale(1)',
    })
    expect(onCommitOffset).not.toHaveBeenCalled()
    expect(onCommitZoom).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('commit'))

    expect(onCommitOffset).toHaveBeenCalledTimes(1)
    expect(onCommitOffset).toHaveBeenLastCalledWith({ x: 40, y: -12 })
    expect(onCommitZoom).toHaveBeenCalledTimes(1)
    expect(onCommitZoom).toHaveBeenLastCalledWith(100)
  })

  it('commits explicit zoom camera updates immediately when requested', () => {
    const onCommitOffset = vi.fn()
    const onCommitZoom = vi.fn()
    render(<CameraHarness onCommitOffset={onCommitOffset} onCommitZoom={onCommitZoom} />)

    onCommitOffset.mockClear()
    onCommitZoom.mockClear()
    fireEvent.click(screen.getByText('zoom'))

    expect(screen.getByTestId('content')).toHaveStyle({
      transform: 'translate(-50%, -50%) translate(8px, 16px) scale(0.8)',
    })
    expect(onCommitOffset).toHaveBeenLastCalledWith({ x: 8, y: 16 })
    expect(onCommitZoom).toHaveBeenLastCalledWith(80)
  })
})
