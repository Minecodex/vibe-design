import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { BrushColorPopover, CanvasBrushToolbar } from './CanvasBrushToolbar'

const brushItem: CanvasItem = {
  id: 'brush-1',
  type: 'brush_path',
  url: '',
  x: 120,
  y: 80,
  width: 153,
  height: 162,
  brushColor: '#00ff00',
  brushSize: 10,
  pathBounds: {
    x: 115,
    y: 75,
    width: 153,
    height: 162,
  },
  points: [
    { x: 0.1, y: 0.2 },
    { x: 0.7, y: 0.8 },
  ],
}

describe('CanvasBrushToolbar', () => {
  it('renders color, brush size, width, and height controls in the shared floating chrome', () => {
    render(
      <CanvasBrushToolbar
        item={brushItem}
        rect={{ left: 120, top: 60, width: 153, height: 162 }}
        isDark={false}
        colorLabel="Color"
        sizeLabel="Size"
        widthLabel="W"
        heightLabel="H"
        state={{ activePanel: null }}
        setState={() => {}}
        updateBrushItem={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: 'Color' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('10')).toBeInTheDocument()
    expect(screen.getByDisplayValue('153')).toBeInTheDocument()
    expect(screen.getByDisplayValue('162')).toBeInTheDocument()
    expect(screen.getByText('Px')).toBeInTheDocument()
  })

  it('forwards direct size and dimension edits', () => {
    const updateBrushItem = vi.fn()

    render(
      <CanvasBrushToolbar
        item={brushItem}
        rect={{ left: 120, top: 60, width: 153, height: 162 }}
        isDark={false}
        colorLabel="Color"
        sizeLabel="Size"
        widthLabel="W"
        heightLabel="H"
        state={{ activePanel: null }}
        setState={() => {}}
        updateBrushItem={updateBrushItem}
      />,
    )

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '18' } })
    fireEvent.change(screen.getByDisplayValue('153'), { target: { value: '220' } })
    fireEvent.change(screen.getByDisplayValue('162'), { target: { value: '90' } })

    expect(updateBrushItem).toHaveBeenNthCalledWith(1, 'brush-1', { brushSize: 18 })
    expect(updateBrushItem).toHaveBeenNthCalledWith(2, 'brush-1', { width: 220 })
    expect(updateBrushItem).toHaveBeenNthCalledWith(3, 'brush-1', { height: 90 })
  })

  it('opens the shared color popover above the active control', () => {
    const setState = vi.fn()

    render(
      <CanvasBrushToolbar
        item={brushItem}
        rect={{ left: 120, top: 60, width: 153, height: 162 }}
        isDark={false}
        colorLabel="Color"
        sizeLabel="Size"
        widthLabel="W"
        heightLabel="H"
        state={{ activePanel: 'color' }}
        setState={setState}
        updateBrushItem={() => {}}
      />,
    )

    expect(screen.getAllByText('Color').length).toBeGreaterThan(1)
    expect(screen.getByDisplayValue('00ff00')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Color' }))
    expect(setState).toHaveBeenCalledWith({ activePanel: null })
  })

  it('matches the text color popover affordances, including transparent swatches and opacity percentage', () => {
    const onChange = vi.fn()

    render(
      <BrushColorPopover
        title="Color"
        color="#112233"
        isDark={false}
        onClose={() => {}}
        onChange={onChange}
      />,
    )

    expect(screen.getByRole('button', { name: 'Color-transparent' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton')).toHaveValue(100)

    fireEvent.click(screen.getByRole('button', { name: 'Color-transparent' }))
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '40' } })

    expect(onChange).toHaveBeenNthCalledWith(1, 'transparent')
    expect(onChange).toHaveBeenNthCalledWith(2, '#11223366')
  })
})


