import { describe, expect, it } from 'vitest'
import { mergeGenerationTaskSnapshot } from './components/generationTaskSnapshot'

describe('MessageList generation failure metadata', () => {
  it('prefers persisted task params over request args for display metadata', () => {
    const result = mergeGenerationTaskSnapshot(
      { params: { aspect_ratio: '1:1', resolution: '1K' } },
      { id: 9, provider_code: 'builtin', params: { aspect_ratio: '16:9', resolution: '4K' } },
    )
    expect(result.params).toEqual({ aspect_ratio: '16:9', resolution: '4K' })
    expect(result.provider_code).toBe('builtin')
  })

  it('retains terminal failure metadata and marks the task snapshot as loaded', () => {
    const result = mergeGenerationTaskSnapshot(
      { canvas_item: { id: 'image-9', status: 'generating' } },
      { id: 9, status: 'failed', error_message: 'Provider rejected the request' },
    )
    expect(result.task_snapshot_loaded).toBe(true)
    expect(result.error_message).toBe('Provider rejected the request')
    expect(result.canvas_item?.status).toBe('failed')
    expect(result.canvas_item?.failure_kind).toBe('task_failed')
  })
})
