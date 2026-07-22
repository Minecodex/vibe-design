import { describe, expect, it } from 'vitest'

import { generationApi } from '@/api/endpoints/generation'

describe('text redraw api surface', () => {
  it('exposes extract and submit methods', () => {
    expect(typeof generationApi.extractTextRedraw).toBe('function')
    expect(typeof generationApi.generateTextRedraw).toBe('function')
  })
})
