import { describe, expect, it } from 'vitest'
import type { CanvasItem } from '@/api/endpoints/projects'
import {
  BUILTIN_IMAGE_CFG,
  getCanvasItemDimensions,
  getMediaDimensions,
  getClosestImageGenerationDefaults,
  resolveImageModelDimensions,
  resolveMediaModelDimensions,
} from './mediaDimensions'

describe('mediaDimensions', () => {
  const gptImage2Config = {
    dimension_table: {
      '4K': {
        '1:1': { width: 2880, height: 2880 },
        '16:9': { width: 3840, height: 2160 },
      },
    },
  }
  const seedream5LiteConfig = {
    dimension_table: {
      '4K': {
        '16:9': { width: 5504, height: 3040 },
      },
    },
    dimension_source: 'apimart_docs',
  }

  const imageGenerator = (overrides: Partial<CanvasItem> = {}): CanvasItem => ({
    id: 'img-1',
    type: 'image_generator',
    x: 0,
    y: 0,
    ...overrides,
  } as CanvasItem)

  const videoGenerator = (overrides: Partial<CanvasItem> = {}): CanvasItem => ({
    id: 'video-1',
    type: 'video_generator',
    x: 0,
    y: 0,
    ...overrides,
  } as CanvasItem)

  it('keeps builtin image config for the official Gemini flash image model id', () => {
    expect(BUILTIN_IMAGE_CFG['gemini-3.1-flash-image-preview-official']).toEqual({
      sizes: ['0.5K', '1K', '2K', '4K'],
      ratios: ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '1:4', '4:1', '1:8', '8:1'],
    })
  })

  it('keeps builtin image config for the official Gemini pro image model id', () => {
    expect(BUILTIN_IMAGE_CFG['gemini-3-pro-image-preview-official']).toEqual({
      sizes: ['1K', '2K', '4K'],
      ratios: ['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9'],
    })
  })

  it('keeps builtin image config for gpt-image-2', () => {
    expect(BUILTIN_IMAGE_CFG['gpt-image-2']).toEqual({
      sizes: ['1K', '2K', '4K'],
      ratios: ['1:1', '16:9', '9:16', '2:1', '1:2', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', '3:1', '1:3'],
    })
  })

  it('keeps builtin image config for Seedream 4.5', () => {
    expect(BUILTIN_IMAGE_CFG['doubao-seedream-4-5']).toEqual({
      sizes: ['2K', '4K'],
      ratios: [],
    })
  })

  it('uses builtin image dimensions for supported aspect ratios', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({ provider_code: 'builtin', aspect_ratio: '16:9' }))
    ).toMatchObject({
      width: 1365,
      height: 768,
      label: '1365 × 768',
    })
  })

  it('uses provider resolution maps for non-builtin image generators', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'volcark',
        resolution: '3K',
        aspect_ratio: '9:16',
      }))
    ).toMatchObject({
      width: 2304,
      height: 4096,
      label: '2304 × 4096',
    })
  })

  it('uses model dimension tables before builtin image fallbacks', () => {
    expect(
      resolveImageModelDimensions(gptImage2Config, 'builtin', 'gpt-image-2', '4K', '1:1')
    ).toMatchObject({
      width: 2880,
      height: 2880,
      label: '2880 × 2880',
    })

    expect(
      resolveImageModelDimensions(gptImage2Config, 'builtin', 'gpt-image-2', '4K', '16:9')
    ).toMatchObject({
      width: 3840,
      height: 2160,
      label: '3840 × 2160',
    })
  })

  it('uses the generic media resolver for Apimart image dimension tables', () => {
    expect(
      resolveMediaModelDimensions({
        config: gptImage2Config,
        provider: 'builtin',
        model: 'gpt-image-2',
        resolution: '4K',
        ratio: '1:1',
        kind: 'image',
      }),
    ).toMatchObject({
      width: 2880,
      height: 2880,
      label: '2880 × 2880',
    })

    expect(
      resolveMediaModelDimensions({
        config: seedream5LiteConfig,
        provider: 'builtin',
        model: 'doubao-seedream-5-0-lite',
        resolution: '4K',
        ratio: '16:9',
        kind: 'image',
      }),
    ).toMatchObject({
      width: 5504,
      height: 3040,
      label: '5504 × 3040',
    })
  })

  it('uses the Ollama GPT-Image-2 policy without the Apimart dimension table', () => {
    expect(
      resolveMediaModelDimensions({
        config: { dimension_policy: 'ollama_gpt_image_2', dimension_source: 'estimated' },
        provider: 'ollama',
        model: 'gpt-image-2',
        resolution: '4K',
        ratio: '1:1',
        kind: 'image',
      }),
    ).toMatchObject({
      width: 2880,
      height: 2880,
      label: '2880 × 2880',
    })
  })

  it('does not reuse exact GPT-Image-2 tables for estimated builtin models', () => {
    expect(
      resolveMediaModelDimensions({
        config: { dimension_policy: 'image_area', dimension_source: 'estimated' },
        provider: 'builtin',
        model: 'gemini-3-pro-image-preview-official',
        resolution: '4K',
        ratio: '1:1',
        kind: 'image',
      }),
    ).toMatchObject({
      width: 4096,
      height: 4096,
      label: '4096 × 4096',
    })
  })

  it('uses model dimension tables for builtin gpt-image-2 canvas items', () => {
    expect(
      getCanvasItemDimensions(
        imageGenerator({
          provider_code: 'builtin',
          model_name: 'gpt-image-2',
          resolution: '4K',
          aspect_ratio: '1:1',
        }),
        { imageModelConfig: gptImage2Config },
      )
    ).toMatchObject({
      width: 2880,
      height: 2880,
      label: '2880 × 2880',
    })

    expect(
      getCanvasItemDimensions(
        imageGenerator({
          provider_code: 'builtin',
          model_name: 'gpt-image-2',
          resolution: '4K',
          aspect_ratio: '16:9',
        }),
        { imageModelConfig: gptImage2Config },
      )
    ).toMatchObject({
      width: 3840,
      height: 2160,
      label: '3840 × 2160',
    })
  })

  it('uses Ollama image constraints without the builtin Apimart table', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'ollama',
        resolution: '4K',
        aspect_ratio: '9:16',
      }))
    ).toMatchObject({
      width: 2160,
      height: 3840,
      label: '2160 × 3840',
    })
  })

  it('uses Ollama image constraints for 4K square image generators', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'ollama',
        resolution: '4K',
        aspect_ratio: '1:1',
      }))
    ).toMatchObject({
      width: 2880,
      height: 2880,
      label: '2880 × 2880',
    })
  })

  it('uses Ollama image constraints for 1K and 2K image generators', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'ollama',
        resolution: '1K',
        aspect_ratio: '16:9',
      }))
    ).toMatchObject({
      width: 1824,
      height: 1024,
      label: '1824 × 1024',
    })

    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'ollama',
        resolution: '2K',
        aspect_ratio: '9:16',
      }))
    ).toMatchObject({
      width: 1152,
      height: 2048,
      label: '1152 × 2048',
    })
  })

  it('uses Ollama image constraints for 4:3 and 3:4 image generators', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'ollama',
        resolution: '4K',
        aspect_ratio: '4:3',
      }))
    ).toMatchObject({
      width: 3312,
      height: 2480,
      label: '3312 × 2480',
    })

    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'ollama',
        resolution: '4K',
        aspect_ratio: '3:4',
      }))
    ).toMatchObject({
      width: 2480,
      height: 3312,
      label: '2480 × 3312',
    })
  })

  it('falls back to the first available provider ratio when the requested ratio is unavailable', () => {
    expect(
      getCanvasItemDimensions(imageGenerator({
        provider_code: 'jimeng',
        resolution: '1K',
        aspect_ratio: '16:9',
      }))
    ).toMatchObject({
      width: 1024,
      height: 1024,
      label: '1024 × 1024',
    })
  })

  it('resolves default video sizes from aspect ratio', () => {
    expect(
      getCanvasItemDimensions(videoGenerator({ aspect_ratio: '9:16' }))
    ).toMatchObject({
      width: 720,
      height: 1280,
      label: '720 × 1280',
    })
  })

  it('uses video resolution tiers when provided', () => {
    expect(
      getCanvasItemDimensions(videoGenerator({ aspect_ratio: '16:9', resolution: '4k' }))
    ).toMatchObject({
      width: 3840,
      height: 2160,
      label: '3840 × 2160',
    })
  })

  it('uses the generic media resolver for video short-side policies', () => {
    expect(
      resolveMediaModelDimensions({
        config: { dimension_policy: 'video_short_side', dimension_source: 'estimated' },
        provider: 'builtin',
        model: 'kling-v3',
        resolution: '4k',
        ratio: '16:9',
        kind: 'video',
      }),
    ).toMatchObject({
      width: 3840,
      height: 2160,
      label: '3840 × 2160',
    })

    expect(
      resolveMediaModelDimensions({
        config: { dimension_policy: 'video_short_side', dimension_source: 'estimated' },
        provider: 'builtin',
        model: 'grok-imagine-1.0-video-apimart',
        resolution: '720p',
        ratio: '9:16',
        kind: 'video',
      }),
    ).toMatchObject({
      width: 720,
      height: 1280,
      label: '720 × 1280',
    })
  })

  it('uses 4k audio video resolution tiers when provided', () => {
    expect(
      getCanvasItemDimensions(videoGenerator({ aspect_ratio: '16:9', resolution: '4k_audio' }))
    ).toMatchObject({
      width: 3840,
      height: 2160,
      label: '3840 × 2160',
    })
  })

  it('returns configured and actual media dimensions together', () => {
    expect(
      getMediaDimensions(
        videoGenerator({ aspect_ratio: '9:16', resolution: '1080p' }),
        undefined,
        { width: 720, height: 1280 },
      )
    ).toMatchObject({
      configured: {
        width: 1080,
        height: 1920,
        label: '1080 × 1920',
      },
      actual: {
        width: 720,
        height: 1280,
        label: '720 × 1280',
      },
      display: {
        width: 720,
        height: 1280,
        label: '720 × 1280',
      },
    })
  })

  it('chooses the nearest allowed landscape ratio and resolution for anchored image defaults', () => {
    expect(
      getClosestImageGenerationDefaults({
        sourceWidth: 1600,
        sourceHeight: 900,
        providerCode: 'builtin',
        allowedRatios: ['1:1', '4:3', '16:9'],
        allowedResolutions: ['0.5K', '1K', '2K'],
      }),
    ).toEqual({
      aspect_ratio: '16:9',
      resolution: '1K',
    })
  })

  it('chooses the nearest allowed portrait ratio and resolution for anchored image defaults', () => {
    expect(
      getClosestImageGenerationDefaults({
        sourceWidth: 1200,
        sourceHeight: 1800,
        providerCode: 'builtin',
        allowedRatios: ['1:1', '3:4', '9:16'],
        allowedResolutions: ['1K', '2K', '4K'],
      }),
    ).toEqual({
      aspect_ratio: '3:4',
      resolution: '1K',
    })
  })

  it('falls back to the first allowed ratio and resolution when source dimensions are missing', () => {
    expect(
      getClosestImageGenerationDefaults({
        sourceWidth: undefined,
        sourceHeight: undefined,
        providerCode: 'builtin',
        allowedRatios: ['4:3', '1:1'],
        allowedResolutions: ['2K', '1K'],
      }),
    ).toEqual({
      aspect_ratio: '4:3',
      resolution: '2K',
    })
  })
})
