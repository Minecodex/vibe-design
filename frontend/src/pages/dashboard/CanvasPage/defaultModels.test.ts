import { describe, expect, it } from 'vitest'

import { DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_MODEL_LABEL } from './defaultModels'

describe('defaultModels', () => {
  it('uses Seedream 5.0 Lite as the default image model', () => {
    expect(DEFAULT_IMAGE_MODEL).toBe('doubao-seedream-5-0-lite')
    expect(DEFAULT_IMAGE_MODEL_LABEL).toBe('Seedream-5.0-Lite')
  })
})
