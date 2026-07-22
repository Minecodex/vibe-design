import { describe, expect, test } from 'vitest'

import {
  getAllowedVideoRatios,
  getAllowedVideoResolutions,
  getResolvedVideoDurationsFromConfig,
  getResolvedVideoModelCapability,
} from './videoModelConfig'

describe('videoModelConfig', () => {
  const videoModels = [
    {
      value: 'kling-v3',
      provider: 'builtin',
      config: {
        allowed_sizes: ['720p', '1080p'],
        allowed_aspect_ratios: ['16:9', '9:16'],
        allowed_durations_by_mode: {
          text: ['5s', '10s', '15s'],
          reference: ['5s', '10s'],
          frames: ['5s'],
        },
        supports_first_frame: true,
        supports_tail_frame: true,
        supports_audio: true,
        audio_allowed_sizes: ['1080p_audio'],
        tail_frame_allowed_sizes: ['1080p'],
        requires_first_frame_for_tail_frame: true,
        audio_tail_frame_mutually_exclusive: true,
        max_image_inputs: 2,
        image_modes_conflict: true,
      },
    },
  ]

  test('prefers backend config for video capabilities', () => {
    expect(getResolvedVideoModelCapability(videoModels, 'kling-v3', 'builtin')).toMatchObject({
      supportsReferenceImages: true,
      maxReferenceImages: 2,
      supportsFirstFrame: true,
      supportsTailFrame: true,
      supportsAudio: true,
      audioAllowedResolutions: ['1080p_audio'],
      tailFrameAllowedResolutions: ['1080p'],
      requiresFirstFrameForTailFrame: true,
      audioTailFrameMutuallyExclusive: true,
      imageModesConflict: true,
    })
  })

  test('uses backend config for video ratios, resolutions, and durations', () => {
    expect(getAllowedVideoResolutions(videoModels[0].config)).toEqual(['720p', '1080p'])
    expect(getAllowedVideoRatios(videoModels[0].config)).toEqual(['16:9', '9:16'])
    expect(
      getResolvedVideoDurationsFromConfig(
        videoModels,
        { reference_images: ['https://example.com/ref.png'] },
        'kling-v3',
        'builtin',
      ),
    ).toEqual(['5s', '10s'])
  })
})
