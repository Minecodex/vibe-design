import { describe, expect, it } from 'vitest'

import { mergeGenerationTaskSnapshot } from './generationTaskSnapshot'

describe('mergeGenerationTaskSnapshot', () => {
  it('hydrates polling metadata without losing existing canvas item display fields', () => {
    const merged = mergeGenerationTaskSnapshot(
      {
        task_id: 42,
        status: 'completed',
        result_url: '/generated/current.png',
        canvas_item: {
          id: 'canvas-item-42',
          task_id: 42,
          status: 'completed',
          model_name: 'flux',
          model_label: 'Flux',
          provider_code: 'builtin',
          resolution: '1K',
          aspect_ratio: '1:1',
          url: '/generated/current.png',
        },
      },
      {
        id: 42,
        status: 'processing',
        progress: 50,
        canvas_revision: 18,
        canvas_item_deleted: false,
        model_name: 'flux',
        provider_code: 'builtin',
        params: {
          resolution: '1K',
          aspect_ratio: '1:1',
        },
      },
    )

    expect(merged.task_snapshot_loaded).toBe(true)
    expect(merged.result_url).toBe('/generated/current.png')
    expect(merged.canvas_revision).toBe(18)
    expect(merged.canvas_item_deleted).toBe(false)
    expect(merged.canvas_item.model_label).toBe('Flux')
    expect(merged.canvas_item.status).toBe('completed')
  })
})
