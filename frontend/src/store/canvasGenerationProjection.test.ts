import { describe, expect, it } from 'vitest'

import { applyCanvasGenerationEvent } from './canvasGenerationProjection'
import { createGenerationProjectionState } from './generationProjection'

describe('canvasGenerationProjection', () => {
  it('emits a stable canvas placeholder for a started image generation event', () => {
    const session = { generationProjection: createGenerationProjectionState() }
    const event = {
      type: 'generation_started',
      sequence: 2,
      data: {
        task_id: 'task-1',
        artifact_ref: 'artifact_ref:image-1',
        media_type: 'image_generation',
        progress: 0,
      },
    }

    const first = applyCanvasGenerationEvent(session, event, 'conv-1')
    const duplicate = applyCanvasGenerationEvent(first.session, { ...event, sequence: 3 }, 'conv-1')

    expect(first.canvasUpdate).toEqual({
      action: 'add',
      item: expect.objectContaining({
        id: 'agent-generated-artifact_ref-image-1',
        type: 'image_generator',
        url: '',
        task_id: 'task-1',
        artifact_ref: 'artifact_ref:image-1',
        status: 'generating',
        progress: 0,
        conversationId: 'conv-1',
        agentMediaKey: 'agent-generated-artifact_ref-image-1',
      }),
    })
    expect(duplicate.canvasUpdate).toBeUndefined()
  })

  it('can complete a generation after emitting its placeholder', () => {
    const started = applyCanvasGenerationEvent(
      { generationProjection: createGenerationProjectionState() },
      {
        type: 'generation_started',
        sequence: 2,
        data: {
          task_id: 'task-2',
          artifact_ref: 'artifact_ref:image-2',
          media_type: 'image_generation',
        },
      },
      'conv-1',
    )

    const completed = applyCanvasGenerationEvent(
      started.session,
      {
        type: 'generation_completed',
        sequence: 4,
        data: {
          task_id: 'task-2',
          artifact_ref: 'artifact_ref:image-2',
          result_url: '/api/v1/uploads/generated/final.png',
          status: 'completed',
          canvas_revision: 21,
          canvas_item_deleted: false,
        },
      },
      'conv-1',
    )

    expect(completed.canvasUpdate).toEqual({
      action: 'add_generated_media',
      meta: { canvasRevision: 21, canvasItemDeleted: false },
      item: expect.objectContaining({
        id: 'artifact_ref:image-2',
        task_id: 'task-2',
        artifact_ref: 'artifact_ref:image-2',
        url: '/api/v1/uploads/generated/final.png',
        result_url: '/api/v1/uploads/generated/final.png',
        canvas_revision: 21,
        conversationId: 'conv-1',
      }),
    })
  })

  it('passes nested canvas revision meta through completed generation projections', () => {
    const result = applyCanvasGenerationEvent(
      { generationProjection: createGenerationProjectionState() },
      {
        type: 'generation_completed',
        sequence: 5,
        data: {
          result: {
            task_id: 52,
            status: 'completed',
            result_url: '/api/v1/uploads/generated/nested.png',
            artifact_ref: 'artifact_ref:nested',
            canvas_revision: 33,
            canvas_item_deleted: false,
          },
        },
      },
      'conv-1',
    )

    expect(result.canvasUpdate).toEqual({
      action: 'add_generated_media',
      meta: { canvasRevision: 33, canvasItemDeleted: false },
      item: expect.objectContaining({
        canvas_revision: 33,
        url: '/api/v1/uploads/generated/nested.png',
      }),
    })
  })

  it('emits one canvas media insertion for a completed generation event', () => {
    const session = { generationProjection: createGenerationProjectionState() }
    const event = {
      type: 'generation_completed',
      sequence: 4,
      data: {
        result: {
          task_id: 42,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/result.png',
          asset_id: 9,
          artifact_ref: 'artifact_ref:abc',
        },
      },
    }

    const first = applyCanvasGenerationEvent(session, event, 'conv-1')
    const duplicate = applyCanvasGenerationEvent(first.session, { ...event, sequence: 5 }, 'conv-1')

    expect(first.canvasUpdate).toEqual({
      action: 'add_generated_media',
      item: {
        id: '9',
        type: 'image',
        url: '/api/v1/uploads/generated/result.png',
        task_id: '42',
        result_url: '/api/v1/uploads/generated/result.png',
        artifact_ref: 'artifact_ref:abc',
        agentMediaKey: '9',
        conversationId: 'conv-1',
      },
    })
    expect(duplicate.canvasUpdate).toBeUndefined()
  })

  it('keeps a completed event newer than a stale started event', () => {
    const completed = applyCanvasGenerationEvent(
      { generationProjection: createGenerationProjectionState() },
      {
        type: 'generation_completed',
        sequence: 8,
        data: { task_id: 'task-1', result_url: '/result.png', artifact_ref: 'artifact_ref:1' },
      },
      'conv-1',
    )

    const stale = applyCanvasGenerationEvent(
      completed.session,
      {
        type: 'generation_started',
        sequence: 3,
        data: { task_id: 'task-1', progress: 20 },
      },
      'conv-1',
    )

    expect(stale.session.generationProjection.tasks['task-1'].status).toBe('completed')
    expect(stale.canvasUpdate).toBeUndefined()
  })

  it('does not emit a canvas insertion when the backend says the agent item was deleted', () => {
    const session = { generationProjection: createGenerationProjectionState() }
    const event = {
      type: 'generation_completed',
      sequence: 4,
      data: {
        result: {
          task_id: 42,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/result.png',
          artifact_ref: 'artifact_ref:deleted',
        },
        canvas_item_deleted: true,
      },
    }

    const result = applyCanvasGenerationEvent(session, event, 'conv-1')

    expect(result.handled).toBe(true)
    expect(result.canvasUpdate).toBeUndefined()
    expect(result.session.generationProjection.tasks['42'].status).toBe('completed')
  })

  it('does not emit a canvas insertion when nested result marks the agent item deleted', () => {
    const session = { generationProjection: createGenerationProjectionState() }
    const event = {
      type: 'generation_completed',
      sequence: 5,
      data: {
        result: {
          task_id: 43,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/deleted-result.png',
          artifact_ref: 'artifact_ref:deleted-result',
          canvas_item_deleted: true,
          canvas_revision: 44,
        },
      },
    }

    const result = applyCanvasGenerationEvent(session, event, 'conv-1')

    expect(result.handled).toBe(true)
    expect(result.canvasUpdate).toBeUndefined()
    expect(result.session.generationProjection.tasks['43'].status).toBe('completed')
  })
})
