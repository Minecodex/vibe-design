import { describe, expect, it } from 'vitest'

import {
  filterMultimodalModelsForMode,
  getModeSwitchTargetMultimodalModel,
  isThinkingModeAvailableForMultimodalModel,
  pickDefaultMultimodalModel,
  resolveCanvasModelPreferences,
} from './chatSidebarModelHelpers'

const ollamaModel = {
  name: 'Ollama (gemma4:e4b)',
  value: 'gemma4:e4b',
  provider: 'ollama',
  supportsFastMode: true,
  supportsThinkingMode: true,
  thinkingVariantOf: undefined,
}

describe('chatSidebarModelHelpers', () => {
  it('prefers ollama as the default multimodal model when present', () => {
    const selected = pickDefaultMultimodalModel([
      { name: 'Opus 4.7', value: 'claude-opus-4-7', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      ollamaModel,
    ], 'fast')

    expect(selected).toEqual(ollamaModel)
  })

  it('keeps ollama visible in plan mode even without thinking keywords', () => {
    const filtered = filterMultimodalModelsForMode([
      ollamaModel,
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: true },
      { name: 'Opus 4.7', value: 'claude-opus-4-7', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
    ], 'plan')

    expect(filtered).toEqual([
      ollamaModel,
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: true },
    ])
  })

  it('filters out thinking-only cloud models in fast mode but keeps ollama', () => {
    const filtered = filterMultimodalModelsForMode([
      ollamaModel,
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: false, supportsThinkingMode: true },
      { name: 'Opus 4.7', value: 'claude-opus-4-7', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
    ], 'fast')

    expect(filtered).toEqual([
      ollamaModel,
      { name: 'Opus 4.7', value: 'claude-opus-4-7', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
    ])
  })

  it('hides glm and kimi from plan mode when they do not support thinking mode', () => {
    const filtered = filterMultimodalModelsForMode([
      { name: 'GLM 5.1', value: 'glm-5.1', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Kimi K2.5', value: 'kimi-k2.5', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: true },
    ], 'plan')

    expect(filtered).toEqual([
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: true },
    ])
  })

  it('defaults to kimi-k2.5 for fast mode when available', () => {
    const selected = pickDefaultMultimodalModel([
      { name: 'GLM 5.1', value: 'glm-5.1', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Kimi K2.5', value: 'kimi-k2.5', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
    ], 'fast')

    expect(selected).toEqual(
      { name: 'Kimi K2.5', value: 'kimi-k2.5', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
    )
  })

  it('switches paired builtin models by reading thinking_variant_of metadata', () => {
    const models = [
      { name: 'Opus 4.7', value: 'claude-opus-4-7', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: false, supportsThinkingMode: true, thinkingVariantOf: 'claude-opus-4-7' },
      { name: 'Gemini 3.1 Pro', value: 'gemini-3.1-pro-preview', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Gemini 3.0 Pro Thinking', value: 'gemini-3-pro-preview-thinking', provider: 'builtin', supportsFastMode: false, supportsThinkingMode: true, thinkingVariantOf: 'gemini-3.1-pro-preview' },
    ]

    expect(getModeSwitchTargetMultimodalModel(models, 'fast', 'plan', { value: 'claude-opus-4-7', provider: 'builtin' })?.value)
      .toBe('claude-opus-4-6-thinking')
    expect(getModeSwitchTargetMultimodalModel(models, 'plan', 'fast', { value: 'gemini-3-pro-preview-thinking', provider: 'builtin' })?.value)
      .toBe('gemini-3.1-pro-preview')
  })

  it('disables thinking mode for multimodal models without a thinking pair', () => {
    const models = [
      { name: 'GLM 5.1', value: 'glm-5.1', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Opus 4.7', value: 'claude-opus-4-7', provider: 'builtin', supportsFastMode: true, supportsThinkingMode: false },
      { name: 'Opus 4.6 Thinking', value: 'claude-opus-4-6-thinking', provider: 'builtin', supportsFastMode: false, supportsThinkingMode: true, thinkingVariantOf: 'claude-opus-4-7' },
    ]

    expect(isThinkingModeAvailableForMultimodalModel(models, { value: 'glm-5.1', provider: 'builtin' })).toBe(false)
    expect(isThinkingModeAvailableForMultimodalModel(models, { value: 'claude-opus-4-7', provider: 'builtin' })).toBe(true)
    expect(isThinkingModeAvailableForMultimodalModel(models, { value: 'gemma4:e4b', provider: 'ollama' })).toBe(true)
  })

  it('replaces stale persisted model references with available defaults', () => {
    const next = resolveCanvasModelPreferences(
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
          { name: 'Image', value: 'image-live', provider: 'builtin' },
        ],
        videoModels: [
          { name: 'Video', value: 'video-live', provider: 'builtin' },
        ],
        multimodalModels: [
          { name: 'Chat', value: 'kimi-k2.5', provider: 'builtin', supportsFastMode: true },
        ],
      },
      'fast',
    )

    expect(next).toEqual({
      image_model: 'image-live',
      image_provider: 'builtin',
      video_model: 'video-live',
      video_provider: 'builtin',
      multimodal_model: 'kimi-k2.5',
      multimodal_provider: 'builtin',
      auto: false,
    })
  })
})
