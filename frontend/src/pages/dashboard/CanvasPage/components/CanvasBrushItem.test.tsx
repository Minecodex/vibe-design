import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { CanvasBrushItem } from './CanvasBrushItem'

describe('CanvasBrushItem', () => {
  it('renders a visible dot for a single-point brush draft so drawing is visible immediately', () => {
    const item: CanvasItem = {
      id: 'brush-preview',
      type: 'brush_path',
      url: '',
      x: 0,
      y: 0,
      width: 24,
      height: 24,
      brushColor: '#00ff00',
      brushSize: 12,
      points: [{ x: 0.5, y: 0.5 }],
    }

    const { container } = render(<CanvasBrushItem item={item} />)

    expect(screen.getByLabelText('brush-preview')).toBeInTheDocument()
    expect(container.querySelector('circle')).not.toBeNull()
  })
})
