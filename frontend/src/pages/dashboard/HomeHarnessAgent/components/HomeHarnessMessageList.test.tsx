import type { WorkspaceFileRead } from '@/api/endpoints/agent'
import { createTranslationFixture } from '@/store/testing/translationFixture'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage, MessageBlock } from '@/store/homeHarnessStore'
import type { ReactNode } from 'react'

vi.mock('react-virtuoso', async () => {
  const React = await import('react')
  return {
    Virtuoso: ({
      data = [],
      initialTopMostItemIndex,
      itemContent,
    }: {
      data?: unknown[]
      initialTopMostItemIndex?: number | { index?: number; align?: string }
      itemContent?: (index: number) => ReactNode
    }) => {
      const initialIndex = typeof initialTopMostItemIndex === 'number'
        ? initialTopMostItemIndex
        : initialTopMostItemIndex?.index
      const initialAlign = typeof initialTopMostItemIndex === 'number'
        ? ''
        : initialTopMostItemIndex?.align
      return React.createElement(
        'div',
        {
          'data-testid': 'home-virtuoso',
          'data-initial-top-most-item-index': String(initialIndex ?? ''),
          'data-initial-align': String(initialAlign ?? ''),
        },
        data.map((_, index) => React.createElement(
          'div',
          { key: index },
          itemContent?.(index),
        )),
      )
    },
  }
})

vi.mock('@/api/endpoints/referenceGallery', () => ({
  referenceGalleryApi: {
    listCategories: vi.fn().mockResolvedValue({
      data: [{
        id: 1,
        kind: 'category',
        name: '夹克',
        prompt: '夹克分类提示词',
        image_count: 1,
        created_at: '',
        updated_at: '',
      }],
    }),
    listStyles: vi.fn().mockResolvedValue({
      data: [{
        id: 2,
        kind: 'style',
        name: '都市通勤',
        prompt: '都市通勤风格提示词',
        image_count: 1,
        created_at: '',
        updated_at: '',
      }],
    }),
  },
}))

import { HomeHarnessMessageList } from '../index'

const t = createTranslationFixture({ 'subagent.purposeLabels.qualityReview': '质量评审' })

const reportFile = {
  file_id: 'file-report',
  name: 'report.docx',
  path: 'references/sources/report.docx',
  type: 'document',
  size: 128,
  created_at: '2026-06-01T00:00:00.000Z',
  updated_at: null,
  current_version_id: '',
  versions: [],
  source: 'reference_asset',
} satisfies WorkspaceFileRead

beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  Object.defineProperty(window.HTMLElement.prototype, 'hasPointerCapture', {
    configurable: true,
    value: vi.fn(() => false),
  })
  Object.defineProperty(window.HTMLElement.prototype, 'setPointerCapture', {
    configurable: true,
    value: vi.fn(),
  })
  Object.defineProperty(window.HTMLElement.prototype, 'releasePointerCapture', {
    configurable: true,
    value: vi.fn(),
  })
})

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

function createAssistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'assistant-message',
    role: 'assistant',
    content: 'Main answer',
    blocks: [],
    createdAt: '2026-04-20T00:00:00.000Z',
    ...overrides,
  }
}

