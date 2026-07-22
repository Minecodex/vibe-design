import { describe, expect, it } from 'vitest'

import { buildForwardSelectionText, getForwardSelectableMessageText, isForwardSelectableMessage } from './chatForwardSelection'

describe('chatForwardSelection', () => {
  it('treats assistant message content as selectable text', () => {
    expect(getForwardSelectableMessageText({
      role: 'assistant',
      content: 'Summary from canvas agent',
      blocks: [],
    } as any)).toBe('Summary from canvas agent')
  })

  it('falls back to assistant text blocks when content is empty', () => {
    expect(getForwardSelectableMessageText({
      role: 'assistant',
      content: null,
      blocks: [
        {
          id: 'b1',
          kind: 'text',
          order: 0,
          status: 'completed',
          visible: true,
          uiKind: 'assistant_text',
          payload: { text: 'Block answer' },
        },
      ],
    } as any)).toBe('Block answer')
  })

  it('treats visible interaction and plan text blocks as selectable text', () => {
    expect(getForwardSelectableMessageText({
      role: 'assistant',
      content: null,
      blocks: [
        {
          id: 'choice',
          kind: 'interaction',
          order: 0,
          status: 'completed',
          visible: true,
          uiKind: 'choice_prompt',
          payload: {
            question: '请选择执行模式',
            options: [{ label: '模式A', value: 'a' }, { label: '模式B', value: 'b' }],
          },
        },
      ],
    } as any)).toBe('请选择执行模式\n模式A / 模式B')
  })

  it('ignores user messages and non-text assistant cards', () => {
    expect(isForwardSelectableMessage({
      role: 'user',
      content: 'User question',
      blocks: [],
    } as any)).toBe(false)

    expect(isForwardSelectableMessage({
      role: 'assistant',
      content: null,
      blocks: [
        {
          id: 'card',
          kind: 'content',
          order: 0,
          status: 'completed',
          visible: true,
          uiKind: 'media_card',
          payload: { text: 'Image card' },
        },
      ],
    } as any)).toBe(false)
  })

  it('builds ordered text from selected assistant replies only', () => {
    expect(buildForwardSelectionText([
      { id: 'a1', role: 'assistant', content: 'First reply', blocks: [] },
      { id: 'u1', role: 'user', content: 'Question', blocks: [] },
      { id: 'a2', role: 'assistant', content: null, blocks: [{ id: 'b2', kind: 'text', order: 0, status: 'completed', visible: true, uiKind: 'assistant_text', payload: { text: 'Second reply' } }] },
    ] as any, new Set(['message:a1:content', 'message:a2:block:b2']))).toBe('First reply\n\nSecond reply')
  })
})
