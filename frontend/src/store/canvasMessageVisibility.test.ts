import { describe, expect, it } from 'vitest'

import { hasRenderableChatMessage, hasRenderableMessageBlock } from './canvasMessageVisibility'
import type { ChatMessage, MessageBlock } from './canvasAgentTypes'

function progressBlock(overrides: Partial<MessageBlock> = {}): MessageBlock {
  return {
    id: 'progress-1',
    kind: 'content',
    order: 0,
    status: 'completed',
    visible: true,
    uiKind: 'progress_update',
    payload: {},
    ...overrides,
  } as MessageBlock
}

describe('canvasMessageVisibility - progress blocks', () => {
  it('treats a text-less progress block as not renderable even when it carries a tool identity', () => {
    expect(hasRenderableMessageBlock(progressBlock({ payload: { tool_name: 'do_thing', call_id: 'c1' } }))).toBe(false)
  })

  it('keeps a progress block that actually has text', () => {
    expect(hasRenderableMessageBlock(progressBlock({ payload: { text: '正在处理…' } }))).toBe(true)
  })

  it('drops a message whose only block is an empty progress update (no blank bubble)', () => {
    const message: ChatMessage = {
      id: 'm1',
      role: 'assistant',
      content: null,
      createdAt: '2026-06-18T00:00:00Z',
      blocks: [progressBlock({ payload: { tool_name: 'do_thing' } })],
    }
    expect(hasRenderableChatMessage(message)).toBe(false)
  })

  it('still renders a message that pairs real text with an empty progress block', () => {
    const message: ChatMessage = {
      id: 'm2',
      role: 'assistant',
      content: null,
      createdAt: '2026-06-18T00:00:00Z',
      blocks: [
        { id: 'text-1', kind: 'text', order: 0, status: 'completed', visible: true, uiKind: 'assistant_text', payload: { text: '你好' } } as MessageBlock,
        progressBlock({ payload: {} }),
      ],
    }
    expect(hasRenderableChatMessage(message)).toBe(true)
  })
})