describe('HomeHarnessMessageList', () => {
  it('positions virtualized long history at the latest group', () => {
    const scrollParent = document.createElement('div')
    const messages = Array.from({ length: 52 }, (_, index) => ({
      id: `message-${index}`,
      role: index % 2 === 0 ? 'user' : 'assistant',
      content: `Message ${index}`,
      blocks: [],
      createdAt: '2026-04-20T00:00:00.000Z',
    })) as ChatMessage[]

    render(
      <HomeHarnessMessageList
        messages={messages}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        scrollParent={scrollParent}
        conversationId="conv-long"
      />,
    )

    expect(screen.getByTestId('home-virtuoso')).toHaveAttribute(
      'data-initial-top-most-item-index',
      '51',
    )
    expect(screen.getByTestId('home-virtuoso')).toHaveAttribute('data-initial-align', 'end')
  })

  it('renders Design Jury cards from persisted message blocks', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'critique-card',
                uiKind: 'design_jury_card',
                payload: {
                  critique_run_id: 'critique-1',
                  status: 'shipped',
                  round: 1,
                  max_rounds: 3,
                  score_threshold: 8,
                  score_scale: 10,
                  composite: 8.6,
                  scores: { critic: 8.6, brand: 8.4 },
                  dimensions: [
                    { role: 'critic', name: 'visual-quality', score: 8.6, note: 'Strong hierarchy.' },
                  ],
                  findings: [{ role: 'critic', text: 'Strong hierarchy.' }],
                  warnings: [],
                  selected_round: 1,
                  selected_score: 8.6,
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByTestId('home-harness-critique-panel')).toBeInTheDocument()
    expect(screen.getByText('Design Jury')).toBeInTheDocument()
    expect(screen.getAllByText('8.6 / 10').length).toBeGreaterThan(0)
    expect(screen.getByText(/Strong hierarchy\./)).toBeInTheDocument()
  })

  it('renders QualityReview Design Jury child cards without exposing raw JSON summaries', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'subagent-quality-review',
                kind: 'tool',
                uiKind: 'subagent_card',
                taskId: 'quality-review-1',
                expanded: true,
                summary: '{"review_id":"critique-1","critic":{"score":8.6}}',
                payload: {
                  taskId: 'quality-review-1',
                  label: 'Quality review',
                  status: 'completed',
                  subagentType: 'QualityReview',
                },
                children: [
                  createBlock({
                    id: 'subagent-quality-review-design-jury',
                    uiKind: 'design_jury_card',
                    payload: {
                      critique_run_id: 'critique-1',
                      status: 'shipped',
                      round: 1,
                      max_rounds: 3,
                      score_threshold: 8,
                      score_scale: 10,
                      composite: 8.6,
                      scores: { critic: 8.6 },
                      dimensions: [],
                      findings: [],
                      warnings: [],
                      selected_round: 1,
                      selected_score: 8.6,
                    },
                  }),
                ],
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByTestId('home-harness-critique-panel')).toBeInTheDocument()
    expect(screen.getByText('Design Jury')).toBeInTheDocument()
    expect(screen.getByText('质量评审')).toBeInTheDocument()
    expect(screen.queryByText('Quality review')).not.toBeInTheDocument()
    expect(screen.queryByText(/review_id/)).not.toBeInTheDocument()
  })

  it('renders nested subagent image analysis children as analysis cards instead of raw containers', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'subagent-quality-review',
                kind: 'tool',
                uiKind: 'subagent_card',
                taskId: 'quality-review-1',
                expanded: true,
                payload: {
                  taskId: 'quality-review-1',
                  label: 'Quality review',
                  status: 'running',
                  subagentType: 'QualityReview',
                },
                children: [
                  createBlock({
                    id: 'media-call-image-1',
                    uiKind: 'content',
                    status: 'running',
                    payload: { status: 'running' },
                    children: [
                      createBlock({
                        id: 'analyze-image-text-call-image-1',
                        kind: 'text',
                        uiKind: 'text',
                        status: 'completed',
                        payload: {
                          toolName: 'analyze_image',
                          tool_name: 'analyze_image',
                          text: 'Desktop screenshot analysis',
                        },
                      }),
                    ],
                  }),
                ],
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText(/Analyze Image/)).toBeInTheDocument()
    expect(screen.queryByText('Desktop screenshot analysis')).not.toBeInTheDocument()
  })

  it('renders Claude-Code-style tool rows with action label and argument summary', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'tool-call-shell',
                uiKind: 'tool_result',
                status: 'completed',
                payload: {
                  tool: 'exec_command',
                  call_id: 'call-shell',
                  status: 'completed',
                  args: { command: 'pytest -q' },
                  output: 'all tests passed',
                  elapsed_ms: 1200,
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('执行命令')).toBeInTheDocument()
    expect(screen.getByText('pytest -q')).toBeInTheDocument()
    expect(screen.getByText('1.2s')).toBeInTheDocument()
    expect(screen.queryByText('exec_command / exec_command')).not.toBeInTheDocument()
  })

  it('forwards generated image reuse actions from message blocks', async () => {
    const user = userEvent.setup()
    const onUseGeneratedAsReference = vi.fn()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            blocks: [
              createBlock({
                id: 'generated-image-card',
                uiKind: 'generation_card',
                payload: {
                  taskId: 42,
                  status: 'completed',
                  mediaType: 'image',
                  toolName: 'generate_image',
                  resultUrl: 'references/generated/generated_image_042/original.png',
                  prompt: 'A clean product frame',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        onUseGeneratedAsReference={onUseGeneratedAsReference}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Toggle generation 42' }))
    await user.click(screen.getByRole('button', { name: 'Use as reference' }))

    expect(onUseGeneratedAsReference).toHaveBeenCalledWith({
      type: 'image',
      url: 'references/generated/generated_image_042/original.png',
      name: 'original.png',
    })
  })

  it.skip('keeps subagent content stable while hiding image analysis utility cards in both running and refreshed views', () => {
    const runtimeBlocks = [
      createBlock({
        id: 'assistant-stream',
        kind: 'text',
        uiKind: 'assistant_text',
        payload: { text: 'Main answer' },
      }),
      createBlock({
        id: 'subagent-card',
        uiKind: 'subagent_card',
        label: 'Research QA',
        payload: { label: 'Research QA' },
        children: [
          createBlock({
            id: 'subagent-child',
            kind: 'text',
            uiKind: 'assistant_text',
            payload: { text: 'Subagent detail' },
          }),
        ],
      }),
      createBlock({
        id: 'image-analysis-stream',
        uiKind: 'stream_panel',
        payload: {
          toolName: 'analyze_image',
          streamText: 'Chart goes up',
        },
      }),
    ]

    const refreshedMessages = [
      createAssistantMessage({
        blocks: [
          createBlock({
            id: 'subagent-card',
            uiKind: 'subagent_card',
            label: 'Research QA',
            payload: { label: 'Research QA' },
            children: [
              createBlock({
                id: 'subagent-child',
                kind: 'text',
                uiKind: 'assistant_text',
                payload: { text: 'Subagent detail' },
              }),
            ],
          }),
          createBlock({
            id: 'image-analysis-final',
            uiKind: 'media_card',
            payload: {
              mediaType: 'image_analysis',
              text: 'Chart goes up',
            },
          }),
        ],
      }),
    ]

    const { rerender } = render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={runtimeBlocks}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('Main answer')).toBeInTheDocument()
    expect(screen.getByText('Research QA')).toBeInTheDocument()
    expect(screen.getByText('Subagent detail')).toBeInTheDocument()
    expect(screen.getByText('图片分析 / Analyze Image')).toBeInTheDocument()

    rerender(
      <HomeHarnessMessageList
        messages={refreshedMessages}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('Main answer')).toBeInTheDocument()
    expect(screen.getByText('Research QA')).toBeInTheDocument()
    expect(screen.getByText('Subagent detail')).toBeInTheDocument()
    expect(screen.getByText('图片分析 / Analyze Image')).toBeInTheDocument()
  })

  it('renders an image analysis card while the analysis text block is still streaming', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[
          createBlock({
            id: 'analyze-image-text-functions.analyze_image:0',
            kind: 'text',
            uiKind: 'text',
            status: 'running',
            payload: {
              toolName: 'analyze_image',
              callId: 'functions.analyze_image:0',
              text: 'Detected a coffee cup on a wooden table.',
            },
          }),
        ]}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('图片分析 / Analyze Image')).toBeInTheDocument()
    expect(screen.queryByText('Detected a coffee cup on a wooden table.')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Toggle analysis tool output' }))

    expect(screen.getByText('Detected a coffee cup on a wooden table.')).toBeInTheDocument()
  })

  it('shows one image analysis card and keeps the streaming text when the media card and text stream coexist', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[
          createBlock({
            id: 'media-functions.analyze_image:0',
            kind: 'content',
            uiKind: 'media_card',
            status: 'running',
            payload: {
              mediaType: 'image_analysis',
              text: '',
            },
          }),
          createBlock({
            id: 'analyze-image-text-functions.analyze_image:0',
            kind: 'text',
            uiKind: 'text',
            status: 'running',
            payload: {
              toolName: 'analyze_image',
              callId: 'functions.analyze_image:0',
              text: 'Streaming image analysis output',
            },
          }),
        ]}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByText(/Analyze Image/)).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Toggle analysis tool output' }))

    expect(screen.getByText('Streaming image analysis output')).toBeInTheDocument()
  })

  it('does not repeat image analysis text above the card when the persisted message only has the card block', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: 'Detected a coffee cup on a wooden table.',
            blocks: [
              createBlock({
                id: 'image-analysis-final',
                kind: 'content',
                order: 0,
                uiKind: 'media_card',
                payload: {
                  mediaType: 'image_analysis',
                  text: 'Detected a coffee cup on a wooden table.',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('图片分析 / Analyze Image')).toBeInTheDocument()
    expect(screen.queryByText('Detected a coffee cup on a wooden table.')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Toggle analysis tool output' }))

    expect(screen.getByText('Detected a coffee cup on a wooden table.')).toBeInTheDocument()
  })

  it('renders homepage assistant blocks in persisted order when a media card precedes assistant text', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: '## 图片分析结果\n\n这是总结正文。',
            blocks: [
              createBlock({
                id: 'image-analysis-final',
                kind: 'content',
                order: 0,
                uiKind: 'media_card',
                payload: {
                  mediaType: 'image_analysis',
                  text: 'Card summary',
                },
              }),
              createBlock({
                id: 'assistant-text-final',
                kind: 'content',
                order: 1,
                uiKind: 'assistant_text',
                payload: {
                  text: '## 图片分析结果\n\n这是总结正文。',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    const cardLabel = screen.getByText('图片分析 / Analyze Image')
    const summaryHeading = screen.getByText('图片分析结果')

    expect(
      cardLabel.compareDocumentPosition(summaryHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('groups consecutive assistant messages into one visual assistant reply section', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-intro',
            content: '我来分析这张图片。',
            blocks: [
              createBlock({
                id: 'assistant-intro-text',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_text',
                payload: { text: '我来分析这张图片。' },
              }),
            ],
          }),
          createAssistantMessage({
            id: 'assistant-card',
            content: '',
            blocks: [
              createBlock({
                id: 'image-analysis-final',
                kind: 'content',
                order: 0,
                uiKind: 'media_card',
                payload: {
                  mediaType: 'image_analysis',
                  text: '这是一张极简风格的静物摄影照片。',
                },
              }),
            ],
          }),
          createAssistantMessage({
            id: 'assistant-summary',
            content: '根据图片分析，这是一个绿色装饰物。',
            blocks: [
              createBlock({
                id: 'assistant-summary-text',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_text',
                payload: { text: '根据图片分析，这是一个绿色装饰物。' },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByTestId('home-harness-assistant-message')).toHaveLength(1)
    expect(screen.getByText('我来分析这张图片。')).toBeInTheDocument()
    expect(screen.getByText('图片分析 / Analyze Image')).toBeInTheDocument()
    expect(screen.getByText('根据图片分析，这是一个绿色装饰物。')).toBeInTheDocument()
  })

  it('does not render internal tool json messages as visible chat bubbles', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          {
            id: 'tool-message',
            role: 'tool',
            content: '{"status":"success","summary":"internal tool payload"}',
            createdAt: '2026-04-20T00:00:00.000Z',
          } as ChatMessage,
          createAssistantMessage({
            id: 'assistant-summary',
            content: '这是用户可见的最终回复。',
            blocks: [
              createBlock({
                id: 'assistant-summary-text',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_text',
                payload: { text: '这是用户可见的最终回复。' },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.queryByText('{"status":"success","summary":"internal tool payload"}')).not.toBeInTheDocument()
    expect(screen.getByText('这是用户可见的最终回复。')).toBeInTheDocument()
    expect(screen.getAllByTestId('home-harness-assistant-message')).toHaveLength(1)
  })


  it('does not render duplicate image analysis cards when a tool result stream panel appears', () => {
    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[
          createBlock({
            id: 'media-functions.analyze_image:0',
            kind: 'content',
            uiKind: 'media_card',
            status: 'completed',
            payload: {
              mediaType: 'image_analysis',
              text: 'Final analysis summary',
            },
          }),
          createBlock({
            id: 'tool-functions.analyze_image:0',
            kind: 'tool',
            uiKind: 'stream_panel',
            status: 'completed',
            payload: {
              toolName: 'analyze_image',
              callId: 'functions.analyze_image:0',
              streamText: 'Final analysis summary',
              elapsedMs: 36800,
            },
          }),
        ]}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByText(/Analyze Image/)).toHaveLength(1)
  })

  it('does not render duplicate generation cards when a media card and generation task share the same output', () => {
    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[
          createBlock({
            id: 'media-functions.generate_image:1',
            kind: 'content',
            uiKind: 'media_card',
            status: 'completed',
            payload: {
              mediaType: 'image_generation',
              text: 'Image generated',
              taskId: 'task-1',
              resultUrl: 'generated/image.png',
              modelLabel: 'NanoBanana2',
            },
          }),
          createBlock({
            id: 'tool-functions.generate_image:1',
            kind: 'tool',
            uiKind: 'generation_task',
            status: 'completed',
            payload: {
              toolName: 'generate_image',
              callId: 'functions.generate_image:1',
              taskId: 'task-1',
              resultUrl: 'generated/image.png',
              modelLabel: 'NanoBanana2',
            },
          }),
        ]}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByRole('button', { name: /Toggle generation/i })).toHaveLength(1)
  })

  it('does not render duplicate generation cards after refresh when replayed blocks include both sources', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'media-functions.generate_image:1',
                kind: 'content',
                uiKind: 'media_card',
                status: 'completed',
                payload: {
                  mediaType: 'image_generation',
                  text: 'Image generated',
                  taskId: 'task-1',
                  resultUrl: 'generated/image.png',
                  modelLabel: 'NanoBanana2',
                },
              }),
              createBlock({
                id: 'tool-functions.generate_image:1',
                kind: 'tool',
                uiKind: 'generation_task',
                status: 'completed',
                payload: {
                  toolName: 'generate_image',
                  callId: 'functions.generate_image:1',
                  taskId: 'task-1',
                  resultUrl: 'generated/image.png',
                  modelLabel: 'NanoBanana2',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByRole('button', { name: /Toggle generation/i })).toHaveLength(1)
  })

  it('does not keep showing a running plan after a completed plan replay', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'completed-plan',
                uiKind: 'plan_artifact',
                status: 'completed',
                payload: {
                  title: 'Task Plan',
                  status: 'completed',
                  summary: 'Everything is done',
                  steps: [
                    { id: 'step-1', order: 1, title: 'Collect evidence', status: 'completed' },
                  ],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByText('Completed').length).toBeGreaterThan(0)
    expect(screen.queryByText('In progress')).not.toBeInTheDocument()
    expect(screen.queryByTestId('home-harness-thinking')).not.toBeInTheDocument()
  })

  it('shows the thinking placeholder while the transport is streaming before run status catches up', () => {
    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[]}
        isStreaming
        runStatus="idle"
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByTestId('home-harness-thinking')).toBeInTheDocument()
    expect(screen.getByText('Thinking...')).toBeInTheDocument()
  })

  it('renders active-step activity time and completed-step elapsed time inline with the plan status', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'timed-plan',
                uiKind: 'plan_artifact',
                status: 'in_progress',
                payload: {
                  title: 'Task Plan',
                  status: 'in_progress',
                  current_step: 'step-2',
                  steps: [
                    {
                      id: 'step-1',
                      order: 1,
                      title: 'Collect evidence',
                      status: 'completed',
                      elapsed_ms: 125000,
                    },
                    {
                      id: 'step-2',
                      order: 2,
                      title: 'Draft response',
                      status: 'in_progress',
                      last_activity_at: '2026-04-27T10:32:18+08:00',
                    },
                  ],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        conversationLastActivityAt="2026-04-27T10:32:18+08:00"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('耗时 2分5秒')).toBeInTheDocument()
    expect(screen.getByText('10:32:18')).toBeInTheDocument()
  })

  it('renders planning draft cards with their draft outline instead of the generic plan card', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'planning-draft-card',
                uiKind: 'planning_draft_card',
                status: 'draft',
                payload: {
                  summary: '先收拢需求再请求批准。',
                  confirmedInputs: { audience: '潜在客户' },
                  assumptions: ['使用占位联系表单。'],
                  draftOutline: [
                    { id: 'section-1', title: 'Hero', summary: '价值主张。' },
                    { id: 'section-2', title: 'Contact', summary: '联系转化。' },
                  ],
                  openQuestions: ['是否已有品牌色？'],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('Planning draft')).toBeInTheDocument()
    expect(screen.getByText('Draft outline')).toBeInTheDocument()
    expect(screen.getByText('Hero')).toBeInTheDocument()
    expect(screen.getByText('Contact')).toBeInTheDocument()
    expect(screen.getByText('是否已有品牌色？')).toBeInTheDocument()
    expect(screen.queryByText('Task Plan')).not.toBeInTheDocument()
  })

  it('renders user-facing plan and progress cards with artifact navigation', async () => {
    const onOpenWorkspaceRelativeFile = vi.fn()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'user-plan-card',
                uiKind: 'user_plan_card',
                status: 'in_progress',
                payload: {
                  artifactType: 'ppt',
                  title: '融资路演 PPT',
                  summary: '8 页路演框架',
                  status: 'in_progress',
                  filePath: 'outputs/demo.pptx',
                  fileName: 'demo.pptx',
                  outline: [
                    { id: 'slide-1', title: '封面', summary: '项目名称与一句话定位' },
                    { id: 'slide-2', title: '问题', summary: '用户痛点与机会' },
                  ],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        outlineRuntime={null}
        userProgress={{
          status: 'in_progress',
          message: '正在补充解决方案页',
          completed_message: '已完成封面与问题页',
        }}
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={onOpenWorkspaceRelativeFile}
      />,
    )

    expect(screen.getByText('融资路演 PPT')).toBeInTheDocument()
    expect(screen.getByText('8 页路演框架')).toBeInTheDocument()
    expect(screen.getByText('封面')).toBeInTheDocument()
    expect(screen.getByText('问题')).toBeInTheDocument()
    expect(screen.getByText('正在补充解决方案页')).toBeInTheDocument()
    expect(screen.getByText('已完成封面与问题页')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open plan' })).not.toBeInTheDocument()
  })

  it('supports inline manual editing and disables AI revise plus execution while editing', async () => {
    const user = userEvent.setup()
    const onPatchCurrentOutline = vi.fn(async () => {})
    const onRevisePlan = vi.fn(async () => {})
    const onStartExecution = vi.fn(async () => {})

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'user-plan-card',
                uiKind: 'user_plan_card',
                status: 'in_progress',
                payload: {
                  artifactType: 'ppt',
                  title: '设计行业洞察',
                  summary: '四页演示文稿',
                  status: 'planning_ready',
                  outline: [
                    { id: 'slide-1', title: '封面', summary: '主题与一句话定位' },
                    { id: 'slide-2', title: '行业概述', summary: '市场规模与细分领域' },
                  ],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        conversationPhase="planning_ready"
        outlineRuntime={{
          current_outline: {
            artifact_type: 'ppt',
            title: '设计行业洞察',
            summary: '四页演示文稿',
            status: 'planning_ready',
            items: [
              { id: 'slide-1', title: '封面', summary: '主题与一句话定位', order: 1 },
              { id: 'slide-2', title: '行业概述', summary: '市场规模与细分领域', order: 2 },
            ],
            constraints: [],
            style_notes: [],
          },
          last_revision: null,
        }}
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        onStartExecution={onStartExecution}
        onRevisePlan={onRevisePlan}
        onPatchCurrentOutline={onPatchCurrentOutline}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    await user.hover(screen.getByText('封面'))
    expect(screen.queryByText('Pending')).not.toBeInTheDocument()
    expect(screen.queryByText('待处理')).not.toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Edit item' })[0])

    expect(screen.getByRole('button', { name: 'Adjust outline' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Start execution' })).toBeDisabled()

    const titleInput = screen.getByPlaceholderText('Outline title')
    await user.clear(titleInput)
    await user.type(titleInput, '新封面')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(onPatchCurrentOutline).toHaveBeenCalledTimes(1)
    expect(onRevisePlan).not.toHaveBeenCalled()
    expect(onStartExecution).not.toHaveBeenCalled()
  })

  it('opens inline AI revise input and hides manual edit actions while revising', async () => {
    const user = userEvent.setup()
    const onRevisePlan = vi.fn(async () => {})

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'user-plan-card',
                uiKind: 'user_plan_card',
                status: 'in_progress',
                payload: {
                  artifactType: 'ppt',
                  title: '设计行业洞察',
                  summary: '四页演示文稿',
                  status: 'planning_ready',
                  outline: [
                    { id: 'slide-1', title: '封面', summary: '主题与一句话定位' },
                  ],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        conversationPhase="planning_ready"
        outlineRuntime={{
          current_outline: {
            artifact_type: 'ppt',
            title: '设计行业洞察',
            summary: '四页演示文稿',
            status: 'planning_ready',
            items: [
              { id: 'slide-1', title: '封面', summary: '主题与一句话定位', order: 1 },
            ],
            constraints: [],
            style_notes: [],
          },
          last_revision: null,
        }}
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        onStartExecution={vi.fn(async () => {})}
        onRevisePlan={onRevisePlan}
        onPatchCurrentOutline={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Adjust outline' }))
    expect(screen.getByPlaceholderText('Describe how you want the outline to change...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Adjust outline' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Start execution' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Edit item' })).not.toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('Describe how you want the outline to change...'), '把第 2 页改成案例分析')
    await user.click(screen.getByRole('button', { name: 'Apply revision request' }))

    expect(onRevisePlan).toHaveBeenCalledWith('把第 2 页改成案例分析')
  })

  it('does not render a duplicate image analysis card when replayed blocks already contain the same call while streaming is still active', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'media-call_7d792be9c4ae4cad9f7cee67',
                kind: 'content',
                uiKind: 'media_card',
                status: 'completed',
                payload: {
                  callId: 'call_7d792be9c4ae4cad9f7cee67',
                  mediaType: 'image_analysis',
                  title: '图片分析',
                  text: 'Final image analysis',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[
          createBlock({
            id: 'media-call_7d792be9c4ae4cad9f7cee67',
            kind: 'content',
            uiKind: 'media_card',
            status: 'completed',
            payload: {
              callId: 'call_7d792be9c4ae4cad9f7cee67',
              mediaType: 'image_analysis',
              title: '图片分析',
              text: 'Final image analysis',
            },
          }),
          createBlock({
            id: 'analyze-image-text-call_7d792be9c4ae4cad9f7cee67',
            kind: 'text',
            uiKind: 'text',
            status: 'completed',
            payload: {
              toolName: 'analyze_image',
              callId: 'call_7d792be9c4ae4cad9f7cee67',
              text: 'Final image analysis',
            },
          }),
        ]}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getAllByText(/Analyze Image/)).toHaveLength(1)
  })


  it('renders quick brief interaction forms and submits structured answers', async () => {
    const user = userEvent.setup()
    const respondToAgent = vi.fn(async () => {})

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'interaction-form-1',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'pending',
                payload: {
                  requestId: 'req-brief-1',
                  request_id: 'req-brief-1',
                  kind: 'quick_brief',
                  status: 'pending',
                  schema: {
                    title: 'Quick brief',
                    description: 'Lock the core constraints.',
                    submit_label: 'Continue',
                    fields: [
                      { id: 'output', label: 'What should we make', type: 'text', required: true },
                      { id: 'audience', label: 'Audience', type: 'text', required: true },
                    ],
                  },
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={respondToAgent}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    await user.type(screen.getByLabelText('What should we make'), 'Landing page')
    await user.type(screen.getByLabelText('Audience'), 'Founders')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(respondToAgent).toHaveBeenCalledWith(
      'req-brief-1',
      JSON.stringify({ output: 'Landing page', audience: 'Founders' }),
      'Landing page / Founders',
      undefined,
      { output: 'Landing page', audience: 'Founders' },
    )
  })

  it('renders localized subagent card terminal states and diagnostic fields', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'subagent-failed',
                kind: 'tool',
                uiKind: 'subagent_card',
                status: 'failed',
                taskId: 'task-failed',
                label: 'Artifact worker',
                summary: 'Child failed.',
                payload: {
                  taskId: 'task-failed',
                  label: 'Artifact worker',
                  purpose: 'Prepare artifact',
                  status: 'failed',
                  reasonCode: 'child_failed',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark
        t={t}
        language="zh-CN"
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('子代理')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('Prepare artifact')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /子代理/i }))

    expect(screen.getByText('Child failed.')).toBeInTheDocument()
    expect(screen.getByText('child_failed')).toBeInTheDocument()
  })

  it('renders interaction briefing from parent assistant content when block payload has no content or question', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: '### Gate A：品牌战略简报\n\n- 两岸人文融合\n- 青岛商务办公',
            blocks: [
              createBlock({
                id: 'interaction-form-parent-content',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'pending',
                payload: {
                  requestId: 'req-parent-content',
                  request_id: 'req-parent-content',
                  kind: 'quick_brief',
                  status: 'pending',
                  schema: {
                    title: 'Gate A：品牌战略简报确认',
                    submit_label: '确认并继续',
                    fields: [
                      { id: 'approval', label: '是否继续', type: 'radio', required: true, options: [{ label: '继续', value: 'continue' }] },
                    ],
                  },
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸人文融合')).toBeInTheDocument()
  })

  it('renders legacy status history panels collapsed and keeps assistant progress visible', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'legacy-status-history',
                uiKind: 'status_history_panel',
                payload: {
                  status_history: [
                    { id: 'status-1', text: '正在处理', status: 'completed' },
                  ],
                },
              }),
              createBlock({
                id: 'assistant-progress',
                kind: 'text',
                uiKind: 'assistant_text',
                payload: { text: '我先处理一下。' },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    const statusHistoryButton = screen.getByRole('button', { name: '状态历史' })
    expect(statusHistoryButton).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('正在处理')).not.toBeInTheDocument()
    expect(screen.getByText('我先处理一下。')).toBeInTheDocument()

    await user.click(statusHistoryButton)

    expect(statusHistoryButton).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('正在处理')).toBeInTheDocument()
  })

  it('renders assistant final answers with a collapsed status history section that can expand', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-final-answer',
            content: '您的 PPT 已完成制作并发布！',
            blocks: [
              createBlock({
                id: 'assistant-final-answer-block',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_final_answer',
                payload: {
                  text: '您的 PPT 已完成制作并发布！',
                  statusHistory: [
                    {
                      id: 'status-1',
                      text: '正在生成 4 页 PPT',
                      createdAt: '2026-05-07T02:34:36.000Z',
                      status: 'completed',
                    },
                  ],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('您的 PPT 已完成制作并发布！')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '状态历史' })).toBeInTheDocument()
    expect(screen.queryByText('正在生成 4 页 PPT')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '状态历史' }))

    expect(screen.getByText('正在生成 4 页 PPT')).toBeInTheDocument()
  })

  it('renders workspace file references only in assistant final answers', async () => {
    const user = userEvent.setup()
    const onPreviewWorkspaceFile = vi.fn()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-final-answer',
            content: '本地预览: references/sources/report.docx',
            blocks: [
              createBlock({
                id: 'assistant-final-answer-block',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_final_answer',
                payload: {
                  text: '本地预览: references/sources/report.docx',
                  statusHistory: [],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        sessionFiles={[reportFile]}
        onPreviewWorkspaceFile={onPreviewWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file report.docx' }))

    expect(onPreviewWorkspaceFile).toHaveBeenCalledWith(reportFile)
  })

  it('renders workspace file references in persisted assistant content fallback after refresh', async () => {
    const user = userEvent.setup()
    const onPreviewWorkspaceFile = vi.fn()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-replayed-with-card',
            content: '本地图片：`references/sources/report.docx`',
            blocks: [
              createBlock({
                id: 'web-search-card',
                kind: 'content',
                order: 0,
                uiKind: 'web_search_card',
                payload: {
                  query: 'test',
                  status: 'completed',
                  results: [],
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        runStatus="completed"
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        sessionFiles={[reportFile]}
        onPreviewWorkspaceFile={onPreviewWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file report.docx' }))

    expect(onPreviewWorkspaceFile).toHaveBeenCalledWith(reportFile)
  })

  it('renders workspace file chips in completed persisted assistant_text blocks', async () => {
    const user = userEvent.setup()
    const onPreviewWorkspaceFile = vi.fn()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-text',
            content: '本地预览: references/sources/report.docx',
            blocks: [
              createBlock({
                id: 'assistant-text-block',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_text',
                payload: {
                  text: '本地预览: `references/sources/report.docx`',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        runStatus="completed"
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        sessionFiles={[reportFile]}
        onPreviewWorkspaceFile={onPreviewWorkspaceFile}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview file report.docx' }))

    expect(onPreviewWorkspaceFile).toHaveBeenCalledWith(reportFile)
  })

  it('does not render workspace file chips in running assistant_text blocks', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-text',
            content: '本地预览: references/sources/report.docx',
            blocks: [
              createBlock({
                id: 'assistant-text-block',
                kind: 'content',
                order: 0,
                uiKind: 'assistant_text',
                payload: {
                  text: '本地预览: references/sources/report.docx',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        runStatus="running"
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        sessionFiles={[reportFile]}
        onPreviewWorkspaceFile={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Preview file report.docx' })).not.toBeInTheDocument()
    expect(screen.getByText(/references\/sources\/report\.docx/)).toBeInTheDocument()
  })

  it('does not render workspace file chips in streaming assistant text', () => {
    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[
          createBlock({
            id: 'streaming-assistant-text',
            kind: 'content',
            order: 0,
            uiKind: 'assistant_text',
            payload: {
              text: '本地预览: references/sources/report.docx',
            },
          }),
        ]}
        isStreaming
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
        sessionFiles={[reportFile]}
        onPreviewWorkspaceFile={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Preview file report.docx' })).not.toBeInTheDocument()
    expect(screen.getByText(/references\/sources\/report\.docx/)).toBeInTheDocument()
  })

  it('renders a live status history panel before the final answer', async () => {
    const user = userEvent.setup()

    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'status-message',
            content: null,
            blocks: [
              createBlock({
                id: 'home-status-history:run-1',
                kind: 'content',
                uiKind: 'status_history_panel',
                payload: {
                  statusHistory: [
                    {
                      id: 'status-1',
                      text: '正在创建四页 PPT。',
                      status: 'completed',
                      toolCalls: [{ id: 'call-write', name: 'write_file', status: 'completed' }],
                    },
                  ],
                },
              }),
            ],
          }),
          createAssistantMessage({
            id: 'final-message',
            content: 'PPT 已完成。',
            blocks: [
              createBlock({
                id: 'assistant-final',
                kind: 'content',
                uiKind: 'assistant_final_answer',
                payload: { text: 'PPT 已完成。', statusHistory: [] },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    const statusButton = screen.getByRole('button', { name: '状态历史' })
    expect(statusButton.compareDocumentPosition(screen.getByText('PPT 已完成。')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByText('正在创建四页 PPT。')).not.toBeInTheDocument()

    await user.click(statusButton)

    expect(screen.getByText('正在创建四页 PPT。')).toBeInTheDocument()
    expect(screen.getByText('write_file')).toBeInTheDocument()
  })

  it('keeps pending interaction form blocks editable after refresh even when the render block is completed', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'interaction-form-completed',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'completed',
                payload: {
                  requestId: 'req-brief-completed',
                  request_id: 'req-brief-completed',
                  kind: 'quick_brief',
                  status: 'pending',
                  answers: { output: 'Landing page', audience: 'Founders' },
                  schema: {
                    title: 'Quick brief',
                    submit_label: 'Continue',
                    fields: [
                      { id: 'output', label: 'What should we make', type: 'text', required: true },
                      { id: 'audience', label: 'Audience', type: 'text', required: true },
                    ],
                  },
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByLabelText('What should we make')).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
  })

  it('renders visual direction cards from interaction forms', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'interaction-form-direction',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'pending',
                payload: {
                  requestId: 'req-direction-1',
                  request_id: 'req-direction-1',
                  kind: 'visual_direction_picker',
                  status: 'pending',
                  schema: {
                    title: 'Pick a visual direction',
                    fields: [
                      {
                        id: 'direction',
                        label: 'Direction',
                        type: 'cards',
                        required: true,
                        options: [
                          {
                            label: 'Editorial Contrast',
                            value: 'editorial-contrast',
                            description: 'Refined layout',
                            metadata: {
                              palette: ['#F6F1E8', '#D6BFA7'],
                              display_font: 'Canela',
                              body_font: 'Inter',
                              references: ['Aesop', 'Kinfolk'],
                              mood: 'Refined',
                            },
                          },
                        ],
                      },
                    ],
                  },
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('Editorial Contrast')).toBeInTheDocument()
    expect(screen.getByText('Mood: Refined')).toBeInTheDocument()
    expect(screen.getByText('Display: Canela')).toBeInTheDocument()
    expect(screen.getByText('Refs: Aesop / Kinfolk')).toBeInTheDocument()
  })

  it('renders ecommerce generation options interaction cards', async () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            id: 'assistant-ecommerce-options',
            content: null,
            blocks: [
              createBlock({
                id: 'interaction-form-ecommerce-options',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'pending',
                payload: {
                  kind: 'ecommerce_generation_options',
                  requestId: 'call-options',
                  request_id: 'call-options',
                  status: 'pending',
                  question: '商品图生成配置',
                  defaults: {
                    generation_count: 4,
                    generation_count_min: 1,
                    generation_count_max: 6,
                  },
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(await screen.findByText('Product Image Generation Settings')).toBeInTheDocument()
    expect(screen.getByLabelText('Reference gallery image category')).toBeInTheDocument()
    expect(screen.getByLabelText('Image style')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Enable background image' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Enable model reference image' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Enable other product main-image reference' })).toBeInTheDocument()
  })

  it('re-syncs quick brief answers after rerender and keeps the form editable while pending', async () => {
    const user = userEvent.setup()
    const baseMessage = createAssistantMessage({
      content: null,
      blocks: [
        createBlock({
          id: 'interaction-form-rerender',
          kind: 'interaction',
          uiKind: 'interaction_form',
          status: 'pending',
          payload: {
            requestId: 'req-brief-rerender',
            request_id: 'req-brief-rerender',
            kind: 'quick_brief',
            status: 'pending',
            schema: {
              title: 'Quick brief',
              description: 'Lock the core constraints.',
              submit_label: 'Continue',
              fields: [
                { id: 'output', label: 'What should we make', type: 'text', required: true },
                {
                  id: 'platform',
                  label: 'Platform',
                  type: 'select',
                  required: true,
                  options: [
                    { label: 'Internal review', value: 'internal_review' },
                    { label: 'Sales pitch', value: 'sales_pitch' },
                  ],
                },
              ],
            },
            answers: null,
          },
        }),
      ],
    })

    const { rerender } = render(
      <HomeHarnessMessageList
        messages={[baseMessage]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        language="en-US"
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    const outputInput = screen.getByLabelText('What should we make') as HTMLInputElement
    expect(outputInput.value).toBe('')

    rerender(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            ...baseMessage,
            blocks: [
              createBlock({
                id: 'interaction-form-rerender',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'pending',
                payload: {
                  ...((baseMessage.blocks || [])[0]?.payload || {}),
                  answers: {
                    output: 'Pitch deck',
                    platform: 'internal_review',
                  },
                  status: 'pending',
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        language="en-US"
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    const syncedOutputInput = screen.getByLabelText('What should we make') as HTMLInputElement
    expect(syncedOutputInput.value).toBe('Pitch deck')

    await user.clear(syncedOutputInput)
    await user.type(syncedOutputInput, 'Investor deck')
    expect(syncedOutputInput.value).toBe('Investor deck')

    const platformSelect = screen.getByRole('combobox', { name: 'Platform' }) as HTMLButtonElement
    expect(platformSelect.disabled).toBe(false)
    await user.click(platformSelect)
    await user.click(screen.getByRole('option', { name: 'Sales pitch' }))
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Platform' })).toHaveTextContent('Sales pitch')
    })
  })

  it('preserves backend quick brief copy while still localizing known option labels', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: null,
            blocks: [
              createBlock({
                id: 'interaction-form-i18n',
                kind: 'interaction',
                uiKind: 'interaction_form',
                status: 'pending',
                payload: {
                  requestId: 'req-brief-i18n',
                  request_id: 'req-brief-i18n',
                  kind: 'quick_brief',
                  status: 'pending',
                  schema: {
                    title: 'Quick brief',
                    description: '先锁定这次产出的关键约束，后面的大纲、方向和执行都会基于这里的答案。',
                    submit_label: '继续',
                    fields: [
                      { id: 'output', label: '这次要产出什么', type: 'text', required: true, placeholder: '例如：PowerPoint 演示文稿' },
                      {
                        id: 'platform',
                        label: '发布平台 / 使用场景',
                        type: 'select',
                        required: true,
                        options: [
                          { label: '线下演讲', value: 'live_presentation' },
                          { label: '销售提案', value: 'sales_pitch' },
                        ],
                      },
                    ],
                  },
                },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        language="en-US"
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('Quick brief')).toBeInTheDocument()
    expect(screen.getByText('先锁定这次产出的关键约束，后面的大纲、方向和执行都会基于这里的答案。')).toBeInTheDocument()
    expect(screen.getByLabelText('这次要产出什么')).toBeInTheDocument()
    expect(screen.getByLabelText('发布平台 / 使用场景')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '继续' })).toBeInTheDocument()
  })

  it('renders plain text error blocks instead of hiding the message content', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          createAssistantMessage({
            content: 'Error: upstream model_not_found',
            blocks: [
              createBlock({
                id: 'error-block',
                kind: 'text',
                uiKind: 'text',
                payload: { text: 'Error: upstream model_not_found' },
              }),
            ],
          }),
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
      userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByText('Error: upstream model_not_found')).toBeInTheDocument()
  })

  it('renders a pending interaction supplied outside message blocks', () => {
    render(
      <HomeHarnessMessageList
        messages={[]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={{
          request_id: 'interaction-standalone',
          question: 'Choose the next step',
          kind: 'quick_brief',
          status: 'pending',
          schema: {
            title: 'Choose the next step',
            fields: [
              {
                id: 'next_step',
                label: 'Next step',
                type: 'text',
                required: true,
              },
            ],
          },
        }}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    expect(screen.getByTestId('home-harness-standalone-interaction')).toBeInTheDocument()
    expect(screen.getByText('Choose the next step')).toBeInTheDocument()
    expect(screen.getByLabelText('Next step')).toBeInTheDocument()
  })

  it('keeps user message content inside a shrinkable width-constrained column', () => {
    render(
      <HomeHarnessMessageList
        messages={[
          {
            id: 'user-message',
            role: 'user',
            content: '2006年:1581万 2007年:1591万 2008年:1604万 '.repeat(20),
            blocks: [],
            createdAt: '2026-04-20T00:00:00.000Z',
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
        isDark={false}
        t={t}
        conversationId="conv-1"
        userInteraction={null}
        respondToAgent={vi.fn(async () => {})}
        hiddenToolCalls={[]}
        onOpenWorkspaceRelativeFile={vi.fn()}
      />,
    )

    const bubble = screen.getByText(/2006年:1581万/).closest('div')
    expect(bubble).toHaveClass('max-w-full')
    expect(bubble).toHaveClass('[overflow-wrap:anywhere]')

    const messageColumn = bubble?.parentElement
    expect(messageColumn).toHaveClass('min-w-0')
    expect(messageColumn).toHaveClass('max-w-full')
  })
})
