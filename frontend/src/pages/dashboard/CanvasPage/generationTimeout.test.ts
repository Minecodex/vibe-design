import { describe, expect, it } from 'vitest'

import {
  getGenerationPollTimeoutMs,
  IMAGE_GENERATION_POLL_TIMEOUT_MS,
  VIDEO_GENERATION_POLL_TIMEOUT_MS,
} from './generationTimeout'

describe('generationTimeout', () => {
  it('uses 30 minutes for image generation polling', () => {
    expect(getGenerationPollTimeoutMs('image')).toBe(IMAGE_GENERATION_POLL_TIMEOUT_MS)
  })

  it('uses 5 hours for video generation polling', () => {
    expect(getGenerationPollTimeoutMs('video')).toBe(VIDEO_GENERATION_POLL_TIMEOUT_MS)
  })
})
