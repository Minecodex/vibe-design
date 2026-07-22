import { describe, expect, test } from 'vitest'

import {
  findImageModelOption,
  getAllowedImageRatios,
  getAllowedImageRatiosForResolution,
  getAllowedImageResolutions,
  getResolvedImageModelCapability,
  resolveImageModelSelection,
} from './imageModelConfig'

describe('imageModelConfig', () => {
  const imageModels = [
    {
      value: 'gemini-3.1-flash-image-preview-official',
      provider: 'builtin',
      config: {
        allowed_sizes: ['1K', '2K', '4K'],
        allowed_aspect_ratios: ['1:1', '16:9', '9:16'],
        max_reference_images: 14,
      },
    },
    {
      value: 'gpt-image-2',
      provider: 'builtin',
      config: {
        allowed_sizes: ['1K', '2K', '4K'],
        allowed_aspect_ratios: ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', '3:1', '1:3'],
        allowed_aspect_ratios_by_size: {
          '4K': ['1:1', '16:9', '9:16', '2:1', '1:2', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', '3:1', '1:3'],
        },
        max_reference_images: 16,
      },
    },
    {
      value: 'doubao-seedream-5-0-lite',
      provider: 'builtin',
      config: {
        allowed_sizes: ['2K'],
        allowed_aspect_ratios: [],
        max_reference_images: 10,
      },
    },
  ]

  test('prefers backend config for image capabilities', () => {
    expect(
      getResolvedImageModelCapability(
        imageModels,
        'gemini-3.1-flash-image-preview-official',
        'builtin',
      ),
    ).toEqual({
      supportsReferenceImages: true,
      maxReferenceImages: 14,
    })
  })

  test('uses backend config for allowed image resolutions and ratios', () => {
    const model = findImageModelOption(
      imageModels,
      'gemini-3.1-flash-image-preview-official',
      'builtin',
    )

    expect(getAllowedImageResolutions(model?.config)).toEqual(['1K', '2K', '4K'])
    expect(getAllowedImageRatios(model?.config)).toEqual(['1:1', '16:9', '9:16'])
  })

  test('uses resolution-specific image ratios when configured', () => {
    const model = findImageModelOption(imageModels, 'gpt-image-2', 'builtin')

    expect(getAllowedImageRatiosForResolution(model?.config, '4K')).toEqual([
      '1:1',
      '16:9',
      '9:16',
      '2:1',
      '1:2',
      '4:3',
      '3:4',
      '3:2',
      '2:3',
      '5:4',
      '4:5',
      '21:9',
      '9:21',
      '3:1',
      '1:3',
    ])
    expect(getAllowedImageRatiosForResolution(model?.config, '2K')).toEqual([
      '1:1',
      '16:9',
      '9:16',
      '4:3',
      '3:4',
      '3:2',
      '2:3',
      '5:4',
      '4:5',
      '21:9',
      '9:21',
      '3:1',
      '1:3',
    ])
  })

  test('keeps current image ratio when the new resolution allows it', () => {
    const model = findImageModelOption(imageModels, 'gpt-image-2', 'builtin')

    expect(
      resolveImageModelSelection({
        config: model?.config,
        currentResolution: '1K',
        currentAspectRatio: '1:1',
        nextResolution: '4K',
      }),
    ).toEqual({
      resolution: '4K',
      aspect_ratio: '1:1',
    })
  })

  test('keeps seedream image ratios hidden when the backend config disables them', () => {
    const model = findImageModelOption(imageModels, 'doubao-seedream-5-0-lite', 'builtin')

    expect(getAllowedImageRatios(model?.config)).toEqual([])
    expect(getAllowedImageRatiosForResolution(model?.config, '2K')).toEqual([])
  })

  test('keeps a square placeholder ratio when the model has no selectable ratios', () => {
    const model = findImageModelOption(imageModels, 'doubao-seedream-5-0-lite', 'builtin')

    expect(
      resolveImageModelSelection({
        config: model?.config,
        currentResolution: '2K',
        currentAspectRatio: '1:1',
      }),
    ).toEqual({
      resolution: '2K',
      aspect_ratio: '1:1',
    })
  })
})
