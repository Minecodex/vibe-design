import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { BrushToolState } from '../types'
import { CanvasBrushToolPanel } from './CanvasBrushToolPanel'

describe('CanvasBrushToolPanel', () => {
  it('keeps the left brush color trigger aligned with the selected brush toolbar button size', () => {
    const state: BrushToolState = {
      color: '#111111',
      size: 12,
      activePanel: null,
    }

    render(
      <CanvasBrushToolPanel
        isDark={false}
        activeTool="brush"
        state={state}
        setState={vi.fn()}
        brushToolIndex={3}
        totalTools={4}
      />,
    )

    expect(screen.getByRole('button', { name: 'Brush Color' })).toHaveStyle({
      width: '32px',
      height: '32px',
    })
  })
})
