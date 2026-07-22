import { describe, expect, it } from 'vitest'

import { appendStreamingBlocksAsAssistantMessage } from './canvasAgentStreamBatching'
import type { ChatMessage, MessageBlock } from './canvasAgentTypes'

function textBlock(id: string, text: string): MessageBlock {
  return {
    id,
    kind: 'text',
    order: 0,
    status: 'completed',
    visible: true,
    uiKind: 'text',
    payload: { text },
  }
}

describe('appendStreamingBlocksAsAssistantMessage', () => {
  it('does not append an assistant message for empty streaming text blocks', () => {
    const messages: ChatMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: '开始',
        createdAt: '2026-06-17T08:48:00Z',
      },
    ]

    const next = appendStreamingBlocksAsAssistantMessage(
      messages,
      [textBlock('empty-stream-text', '')],
      '2026-06-17T08:48:35Z',
    )

    expect(next).toBe(messages)
  })

  it('keeps non-empty streaming text blocks when finalizing', () => {
    const messages: ChatMessage[] = []

    const next = appendStreamingBlocksAsAssistantMessage(
      messages,
      [textBlock('visible-stream-text', '已完成')],
      '2026-06-17T08:48:35Z',
    )

    expect(next).toHaveLength(1)
    expect(next[0]?.content).toBe('已完成')
    expect(next[0]?.blocks?.[0]?.id).toBe('visible-stream-text')
  })
})
