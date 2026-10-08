import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { TEXT_REDRAW_PANEL_TOKENS } from '../textRedrawUi'
import { TextRedrawPanel } from './TextRedrawPanel'

function getSubmitButton() {
  return screen.getByText('确认重绘').closest('button') as HTMLButtonElement
}

describe('TextRedrawPanel', () => {
  test('renders one input per text segment', () => {
    render(
      <TextRedrawPanel
        isDark={false}
        title="文字检测结果"
        segments={[
          { id: '1', text: 'MARSHALL', originalText: 'MARSHALL', order: 1 },
          { id: '2', text: 'EST.1962', originalText: 'EST.1962', order: 2 },
        ]}
        isSubmitting={false}
        onChangeSegment={() => {}}
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    )

    expect(screen.getByDisplayValue('MARSHALL')).toBeInTheDocument()
    expect(screen.getByDisplayValue('EST.1962')).toBeInTheDocument()
    expect(getSubmitButton()).toBeInTheDocument()
  })

  test('disables submit while submitting', () => {
    render(
      <TextRedrawPanel
        isDark={false}
        title="文字检测结果"
        segments={[
          { id: '1', text: 'MARSHALL', originalText: 'MARSHALL', order: 1 },
        ]}
        isSubmitting
        onChangeSegment={() => {}}
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    )

    expect(getSubmitButton()).toBeDisabled()
  })

  test('forwards input changes', () => {
    const onChangeSegment = vi.fn()

    render(
      <TextRedrawPanel
        isDark={false}
        title="文字检测结果"
        segments={[
          { id: '1', text: 'MARSHALL', originalText: 'MARSHALL', order: 1 },
        ]}
        isSubmitting={false}
        onChangeSegment={onChangeSegment}
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    )

    const input = screen.getByDisplayValue('MARSHALL')
    fireEvent.change(input, { target: { value: 'NEW BRAND' } })

    expect(onChangeSegment).toHaveBeenCalledWith('1', 'NEW BRAND')
  })

  test('uses compact shared sizing tokens', () => {
    render(
      <TextRedrawPanel
        isDark={false}
        title="文字检测结果"
        segments={[
          { id: '1', text: 'MARSHALL', originalText: 'MARSHALL', order: 1 },
        ]}
        isSubmitting={false}
        onChangeSegment={() => {}}
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    )

    const input = screen.getByDisplayValue('MARSHALL')
    const submit = getSubmitButton()

    expect(input).toHaveStyle({ height: `${TEXT_REDRAW_PANEL_TOKENS.inputHeight}px` })
    expect(input).toHaveStyle({ fontSize: `${TEXT_REDRAW_PANEL_TOKENS.inputFontSize}px` })
    expect(submit).toHaveStyle({ height: `${TEXT_REDRAW_PANEL_TOKENS.submitButtonHeight}px` })
    expect(submit).toHaveStyle({ fontSize: `${TEXT_REDRAW_PANEL_TOKENS.submitButtonFontSize}px` })
  })

  test('scrolls the result list when wheeling inside the panel', () => {
    render(
      <TextRedrawPanel
        isDark={false}
        title="文字检测结果"
        segments={Array.from({ length: 12 }, (_, index) => ({
          id: `${index + 1}`,
          text: `SEGMENT-${index + 1}`,
          originalText: `SEGMENT-${index + 1}`,
          order: index + 1,
        }))}
        isSubmitting={false}
        onChangeSegment={() => {}}
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    )

    const scrollArea = screen.getByTestId('text-redraw-scroll-area')
    Object.defineProperties(scrollArea, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
    })
    expect(scrollArea.scrollTop).toBe(0)

    const parentWheel = vi.fn()
    document.addEventListener('wheel', parentWheel)
    const wheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: 120 })
    fireEvent(scrollArea, wheel)

    expect(parentWheel).not.toHaveBeenCalled()
    expect(wheel.defaultPrevented).toBe(false)
    document.removeEventListener('wheel', parentWheel)
  })

  test('renders caller-provided i18n labels for segments and submit action', () => {
    render(
      <TextRedrawPanel
        isDark={false}
        title="Detected text"
        segmentLabelPrefix="Text"
        submitLabel="Apply redraw"
        segments={[
          { id: '1', text: 'MARSHALL', originalText: 'MARSHALL', order: 1 },
        ]}
        isSubmitting={false}
        onChangeSegment={() => {}}
        onCancel={() => {}}
        onSubmit={() => {}}
      />,
    )

    expect(screen.getByText('Text 1')).toBeInTheDocument()
    expect(screen.getByText('Apply redraw')).toBeInTheDocument()
  })
})
