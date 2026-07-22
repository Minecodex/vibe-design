import { describe, expect, it } from 'vitest'

import {
  buildHomepageSelectableModels,
  fillHomepageDefaultModelPreferences,
} from './homeChatModelPreferences'

describe('buildHomepageSelectableModels', () => {
  it('exposes builtin Ollama text-to-image models from the registry', () => {
    const catalogs = buildHomepageSelectableModels(
      [{ code: 'ollama', name: 'Ollama', status: 'authorized', is_builtin: true }],
      {
        ollama: {
          models: {
            text2image: [
              {
                model_name: 'gpt-image-2',
                label: 'Ollama Image (gpt-image-2)',
                description: 'Local image generation',
                config: {
                  max_reference_images: 16,
                },
              },
            ],
          },
        },
      },
      { ollama: [] },
    )

    expect(catalogs.imageModels).toEqual([
      {
        name: 'Ollama Image (gpt-image-2)',
        value: 'gpt-image-2',
        provider: 'ollama',
        providerName: 'Ollama',
        description: 'Local image generation',
        tag: undefined,
        config: {
          max_reference_images: 16,
        },
        supportsFastMode: undefined,
        supportsThinkingMode: undefined,
        thinkingVariantOf: undefined,
        maxReferenceImages: 16,
        supportsReferenceImages: true,
      },
    ])
  })
})

describe('fillHomepageDefaultModelPreferences', () => {
  it('replaces stale persisted model references with available defaults', () => {
    const next = fillHomepageDefaultModelPreferences(
      {
        image_model: 'removed-image',
        image_provider: 'removed-provider',
        video_model: 'removed-video',
        video_provider: 'removed-provider',
        multimodal_model: 'removed-chat',
        multimodal_provider: 'removed-provider',
        auto: false,
      },
      {
        imageModels: [
          { name: 'Image', value: 'image-live', provider: 'builtin', providerName: 'Builtin' },
        ],
        videoModels: [
          { name: 'Video', value: 'video-live', provider: 'builtin', providerName: 'Builtin' },
        ],
        multimodalModels: [
          { name: 'Chat', value: 'chat-live', provider: 'builtin', providerName: 'Builtin', supportsFastMode: true },
        ],
      },
      false,
    )

    expect(next).toMatchObject({
      image_model: 'image-live',
      image_provider: 'builtin',
      video_model: 'video-live',
      video_provider: 'builtin',
      multimodal_model: 'chat-live',
      multimodal_provider: 'builtin',
      auto: false,
    })
  })
})
