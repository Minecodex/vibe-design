import { describe, expect, it } from 'vitest'

import {
  CROP_PRESET_GROUPS,
  computeCropArea,
  createCenteredCropRectFromPreset,
  createInitialCropRect,
  getCropCommitMode,
  getCropDisplaySize,
  getPresetById,
  moveCropRect,
  resizeCropRectFromDimensions,
} from './cropUtils'

describe('cropUtils', () => {
  it('returns a centered crop area for general presets based on the current image ratio', () => {
    const preset = getPresetById(CROP_PRESET_GROUPS, 'general-1-1')

    expect(preset).toBeTruthy()
    expect(computeCropArea({ sourceWidth: 1280, sourceHeight: 1707, preset: preset! })).toEqual({
      x: 0,
      y: 213.5,
      width: 1280,
      height: 1280,
    })
  })

  it('treats platform presets larger than the current image as a no-op on confirm', () => {
    const preset = getPresetById(CROP_PRESET_GROUPS, 'douyin-feed')

    expect(preset).toBeTruthy()
    expect(
      getCropCommitMode({
        sourceWidth: 960,
        sourceHeight: 600,
        preset: preset!,
      }),
    ).toBe('noop')
  })

  it('keeps platform presets as a crop when the current image is large enough', () => {
    const preset = getPresetById(CROP_PRESET_GROUPS, 'xiaohongshu-feed')

    expect(preset).toBeTruthy()
    expect(
      getCropCommitMode({
        sourceWidth: 1773,
        sourceHeight: 1707,
        preset: preset!,
      }),
    ).toBe('crop')
    expect(
      getCropDisplaySize({
        sourceWidth: 1773,
        sourceHeight: 1707,
        preset: preset!,
      }),
    ).toEqual({
      width: 1080,
      height: 1440,
    })
  })

  it('creates the initial crop rectangle from the full source image bounds', () => {
    expect(
      createInitialCropRect({
        sourceWidth: 1280,
        sourceHeight: 1707,
      }),
    ).toEqual({
      x: 0,
      y: 0,
      width: 1280,
      height: 1707,
    })
  })

  it('creates a centered crop rectangle from a preset ratio', () => {
    const preset = getPresetById(CROP_PRESET_GROUPS, 'general-1-1')

    expect(preset).toBeTruthy()
    expect(
      createCenteredCropRectFromPreset({
        sourceWidth: 1280,
        sourceHeight: 1707,
        preset: preset!,
      }),
    ).toEqual({
      x: 0,
      y: 213.5,
      width: 1280,
      height: 1280,
    })
  })

  it('resizes a crop rectangle from freeform dimensions and clamps it inside the source bounds', () => {
    expect(
      resizeCropRectFromDimensions({
        rect: {
          x: 100,
          y: 150,
          width: 400,
          height: 500,
        },
        nextWidth: 900,
        nextHeight: 700,
        sourceWidth: 1000,
        sourceHeight: 800,
      }),
    ).toEqual({
      x: 0,
      y: 50,
      width: 900,
      height: 700,
    })
  })

  it('moves a crop rectangle and clamps it inside the source bounds', () => {
    expect(
      moveCropRect({
        rect: {
          x: 100,
          y: 150,
          width: 300,
          height: 400,
        },
        deltaX: 900,
        deltaY: 500,
        sourceWidth: 1000,
        sourceHeight: 800,
      }),
    ).toEqual({
      x: 700,
      y: 400,
      width: 300,
      height: 400,
    })
  })
})
