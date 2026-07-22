import { describe, expect, test } from 'vitest'

import {
  getAllowedVideoDurations,
  getImageGeneratorCapability,
  getVideoGeneratorCapability,
} from './generatorCapabilities'

describe('generatorCapabilities', () => {
  test('supports reference images for the official Gemini flash image model id', () => {
    const capability = getImageGeneratorCapability('gemini-3.1-flash-image-preview-official')

    expect(capability).toMatchObject({
      supportsReferenceImages: true,
      maxReferenceImages: 14,
    })
  })

  test('supports reference images for the official Gemini pro image model id', () => {
    const capability = getImageGeneratorCapability('gemini-3-pro-image-preview-official')

    expect(capability).toMatchObject({
      supportsReferenceImages: true,
      maxReferenceImages: 14,
    })
  })

  test('supports up to 16 reference images for gpt-image-2', () => {
    const capability = getImageGeneratorCapability('gpt-image-2')

    expect(capability).toMatchObject({
      supportsReferenceImages: true,
      maxReferenceImages: 16,
    })
  })

  test('supports reference images for the builtin Seedream 4.5 model id', () => {
    const capability = getImageGeneratorCapability('doubao-seedream-4-5')

    expect(capability).toMatchObject({
      supportsReferenceImages: true,
      maxReferenceImages: 10,
    })
  })

  test('returns the full 4s-12s range for doubao-seedance-1-5-pro', () => {
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

  test('treats doubao-seedance-1-5-pro as first-tail-frame video instead of reference-image video', () => {
    const capability = getVideoGeneratorCapability('doubao-seedance-1-5-pro')

    expect(capability).toMatchObject({
      supportsReferenceImages: false,
      maxReferenceImages: 0,
      supportsFirstFrame: true,
      supportsTailFrame: true,
    })
  })
})
