import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { GeneratorImageSourcePicker } from './GeneratorImageSourcePicker'

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
      media: '(hover: hover)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe('GeneratorImageSourcePicker', () => {
  beforeEach(() => {
    mockMatchMedia(true)
  })

  test('shows local and asset library options on hover and triggers local pick', () => {
    const onPickLocal = vi.fn()
    const onPickFromLibrary = vi.fn()

    render(
      <GeneratorImageSourcePicker
        isDark={false}
        label="参考图片"
        onPickLocal={onPickLocal}
        onPickFromLibrary={onPickFromLibrary}
      />,
    )

    fireEvent.mouseEnter(screen.getByRole('button', { name: '参考图片' }))

    fireEvent.click(screen.getByRole('button', { name: '本地图片' }))

    expect(onPickLocal).toHaveBeenCalledTimes(1)
    expect(onPickFromLibrary).not.toHaveBeenCalled()
  })

  test('opens the menu on click when hover is unavailable', () => {
    mockMatchMedia(false)
    const onPickLocal = vi.fn()
    const onPickFromLibrary = vi.fn()

    render(
      <GeneratorImageSourcePicker
        isDark={false}
        label="首帧"
        onPickLocal={onPickLocal}
        onPickFromLibrary={onPickFromLibrary}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '首帧' }))
    fireEvent.click(screen.getByRole('button', { name: '素材库' }))

    expect(onPickLocal).not.toHaveBeenCalled()
    expect(onPickFromLibrary).toHaveBeenCalledTimes(1)
  })

  test('shows reference gallery option when provided', () => {
    const onPickLocal = vi.fn()
    const onPickFromLibrary = vi.fn()
    const onPickFromReferenceLibrary = vi.fn()

    render(
      <GeneratorImageSourcePicker
        isDark={false}
        label="参考图片"
        onPickLocal={onPickLocal}
        onPickFromLibrary={onPickFromLibrary}
        onPickFromReferenceLibrary={onPickFromReferenceLibrary}
      />,
    )

    fireEvent.mouseEnter(screen.getByRole('button', { name: '参考图片' }))
    fireEvent.click(screen.getByRole('button', { name: '参考图库' }))

    expect(onPickFromReferenceLibrary).toHaveBeenCalledTimes(1)
    expect(onPickLocal).not.toHaveBeenCalled()
    expect(onPickFromLibrary).not.toHaveBeenCalled()
  })
})
