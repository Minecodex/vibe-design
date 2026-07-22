import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { CanvasVideoItem } from './CanvasVideoItem'

function mockVideoPlaybackApis() {
  const playMock = vi.fn().mockResolvedValue(undefined)
  const pauseMock = vi.fn()
  let currentTimeValue = 12

  Object.defineProperty(HTMLMediaElement.prototype, 'play', {
    configurable: true,
    writable: true,
    value: playMock,
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    writable: true,
    value: pauseMock,
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
    configurable: true,
    get() {
      return currentTimeValue
    },
    set(value: number) {
      currentTimeValue = value
    },
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'duration', {
    configurable: true,
    get() {
      return 12
    },
  })

  return {
    playMock,
    pauseMock,
    getCurrentTime: () => currentTimeValue,
  }
}

describe('CanvasVideoItem', () => {
  test('shows a default play button before hover', () => {
    render(
      <CanvasVideoItem
        url="https://example.com/demo.mp4"
        zoom={100}
        onLoadedMetadata={vi.fn()}
      />,
    )

    expect(screen.getByLabelText('Play video preview')).toBeInTheDocument()
  })

  test('hides the default play button and starts autoplay on hover', async () => {
    const { playMock } = mockVideoPlaybackApis()

    render(
      <CanvasVideoItem
        url="https://example.com/demo.mp4"
        zoom={100}
        onLoadedMetadata={vi.fn()}
      />,
    )

    const container = screen.getByTestId('canvas-video-item')
    fireEvent.mouseEnter(container)

    expect(screen.queryByLabelText('Play video preview')).not.toBeInTheDocument()
    expect(playMock).toHaveBeenCalled()
  })

  test('starts autoplay immediately when mounted as an active preview', () => {
    const { playMock } = mockVideoPlaybackApis()

    render(
      <CanvasVideoItem
        url="https://example.com/demo.mp4"
        zoom={100}
        autoPreview
        onLoadedMetadata={vi.fn()}
      />,
    )

    expect(screen.queryByLabelText('Play video preview')).not.toBeInTheDocument()
    expect(playMock).toHaveBeenCalled()
  })

  test('pauses and resets playback when hover ends', () => {
    const { pauseMock, getCurrentTime } = mockVideoPlaybackApis()

    render(
      <CanvasVideoItem
        url="https://example.com/demo.mp4"
        zoom={100}
        onLoadedMetadata={vi.fn()}
      />,
    )

    const container = screen.getByTestId('canvas-video-item')
    fireEvent.mouseEnter(container)
    fireEvent.mouseLeave(container)

    expect(pauseMock).toHaveBeenCalled()
    expect(getCurrentTime()).toBe(0)
    expect(screen.getByLabelText('Play video preview')).toBeInTheDocument()
  })
})
