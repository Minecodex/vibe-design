import { describe, expect, it } from 'vitest'

import {
  getAvailableVideoResolutions,
  getGeneratorOptionsDropdownType,
  getAllowedVideoDurations,
  getImageGeneratorCapability,
  getTailFrameConstraintState,
  getVideoGeneratorCapability,
  getVideoImageInputMode,
  normalizeReferenceImages,
  shouldDisableVideoAspectRatio,
  type GeneratorCanvasItemLike,
} from '@/pages/dashboard/CanvasPage/generatorCapabilities'

describe('generatorCapabilities', () => {
  it('uses supported builtin image capability entries', () => {
    expect(getImageGeneratorCapability('gemini-3.1-flash-image-preview-official').maxReferenceImages).toBe(14)
    expect(getImageGeneratorCapability('doubao-seedream-5-0-lite').maxReferenceImages).toBe(10)
  })

  it('keeps manual aspect ratio available for supported video image modes', () => {
    const item: GeneratorCanvasItemLike = {
      reference_images: ['https://example.com/ref.png'],
    }

    expect(shouldDisableVideoAspectRatio(getVideoGeneratorCapability('kling-v2-6'), item)).toBe(false)
  })

  it('supports reference images and frame controls for kling 2.6', () => {
    const capability = getVideoGeneratorCapability('kling-v2-6')

    expect(capability.supportsReferenceImages).toBe(true)
    expect(capability.supportsFirstFrame).toBe(true)
    expect(capability.supportsTailFrame).toBe(true)
  })

  it('supports kling v3 text and image duration differences', () => {
    const capability = getVideoGeneratorCapability('kling-v3')

    expect(capability.supportsReferenceImages).toBe(true)
    expect(capability.supportsFirstFrame).toBe(true)
    expect(capability.supportsTailFrame).toBe(true)
    expect(getAllowedVideoDurations(capability, {})).toEqual([
      '3s', '4s', '5s', '6s', '7s', '8s', '9s', '10s', '11s', '12s', '13s', '14s', '15s',
    ])
    expect(
      getAllowedVideoDurations(capability, {
        reference_images: ['https://example.com/ref.png'],
      }),
    ).toEqual([
      '3s', '4s', '5s', '6s', '7s', '8s', '9s', '10s', '11s', '12s', '13s', '14s', '15s',
    ])
  })

  it('treats seedance 1.5 pro as a first/tail-frame model instead of reference mode', () => {
    const capability = getVideoGeneratorCapability('doubao-seedance-1-5-pro')

    expect(capability.supportsReferenceImages).toBe(false)
    expect(capability.maxReferenceImages).toBe(0)
  })

  it('treats reference images as reference mode for kling 2.6', () => {
    const item: GeneratorCanvasItemLike = {
      reference_images: ['https://example.com/ref-1.png'],
      first_frame_image: 'https://example.com/first.png',
      tail_frame_image: 'https://example.com/last.png',
    }

    expect(getVideoImageInputMode(getVideoGeneratorCapability('kling-v2-6'), item)).toBe('reference')
  })

  it('normalizes the legacy single reference image field into an array', () => {
    expect(normalizeReferenceImages({ reference_image: 'https://example.com/ref.png' })).toEqual([
      'https://example.com/ref.png',
    ])
  })

  it('allows kling v2.6 5 and 10 seconds', () => {
    const capability = getVideoGeneratorCapability('kling-v2-6')

    expect(getAllowedVideoDurations(capability, {})).toEqual(['5s', '10s'])
  })

  it('limits kling v2.6 tail frame mode to pro-compatible non-audio resolutions', () => {
    const capability = getVideoGeneratorCapability('kling-v2-6')

    expect(
      getAvailableVideoResolutions(capability, { first_frame_image: 'https://example.com/first.png' }, [
        '720p',
        '1080p',
        '1080p_audio',
      ]),
    ).toEqual(['720p', '1080p', '1080p_audio'])

    expect(
      getAvailableVideoResolutions(capability, {
        first_frame_image: 'https://example.com/first.png',
        tail_frame_image: 'https://example.com/last.png',
      }, [
        '720p',
        '1080p',
        '1080p_audio',
      ]),
    ).toEqual(['1080p'])
  })

  it('reports why kling v2.6 tail frame input is unavailable', () => {
    const capability = getVideoGeneratorCapability('kling-v2-6')

    expect(getTailFrameConstraintState(capability, {}, '720p')).toMatchObject({
      enabled: false,
      reason: 'requires_first_frame',
    })
    expect(getTailFrameConstraintState(capability, {
      first_frame_image: 'https://example.com/first.png',
    }, '720p')).toMatchObject({
      enabled: false,
      reason: 'requires_pro_resolution',
    })
    expect(getTailFrameConstraintState(capability, {
      first_frame_image: 'https://example.com/first.png',
    }, '1080p_audio')).toMatchObject({
      enabled: false,
      reason: 'audio_conflict',
    })
    expect(getTailFrameConstraintState(capability, {
      first_frame_image: 'https://example.com/first.png',
    }, '1080p')).toMatchObject({
      enabled: true,
      reason: null,
    })
  })

  it('uses the single documented 5 second option for seedance 1.5 pro', () => {
    const capability = getVideoGeneratorCapability('doubao-seedance-1-5-pro')

    expect(getAllowedVideoDurations(capability, {})).toEqual([
      '4s',
      '5s',
      '6s',
      '7s',
      '8s',
      '9s',
      '10s',
      '11s',
      '12s',
    ])
  })

  it('uses the shared primary options dropdown type for both image and video generators', () => {
    expect(getGeneratorOptionsDropdownType(true)).toBe('res')
    expect(getGeneratorOptionsDropdownType(false)).toBe('res')
  })
})
