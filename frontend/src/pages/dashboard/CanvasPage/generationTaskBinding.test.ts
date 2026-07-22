import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  GENERATION_BINDING_RECOVERY_WINDOW_MS,
  applyRecoveredGenerationTask,
  getPendingGenerationBindingItems,
  isGenerationTaskPendingStatus,
  shouldExpireBindingTask,
} from './generationTaskBinding'

describe('generationTaskBinding', () => {
  it('collects unresolved binding items with derived task types', () => {
    const items: CanvasItem[] = [
      {
        id: 'image-gen-1',
        type: 'image_generator',
        url: '',
        x: 0,
        y: 0,
        status: 'binding_task',
        client_request_id: 'image-request-1',
      },
      {
        id: 'video-gen-1',
        type: 'video_generator',
        url: '',
        x: 0,
        y: 0,
        status: 'binding_task',
        client_request_id: 'video-request-1',
        reference_images: ['https://example.com/ref.png'],
      },
      {
        id: 'completed-image',
        type: 'image',
        url: '/done.png',
        x: 0,
        y: 0,
        status: 'completed',
      },
    ]

    expect(getPendingGenerationBindingItems(items)).toEqual([
      {
        itemId: 'image-gen-1',
        client_request_id: 'image-request-1',
        task_type: 'text2image',
      },
      {
        itemId: 'video-gen-1',
        client_request_id: 'video-request-1',
        task_type: 'image2video',
      },
    ])
  })

  it('applies a recovered completed task to a placeholder item', () => {
    const item: CanvasItem = {
      id: 'image-gen-1',
      type: 'image_generator',
      url: '',
      x: 10,
      y: 20,
      status: 'binding_task',
      client_request_id: 'image-request-1',
      prompt: 'make it cinematic',
    }

    expect(applyRecoveredGenerationTask(item, {
      id: 99,
      task_type: 'text2image',
      status: 'completed',
      progress: 100,
      result_url: '/generated/final.png',
      client_request_id: 'image-request-1',
      model_label: 'NanoBanana2',
      prompt: 'make it cinematic',
      created_at: '2026-05-13T00:00:00Z',
    })).toMatchObject({
      id: 'image-gen-1',
      type: 'image',
      status: 'completed',
      task_id: 99,
      url: '/generated/final.png',
      client_request_id: 'image-request-1',
      model_label: 'NanoBanana2',
      progress: 100,
    })
  })

  it('expires old binding placeholders that still do not have a task', () => {
    expect(shouldExpireBindingTask({
      binding_started_at: '2026-05-13T00:00:00.000Z',
    } as CanvasItem, Date.parse('2026-05-13T00:01:01.000Z'))).toBe(true)
    expect(GENERATION_BINDING_RECOVERY_WINDOW_MS).toBeGreaterThan(30_000)
  })

  it('treats binding_task and generating as pending generation states', () => {
    expect(isGenerationTaskPendingStatus('binding_task')).toBe(true)
    expect(isGenerationTaskPendingStatus('generating')).toBe(true)
    expect(isGenerationTaskPendingStatus('completed')).toBe(false)
  })
})
