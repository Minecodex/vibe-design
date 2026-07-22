import { describe, expect, it } from 'vitest'

import type { ChatMessage, MessageBlock } from '@/store/homeHarnessStore'

import {
  filterDuplicateHomepageStreamingBlocks,
  removeRedundantHomepagePlanBlocks,
} from './homepageBlockDedupe'

function createBlock(overrides: Partial<MessageBlock>): MessageBlock {
  return {
    id: 'block-id',
    kind: 'content',
    order: 0,
    status: 'completed',
    visible: true,
    uiKind: 'assistant_text',
    payload: {},
    ...overrides,
  }
}

function createAssistantMessage(blocks: MessageBlock[]): ChatMessage {
  return {
    id: 'assistant-message',
    role: 'assistant',
    content: null,
    blocks,
    createdAt: '2026-04-20T00:00:00.000Z',
  }
}

describe('filterDuplicateHomepageStreamingBlocks', () => {
  it('filters image analysis streaming blocks when the same call is already present in replayed messages', () => {
    const messages = [
      createAssistantMessage([
        createBlock({
          id: 'media-call_7d792be9c4ae4cad9f7cee67',
          kind: 'content',
          uiKind: 'media_card',
          payload: {
            callId: 'call_7d792be9c4ae4cad9f7cee67',
            mediaType: 'image_analysis',
            text: 'Final image analysis',
          },
        }),
      ]),
    ]

    const filtered = filterDuplicateHomepageStreamingBlocks(messages, [
      createBlock({
        id: 'media-call_7d792be9c4ae4cad9f7cee67',
        kind: 'content',
        uiKind: 'media_card',
        payload: {
          callId: 'call_7d792be9c4ae4cad9f7cee67',
          mediaType: 'image_analysis',
          text: 'Final image analysis',
        },
      }),
      createBlock({
        id: 'analyze-image-text-call_7d792be9c4ae4cad9f7cee67',
        kind: 'text',
        uiKind: 'text',
        payload: {
          toolName: 'analyze_image',
          callId: 'call_7d792be9c4ae4cad9f7cee67',
          text: 'Final image analysis',
        },
      }),
    ])

    expect(filtered).toEqual([])
  })

  it('extracts identity from harness-style media and analyze-image block ids', () => {
    const messages = [
      createAssistantMessage([
        createBlock({
          id: 'media-call_03837bdda967418691edd585',
          kind: 'content',
          uiKind: 'media_card',
          payload: {
            mediaType: 'image_analysis',
            text: 'Final image analysis',
          },
        }),
      ]),
    ]

    const filtered = filterDuplicateHomepageStreamingBlocks(messages, [
      createBlock({
        id: 'analyze-image-text-call_03837bdda967418691edd585',
        kind: 'text',
        uiKind: 'text',
        payload: {
          toolName: 'analyze_image',
          text: 'Final image analysis',
        },
      }),
    ])

    expect(filtered).toEqual([])
  })

  it('keeps unrelated streaming blocks even when replayed messages already exist', () => {
    const messages = [
      createAssistantMessage([
        createBlock({
          id: 'plan-artifact',
          uiKind: 'plan_artifact',
          renderKey: 'plan-artifact',
          payload: {
            title: 'Task Plan',
          },
        }),
      ]),
    ]

    const filtered = filterDuplicateHomepageStreamingBlocks(messages, [
      createBlock({
        id: 'md-doc-report',
        uiKind: 'md_document',
        renderKey: 'md-document:report.md',
        payload: {
          filePath: 'report.md',
          title: 'Report Draft',
        },
      }),
    ])

    expect(filtered).toHaveLength(1)
    expect(filtered[0]?.uiKind).toBe('md_document')
  })

  it('filters duplicate plan and markdown cards by render identity', () => {
    const messages = [
      createAssistantMessage([
        createBlock({
          id: 'plan-artifact',
          uiKind: 'plan_artifact',
          renderKey: 'plan-artifact',
          payload: {
            title: 'Task Plan',
          },
        }),
        createBlock({
          id: 'md-doc-report',
          uiKind: 'md_document',
          renderKey: 'md-document:report.md',
          payload: {
            filePath: 'report.md',
            title: 'Report Draft',
          },
        }),
      ]),
    ]

    const filtered = filterDuplicateHomepageStreamingBlocks(messages, [
      createBlock({
        id: 'plan-artifact-stream',
        uiKind: 'plan_artifact',
        renderKey: 'plan-artifact',
        payload: {
          title: 'Task Plan',
        },
      }),
      createBlock({
        id: 'md-doc-report-stream',
        uiKind: 'md_document',
        renderKey: 'md-document:report.md',
        payload: {
          filePath: 'report.md',
          title: 'Report Draft',
        },
      }),
    ])

    expect(filtered).toEqual([])
  })

  it('filters duplicate generation cards by artifact ref even when call and task ids differ', () => {
    const messages = [
      createAssistantMessage([
        createBlock({
          id: 'media-artifact-abc',
          kind: 'content',
          uiKind: 'media_card',
          renderKey: 'media:artifact:artifact_ref:abc',
          payload: {
            callId: 'functions.generate_image:3',
            taskId: 'task-1',
            artifactRef: 'artifact_ref:abc',
            mediaType: 'image_generation',
            status: 'completed',
          },
        }),
      ]),
    ]

    const filtered = filterDuplicateHomepageStreamingBlocks(messages, [
      createBlock({
        id: 'media-call-4',
        kind: 'content',
        uiKind: 'media_card',
        payload: {
          callId: 'functions.generate_image:4',
          taskId: 'task-2',
          artifactRef: 'artifact_ref:abc',
          mediaType: 'image_generation',
          status: 'completed',
        },
      }),
    ])

    expect(filtered).toEqual([])
  })
})

describe('removeRedundantHomepagePlanBlocks', () => {
  it('keeps the structured plan artifact and drops the plan markdown card when both exist', () => {
    const filtered = removeRedundantHomepagePlanBlocks([
      createBlock({
        id: 'plan-artifact',
        uiKind: 'plan_artifact',
        renderKey: 'plan-artifact',
        payload: {
          title: 'Task Plan',
          filePath: 'plan.md',
        },
      }),
      createBlock({
        id: 'md-document:plan.md',
        uiKind: 'md_document',
        renderKey: 'md-document:plan.md',
        payload: {
          title: 'Task Plan',
          filePath: 'plan.md',
        },
      }),
      createBlock({
        id: 'md-document:file_versions/report.md',
        uiKind: 'md_document',
        renderKey: 'md-document:file_versions/report.md',
        payload: {
          title: 'Report Draft',
          filePath: 'file_versions/report.md',
        },
      }),
    ])

    expect(filtered.map((block) => block.id)).toEqual([
      'plan-artifact',
      'md-document:file_versions/report.md',
    ])
  })
})
