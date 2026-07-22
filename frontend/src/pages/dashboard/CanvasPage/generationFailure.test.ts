import { describe, expect, it } from 'vitest'

import {
  getGenerationFailureKind,
  getGenerationPollingStatus,
  isInternalFailedGenerationItem,
  isRetryableFailedGenerationItem,
} from './generationFailure'

describe('generationFailure helpers', () => {
  it('classifies failed items with a generation task as retryable task failures', () => {
    expect(getGenerationFailureKind({ status: 'failed', task_id: 42 })).toBe('task_failed')
    expect(isRetryableFailedGenerationItem({
      type: 'image_generator',
      status: 'failed',
      task_id: 42,
    } as any)).toBe(true)
  })

  it('classifies failed items without a generation task as internal failures', () => {
    expect(getGenerationFailureKind({ status: 'failed', task_id: undefined })).toBe('internal_failed')
    expect(isInternalFailedGenerationItem({
      type: 'video_generator',
      status: 'failed',
      task_id: undefined,
    } as any)).toBe(true)
    expect(isRetryableFailedGenerationItem({
      type: 'video_generator',
      status: 'failed',
      task_id: undefined,
    } as any)).toBe(false)
  })

  it('keeps harness artifact failures generating while automatic retries remain', () => {
    expect(getGenerationPollingStatus({
      status: 'failed',
      auto_retry_count: 1,
      auto_retry_max: 3,
    })).toBe('generating')

    expect(getGenerationPollingStatus({
      status: 'failed',
      auto_retry_count: 3,
      auto_retry_max: 3,
    })).toBe('failed')
  })
})
