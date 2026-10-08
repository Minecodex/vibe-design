import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from '@testing-library/react'
import { agentApi } from '@/api/endpoints/agent'

function mockVideoPlaybackApis() {
  const playMock = vi.fn().mockResolvedValue(undefined)
  const pauseMock = vi.fn()
  let currentTimeValue = 7

  Object.defineProperty(HTMLMediaElement.prototype, 'play', {
    configurable: true,
    writable: true,
    value: playMock,
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
    configurable: true,
    writable: true,
    value: pauseMock,
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
    configurable: true,
    get() {
      return currentTimeValue
    },
    set(value: number) {
      currentTimeValue = value
    },
  })

  Object.defineProperty(HTMLMediaElement.prototype, 'duration', {
    configurable: true,
    get() {
      return 6
    },
  })

  return {
    playMock,
    pauseMock,
    getCurrentTime: () => currentTimeValue,
  }
}

function setDocumentVisibility(value: 'hidden' | 'visible') {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value,
  })
}

const respondToAgentMock = vi.fn()
const onCanvasUpdateMock = vi.fn()
const updateToolCallMock = vi.fn()
const { queryTaskMock, startSerialPollingMock } = vi.hoisted(() => ({
  queryTaskMock: vi.fn(),
  startSerialPollingMock: vi.fn(),
}))

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
  it('does not render an empty interaction card when ask_user payload is invalid', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-ask-invalid',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'ask-invalid',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'choice_prompt',
                payload: {
                  requestId: '',
                  question: '',
                  inputType: 'buttons',
                  status: 'waiting',
                  options: [],
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})

vi.mock('@/api/endpoints/generation', () => ({
  generationApi: {
    queryTask: queryTaskMock,
  },
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getHarnessGenerationTask: queryTaskMock,
    getHarnessGenerationArtifactTask: queryTaskMock,
    createWorkspacePreviewToken: vi.fn().mockResolvedValue({
      preview_token: 'preview-token-123',
      expires_in_seconds: 300,
    }),
    fetchWorkspaceFileBlob: vi.fn(),
    getWorkspaceFileUrl: (conversationId: string, filePath: string) =>
      `http://localhost:8000/api/v1/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(filePath)}`,
    getWorkspacePreviewFileUrl: (conversationId: string, filePath: string, previewToken: string) =>
      `http://localhost:8000/api/v1/agent/harness/conversations/${conversationId}/preview-files/${encodeURIComponent(filePath)}?preview_token=${encodeURIComponent(previewToken)}`,
  },
  isHarnessWorkspaceRelativePath: (filePath: string | null | undefined) => {
    const raw = String(filePath || '').trim()
    return raw.length > 0 && !/^(?:https?:|data:|blob:|\/)/.test(raw)
  },
  normalizeHarnessWorkspacePath: (filePath: string) => {
    const normalized = String(filePath || '').trim().replace(/\\/g, '/').replace(/^sandbox:\/+/i, '').replace(/^\/+/, '')
    if (normalized.startsWith('assets/inputs/')) {
      return `references/inputs/${normalized.slice('assets/inputs/'.length)}`
    }
    if (normalized.startsWith('assets/references/')) {
      return `references/generated/${normalized.slice('assets/references/'.length)}`
    }
    return normalized
  },
  resolveHarnessWorkspaceUrl: (conversationId: string | number | null | undefined, filePath: string | null | undefined) => {
    const normalized = String(filePath || '').trim().replace(/\\/g, '/').replace(/^sandbox:\/+/i, '').replace(/^\/+/, '')
    if (!normalized) {
      return undefined
    }
    if (/^(?:https?:|data:|blob:|\/)/.test(normalized)) {
      return normalized
    }
    if (conversationId == null || conversationId === '') {
      return normalized
    }
    return `http://localhost:8000/api/v1/agent/harness/conversations/${String(conversationId)}/files/${encodeURIComponent(normalized)}`
  },
}))

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

vi.mock('./generationPolling', () => ({
  GENERATION_TASK_STATUS_POLL_INTERVAL_MS: 3000,
  GENERATION_TASK_POLL_ERROR_RETRY_INTERVAL_MS: 3000,
  startSerialPolling: startSerialPollingMock,
}))

vi.mock('@/store/canvasAgentStore', async () => {
  const actual = await vi.importActual('@/store/canvasAgentStore')
  return {
    ...actual,
    useChatStore: Object.assign(
      (selector: (state: any) => any) =>
        selector({
          conversationId: 101,
          engineVersion: 'harness',
          uiConfig: { hiddenToolCalls: [] },
          onCanvasUpdate: onCanvasUpdateMock,
          respondToAgent: respondToAgentMock,
          updateToolCall: updateToolCallMock,
        }),
      {
        getState: () => ({
          conversationId: 101,
          engineVersion: 'harness',
          uiConfig: { hiddenToolCalls: [] },
          onCanvasUpdate: onCanvasUpdateMock,
          respondToAgent: respondToAgentMock,
          updateToolCall: updateToolCallMock,
        }),
      },
    ),
  }
})

import { MessageList } from './MessageList'
import { __resetCanvasHarnessMediaSourceCacheForTests } from './useCanvasHarnessMediaSource'

