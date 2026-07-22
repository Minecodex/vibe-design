import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { CanvasTextToolbar } from './CanvasTextToolbar'

describe('CanvasTextToolbar', () => {
  const baseItem: CanvasItem = {
    id: 'text-1',
    type: 'text',
    url: '',
    x: 0,
    y: 0,
    width: 240,
    height: 120,
    text: 'hello',
    fontFamily: 'Instrument Sans',
    fontVariant: 'Regular',
    fontSize: 32,
    fillColor: '#111111',
    strokeColor: 'transparent',
    strokeWidth: 0,
    textAlign: 'left',
    lineHeight: 1.2,
    letterSpacing: 0,
    writingMode: 'horizontal',
    z_index: 1,
  }

  const labels = {
    fill: 'Fill',
    stroke: 'Stroke',
    font: 'Font',
    variant: 'Style',
    size: 'Size',
    align: 'Align',
    more: 'More',
    vertical: 'Vertical',
  }

  it('scales expanded option popovers up by 30% without changing the toolbar row size', () => {
    render(
      <CanvasTextToolbar
        item={baseItem}
        rect={{ left: 120, top: 180, width: 240, height: 120 }}
        isDark={false}
        labels={labels}
        state={{ activePanel: 'font' }}
        setState={vi.fn()}
        updateTextStyle={vi.fn()}
      />,
    )

    const fontButton = screen.getByRole('button', { name: 'Font' })
    expect(fontButton.style.height).toBe('32px')

    const fontOption = screen.getAllByText('Instrument Sans')[1]
    const popover = fontOption.closest('div[style*="scale"]') as HTMLElement
    expect(popover).not.toBeNull()
    expect(popover.style.transform).toBe('translateX(-50%) scale(0.845)')
  })

  it('opens the requested panel via button click', () => {
    const setState = vi.fn()

    render(
      <CanvasTextToolbar
        item={baseItem}
        rect={{ left: 120, top: 180, width: 240, height: 120 }}
        isDark={false}
        labels={labels}
        state={{ activePanel: null }}
        setState={setState}
        updateTextStyle={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Font' }))
    expect(setState).toHaveBeenCalledWith({ activePanel: 'font' })
  })

  it('raises the size ceiling to 9999 and keeps the size input visibly pinned for direct typing', () => {
    render(
      <CanvasTextToolbar
        item={baseItem}
        rect={{ left: 120, top: 180, width: 240, height: 120 }}
        isDark={false}
        labels={labels}
        state={{ activePanel: 'size' }}
        setState={vi.fn()}
        updateTextStyle={vi.fn()}
      />,
    )

    const sizeInput = screen.getByRole('spinbutton') as HTMLInputElement
    expect(sizeInput.max).toBe('9999')
    expect(sizeInput).toHaveFocus()
    const inputHeader = sizeInput.parentElement as HTMLElement
    expect(inputHeader.style.position).toBe('sticky')
    expect(inputHeader.style.top).toBe('0px')
    expect(screen.queryByText('Size')).not.toBeInTheDocument()
  })

  it('closes the active panel when clicking outside the toolbar', () => {
    const setState = vi.fn()

    render(
      <CanvasTextToolbar
        item={baseItem}
        rect={{ left: 120, top: 180, width: 240, height: 120 }}
        isDark={false}
        labels={labels}
        state={{ activePanel: 'size' }}
        setState={setState}
        updateTextStyle={vi.fn()}
      />,
    )

    fireEvent.pointerDown(document.body)

    expect(setState).toHaveBeenCalledWith({ activePanel: null })
  })
})
