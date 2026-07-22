import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ImagePreviewOverlay } from './ImagePreviewOverlay'

describe('ImagePreviewOverlay', () => {
  test('renders the shared image preview dialog', () => {
    const setPreviewImageUrl = vi.fn()

    render(
      <ImagePreviewOverlay
        previewImageUrl="https://example.com/preview.png"
        setPreviewImageUrl={setPreviewImageUrl}
      />,
    )

    const image = screen.getByAltText('Preview')
    expect(image).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toHaveClass('z-[2147483647]')
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  test('closes when the dialog requests close', () => {
    const setPreviewImageUrl = vi.fn()

    render(
      <ImagePreviewOverlay
        previewImageUrl="https://example.com/preview.png"
        setPreviewImageUrl={setPreviewImageUrl}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(setPreviewImageUrl).toHaveBeenCalledWith(null)
  })
})
