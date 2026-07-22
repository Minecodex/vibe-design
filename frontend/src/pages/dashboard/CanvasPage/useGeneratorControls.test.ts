import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolve(currentDir, 'hooks', 'useGeneratorControls.ts'),
  'utf8',
)

describe('useGeneratorControls image model fallback', () => {
  it('falls back to the first available image model when the current one is missing', () => {
    expect(source).toContain('const currentModelExists = availableImageModels.some(model =>')
    expect(source).toContain('model.value === imageModel && model.provider === imageProvider')
    expect(source).toContain("availableImageModels.find(model => model.value === DEFAULT_IMAGE_MODEL)")
    expect(source).toContain('setImageModel(fallbackImageModel.value)')
    expect(source).toContain('setImageProvider(fallbackImageModel.provider)')
  })

  it('prefers the configured default image model when initializing image controls', () => {
    expect(source).toContain("availableImageModels.find(model => model.value === DEFAULT_IMAGE_MODEL)")
    expect(source).toContain('setImageModel(prev => prev || fallbackImageModel.value)')
    expect(source).toContain('setImageProvider(prev => prev || fallbackImageModel.provider)')
  })

  it('normalizes the global video duration when the selected model changes', () => {
    expect(source).toContain('const allowedVideoDurations = getResolvedVideoDurationsFromConfig(')
    expect(source).toContain('if (!allowedVideoDurations.includes(videoDuration) && allowedVideoDurations.length > 0) {')
    expect(source).toContain('setVideoDuration(allowedVideoDurations[0])')
  })

  it('localizes builtin provider labels through the shared brand helper', () => {
    expect(source).toContain('resolveLocalizedProviderName(')
    expect(source).toContain("provider.code === 'builtin'")
  })
})
