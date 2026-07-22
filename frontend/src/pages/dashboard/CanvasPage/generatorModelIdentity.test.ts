import { describe, expect, test } from 'vitest'

import {
  getGeneratorModelOptionKey,
  isGeneratorModelOptionSelected,
} from './generatorModelIdentity'

describe('generatorModelIdentity', () => {
  const builtinGptImage = {
    value: 'gpt-image-2',
    provider: 'builtin',
  }
  const ollamaGptImage = {
    value: 'gpt-image-2',
    provider: 'ollama',
  }

  test('distinguishes models with the same name from different providers', () => {
    expect(isGeneratorModelOptionSelected(builtinGptImage, 'gpt-image-2', 'builtin')).toBe(true)
    expect(isGeneratorModelOptionSelected(ollamaGptImage, 'gpt-image-2', 'builtin')).toBe(false)
    expect(isGeneratorModelOptionSelected(builtinGptImage, 'gpt-image-2', 'ollama')).toBe(false)
    expect(isGeneratorModelOptionSelected(ollamaGptImage, 'gpt-image-2', 'ollama')).toBe(true)
  })

  test('uses provider and model name for stable option keys', () => {
    expect(getGeneratorModelOptionKey(builtinGptImage)).toBe('builtin:gpt-image-2')
    expect(getGeneratorModelOptionKey(ollamaGptImage)).toBe('ollama:gpt-image-2')
  })
})
