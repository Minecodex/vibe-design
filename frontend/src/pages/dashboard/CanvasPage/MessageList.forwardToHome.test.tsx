import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback ?? _key,
    }),
  }
})

vi.mock('@/store/canvasAgentStore', async () => {
  const actual = await vi.importActual('@/store/canvasAgentStore')
  return {
    ...actual,
    useChatStore: Object.assign(
      (selector: (state: any) => any) =>
        selector({
          conversationId: 101,
          uiConfig: { hiddenToolCalls: [] },
          onCanvasUpdate: null,
          respondToAgent: vi.fn(),
          updateToolCall: vi.fn(),
        }),
      {
        getState: () => ({
          conversationId: 101,
          uiConfig: { hiddenToolCalls: [] },
          onCanvasUpdate: null,
          respondToAgent: vi.fn(),
          updateToolCall: vi.fn(),
        }),
      },
    ),
  }
})

vi.mock('@/api/endpoints/generation', () => ({
  generationApi: {
    queryTask: vi.fn(),
  },
}))

vi.mock('./generationPolling', () => ({
  startSerialPolling: vi.fn(() => vi.fn()),
}))

import { MessageList } from './MessageList'

describe('MessageList forward to homepage affordances', () => {
  it('renders a homepage-forward action for assistant text replies and assistant_final_answer blocks', async () => {
    const user = userEvent.setup()
    const handleEnterForwardSelectionMode = vi.fn()

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-text',
            role: 'assistant',
            content: 'Canvas answer',
            createdAt: '2026-04-23T00:00:00Z',
            blocks: [],
          },
          {
            id: 'assistant-card',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-23T00:01:00Z',
            blocks: [
              {
                id: 'final-answer',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'assistant_final_answer',
                payload: { text: 'Structured final answer' },
              },
            ],
          },
          {
            id: 'assistant-media-only',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-23T00:02:00Z',
            blocks: [
              {
                id: 'card',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: { media_type: 'image', result_url: 'https://example.com/generated.png' },
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
        forwardSelectionMode={false}
        selectedForwardMessageIds={new Set<string>()}
        onEnterForwardSelectionMode={handleEnterForwardSelectionMode}
        onToggleForwardMessage={vi.fn()}
      />,
    )

    const forwardButtons = screen.getAllByRole('button', { name: 'Send reply to homepage agent' })
    expect(forwardButtons).toHaveLength(2)
    expect(forwardButtons[0].parentElement).toHaveStyle({ display: 'flex' })
    expect(forwardButtons[1].parentElement).toHaveStyle({ display: 'flex' })

    await user.click(forwardButtons[0])
    expect(handleEnterForwardSelectionMode).toHaveBeenCalledWith('message:assistant-text:content')

    await user.click(forwardButtons[1])
    expect(handleEnterForwardSelectionMode).toHaveBeenCalledWith('message:assistant-card:block:final-answer')
  })

  it('shows a checkbox only for selectable text blocks in forward selection mode', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-text',
            role: 'assistant',
            content: 'Canvas answer',
            createdAt: '2026-04-23T00:00:00Z',
            blocks: [],
          },
          {
            id: 'assistant-mixed',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-23T00:01:00Z',
            blocks: [
              {
                id: 'text-card',
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'assistant_text',
                payload: { text: 'Selectable text block' },
              },
              {
                id: 'card',
                kind: 'content',
                order: 1,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: { media_type: 'image', result_url: 'https://example.com/generated.png' },
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
        forwardSelectionMode
        selectedForwardMessageIds={new Set(['message:assistant-text:content', 'message:assistant-mixed:block:text-card'])}
        onEnterForwardSelectionMode={vi.fn()}
        onToggleForwardMessage={vi.fn()}
      />,
    )

    expect(screen.getAllByRole('checkbox', { name: 'Select reply to forward' })).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Send reply to homepage agent' })).not.toBeInTheDocument()
  })
})
