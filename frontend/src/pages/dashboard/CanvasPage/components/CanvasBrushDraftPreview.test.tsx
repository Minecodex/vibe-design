import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CanvasBrushDraftPreview } from './CanvasBrushDraftPreview'

describe('CanvasBrushDraftPreview', () => {
  it('renders the in-progress brush stroke in a positioned local preview box', () => {
    const { container } = render(
      <CanvasBrushDraftPreview
        points={[
          { x: 100, y: 120 },
          { x: 140, y: 180 },
        ]}
        brushColor="#00ff00"
        brushSize={12}
      />,
    )

    expect(screen.getByLabelText('brush-draft-preview')).toBeInTheDocument()
    expect(screen.getByTestId('brush-draft-preview-box')).toHaveStyle({
      left: '94px',
      top: '114px',
      width: '52px',
      height: '72px',
    })
    expect(container.querySelector('path')).not.toBeNull()
    expect(container.querySelector('path')).toHaveAttribute('d', 'M 6 6 L 46 66')
  })
})
