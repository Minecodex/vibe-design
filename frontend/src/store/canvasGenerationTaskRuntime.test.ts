import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentApi, type AgentEvent } from '@/api/endpoints/agent'
import {
  applyGenerationTaskSnapshot,
  disposeConversationGenerationTasks,
  recoverGenerationTasksFromSession,
  resetCanvasGenerationTaskRuntimeForTests,
  startGenerationTaskPolling,
  stopGenerationTaskPolling,
  updateBlocksByGenerationTask,
  updateToolCallsByGenerationTask,
  upsertGenerationTaskFromItemEvent,
  type CanvasGenerationRuntimeAdapter,
} from './canvasGenerationTaskRuntime'

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getHarnessGenerationTask: vi.fn(),
    getHarnessGenerationArtifactTask: vi.fn(),
  },
}))

vi.mock('@/api/endpoints/generation', () => ({
  generationApi: {
    queryTask: vi.fn(),
  },
}))

function event(type: AgentEvent['type'], data: Record<string, any>): AgentEvent {
  return { type, data, sequence: 1 }
}

function adapter(overrides: Partial<CanvasGenerationRuntimeAdapter> = {}): CanvasGenerationRuntimeAdapter {
  return {
    getState: () => ({
      conversationId: 'conv-1',
      engineVersion: 'harness',
      onCanvasUpdate: vi.fn(),
    } as any),
    updateToolCallByGenerationTask: vi.fn(),
    updateCanvasItemByGenerationTask: vi.fn(),
    saveCanvasItems: vi.fn(),
    ...overrides,
  }
}

