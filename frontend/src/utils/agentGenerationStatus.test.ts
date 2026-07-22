import { describe, expect, it } from 'vitest'

import { getGenerationTaskId, resolveAsyncGenerationToolStatus } from './agentGenerationStatus'

describe('getGenerationTaskId', () => {
  it('preserves harness string task ids instead of coercing them to null', () => {
    expect(getGenerationTaskId({
      task_id: 'b48c0f756a8140e2bccf3f239ef132c2',
    })).toBe('b48c0f756a8140e2bccf3f239ef132c2')
  })
})

describe('resolveAsyncGenerationToolStatus', () => {
  it('keeps async generation running when a task id exists but only a transient error is present', () => {
    expect(resolveAsyncGenerationToolStatus({
      currentStatus: 'running',
      result: {
        task_id: 123,
        status: 'processing',
      },
      error: 'temporary llm error',
    })).toBe('running')
  })

  it('treats async generation as failed when no task id was created and an error is present', () => {
    expect(resolveAsyncGenerationToolStatus({
      currentStatus: 'running',
      result: {
        status: 'failed',
      },
      error: 'submission failed',
    })).toBe('failed')
  })

  it('trusts the generation task snapshot once it explicitly reports failure', () => {
    expect(resolveAsyncGenerationToolStatus({
      currentStatus: 'running',
      result: {
        task_id: 123,
        status: 'failed',
        task_snapshot_loaded: true,
        error_message: 'provider failed',
      },
    })).toBe('failed')
  })

  it('treats terminal generation item failures as failed even before a task snapshot reloads', () => {
    expect(resolveAsyncGenerationToolStatus({
      currentStatus: 'running',
      result: {
        task_id: '7',
        status: 'failed',
        error_message: 'Server disconnected without sending a response.',
        canvas_item: {
          status: 'failed',
        },
      },
    })).toBe('failed')
  })

  it('does not let a planned result url override an explicit failure status', () => {
    expect(resolveAsyncGenerationToolStatus({
      currentStatus: 'running',
      result: {
        task_id: '7',
        status: 'failed',
        result_url: 'references/sources/generated_image/original.png',
        error_message: 'provider failed',
      },
    })).toBe('failed')
  })
})
