import { describe, expect, it } from 'vitest'
import {
  isMarkModifierPressed,
  isTransientMarkModeActive,
} from './gestureMode'

describe('canvas gesture mode', () => {
  it('treats alt as the transient mark modifier in select mode', () => {
    expect(isMarkModifierPressed({ altKey: true, metaKey: false, ctrlKey: false })).toBe(true)
  })

  it('treats cmd/meta as the transient mark modifier in select mode', () => {
    expect(isMarkModifierPressed({ altKey: false, metaKey: true, ctrlKey: false })).toBe(true)
  })

  it('does not treat ctrl as the transient mark modifier', () => {
    expect(isMarkModifierPressed({ altKey: false, metaKey: false, ctrlKey: true })).toBe(false)
  })

  it('activates transient mark mode only when select is hovering a markable image', () => {
    expect(
      isTransientMarkModeActive({
        activeTool: 'select',
        isHoveringMarkableImage: true,
        modifierState: { altKey: true, metaKey: false, ctrlKey: false },
      }),
    ).toBe(true)
  })

  it('keeps select behavior when the pointer is not over a markable image', () => {
    expect(
      isTransientMarkModeActive({
        activeTool: 'select',
        isHoveringMarkableImage: false,
        modifierState: { altKey: true, metaKey: false, ctrlKey: false },
      }),
    ).toBe(false)
  })

  it('does not use transient mark mode outside select', () => {
    expect(
      isTransientMarkModeActive({
        activeTool: 'hand',
        isHoveringMarkableImage: true,
        modifierState: { altKey: true, metaKey: false, ctrlKey: false },
      }),
    ).toBe(false)
  })
})