describe('MessageList block renderers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setDocumentVisibility('visible')
    __resetCanvasHarnessMediaSourceCacheForTests()
    respondToAgentMock.mockReset()
    onCanvasUpdateMock.mockReset()
    updateToolCallMock.mockReset()
    queryTaskMock.mockReset()
    startSerialPollingMock.mockReset()
    queryTaskMock.mockResolvedValue({
      data: {
        id: 199,
        status: 'completed',
        progress: 100,
        result_url: '/generated/airport-poster.png',
        model_name: 'seedream',
        model_label: 'Seedream-5.0-Lite',
        provider_code: 'builtin',
        params: {
          resolution: '1K',
          aspect_ratio: '1:1',
        },
      },
    })
    startSerialPollingMock.mockImplementation(() => {
      return vi.fn()
    })
    URL.createObjectURL = vi.fn(() => 'blob:canvas-protected-image')
    URL.revokeObjectURL = vi.fn()
    HTMLAnchorElement.prototype.click = vi.fn()
  })

  it('does not render assistant bubbles that only contain empty text blocks', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-empty-text-shell',
            role: 'assistant',
            content: null,
            createdAt: '2026-06-17T08:48:35Z',
            blocks: [
              {
                id: 'empty-text-block',
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'text',
                payload: { text: '' },
              },
            ],
          },
          {
            id: 'assistant-visible-text',
            role: 'assistant',
            content: null,
            createdAt: '2026-06-17T08:48:36Z',
            blocks: [
              {
                id: 'visible-text-block',
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'text',
                payload: { text: '可见回复' },
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.queryByTestId('assistant-reply-timestamp-assistant-empty-text-shell')).not.toBeInTheDocument()
    expect(screen.getByText('可见回复')).toBeInTheDocument()
  })

  it('renders canonical canvas mention and mark tokens as chips', () => {
    const focusMock = vi.fn()
    render(
      <MessageList
        messages={[
          {
            id: 'user-canvas-refs',
            role: 'user',
            content: '参考 @[图片](canvas:img-1) 调整 #[葡萄](canvas-mark:mark-1:image:img-1:x:0.42:y:0.61)',
            createdAt: '2026-05-21T00:00:00Z',
            blocks: [],
            attachments: [],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
        onFocusItem={focusMock}
        canvasItems={[
          {
            id: 'img-1',
            type: 'image',
            url: '/api/v1/uploads/canvas/1/source.png',
            name: '图片',
          } as any,
        ]}
      />,
    )

    fireEvent.click(screen.getByText('图片'))
    fireEvent.click(screen.getByText('葡萄'))
    expect(focusMock).toHaveBeenCalledWith('img-1')
  })

  it('right-aligns user text messages inside the canvas chat list', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'user-1',
            role: 'user',
            content: '生成一个猴子吃桃子的图片',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const textNode = screen.getByText('生成一个猴子吃桃子的图片')
    const bubbleRow = textNode.parentElement?.parentElement

    expect(bubbleRow).toHaveStyle({
      justifyContent: 'flex-end',
      width: '100%',
    })
  })

  it('renders non-image user attachments as file cards in the chat list', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'user-file-1',
            role: 'user',
            content: 'Please review the brief',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [
              {
                type: 'file',
                url: 'assets/inputs/upload_001/source.docx',
                name: 'brief.docx',
              },
              {
                type: 'file',
                url: 'assets/inputs/upload_002/source.html',
                name: 'landing.html',
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('brief.docx')).toBeInTheDocument()
    expect(screen.getByText('landing.html')).toBeInTheDocument()
  })

  it('renders protected user image attachments through preview URLs', async () => {
    vi.mocked(agentApi.fetchWorkspaceFileBlob).mockResolvedValue(new Blob(['image-bytes'], { type: 'image/png' }))

    render(
      <MessageList
        messages={[
          {
            id: 'user-image-1',
            role: 'user',
            content: 'Use this image as reference',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [
              {
                type: 'image',
                url: 'assets/inputs/upload_003/source.png',
                name: 'source.png',
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(vi.mocked(agentApi.createWorkspacePreviewToken)).toHaveBeenCalledWith('101')
    })

    expect(agentApi.fetchWorkspaceFileBlob).not.toHaveBeenCalled()
    expect(screen.getByAltText('source.png')).toHaveAttribute(
      'src',
      'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Finputs%2Fupload_003%2Fsource.png?preview_token=preview-token-123',
    )
  })

  it('opens protected canvas user image attachments from the original workspace blob', async () => {
    vi.mocked(agentApi.fetchWorkspaceFileBlob).mockResolvedValue(new Blob(['original-image-bytes'], { type: 'image/png' }))

    render(
      <MessageList
        messages={[
          {
            id: 'user-image-preview-1',
            role: 'user',
            content: 'Use this image as reference',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [
              {
                type: 'image',
                url: 'assets/inputs/upload_005/source.png',
                name: 'source.png',
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const attachmentImage = await screen.findByAltText('source.png')
    await waitFor(() => {
      expect(attachmentImage).toHaveAttribute(
        'src',
        'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Finputs%2Fupload_005%2Fsource.png?preview_token=preview-token-123',
      )
    })

    fireEvent.click(attachmentImage)

    await waitFor(() => {
      expect(agentApi.fetchWorkspaceFileBlob).toHaveBeenCalledWith('101', 'references/inputs/upload_005/source.png')
    })
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(screen.getByAltText('canvas.chat.enlarge_view')).toHaveAttribute('src', 'blob:canvas-protected-image')
  })

  it('falls back to an authenticated blob for protected user image attachments when preview tokens fail', async () => {
    vi.mocked(agentApi.createWorkspacePreviewToken).mockRejectedValueOnce(new Error('preview token unavailable'))
    vi.mocked(agentApi.fetchWorkspaceFileBlob).mockResolvedValue(new Blob(['image-bytes'], { type: 'image/png' }))

    render(
      <MessageList
        messages={[
          {
            id: 'user-image-fallback-1',
            role: 'user',
            content: 'Use this image as reference',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [
              {
                type: 'image',
                url: 'assets/inputs/upload_004/source.png',
                name: 'fallback.png',
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(agentApi.fetchWorkspaceFileBlob).toHaveBeenCalledWith('101', 'references/inputs/upload_004/source.png')
    })

    expect(screen.getByAltText('fallback.png')).toHaveAttribute('src', 'blob:canvas-protected-image')
  })

  it('renders user attachments above the message bubble', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'user-file-order-1',
            role: 'user',
            content: 'Please review the brief',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [
              {
                type: 'file',
                url: 'assets/inputs/upload_001/source.docx',
                name: 'brief.docx',
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const attachmentNode = screen.getByText('brief.docx')
    const contentNode = screen.getByText('Please review the brief')
    expect(attachmentNode.compareDocumentPosition(contentNode) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('renders text attachments with a download button instead of a clickable card', async () => {
    vi.mocked(agentApi.fetchWorkspaceFileBlob).mockResolvedValue(new Blob(['account-bytes'], { type: 'text/plain' }))

    render(
      <MessageList
        messages={[
          {
            id: 'user-text-download-1',
            role: 'user',
            content: '请下载这个文本文件',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
            attachments: [
              {
                type: 'file',
                url: 'assets/inputs/upload_001/source.txt',
                name: '账号.txt',
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.queryByRole('link', { name: /账号\.txt/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /download 账号\.txt/i }))

    await waitFor(() => {
      expect(agentApi.fetchWorkspaceFileBlob).toHaveBeenCalledWith('101', 'references/inputs/upload_001/source.txt')
    })

    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('renders generation and interaction blocks while hiding hidden tools', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'hidden-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: false,
                uiKind: 'hidden_tool',
                payload: {
                  tool_name: 'read_skill_file',
                },
              },
              {
                id: 'generation-1',
                kind: 'tool',
                order: 1,
                status: 'running',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a cat',
                  model: 'flux',
                  provider: 'builtin',
                  progress: 42,
                  task_id: 9,
                  status: 'running',
                  meta: { media_type: 'image' },
                },
              },
              {
                id: 'ask-1',
                kind: 'interaction',
                order: 2,
                status: 'completed',
                visible: true,
                uiKind: 'choice_prompt',
                payload: {
                  requestId: 'req-1',
                  question: 'Which version should we keep?',
                  inputType: 'buttons',
                  status: 'waiting',
                  options: [
                    { label: 'Version A', value: 'a' },
                    { label: 'Version B', value: 'b' },
                  ],
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.queryByText('read_skill_file')).not.toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.queryByText('Seedream-5.0-Lite')).not.toBeInTheDocument()
    expect(screen.getAllByText('Which version should we keep?').length).toBeGreaterThan(0)
    expect(screen.getByText('Version A')).toBeInTheDocument()
    expect(screen.getByText('Version B')).toBeInTheDocument()
  })

  it('renders choice prompt questions with markdown formatting', () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-choice-markdown',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'ask-markdown-1',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'choice_prompt',
                payload: {
                  requestId: 'req-markdown-1',
                  question: [
                    '请确认方向：',
                    '',
                    '**Option A：方向A**',
                    '* **设计理念：** 更克制',
                    '* **视觉特征：** 更留白',
                  ].join('\n'),
                  inputType: 'buttons',
                  status: 'waiting',
                  options: [
                    { label: '继续', value: 'continue' },
                    { label: '调整', value: 'revise' },
                  ],
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(container.textContent).toContain('请确认方向：')
    expect(screen.getByText('继续')).toBeInTheDocument()
    expect(container.textContent).toContain('Option A：方向A')
  })

  it('renders the ask_user tool card when it is the only block', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-ask-user-tool-only',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'ask-tool-only',
                kind: 'tool',
                order: 0,
                status: 'running',
                visible: true,
                uiKind: 'compact_tool',
                payload: {
                  tool_name: 'ask_user',
                  call_id: 'tool-ask-only',
                  status: 'running',
                  result: {},
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('询问用户')).toBeInTheDocument()
  })

  it('does not render the ask_user tool card when a choice prompt block is present', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-ask-user-deduped',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'ask-choice-1',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'choice_prompt',
                payload: {
                  requestId: 'req-ask-1',
                  question: 'Choose a mode',
                  inputType: 'buttons',
                  status: 'waiting',
                  options: [
                    { label: 'Mode A', value: 'a' },
                    { label: 'Mode B', value: 'b' },
                  ],
                },
              },
              {
                id: 'ask-tool-1',
                kind: 'tool',
                order: 1,
                status: 'running',
                visible: true,
                uiKind: 'compact_tool',
                payload: {
                  tool_name: 'ask_user',
                  call_id: 'tool-ask-1',
                  status: 'running',
                  result: {},
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getAllByText('Choose a mode').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Mode A' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mode B' })).toBeInTheDocument()
    expect(screen.queryByText('询问用户')).not.toBeInTheDocument()
  })

  it('hides model and resolution pills on generation cards until real metadata arrives', () => {
    queryTaskMock.mockResolvedValue({
      data: {
        id: 201,
        status: 'running',
        progress: 42,
        result_url: null,
        provider_code: 'builtin',
        params: {},
      },
    })

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-generation-pending-meta',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'generation-pending-meta',
                kind: 'tool',
                order: 0,
                status: 'running',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a banana astronaut',
                  model: 'doubao-seedream-5-0-lite',
                  provider: 'builtin',
                  progress: 42,
                  task_id: 201,
                  status: 'running',
                  args: {
                    model: 'doubao-seedream-5-0-lite',
                    resolution: '1K',
                    aspect_ratio: '1:1',
                  },
                  meta: { media_type: 'image' },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.queryByText('Seedream-5.0-Lite')).not.toBeInTheDocument()
    expect(screen.queryByText('1K')).not.toBeInTheDocument()
  })

  it('uses a hover autoplay video preview on completed video generation cards while keeping metadata pills', () => {
    const { playMock, pauseMock, getCurrentTime } = mockVideoPlaybackApis()

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-generation-video-preview',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'generation-video-preview',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_video',
                  prompt: 'a woman drinking coffee in a cafe',
                  model: 'grok-video',
                  provider: 'builtin',
                  progress: 100,
                  task_id: 301,
                  status: 'completed',
                  meta: { media_type: 'video' },
                  result: {
                    task_id: 301,
                    status: 'completed',
                    result_url: '/generated/coffee.mp4',
                    model_label: 'Grok-Imagine-video-1.0',
                    model_name: 'grok-video',
                    provider_code: 'builtin',
                    resolution: '720p',
                    params: {
                      resolution: '720p',
                      aspect_ratio: '16:9',
                    },
                    canvas_item: {
                      id: 'canvas-video-301',
                      type: 'video_generator',
                      task_id: 301,
                      prompt: 'a woman drinking coffee in a cafe',
                      x: 100,
                      y: 120,
                      aspect_ratio: '16:9',
                      resolution: '720p',
                      model_label: 'Grok-Imagine-video-1.0',
                      model_name: 'grok-video',
                      provider_code: 'builtin',
                      status: 'completed',
                      url: '/generated/coffee.mp4',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Grok-Imagine-video-1.0')).toBeInTheDocument()
    expect(screen.getByText('720p')).toBeInTheDocument()
    expect(screen.getByLabelText('Play video preview')).toBeInTheDocument()

    const container = screen.getByTestId('message-video-preview')
    const video = container.querySelector('video') as HTMLVideoElement | null

    expect(video).toBeTruthy()
    expect(video?.muted).toBe(true)
    expect(video?.hasAttribute('controls')).toBe(false)

    Object.defineProperty(video!, 'videoWidth', { configurable: true, value: 1280 })
    Object.defineProperty(video!, 'videoHeight', { configurable: true, value: 720 })
    fireEvent.loadedMetadata(video!)
    expect(screen.getByText('1280×720')).toBeInTheDocument()

    fireEvent.mouseEnter(container)

    expect(playMock).toHaveBeenCalled()
    expect(screen.queryByLabelText('Play video preview')).not.toBeInTheDocument()
    expect(screen.getByText('00:06')).toBeInTheDocument()

    fireEvent.mouseLeave(container)

    expect(pauseMock).toHaveBeenCalled()
    expect(getCurrentTime()).toBe(0)
    expect(screen.getByLabelText('Play video preview')).toBeInTheDocument()
  })

  it('renders plan, progress, and media blocks without exposing raw tool details', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-user-facing-1',
            role: 'assistant',
            content: 'done',
            createdAt: '2026-04-19T00:00:00Z',
            blocks: [
              {
                id: 'plan-1',
                kind: 'content',
                order: 0,
                status: 'in_progress',
                visible: true,
                uiKind: 'plan_artifact',
                payload: {
                  title: 'Task Plan',
                  summary: 'First gather input, then draft.',
                  currentStep: 'step-2',
                  steps: [
                    { id: 'step-1', order: 1, title: 'Gather input', status: 'completed' },
                    { id: 'step-2', order: 2, title: 'Draft output', status: 'in_progress' },
                  ],
                },
              },
              {
                id: 'progress-1',
                kind: 'content',
                order: 1,
                status: 'completed',
                visible: true,
                uiKind: 'progress_update',
                payload: {
                  text: 'Reading reference files',
                },
              },
              {
                id: 'media-1',
                kind: 'content',
                order: 2,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  media_type: 'image_analysis',
                  text: 'This image contains a cat.',
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Task Plan')).toBeInTheDocument()
    expect(screen.getByText('Reading reference files')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.queryByText('This image contains a cat.')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '图片分析' }))

    expect(screen.getByText('This image contains a cat.')).toBeInTheDocument()
    expect(screen.queryByText('read_skill_file')).not.toBeInTheDocument()
  })

  it('renders awaiting approval plan guidance on user-facing plan blocks', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-plan-awaiting-message-list',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-19T00:00:00Z',
            blocks: [
              {
                id: 'plan-awaiting-message-list',
                kind: 'content',
                order: 0,
                status: 'awaiting_approval',
                visible: true,
                uiKind: 'plan_artifact',
                payload: {
                  title: 'Task Plan',
                  status: 'awaiting_approval',
                  summary: 'Wait for approval before execution.',
                  currentStep: 'step-2',
                  steps: [
                    { id: 'step-1', order: 1, title: 'Gather input', status: 'completed' },
                    { id: 'step-2', order: 2, title: 'Draft output', status: 'in_progress' },
                  ],
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getAllByText('Awaiting approval').length).toBeGreaterThan(0)
    expect(screen.getByText('Reply to approve the plan or tell the agent what to change before execution continues.')).toBeInTheDocument()
  })

  it('keeps assistant markdown replies selectable even when an ancestor disables selection', () => {
    const { container } = render(
      <div style={{ userSelect: 'none' }}>
        <MessageList
          messages={[
            {
              id: 'assistant-selectable',
              role: 'assistant',
              content: 'copy **this** reply',
              createdAt: '2026-03-30T00:00:00Z',
              blocks: [],
            },
          ]}
          streamingBlocks={[]}
          isStreaming={false}
          onFocusItem={vi.fn()}
          canvasItems={[]}
          deletedAgentMediaKeys={[]}
          canReplayCompletedMedia={false}
        />
      </div>,
    )

    const markdownBody = container.querySelector('.markdown-body') as HTMLDivElement | null
    expect(markdownBody).toBeTruthy()
    expect(markdownBody?.style.userSelect).toBe('text')

    const scrollArea = container.querySelector('[data-testid="chat-message-scroll"]') as HTMLDivElement | null
    expect(scrollArea).toBeTruthy()
    expect(scrollArea?.style.userSelect).toBe('text')
  })

  it('keeps bottom content reachable above the fixed canvas composer', () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-bottom-safe',
            role: 'assistant',
            content: 'Bottom safe reply',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const scrollArea = container.querySelector('[data-testid="chat-message-scroll"]') as HTMLDivElement | null
    expect(scrollArea).toBeTruthy()
    expect(scrollArea?.style.minHeight).toBe('0')
    expect(scrollArea?.style.paddingBottom).toBe('20px')
  })

  it('keeps plain wheel scrolling inside the chat message list', () => {
    const { container } = render(
      <div onWheel={(event) => event.currentTarget.setAttribute('data-bubbled', 'true')}>
        <MessageList
          messages={[
            {
              id: 'assistant-scrollable',
              role: 'assistant',
              content: 'Scroll me',
              createdAt: '2026-03-30T00:00:00Z',
              blocks: [],
            },
          ]}
          streamingBlocks={[]}
          isStreaming={false}
        />
      </div>,
    )

    const scrollArea = container.querySelector('[data-testid="chat-message-scroll"]') as HTMLDivElement | null
    expect(scrollArea).toBeTruthy()
    fireEvent.wheel(scrollArea!, { deltaY: 120 })

    expect(container.firstElementChild).not.toHaveAttribute('data-bubbled')
  })

  it('remounts the virtualized message list when returning to a running background tab', async () => {
    const messages = Array.from({ length: 56 }, (_item, index) => ({
      id: `assistant-virtual-${index}`,
      role: 'assistant' as const,
      content: `Virtual message ${index}`,
      createdAt: '2026-03-30T00:00:00Z',
      blocks: [],
    }))

    const { container } = render(
      <MessageList
        messages={messages}
        streamingBlocks={[]}
        isStreaming={true}
        runStatus="running"
        conversationId="conv-virtual-resume"
      />,
    )

    const virtualScroll = () => container.querySelector('[data-testid="chat-message-virtual-scroll"]') as HTMLDivElement | null
    expect(virtualScroll()).toBeTruthy()
    expect(virtualScroll()).toHaveAttribute('data-recovery-epoch', '0')

    setDocumentVisibility('hidden')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    setDocumentVisibility('visible')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await waitFor(() => {
      expect(virtualScroll()).toHaveAttribute('data-recovery-epoch', '1')
    })
  })

  it('remounts after becoming virtualized while hidden even when the run completed in the background', async () => {
    const initialMessages = Array.from({ length: 20 }, (_item, index) => ({
      id: `assistant-plain-${index}`,
      role: 'assistant' as const,
      content: `Plain message ${index}`,
      createdAt: '2026-03-30T00:00:00Z',
      blocks: [],
    }))
    const completedMessages = Array.from({ length: 56 }, (_item, index) => ({
      id: `assistant-completed-${index}`,
      role: 'assistant' as const,
      content: `Completed message ${index}`,
      createdAt: '2026-03-30T00:00:00Z',
      blocks: [],
    }))

    const { container, rerender } = render(
      <MessageList
        messages={initialMessages}
        streamingBlocks={[]}
        isStreaming={true}
        runStatus="running"
        conversationId="conv-background-threshold"
      />,
    )

    expect(container.querySelector('[data-testid="chat-message-scroll"]')).toBeTruthy()
    expect(container.querySelector('[data-testid="chat-message-virtual-scroll"]')).toBeNull()

    setDocumentVisibility('hidden')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    rerender(
      <MessageList
        messages={completedMessages}
        streamingBlocks={[]}
        isStreaming={false}
        runStatus="completed"
        conversationId="conv-background-threshold"
      />,
    )

    const virtualScroll = () => container.querySelector('[data-testid="chat-message-virtual-scroll"]') as HTMLDivElement | null
    expect(virtualScroll()).toBeTruthy()
    expect(virtualScroll()).toHaveAttribute('data-recovery-epoch', '0')

    setDocumentVisibility('visible')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await waitFor(() => {
      expect(virtualScroll()).toHaveAttribute('data-recovery-epoch', '1')
    })
  })

  it('renders assistant markdown tables with visible cell borders', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-table',
            role: 'assistant',
            content: '| Name | Value |\n| --- | --- |\n| Foo | Bar |',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const headerCell = screen.getByRole('columnheader', { name: 'Name' })
    const bodyCell = screen.getByRole('cell', { name: 'Foo' })

    expect(headerCell.style.border).toBe('1px solid var(--app-border)')
    expect(bodyCell.style.border).toBe('1px solid var(--app-border)')
  })

  it('renders streaming assistant text as plain text without markdown parsing', () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-streaming-text',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'assistant-streaming-text-block',
                kind: 'content',
                order: 0,
                status: 'streaming',
                visible: true,
                uiKind: 'assistant_text',
                payload: {
                  text: '| Name | Value |\n| --- | --- |\n| Foo | Bar |',
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(container.querySelector('[data-testid="chat-message-scroll"]')?.textContent).toContain('| Name | Value |')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders assistant final answer blocks in the canvas chat list', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-final-answer',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'assistant-final-answer-block',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'assistant_final_answer',
                payload: {
                  text: '图片生成任务已提交，正在处理中。\n\n生成完成后会自动显示在画布上，请稍候。',
                  message_kind: 'final_answer',
                },
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('图片生成任务已提交，正在处理中。')).toBeInTheDocument()
    expect(screen.getByText('生成完成后会自动显示在画布上，请稍候。')).toBeInTheDocument()
  })

  it('renders artifact refs in assistant final answers as generated media chips', async () => {
    queryTaskMock.mockResolvedValue({
      data: {
        task_id: 'task-artifact-image',
        artifact_ref: 'artifact_ref:canvas-image-1',
        status: 'processing',
        kind: 'image',
        progress: 18,
        result_url: null,
        error_message: null,
      },
    })

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-final-artifact-ref',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'final-artifact-ref',
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'assistant_final_answer',
                payload: {
                  text: '`artifact_ref:canvas-image-1`',
                },
              },
            ],
          },
        ] as any}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(await screen.findByTestId('generation-artifact-reference')).toHaveTextContent('Generating image...')
    expect(queryTaskMock).toHaveBeenCalledWith('101', 'artifact_ref:canvas-image-1')
  })

  it('shows a timestamp only above the first assistant reply after each user turn', () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date('2026-04-16T12:00:00'))

      render(
        <MessageList
          messages={[
            {
              id: 'user-1',
              role: 'user',
              content: 'first prompt',
              createdAt: '2026-04-16T08:00:00',
              blocks: [],
            },
            {
              id: 'assistant-1',
              role: 'assistant',
              content: 'first reply',
              createdAt: '2026-04-16T08:09:00',
              blocks: [],
            },
            {
              id: 'assistant-2',
              role: 'assistant',
              content: 'follow-up reply',
              createdAt: '2026-04-16T08:10:00',
              blocks: [],
            },
            {
              id: 'user-2',
              role: 'user',
              content: 'second prompt',
              createdAt: '2026-04-15T09:00:00',
              blocks: [],
            },
            {
              id: 'assistant-3',
              role: 'assistant',
              content: 'second turn reply',
              createdAt: '2026-04-15T09:05:00',
              blocks: [],
            },
          ]}
          streamingBlocks={[]}
          isStreaming={false}
        />,
      )

      expect(screen.getByTestId('assistant-reply-timestamp-assistant-1')).toHaveTextContent('08:09')
      expect(screen.queryByTestId('assistant-reply-timestamp-assistant-2')).not.toBeInTheDocument()
      expect(screen.getByTestId('assistant-reply-timestamp-assistant-3')).toHaveTextContent('04-15 09:05')
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows image analysis content when available', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-2',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'analysis-1',
                kind: 'content',
                order: 0,
                status: 'running',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  media_type: 'image_analysis',
                  text: 'Analyzing this image now',
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.getByText('Analyzing this image now')).toBeInTheDocument()
    expect(screen.getAllByText(/Analyzing this image now/)).toHaveLength(1)
  })

  it('shows a thinking hint during streaming gaps after rendered blocks', () => {
    render(
      <MessageList
        messages={[]}
        streamingBlocks={[
          {
            id: 'analysis-2',
            kind: 'tool',
            order: 0,
            status: 'completed',
            visible: true,
            uiKind: 'stream_panel',
            payload: {
              tool_name: 'analyze_image',
              stream_text: 'Analysis is complete',
              result: { analysis: 'Analysis is complete' },
            },
          },
        ]}
        isStreaming={true}
      />,
    )

    expect(screen.getByText('canvas.chat.thinking')).toBeInTheDocument()
  })

  it('shows a thinking hint while the transport is streaming before run status catches up', () => {
    render(
      <MessageList
        messages={[]}
        streamingBlocks={[]}
        isStreaming
        runStatus="idle"
      />,
    )

    expect(screen.getByText('canvas.chat.thinking')).toBeInTheDocument()
  })

  it('pauses the thinking spinner while canvas interactions are active', () => {
    const { container } = render(
      <MessageList
        messages={[]}
        streamingBlocks={[]}
        isStreaming
        runStatus="idle"
        pauseThinkingAnimation
      />,
    )

    expect(screen.getByText('canvas.chat.thinking')).toBeInTheDocument()
    expect(container.querySelector('svg')).toHaveStyle({
      animationPlayState: 'paused',
    })
  })

  it('keeps streaming blocks and the thinking hint visible while the agent run is still active after transport reconnect gaps', () => {
    render(
      <MessageList
        messages={[]}
        streamingBlocks={[
          {
            id: 'analysis-gap',
            kind: 'tool',
            order: 0,
            status: 'completed',
            visible: true,
            uiKind: 'stream_panel',
            payload: {
              tool_name: 'analyze_image',
              stream_text: 'Analysis is complete',
              result: { analysis: 'Analysis is complete' },
            },
          },
        ]}
        isStreaming={false}
        runStatus="running"
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.getByText('canvas.chat.thinking')).toBeInTheDocument()
  })

  it('renders analyze_image stream panels inside the canvas agent conversation', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-analyze-image-panel',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-20T00:00:00Z',
            blocks: [
              {
                id: 'analyze-image-stream-panel',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'stream_panel',
                payload: {
                  tool_name: 'analyze_image',
                  stream_text: JSON.stringify({
                    analysis: 'Detected a coffee cup on a wooden table.',
                    elapsed_ms: 3725,
                  }),
                  elapsed_ms: 3725,
                  result: {
                    analysis: 'Detected a coffee cup on a wooden table.',
                    elapsed_ms: 3725,
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '图片分析' }))
    expect(screen.getByText('Detected a coffee cup on a wooden table.')).toBeInTheDocument()
  })

  it('merges transient analyze_image text blocks into streaming media cards', () => {
    render(
      <MessageList
        messages={[]}
        streamingBlocks={[
          {
            id: 'analyze-image-text-functions.analyze_image:1',
            kind: 'text',
            order: 0,
            status: 'completed',
            visible: true,
            uiKind: 'text',
            payload: {
              tool_name: 'analyze_image',
              text: 'Transient streaming analysis body.',
            },
          },
          {
            id: 'media-functions.analyze_image:1',
            kind: 'content',
            order: 1,
            status: 'completed',
            visible: true,
            uiKind: 'media_card',
            payload: {
              tool_name: 'analyze_image',
              call_id: 'functions.analyze_image:1',
              media_type: 'image_analysis',
              text: '',
              analysis: null,
            },
          },
        ] as any}
        isStreaming={true}
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.queryByText('Transient streaming analysis body.')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '图片分析' }))

    expect(screen.getByText('Transient streaming analysis body.')).toBeInTheDocument()
    expect(screen.getAllByText('Transient streaming analysis body.')).toHaveLength(1)
  })

  it('streams analyze_image child text inside media cards while running', () => {
    render(
      <MessageList
        messages={[]}
        streamingBlocks={[
          {
            id: 'media-functions.analyze_image:child',
            kind: 'content',
            order: 1,
            status: 'running',
            visible: true,
            uiKind: 'media_card',
            payload: {
              tool_name: 'analyze_image',
              call_id: 'functions.analyze_image:child',
              media_type: 'image_analysis',
              text: '',
              analysis: null,
              status: 'running',
            },
            children: [
              {
                id: 'analyze-image-text-functions.analyze_image:child',
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'text',
                payload: {
                  tool_name: 'analyze_image',
                  call_id: 'functions.analyze_image:child',
                  text: 'Nested streaming analysis body.',
                },
              },
            ],
          },
        ] as any}
        isStreaming={true}
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.getByText('Nested streaming analysis body.')).toBeInTheDocument()
    expect(screen.getAllByText('Nested streaming analysis body.')).toHaveLength(1)
  })

  it('keeps analyze image cards expanded with a scrollable body while streaming', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-analyze-image-running',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-20T00:00:00Z',
            blocks: [
              {
                id: 'analyze-image-running',
                kind: 'tool',
                order: 0,
                status: 'running',
                visible: true,
                uiKind: 'stream_panel',
                payload: {
                  tool_name: 'analyze_image',
                  stream_text: JSON.stringify({
                    analysis: 'Streaming image analysis body.',
                  }),
                  result: null,
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.getByText('Streaming image analysis body.')).toBeInTheDocument()
    expect(screen.getByTestId('analyze-image-body')).toHaveStyle({
      maxHeight: '240px',
      overflowY: 'auto',
      overflowX: 'hidden',
    })
  })

  it('collapses analyze image cards after completion but allows reopening', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-analyze-image-completed',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-20T00:00:00Z',
            blocks: [
              {
                id: 'analyze-image-completed',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'stream_panel',
                payload: {
                  tool_name: 'analyze_image',
                  stream_text: JSON.stringify({
                    analysis: 'Completed image analysis body.',
                  }),
                  result: {
                    analysis: 'Completed image analysis body.',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.queryByText('Completed image analysis body.')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '图片分析' }))

    expect(screen.getByText('Completed image analysis body.')).toBeInTheDocument()
    expect(screen.getByTestId('analyze-image-body')).toHaveStyle({
      maxHeight: '240px',
      overflowY: 'auto',
      overflowX: 'hidden',
    })
  })

  it('collapses image-analysis media cards by default but allows reopening', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-analyze-image-media-card',
            role: 'assistant',
            content: null,
            createdAt: '2026-04-20T00:00:00Z',
            blocks: [
              {
                id: 'media-analyze-image-completed',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  tool_name: 'analyze_image',
                  media_type: 'image_analysis',
                  text: 'Collapsed media card analysis body.',
                  analysis: 'Collapsed media card analysis body.',
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByRole('button', { name: '图片分析' })).toBeInTheDocument()
    expect(screen.queryByText('Collapsed media card analysis body.')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '图片分析' }))

    expect(screen.getByText('Collapsed media card analysis body.')).toBeInTheDocument()
    expect(screen.getByTestId('analyze-image-body')).toHaveStyle({
      maxHeight: '240px',
      overflowY: 'auto',
      overflowX: 'hidden',
    })
  })

  it('marks analyze image tool results as completed when analysis text is present', async () => {
    const actualStore = await vi.importActual<typeof import('@/store/canvasAgentStore')>('@/store/canvasAgentStore')
    const { upsertStreamingToolResultBlock } = actualStore.__chatStoreTestUtils

    const blocks = upsertStreamingToolResultBlock([], {
      type: 'tool_result',
      data: {
        tool: 'analyze_image',
        call_id: 'call-analyze-1',
        result: {
          analysis: 'Finished analyzing the uploaded image.',
          elapsed_ms: 1800,
        },
      },
    } as any)

    expect(blocks).toHaveLength(1)
    expect(blocks[0].status).toBe('completed')
  })

  it('renders compact tool results inside the canvas agent conversation', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-compact-tool',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'tool-compact-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'compact_tool',
                payload: {
                  tool_name: 'read_file',
                  call_id: 'call-read-file',
                  result: {
                    message: 'Loaded README.md successfully.',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('read_file')).toBeInTheDocument()
    expect(screen.getByText('Loaded README.md successfully.')).toBeInTheDocument()
  })

  it('resolves generated markdown image paths to backend upload urls', () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-markdown-image',
            role: 'assistant',
            content: '![Search image](generated/web_search_demo.jpg)',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const image = container.querySelector('img')
    expect(image?.getAttribute('src')).toBe('http://localhost:8000/api/v1/uploads/generated/web_search_demo.jpg')
  })

  it('opens markdown images in the preview dialog when clicked', () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-markdown-image-preview',
            role: 'assistant',
            content: '![Search image](generated/web_search_preview.jpg)',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const image = container.querySelector('img')
    expect(image).toBeTruthy()

    fireEvent.click(image!)

    const preview = screen.getByAltText('canvas.chat.enlarge_view') as HTMLImageElement
    expect(preview.getAttribute('src')).toBe('http://localhost:8000/api/v1/uploads/generated/web_search_preview.jpg')
  })

  it('resolves sandbox markdown image paths through the harness preview-files endpoint', async () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-sandbox-markdown-image',
            role: 'assistant',
            content: '![Direction board](sandbox:/assets/references/generated_image_001/original.png)',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(vi.mocked(agentApi.createWorkspacePreviewToken)).toHaveBeenCalledWith('101')
    })

    const image = container.querySelector('img')
    expect(image?.getAttribute('src')).toBe(
      'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Fgenerated%2Fgenerated_image_001%2Foriginal.png?preview_token=preview-token-123',
    )
  })

  it('renders canvas workspace image paths in message content as media chips', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-workspace-image-reference',
            role: 'assistant',
            content: '本地参考图：`references/sources/web_image_001/original.jpg`',
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const chip = await screen.findByTestId('canvas-workspace-media-reference')
    expect(chip).toHaveTextContent('Image')
    expect(screen.queryByText('references/sources/web_image_001/original.jpg')).not.toBeInTheDocument()
    expect(vi.mocked(agentApi.createWorkspacePreviewToken)).toHaveBeenCalledWith('101')
    await waitFor(() =>
      expect(chip.querySelector('img')?.getAttribute('src')).toBe(
        'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Fsources%2Fweb_image_001%2Foriginal.jpg?preview_token=preview-token-123',
      ),
    )
  })

  it('reuses canvas workspace media preview URLs across message remounts', async () => {
    const messages = [
      {
        id: 'assistant-workspace-image-reference-rerender',
        role: 'assistant',
        content: '本地参考图：`references/sources/web_image_001/original.jpg`',
        createdAt: '2026-03-30T00:00:00Z',
        blocks: [],
      },
    ] as any

    const firstRender = render(
      <MessageList
        messages={messages}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const firstChip = await screen.findByTestId('canvas-workspace-media-reference')
    await waitFor(() =>
      expect(firstChip.querySelector('img')?.getAttribute('src')).toBe(
        'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Fsources%2Fweb_image_001%2Foriginal.jpg?preview_token=preview-token-123',
      ),
    )
    expect(vi.mocked(agentApi.createWorkspacePreviewToken)).toHaveBeenCalledTimes(1)

    firstRender.unmount()

    render(
      <MessageList
        messages={[...messages]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const rerenderedChip = await screen.findByTestId('canvas-workspace-media-reference')
    expect(rerenderedChip.querySelector('img')?.getAttribute('src')).toBe(
      'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Fsources%2Fweb_image_001%2Foriginal.jpg?preview_token=preview-token-123',
    )
    expect(vi.mocked(agentApi.createWorkspacePreviewToken)).toHaveBeenCalledTimes(1)
  })

  it('prefers web search ui results when rendering image cards', () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-web-search-card',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'web-search-card-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'web_search_card',
                payload: {
                  result: {
                    searchType: 'image',
                    query: 'kant portrait',
                    message: "图片搜索 'kant portrait' 返回了 5 条结果",
                    results: [
                      {
                        title: 'model-visible result',
                        local_image_path: 'generated/should-not-win.jpg',
                      },
                    ],
                    ui_results: [
                      {
                        title: 'ui result',
                        local_image_url: '/api/v1/uploads/generated/should-win.jpg',
                        source_url: 'https://example.com/source',
                      },
                    ],
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /联网图片搜索/i }))

    expect(screen.getByText("图片搜索 'kant portrait' 返回了 1 条结果")).toBeInTheDocument()
    expect(screen.queryByText("图片搜索 'kant portrait' 返回了 5 条结果")).not.toBeInTheDocument()

    const image = container.querySelector('img[alt="ui result"]')
    expect(image?.getAttribute('src')).toBe('http://localhost:8000/api/v1/uploads/generated/should-win.jpg')
  })

  it('resolves harness workspace image search results through the preview file endpoint', async () => {
    const { container } = render(
      <MessageList
        messages={[
          {
            id: 'assistant-web-search-local-path',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'web-search-card-local-path',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'web_search_card',
                payload: {
                  search_type: 'image',
                  query: 'nietzsche portrait',
                  message: 'ok',
                  results: [
                    {
                      title: 'local result',
                      local_image_path: 'assets/references/web_image_001/original.jpg',
                      source_url: 'https://example.com/source',
                    },
                  ],
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /联网图片搜索/i }))

    await waitFor(() => {
      const image = container.querySelector('img[alt="local result"]')
      expect(image?.getAttribute('src')).toBe(
        'http://localhost:8000/api/v1/agent/harness/conversations/101/preview-files/references%2Fgenerated%2Fweb_image_001%2Foriginal.jpg?preview_token=preview-token-123',
      )
    })
  })

  it('adds a generation placeholder to canvas as soon as a running task card appears', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-gen-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'generation-running-1',
                kind: 'tool',
                order: 0,
                status: 'running',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a glowing tree logo',
                  progress: 10,
                  task_id: 42,
                  canvas_revision: 19,
                  status: 'running',
                  result: {
                    task_id: 42,
                    status: 'processing',
                    canvas_item: {
                      id: 'canvas-item-42',
                      type: 'image_generator',
                      task_id: 42,
                      prompt: 'a glowing tree logo',
                      x: 100,
                      y: 120,
                      aspect_ratio: '1:1',
                      resolution: '1K',
                      model_name: 'flux',
                      model_label: 'Flux',
                      provider_code: 'builtin',
                      status: 'generating',
                      url: '',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(onCanvasUpdateMock).toHaveBeenCalledWith(
        'add',
        expect.objectContaining({
          id: 'canvas-item-42',
          type: 'image_generator',
          conversationId: 101,
          task_id: 42,
          messageId: 'assistant-gen-1',
          agentMediaKey: 'canvas-item-42',
        }),
      )
    })
    expect(onCanvasUpdateMock).toHaveBeenNthCalledWith(
      1,
      'sync_canvas_revision',
      {},
      { canvasRevision: 19, canvasItemDeleted: false },
    )
  })

  it('does not regress a completed generation card without a newer projection event', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-gen-stale-hydration',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'gen-stale-hydration',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  status: 'completed',
                  progress: 100,
                  task_id: 301,
                  result: {
                    task_id: 301,
                    status: 'completed',
                    progress: 100,
                    result_url: '/generated/completed.png',
                    canvas_item: {
                      id: 'canvas-item-301',
                      type: 'image_generator',
                      task_id: 301,
                      prompt: 'completed image',
                      x: 100,
                      y: 120,
                      aspect_ratio: '1:1',
                      resolution: '1K',
                      model_name: 'flux',
                      model_label: 'Flux',
                      provider_code: 'builtin',
                      status: 'completed',
                      url: '/generated/completed.png',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const image = document.querySelector('img[src="http://localhost:8000/api/v1/uploads/generated/completed.png"]')
    expect(image).toBeInTheDocument()
    expect(queryTaskMock).not.toHaveBeenCalled()
    expect(updateToolCallMock).not.toHaveBeenCalledWith(
      'assistant-gen-stale-hydration',
      'gen-stale-hydration',
      expect.objectContaining({ status: 'running' }),
    )
  })

  it('does not mutate generation state from renderer polling side effects', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-gen-poll-dedupe',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'gen-poll-dedupe',
                kind: 'tool',
                order: 0,
                status: 'running',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  call_id: 'functions.generate_image:201',
                  status: 'processing',
                  progress: 25,
                  task_id: 201,
                  result: {
                    task_id: 201,
                    status: 'processing',
                    progress: 25,
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(queryTaskMock).not.toHaveBeenCalled()
    expect(updateToolCallMock).not.toHaveBeenCalled()
  })

  it('renders Agent as a collapsed subagent card and reveals nested content on expand', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-subagent-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'subagent-card-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'subagent_card',
                taskId: 'subagent-1',
                label: 'Concept image',
                summary: '宸插畬鎴愬苟杩斿洖鎽樿',
                expanded: false,
                children: [
                  {
                    id: 'subagent-text-1',
                    kind: 'text',
                    order: 0,
                    status: 'completed',
                    visible: true,
                    uiKind: 'text',
                    payload: {
                      text: '杩欐槸涓嬫父鏈哄櫒浜鸿緭鍑虹殑鏂囨鎽樿',
                    },
                  },
                  {
                    id: 'subagent-generation-1',
                    kind: 'tool',
                    order: 1,
                    status: 'completed',
                    visible: true,
                    uiKind: 'generation_task',
                    payload: {
                      tool_name: 'generate_image',
                      prompt: 'a signature airport drink',
                      model: 'flux',
                      provider: 'builtin',
                      progress: 100,
                      task_id: 99,
                      status: 'completed',
                  meta: { media_type: 'image' },
                      result: {
                        task_id: 99,
                        status: 'completed',
                        result_url: '/generated/drink.png',
                        canvas_item: {
                          id: 'canvas-subagent-99',
                          type: 'image_generator',
                          task_id: 99,
                          prompt: 'a signature airport drink',
                          x: 100,
                          y: 120,
                          aspect_ratio: '1:1',
                          resolution: '1K',
                          model_name: 'flux',
                          model_label: 'Flux',
                          provider_code: 'builtin',
                          status: 'completed',
                          url: '/generated/drink.png',
                        },
                      },
                    },
                  },
                ],
                payload: {
                  tool_name: 'Agent',
                  purpose: 'Concept image',
                  status: 'completed',
                  result: {
                    task_id: 'subagent-1',
                    label: 'Concept image',
                    purpose: 'Concept image',
                    status: 'completed',
                    result: '宸插畬鎴愬苟杩斿洖鎽樿',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('子代理')).toBeInTheDocument()
    expect(screen.getByText('任务目的')).toBeInTheDocument()
    expect(screen.getByText('Concept image')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.queryByText('宸插畬鎴愬苟杩斿洖鎽樿')).not.toBeInTheDocument()
    expect(screen.queryByText('杩欐槸涓嬫父鏈哄櫒浜鸿緭鍑虹殑鏂囨鎽樿')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Concept image/ }))

    await waitFor(() => {
      expect(screen.getByText('宸插畬鎴愬苟杩斿洖鎽樿')).toBeInTheDocument()
      expect(screen.getByText('杩欐槸涓嬫父鏈哄櫒浜鸿緭鍑虹殑鏂囨鎽樿')).toBeInTheDocument()
    })
    expect(screen.getAllByText('Flux').length).toBeGreaterThan(0)
  })

  it('mirrors completed subagent media into the main message flow without replaying canvas twice after expand', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-subagent-mirror-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'subagent-card-mirror-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'subagent_card',
                taskId: 'subagent-mirror-1',
                label: 'Airport concept media',
                summary: 'Generated image delivered',
                expanded: false,
                children: [
                  {
                    id: 'subagent-text-mirror-1',
                    kind: 'text',
                    order: 0,
                    status: 'completed',
                    visible: true,
                    uiKind: 'text',
                    payload: {
                      text: 'Nested subagent summary',
                    },
                  },
                  {
                    id: 'subagent-generation-mirror-1',
                    kind: 'tool',
                    order: 1,
                    status: 'completed',
                    visible: true,
                    uiKind: 'generation_task',
                    payload: {
                      tool_name: 'generate_image',
                      prompt: 'airport concept poster',
                      model: 'seedream',
                      provider: 'builtin',
                      progress: 100,
                      task_id: 199,
                      status: 'completed',
                      meta: { media_type: 'image' },
                      result: {
                        task_id: 199,
                        status: 'completed',
                        result_url: '/generated/airport-poster.png',
                        model_label: 'Seedream-5.0-Lite',
                        model_name: 'seedream',
                        provider_code: 'builtin',
                        params: {
                          resolution: '1K',
                          aspect_ratio: '1:1',
                        },
                        canvas_item: {
                          id: 'canvas-subagent-mirror-199',
                          type: 'image_generator',
                          task_id: 199,
                          prompt: 'airport concept poster',
                          x: 100,
                          y: 120,
                          aspect_ratio: '1:1',
                          resolution: '1K',
                          model_name: 'seedream',
                          model_label: 'Seedream-5.0-Lite',
                          provider_code: 'builtin',
                          status: 'completed',
                          url: '/generated/airport-poster.png',
                        },
                      },
                    },
                  },
                ],
                payload: {
                  tool_name: 'Agent',
                  status: 'completed',
                  result: {
                    task_id: 'subagent-mirror-1',
                    label: 'Airport concept media',
                    status: 'completed',
                    result: 'Generated image delivered',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Airport concept media')).toBeInTheDocument()
    expect(screen.queryByText('Generated image delivered')).not.toBeInTheDocument()
    expect(screen.queryByText('Nested subagent summary')).not.toBeInTheDocument()
    expect(screen.getAllByText('Seedream-5.0-Lite').length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(onCanvasUpdateMock).toHaveBeenCalledWith(
        'add_generated_media',
        expect.objectContaining({
          id: 'canvas-subagent-mirror-199',
          messageId: 'assistant-subagent-mirror-1',
          agentMediaKey: 'canvas-subagent-mirror-199',
          url: 'http://localhost:8000/api/v1/uploads/generated/airport-poster.png',
        }),
      )
    })

    fireEvent.click(screen.getByText('Airport concept media'))

    await waitFor(() => {
      expect(screen.getByText('Nested subagent summary')).toBeInTheDocument()
    })

    expect(
      onCanvasUpdateMock.mock.calls.filter(([action]) => action === 'add_generated_media'),
    ).toHaveLength(1)
  })

  it('does not hydrate failed history generation cards again after reload', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-history-failed-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            isHistoryLoaded: true,
            blocks: [
              {
                id: 'generation-history-failed-1',
                kind: 'tool',
                order: 0,
                status: 'failed',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a failed poster concept',
                  task_id: 302,
                  status: 'failed',
                  result: {
                    task_id: 302,
                    status: 'failed',
                    canvas_item: {
                      id: 'canvas-history-failed-302',
                      type: 'image_generator',
                      task_id: 302,
                      prompt: 'a failed poster concept',
                      x: 100,
                      y: 120,
                      aspect_ratio: '1:1',
                      resolution: '1K',
                      model_name: 'seedream',
                      model_label: 'Seedream-5.0-Lite',
                      provider_code: 'builtin',
                      status: 'failed',
                      url: '',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(screen.getAllByText('canvas.generator.failed_label').length).toBeGreaterThan(0)
    })

    expect(queryTaskMock).not.toHaveBeenCalled()
  })

  it('does not show failed tooltips for history-loaded generation cards', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-history-failed-tooltip-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            isHistoryLoaded: true,
            blocks: [
              {
                id: 'generation-history-failed-tooltip-1',
                kind: 'tool',
                order: 0,
                status: 'failed',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a failed city poster',
                  task_id: 402,
                  status: 'failed',
                  error_message: '鍘嗗彶澶辫触璇︽儏',
                  result: {
                    task_id: 402,
                    status: 'failed',
                    error_message: '鍘嗗彶澶辫触璇︽儏',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    const failedLabels = await screen.findAllByText('canvas.generator.failed_label')
    failedLabels.forEach((label) => {
      fireEvent.mouseEnter(label)
    })

    await waitFor(() => {
      expect(screen.queryByText('鍘嗗彶澶辫触璇︽儏')).not.toBeInTheDocument()
    })
  })

  it('renders failed history harness generation cards without polling for retries', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-history-retrying-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            isHistoryLoaded: true,
            blocks: [
              {
                id: 'generation-history-retrying-1',
                kind: 'tool',
                order: 0,
                status: 'failed',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a retrying poster concept',
                  task_id: 'h-task-902-old',
                  status: 'failed',
                  result: {
                    task_id: 'h-task-902-old',
                    artifact_ref: 'artifact_ref:harness-retrying-image',
                    status: 'failed',
                    canvas_item: {
                      id: 'canvas-history-retry-902',
                      type: 'image_generator',
                      task_id: 'h-task-902-old',
                      prompt: 'a retrying poster concept',
                      x: 100,
                      y: 120,
                      aspect_ratio: '1:1',
                      resolution: '1K',
                      model_name: 'seedream',
                      model_label: 'Seedream-5.0-Lite',
                      provider_code: 'builtin',
                      status: 'failed',
                      url: '',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getAllByText('canvas.generator.failed_label').length).toBeGreaterThan(0)
    expect(queryTaskMock).not.toHaveBeenCalled()
    expect(updateToolCallMock).not.toHaveBeenCalled()
  })

  it('does not replay history generation cards into canvas when they are reloaded from past messages', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-history-failed-replay-1',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            isHistoryLoaded: true,
            blocks: [
              {
                id: 'generation-history-failed-replay-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'generation_task',
                payload: {
                  tool_name: 'generate_image',
                  prompt: 'a failed scenic poster',
                  task_id: 502,
                  status: 'completed',
                  result: {
                    task_id: 502,
                    canvas_item: {
                      id: 'canvas-history-failed-replay-502',
                      type: 'image_generator',
                      task_id: 502,
                      prompt: 'a failed scenic poster',
                      x: 100,
                      y: 120,
                      aspect_ratio: '1:1',
                      resolution: '1K',
                      model_name: 'seedream',
                      model_label: 'Seedream-5.0-Lite',
                      provider_code: 'builtin',
                      status: 'generating',
                      url: '',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(queryTaskMock).not.toHaveBeenCalled()
    expect(onCanvasUpdateMock).not.toHaveBeenCalled()
  })

  it('renders a v2 subagent card with nested progress blocks', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-subagent-v2',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'subagent-task-1',
                kind: 'tool',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'subagent_card',
                taskId: 'subagent-task-1',
                label: 'Notes QA',
                summary: 'Notes look good',
                expanded: false,
                payload: {
                  taskId: 'subagent-task-1',
                  task_id: 'subagent-task-1',
                  label: 'Notes QA',
                  status: 'completed',
                  result: {
                    usage: { input_tokens: 7, output_tokens: 3 },
                  },
                },
                children: [
                  {
                    id: 'child-text-1',
                    kind: 'text',
                    order: 0,
                    status: 'completed',
                    visible: true,
                    uiKind: 'text',
                    payload: { text: 'Inspecting notes' },
                  },
                  {
                    id: 'child-tool-1',
                    kind: 'tool',
                    order: 1,
                    status: 'completed',
                    visible: true,
                    uiKind: 'compact_tool',
                    payload: {
                      tool_name: 'file_read',
                      result: {
                        output: 'first line',
                        is_error: false,
                        elapsed_ms: 12,
                      },
                    },
                  },
                ],
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Notes QA')).toBeInTheDocument()
    expect(screen.queryByText('Inspecting notes')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Notes QA/ }))

    await waitFor(() => {
      expect(screen.getByText('Notes look good')).toBeInTheDocument()
      expect(screen.getByText('Inspecting notes')).toBeInTheDocument()
      expect(screen.getByText('file_read')).toBeInTheDocument()
    })
  })

  it('adds a fixed custom option entry and submits free-form input without duplicating model-provided other options', async () => {
    respondToAgentMock.mockResolvedValue(undefined)

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-3',
            role: 'assistant',
            content: null,
            createdAt: '2026-03-30T00:00:00Z',
            blocks: [
              {
                id: 'ask-2',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'choice_prompt',
                payload: {
                  requestId: 'req-2',
                  question: 'Which direction feels best?',
                  inputType: 'cards',
                  status: 'waiting',
                  options: [
                    { label: 'Option A', value: 'a' },
                    { label: 'Other', value: 'other' },
                    { label: 'Custom idea', value: 'custom' },
                  ],
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Option A')).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'Custom idea' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Other' }))

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'Make it more minimal' } })
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[buttons.length - 1]!)

    await waitFor(() => {
      expect(respondToAgentMock).toHaveBeenCalledWith(
        'req-2',
        JSON.stringify({
          response: {
            type: 'other',
            value: 'Make it more minimal',
            label: 'Other: Make it more minimal',
          },
        }),
        'Other: Make it more minimal',
        {
          response: {
            type: 'other',
            value: 'Make it more minimal',
            label: 'Other: Make it more minimal',
          },
        },
      )
    })
  })

  it('renders harness interaction_form cards from schema payloads and submits the selected option', async () => {
    respondToAgentMock.mockResolvedValue(undefined)

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-interaction',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'interaction-form-1',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'interaction_form',
                payload: {
                  request_id: 'functions.ask_user:0',
                  question: 'Which direction should we explore?',
                  kind: 'ask_user',
                  status: 'pending',
                  schema: {
                    title: 'Direction',
                    questions: [
                      {
                        id: 'direction',
                        header: 'Direction',
                        question: 'Direction',
                        type: 'single',
                        options: [
                          { label: 'Option A', value: 'a' },
                          { label: 'Other', value: 'other' },
                        ],
                      },
                    ],
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Option A' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => {
      expect(respondToAgentMock).toHaveBeenCalledWith(
        'functions.ask_user:0',
        JSON.stringify({
          direction: {
            type: 'option',
            value: 'a',
            label: 'Option A',
          },
        }),
        'Option A',
        {
          direction: {
            type: 'option',
            value: 'a',
            label: 'Option A',
          },
        },
      )
    })
  })

  it('renders ecommerce generation options interaction forms', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-ecommerce-options',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'interaction-form-ecommerce-options',
                kind: 'interaction',
                order: 0,
                status: 'pending',
                visible: true,
                uiKind: 'interaction_form',
                payload: {
                  request_id: 'call-ecommerce-options',
                  requestId: 'call-ecommerce-options',
                  question: '商品图生成配置',
                  kind: 'ecommerce_generation_options',
                  status: 'pending',
                  defaults: {
                    generation_count: 4,
                    generation_count_min: 1,
                    generation_count_max: 6,
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(await screen.findByText('agent.ecommerceInteraction.options.title')).toBeInTheDocument()
    expect(screen.getByLabelText('agent.ecommerceInteraction.options.category')).toBeInTheDocument()
    expect(screen.getByLabelText('agent.ecommerceInteraction.options.style')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'agent.ecommerceInteraction.actions.submit' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'agent.ecommerceInteraction.actions.cancel' })).toBeEnabled()
  })

  it('submits multi-field harness interaction_form answers as structured quick-brief payloads', async () => {
    respondToAgentMock.mockResolvedValue(undefined)

    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-interaction-multi',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'interaction-form-2',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'interaction_form',
                payload: {
                  request_id: 'functions.ask_user:1',
                  question: 'Need a few choices',
                  kind: 'ask_user',
                  status: 'pending',
                  schema: {
                    title: 'Quick brief',
                    submit_label: 'Submit',
                    questions: [
                      {
                        id: 'direction',
                        header: 'Direction',
                        question: 'Direction',
                        type: 'single',
                        required: true,
                        options: [
                          { label: 'Option A', value: 'a' },
                          { label: 'Option B', value: 'b' },
                        ],
                      },
                      {
                        id: 'tone',
                        header: 'Tone',
                        question: 'Tone',
                        type: 'input',
                        required: true,
                        placeholder: 'Describe the tone',
                      },
                    ],
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Option A' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Tone' }), { target: { value: 'Warm and editorial' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

    await waitFor(() => {
      expect(respondToAgentMock).toHaveBeenCalledWith(
        'functions.ask_user:1',
        JSON.stringify({
          direction: {
            type: 'option',
            value: 'a',
            label: 'Option A',
          },
          tone: {
            type: 'input',
            value: 'Warm and editorial',
            label: 'Warm and editorial',
          },
        }),
        'Option A / Warm and editorial',
        {
          direction: {
            type: 'option',
            value: 'a',
            label: 'Option A',
          },
          tone: {
            type: 'input',
            value: 'Warm and editorial',
            label: 'Warm and editorial',
          },
        },
      )
    })
  })

  it('renders interaction briefing from parent assistant content when block payload has no content or question', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-parent-content',
            role: 'assistant',
            content: '### Gate A：品牌战略简报\n\n- 两岸文化融合\n- 商务办公第三空间',
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'interaction-form-parent-content',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'interaction_form',
                payload: {
                  request_id: 'functions.ask_user:parent-content',
                  kind: 'ask_user',
                  status: 'pending',
                  schema: {
                    title: 'Gate A：品牌战略简报确认',
                    submit_label: '确认并继续',
                    questions: [
                      {
                        id: 'approval',
                        header: '是否继续',
                        question: '是否继续',
                        type: 'single',
                        options: [{ label: '继续', value: 'continue' }],
                      },
                    ],
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Gate A：品牌战略简报', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('两岸文化融合')).toBeInTheDocument()
  })

  it('disables harness interaction_form cards once a user reply appears below them', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-interaction-answered',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'interaction-form-answered',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'interaction_form',
                payload: {
                  request_id: 'functions.ask_user:2',
                  question: 'Which direction should we explore?',
                  kind: 'ask_user',
                  status: 'pending',
                  schema: {
                    title: 'Direction',
                    questions: [
                      {
                        id: 'direction',
                        header: 'Direction',
                        question: 'Direction',
                        type: 'single',
                        options: [
                          { label: 'Option A', value: 'a' },
                          { label: 'Option B', value: 'b' },
                        ],
                      },
                    ],
                  },
                },
              },
            ],
          },
          {
            id: 'user-follow-up',
            role: 'user',
            content: 'Pick option A',
            createdAt: '2026-05-11T00:00:05Z',
            blocks: [],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByRole('button', { name: 'Option A' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Option B' })).toBeDisabled()
  })

  it('renders harness interaction_form cards with a stable sidebar width', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-interaction-width',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'interaction-form-width',
                kind: 'interaction',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'interaction_form',
                payload: {
                  request_id: 'functions.ask_user:width',
                  question: 'Which direction should we explore?',
                  kind: 'ask_user',
                  status: 'pending',
                  schema: {
                    title: 'Direction',
                    submit_label: 'Submit',
                    questions: [
                      {
                        id: 'direction',
                        header: 'Direction',
                        question: 'Direction',
                        type: 'single',
                        options: [
                          { label: 'Option A', value: 'a' },
                          { label: 'Option B', value: 'b' },
                        ],
                      },
                    ],
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByTestId('interaction-block-shell')).toHaveStyle({ width: '85%', maxWidth: '85%' })
    expect(screen.getByTestId('interaction-card-shell')).toHaveStyle({ width: '100%' })
  })

  it('renders completed harness media_card generation blocks from projection payloads', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-generation',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'media-functions.generate_image:0',
                kind: 'content',
                order: 0,
                status: 'processing',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  tool_name: 'generate_image',
                  call_id: 'functions.generate_image:0',
                  media_type: 'image_generation',
                  status: 'completed',
                  task_id: 'h-task-1',
                  result_url: 'assets/references/generated_image_001/original.png',
                  model_label: 'GPT-Image 2',
                  resolution: '4K',
                  aspect_ratio: '1:1',
                  prompt: 'A monkey portrait',
                  canvas_item: {
                    id: 'canvas-h-task-1',
                    type: 'image_generator',
                    task_id: 'h-task-1',
                    status: 'completed',
                    url: 'assets/references/generated_image_001/original.png',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('GPT-Image 2')).toBeInTheDocument()

    await waitFor(() => {
      expect(onCanvasUpdateMock).toHaveBeenCalledWith(
        'add_generated_media',
        expect.objectContaining({
          status: 'completed',
          id: 'canvas-h-task-1',
          url: expect.stringContaining('assets%2Freferences%2Fgenerated_image_001%2Foriginal.png'),
        }),
      )
    })
    expect(queryTaskMock).not.toHaveBeenCalled()
  })

  it('renders harness media_card metadata when it is nested under the result payload', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-generation-nested-result',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'media-functions.generate_image:nested',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  tool_name: 'generate_image',
                  call_id: 'functions.generate_image:nested',
                  media_type: 'image_generation',
                  status: 'completed',
                  task_id: 'h-task-nested',
                  result_url: '/generated/monkey.png',
                  result: {
                    task_id: 'h-task-nested',
                    status: 'completed',
                    result_url: '/generated/monkey.png',
                    model_name: 'doubao-seedream-5-0-lite',
                    model_label: 'Seedream 5.0 Lite',
                    provider_code: 'builtin',
                    params: {
                      resolution: '2K',
                      aspect_ratio: '1:1',
                    },
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Seedream 5.0 Lite')).toBeInTheDocument()
    expect(screen.getByText('2K')).toBeInTheDocument()
  })

  it('renders aliased model names for generation media cards when only a raw suffixed model name is present', () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-generation-alias',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'media-functions.generate_image:alias',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  tool_name: 'generate_image',
                  call_id: 'functions.generate_image:alias',
                  media_type: 'image_generation',
                  status: 'completed',
                  task_id: 'h-task-alias',
                  model_name: 'doubao-seedream-5-0-260128',
                  resolution: '4K',
                  aspect_ratio: '1:1',
                  prompt: 'A monkey portrait',
                  result_url: '/generated/monkey.png',
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    expect(screen.getByText('Seedream 5.0')).toBeInTheDocument()
    expect(screen.queryByText('doubao-seedream-5-0-260128')).not.toBeInTheDocument()
  })

  it('inserts harness media_card placeholders into the canvas immediately when the payload includes a canvas item', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-generation-placeholder',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'media-functions.generate_image:placeholder',
                kind: 'content',
                order: 0,
                status: 'processing',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  tool_name: 'generate_image',
                  call_id: 'functions.generate_image:placeholder',
                  media_type: 'image_generation',
                  status: 'processing',
                  task_id: 'h-task-placeholder',
                  canvas_revision: 23,
                  prompt: 'A monkey placeholder',
                  canvas_item: {
                    id: 'canvas-h-placeholder',
                    type: 'image_generator',
                    task_id: 'h-task-placeholder',
                    status: 'generating',
                    url: '',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(onCanvasUpdateMock).toHaveBeenCalledWith(
        'add',
        expect.objectContaining({
          id: 'canvas-h-placeholder',
          type: 'image_generator',
          status: 'generating',
        }),
      )
    })
    expect(onCanvasUpdateMock).toHaveBeenNthCalledWith(
      1,
      'sync_canvas_revision',
      {},
      { canvasRevision: 23, canvasItemDeleted: false },
    )
  })

  it('syncs canvas revision before replacing a harness media_card placeholder with completed media', async () => {
    render(
      <MessageList
        messages={[
          {
            id: 'assistant-harness-generation-completed',
            role: 'assistant',
            content: null,
            createdAt: '2026-05-11T00:00:00Z',
            blocks: [
              {
                id: 'media-functions.generate_image:completed',
                kind: 'content',
                order: 0,
                status: 'completed',
                visible: true,
                uiKind: 'media_card',
                payload: {
                  tool_name: 'generate_image',
                  call_id: 'functions.generate_image:completed',
                  media_type: 'image_generation',
                  status: 'completed',
                  task_id: 'h-task-completed',
                  result_url: '/api/v1/uploads/canvas/1/completed.png',
                  canvas_revision: 31,
                  canvas_item_deleted: false,
                  canvas_item: {
                    id: 'canvas-h-completed',
                    type: 'image',
                    task_id: 'h-task-completed',
                    status: 'completed',
                    url: '/api/v1/uploads/canvas/1/completed.png',
                  },
                },
              },
            ],
          },
        ]}
        streamingBlocks={[]}
        isStreaming={false}
      />,
    )

    await waitFor(() => {
      expect(onCanvasUpdateMock).toHaveBeenCalledWith(
        'add_generated_media',
        expect.objectContaining({
          id: 'canvas-h-completed',
          type: 'image',
          status: 'completed',
          url: expect.stringContaining('/api/v1/uploads/canvas/1/completed.png'),
        }),
      )
    })
    expect(onCanvasUpdateMock).toHaveBeenNthCalledWith(
      1,
      'sync_canvas_revision',
      {},
      { canvasRevision: 31, canvasItemDeleted: false },
    )
  })



})
