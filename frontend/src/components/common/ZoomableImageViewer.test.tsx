import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ZoomableImageViewer } from './ZoomableImageViewer'

describe('ZoomableImageViewer', () => {
  it('zooms with plain wheel input', () => {
    render(<ZoomableImageViewer src="/preview.png" alt="Preview image" />)

    const image = screen.getByAltText('Preview image')
    const viewport = image.parentElement?.parentElement

    expect(viewport).not.toBeNull()

    Object.defineProperty(image, 'naturalWidth', { configurable: true, value: 2000 })
    Object.defineProperty(image, 'naturalHeight', { configurable: true, value: 1000 })
    fireEvent.load(image)
    fireEvent.wheel(viewport!, { deltaY: -120 })

    expect(image).toHaveStyle({ width: '2400px', height: '1200px' })
  })

  it('ignores ctrl + wheel zoom gestures', () => {
    render(<ZoomableImageViewer src="/preview.png" alt="Preview image" />)

    const image = screen.getByAltText('Preview image')
    const viewport = image.parentElement?.parentElement

    expect(viewport).not.toBeNull()

    Object.defineProperty(image, 'naturalWidth', { configurable: true, value: 2000 })
    Object.defineProperty(image, 'naturalHeight', { configurable: true, value: 1000 })
    fireEvent.load(image)
    fireEvent.wheel(viewport!, { deltaY: -120, ctrlKey: true })

    expect(image).toHaveStyle({ width: '2000px', height: '1000px' })
  })
})