describe('canvasGenerationTaskRuntime', () => {
  afterEach(() => {
    resetCanvasGenerationTaskRuntimeForTests()
    vi.useRealTimers()
  })

  it('starts polling when item_started generation task arrives', () => {
    vi.useFakeTimers()
    const runtimeAdapter = adapter()

    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      status: 'running',
      payload: {
        task_id: 42,
        artifact_ref: 'artifact_ref:image-1',
        kind: 'image',
        progress: 0,
      },
    }), runtimeAdapter)

    expect(startGenerationTaskPolling('conv-1:artifact_ref:image-1')).toBe(false)
  })

  it('polls harness generation tasks by artifact ref when one is available', async () => {
    vi.useFakeTimers()
    vi.mocked(agentApi.getHarnessGenerationArtifactTask).mockResolvedValue({
      data: {
        task_id: '42',
        artifact_ref: 'artifact_ref:image-1',
        status: 'completed',
        result_url: '/uploads/final.png',
      },
    } as any)
    const runtimeAdapter = adapter()

    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      status: 'running',
      payload: {
        task_id: 42,
        artifact_ref: 'artifact_ref:image-1',
        kind: 'image',
      },
    }), runtimeAdapter)

    await vi.runOnlyPendingTimersAsync()

    expect(agentApi.getHarnessGenerationArtifactTask).toHaveBeenCalledWith('conv-1', 'artifact_ref:image-1')
    expect(agentApi.getHarnessGenerationTask).not.toHaveBeenCalled()
  })

  it('publishes a canvas placeholder when item_started lacks a backend canvas item', () => {
    vi.useFakeTimers()
    const onCanvasUpdate = vi.fn()
    const updateCanvasItemByGenerationTask = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({
        conversationId: 'conv-1',
        engineVersion: 'harness',
        onCanvasUpdate,
      } as any),
      updateCanvasItemByGenerationTask,
    })

    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      status: 'running',
      payload: {
        task_id: 42,
        artifact_ref: 'artifact_ref:image-1',
        kind: 'image',
        progress: 0,
      },
    }), runtimeAdapter)

    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      id: 'agent-generated-artifact_ref-image-1',
      type: 'image_generator',
      task_id: '42',
      artifact_ref: 'artifact_ref:image-1',
      status: 'generating',
    }))
    expect(onCanvasUpdate).toHaveBeenCalledWith('add', expect.objectContaining({
      id: 'agent-generated-artifact_ref-image-1',
      type: 'image_generator',
      status: 'generating',
      conversationId: 'conv-1',
    }))
  })

  it('carries presentation message scope into canvas placeholders for agent grouping', () => {
    vi.useFakeTimers()
    const updateCanvasItemByGenerationTask = vi.fn()
    const onCanvasUpdate = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({
        conversationId: 'conv-1',
        engineVersion: 'harness',
        onCanvasUpdate,
      } as any),
      updateCanvasItemByGenerationTask,
    })

    upsertGenerationTaskFromItemEvent(event('item_started', {
      conversation_id: 'conv-1',
      item_type: 'generation_task',
      item_id: 'artifact_ref:white-view',
      status: 'running',
      payload: {
        task_id: 43,
        artifact_ref: 'artifact_ref:white-view',
        kind: 'image',
        presentation_scope: {
          message_key: 'interaction-response:conv-1:white:2',
          parent_block_key: null,
        },
        presentation_message_key: 'interaction-response:conv-1:white:2',
        presentation_order: 2,
      },
    }), runtimeAdapter)

    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      artifact_ref: 'artifact_ref:white-view',
      messageId: 'interaction-response:conv-1:white:2',
      agent_message_id: 'interaction-response:conv-1:white:2',
      agentMediaKey: 'agent-generated-artifact_ref-white-view',
      agent_media_key: 'agent-generated-artifact_ref-white-view',
    }))
    expect(onCanvasUpdate).toHaveBeenCalledWith('add', expect.objectContaining({
      artifact_ref: 'artifact_ref:white-view',
      messageId: 'interaction-response:conv-1:white:2',
      agent_message_id: 'interaction-response:conv-1:white:2',
    }))
  })

  it('does not assign legacy ecommerce white-background group keys', () => {
    vi.useFakeTimers()
    const updateCanvasItemByGenerationTask = vi.fn()
    const onCanvasUpdate = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({
        conversationId: 'conv-1',
        engineVersion: 'harness',
        onCanvasUpdate,
      } as any),
      updateCanvasItemByGenerationTask,
    })

    upsertGenerationTaskFromItemEvent(event('item_started', {
      conversation_id: 'conv-1',
      item_type: 'generation_task',
      item_id: 'artifact_ref:white-view',
      status: 'running',
      payload: {
        task_id: 43,
        artifact_ref: 'artifact_ref:white-view',
        kind: 'image',
        presentation_surface: 'ecommerce_white_background_views',
      },
    }), runtimeAdapter)

    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      artifact_ref: 'artifact_ref:white-view',
    }))
    expect(onCanvasUpdate).toHaveBeenCalledWith('add', expect.objectContaining({
      artifact_ref: 'artifact_ref:white-view',
    }))
    expect(updateCanvasItemByGenerationTask.mock.calls[0][1].agent_group_key).toBeNull()
    expect(onCanvasUpdate.mock.calls[0][1].agent_group_key).toBeNull()
  })

  it('applies progress update to matching tool call', () => {
    const updateToolCallByGenerationTask = vi.fn()
    const runtimeAdapter = adapter({ updateToolCallByGenerationTask })

    upsertGenerationTaskFromItemEvent(event('item_updated', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      status: 'running',
      payload: {
        task_id: 42,
        artifact_ref: 'artifact_ref:image-1',
        kind: 'image',
        progress: 46,
      },
    }), runtimeAdapter)

    expect(updateToolCallByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      task_id: '42',
      artifact_ref: 'artifact_ref:image-1',
      status: 'processing',
      progress: 46,
    }))
  })

  it('notifies the canvas revision from backend agent patch events', () => {
    const updateCanvasRevisionByAgentPatch = vi.fn()
    const runtimeAdapter = adapter({ updateCanvasRevisionByAgentPatch })

    upsertGenerationTaskFromItemEvent(event('item_updated', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      status: 'running',
      payload: {
        task_id: 42,
        artifact_ref: 'artifact_ref:image-1',
        kind: 'image',
        progress: 46,
        canvas_revision: 12,
      },
    }), runtimeAdapter)

    expect(updateCanvasRevisionByAgentPatch).toHaveBeenCalledWith(12, { canvasItemDeleted: false })
  })

  it('does not reinsert canvas media when the backend tombstone wins', () => {
    const updateToolCallByGenerationTask = vi.fn()
    const updateCanvasItemByGenerationTask = vi.fn()
    const updateCanvasRevisionByAgentPatch = vi.fn()
    const onCanvasUpdate = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({
        conversationId: 'conv-1',
        engineVersion: 'harness',
        onCanvasUpdate,
      } as any),
      updateToolCallByGenerationTask,
      updateCanvasItemByGenerationTask,
      updateCanvasRevisionByAgentPatch,
    })

    upsertGenerationTaskFromItemEvent(event('item_completed', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-deleted',
      status: 'completed',
      payload: {
        task_id: 42,
        artifact_ref: 'artifact_ref:image-deleted',
        kind: 'image',
        result_url: '/uploads/deleted.png',
        canvas_revision: 14,
        canvas_item_deleted: true,
        canvas_item: null,
      },
    }), runtimeAdapter)

    expect(updateToolCallByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      task_id: '42',
      artifact_ref: 'artifact_ref:image-deleted',
      status: 'completed',
      result_url: '/uploads/deleted.png',
      canvas_item_deleted: true,
    }))
    expect(updateCanvasRevisionByAgentPatch).toHaveBeenCalledWith(14, { canvasItemDeleted: true })
    expect(updateCanvasItemByGenerationTask).not.toHaveBeenCalled()
    expect(onCanvasUpdate).not.toHaveBeenCalled()
  })

  it('keeps suppressed ecommerce white-background tasks on the canvas without updating chat generation cards', () => {
    vi.useFakeTimers()
    const updateToolCallByGenerationTask = vi.fn()
    const updateCanvasItemByGenerationTask = vi.fn()
    const onCanvasUpdate = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({ conversationId: 'conv-1', engineVersion: 'harness', onCanvasUpdate } as any),
      updateToolCallByGenerationTask,
      updateCanvasItemByGenerationTask,
    })

    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:white',
      status: 'running',
      payload: {
        task_id: 88,
        artifact_ref: 'artifact_ref:white',
        kind: 'image',
        suppress_standard_media_card: true,
      },
    }), runtimeAdapter)

    expect(updateToolCallByGenerationTask).not.toHaveBeenCalled()
    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      artifact_ref: 'artifact_ref:white',
      status: 'generating',
    }))
    expect(onCanvasUpdate).toHaveBeenCalledWith('add', expect.objectContaining({
      artifact_ref: 'artifact_ref:white',
      status: 'generating',
    }))

    applyGenerationTaskSnapshot('conv-1:artifact_ref:white', {
      task_id: 88,
      artifact_ref: 'artifact_ref:white',
      status: 'completed',
      result_url: '/uploads/white.png',
      suppress_standard_media_card: true,
      canvas_item: {
        id: 'canvas-white',
        task_id: 88,
        artifact_ref: 'artifact_ref:white',
        status: 'completed',
        url: '/uploads/white.png',
      },
    }, runtimeAdapter)

    expect(updateToolCallByGenerationTask).not.toHaveBeenCalled()
    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      id: 'canvas-white',
      status: 'completed',
      url: '/uploads/white.png',
    }))
    expect(onCanvasUpdate).toHaveBeenCalledWith('add_generated_media', expect.objectContaining({
      id: 'canvas-white',
      url: '/uploads/white.png',
    }))
  })

  it('rebuilds only the matched message and preserves sibling identity (memo-friendly)', () => {
    const matchingMessage = {
      id: 'm-match',
      role: 'assistant',
      createdAt: '2026-01-01T00:00:00Z',
      content: null,
      toolCalls: [{
        callId: 'call-match',
        name: 'generate_image',
        args: {},
        status: 'running',
        result: { task_id: 42, artifact_ref: 'artifact_ref:image-1', status: 'processing', progress: 0 },
      }],
    }
    const siblingMessage = {
      id: 'm-sibling',
      role: 'assistant',
      createdAt: '2026-01-01T00:00:00Z',
      content: null,
      toolCalls: [{
        callId: 'call-other',
        name: 'generate_image',
        args: {},
        status: 'running',
        result: { task_id: 7, artifact_ref: 'artifact_ref:other', status: 'processing', progress: 0 },
      }],
    }
    const messages = [matchingMessage, siblingMessage]

    const next = updateToolCallsByGenerationTask(messages as any, {
      task_id: 42,
      artifact_ref: 'artifact_ref:image-1',
      status: 'processing',
      progress: 60,
    })

    expect(next).not.toBe(messages)
    // Matched message is rebuilt with the new progress…
    expect(next[0]).not.toBe(matchingMessage)
    expect(next[0].toolCalls?.[0].result?.progress).toBe(60)
    // …but the unrelated sibling keeps its exact reference so memoized bubbles skip it.
    expect(next[1]).toBe(siblingMessage)
  })

  it('returns the same messages array when no tool call matches', () => {
    const messages = [{
      id: 'm1',
      role: 'assistant',
      createdAt: '2026-01-01T00:00:00Z',
      content: null,
      toolCalls: [{
        callId: 'c',
        name: 'generate_image',
        args: {},
        status: 'running',
        result: { task_id: 1, artifact_ref: 'artifact_ref:a', status: 'processing', progress: 0 },
      }],
    }]

    const next = updateToolCallsByGenerationTask(messages as any, {
      task_id: 999,
      artifact_ref: 'artifact_ref:none',
      status: 'processing',
      progress: 10,
    })

    expect(next).toBe(messages)
  })

  it('applies completed snapshot to tool call and canvas item then stops polling', () => {
    vi.useFakeTimers()
    const updateToolCallByGenerationTask = vi.fn()
    const updateCanvasItemByGenerationTask = vi.fn()
    const updateCanvasRevisionByAgentPatch = vi.fn()
    const onCanvasUpdate = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({ conversationId: 'conv-1', engineVersion: 'harness', onCanvasUpdate } as any),
      updateToolCallByGenerationTask,
      updateCanvasItemByGenerationTask,
      updateCanvasRevisionByAgentPatch,
    })

    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      payload: { task_id: 42, artifact_ref: 'artifact_ref:image-1', kind: 'image' },
    }), runtimeAdapter)

    applyGenerationTaskSnapshot('conv-1:artifact_ref:image-1', {
      task_id: 42,
      artifact_ref: 'artifact_ref:image-1',
      status: 'completed',
      progress: 100,
      result_url: '/uploads/final.png',
      canvas_revision: 24,
      canvas_item_deleted: false,
      canvas_item: { id: 'canvas-1', task_id: 42, status: 'completed', url: '/uploads/final.png' },
    }, runtimeAdapter)

    expect(updateToolCallByGenerationTask).toHaveBeenLastCalledWith('conv-1', expect.objectContaining({
      status: 'completed',
      result_url: '/uploads/final.png',
    }))
    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      id: 'canvas-1',
      status: 'completed',
      url: '/uploads/final.png',
    }))
    expect(updateCanvasRevisionByAgentPatch).toHaveBeenCalledWith(24, { canvasItemDeleted: false })
    expect(onCanvasUpdate).toHaveBeenCalledWith('add_generated_media', expect.objectContaining({
      id: 'canvas-1',
      url: '/uploads/final.png',
      canvas_revision: 24,
      canvas_item_deleted: false,
    }))
    // A terminal snapshot disposes the task (stops polling and drops it from the registry)
    // so it no longer leaks; a follow-up stop is a no-op because the entry is already gone.
    expect(stopGenerationTaskPolling('conv-1:artifact_ref:image-1')).toBe(false)
  })

  it('applies completed video snapshots with canvas revision before terminal canvas replacement', () => {
    vi.useFakeTimers()
    const updateToolCallByGenerationTask = vi.fn()
    const updateCanvasItemByGenerationTask = vi.fn()
    const updateCanvasRevisionByAgentPatch = vi.fn()
    const onCanvasUpdate = vi.fn()
    const runtimeAdapter = adapter({
      getState: () => ({ conversationId: 'conv-1', engineVersion: 'harness', onCanvasUpdate } as any),
      updateToolCallByGenerationTask,
      updateCanvasItemByGenerationTask,
      updateCanvasRevisionByAgentPatch,
    })

    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:video-1',
      payload: { task_id: 84, artifact_ref: 'artifact_ref:video-1', kind: 'video' },
    }), runtimeAdapter)

    applyGenerationTaskSnapshot('conv-1:artifact_ref:video-1', {
      task_id: 84,
      artifact_ref: 'artifact_ref:video-1',
      kind: 'video',
      status: 'completed',
      progress: 100,
      result_url: '/uploads/final.mp4',
      canvas_revision: 25,
      canvas_item_deleted: false,
      canvas_item: {
        id: 'canvas-video-1',
        type: 'video_generator',
        task_id: 84,
        status: 'completed',
        url: '/uploads/final.mp4',
      },
    }, runtimeAdapter)

    expect(updateCanvasRevisionByAgentPatch).toHaveBeenCalledWith(25, { canvasItemDeleted: false })
    expect(updateCanvasItemByGenerationTask).toHaveBeenCalledWith('conv-1', expect.objectContaining({
      id: 'canvas-video-1',
      status: 'completed',
      url: '/uploads/final.mp4',
    }))
    expect(onCanvasUpdate.mock.calls.filter(([action]) => action === 'add_generated_media')).toHaveLength(1)
    expect(onCanvasUpdate).toHaveBeenCalledWith('add_generated_media', expect.objectContaining({
      id: 'canvas-video-1',
      type: 'video',
      url: '/uploads/final.mp4',
      canvas_revision: 25,
      canvas_item_deleted: false,
    }))
  })

  it('recovers pending generation tasks from session', () => {
    vi.useFakeTimers()
    const runtimeAdapter = adapter()
    const recovered = recoverGenerationTasksFromSession('conv-1', {
      messages: [{
        id: 'm1',
        role: 'assistant',
        createdAt: '2026-01-01T00:00:00Z',
        content: null,
        toolCalls: [{
          callId: 'call-1',
          name: 'generate_image',
          args: {},
          status: 'running',
          result: { task_id: 99, artifact_ref: 'artifact_ref:pending', status: 'processing' },
        }],
      }],
    } as any, runtimeAdapter)

    expect(recovered).toBe(1)
    expect(startGenerationTaskPolling('conv-1:artifact_ref:pending')).toBe(false)
  })

  it.each([
    ['image_generation', 'image_generator', '/uploads/final.png'],
    ['video_generation', 'video_generator', '/uploads/final.mp4'],
  ])('updates %s media card blocks from completed task snapshots', (mediaType, canvasType, resultUrl) => {
    const blocks = [{
      id: 'media-artifact-image-1',
      kind: 'content',
      uiKind: 'media_card',
      status: 'processing',
      payload: {
        tool_name: mediaType === 'video_generation' ? 'generate_video' : 'generate_image',
        media_type: mediaType,
        task_id: '42',
        artifact_ref: 'artifact_ref:image-1',
        status: 'processing',
        progress: 0,
        result_url: null,
        canvas_item: {
          id: 'canvas-1',
          type: canvasType,
          task_id: '42',
          status: 'generating',
          url: '',
        },
      },
    }]

    const nextBlocks = updateBlocksByGenerationTask(blocks as any, {
      task_id: '42',
      artifact_ref: 'artifact_ref:image-1',
      status: 'completed',
      progress: 100,
      result_url: resultUrl,
      canvas_item: {
        id: 'canvas-1',
        type: canvasType,
        task_id: '42',
        status: 'completed',
        url: resultUrl,
      },
    })

    expect(nextBlocks).not.toBe(blocks)
    expect(nextBlocks[0].status).toBe('completed')
    expect(nextBlocks[0].payload.status).toBe('completed')
    expect(nextBlocks[0].payload.progress).toBe(100)
    expect(nextBlocks[0].payload.result_url).toBe(resultUrl)
    expect(nextBlocks[0].payload.canvas_item.status).toBe('completed')
    expect(nextBlocks[0].payload.canvas_item.url).toBe(resultUrl)
  })

  it('disposes conversation polling tasks', () => {
    vi.useFakeTimers()
    const runtimeAdapter = adapter()
    upsertGenerationTaskFromItemEvent(event('item_started', {
      item_type: 'generation_task',
      item_id: 'artifact_ref:image-1',
      payload: { task_id: 42, artifact_ref: 'artifact_ref:image-1', kind: 'image' },
    }), runtimeAdapter)

    disposeConversationGenerationTasks('conv-1')

    expect(startGenerationTaskPolling('conv-1:artifact_ref:image-1')).toBe(false)
  })
})
