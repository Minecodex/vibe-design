import type { ComponentProps } from 'react'
import type { AgentLazyMedia } from '../agentMedia/AgentLazyMedia'
import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'
import { httpResponse } from '@/store/testing/harnessStateFixtures'
import { providerListResponse, providerRegistryResponse, providerModelsResponse } from '@/store/testing/providerFixtures'
import { fireEvent, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const chatStoreState = {
  messages: [],
  activePlan: null,
  isStreaming: false,
  mode: 'agent',
  activeSkillId: null,
  streamingBlocks: [],
  conversationSessions: {},
  conversations: [],
  conversationId: 123 as string | number | null,
  webSearchEnabled: false,
  modelPreferences: {},
  syncScope: vi.fn(),
  sendMessage: vi.fn(),
  stopStreaming: vi.fn(),
  approvePlan: vi.fn(),
  rejectPlan: vi.fn(),
  setMode: vi.fn(),
  activateSkill: vi.fn(),
  loadConversations: vi.fn(),
  loadConversation: vi.fn(),
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  setWebSearchEnabled: vi.fn(),
  setModelPreferences: vi.fn(),
  loadUiConfig: vi.fn(),
}

const authStoreState = {
  user: { id: 1, balance_cents: 10 },
}

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback ?? _key ?? '',
      i18n: {
        language: 'zh-CN',
      },
    }),
  }
})

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({
    user: authStoreState.user,
  }),
}))

vi.mock('@/api/endpoints/providers', () => ({
  providersApi: {
    list: vi.fn(async () => ({ data: [] })),
    getRegistry: vi.fn(async () => ({ data: {} })),
    listModels: vi.fn(async () => ({ data: [] })),
  },
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    uploadAttachment: vi.fn(),
    uploadHarnessAttachment: vi.fn(),
  },
  isHarnessWorkspaceRelativePath: (value: string) => String(value || '').startsWith('references/'),
  normalizeHarnessWorkspacePath: (value: string) => String(value || ''),
}))

vi.mock('../agentMedia/agentPendingAttachmentPreview', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../agentMedia/agentPendingAttachmentPreview')>()
  return {
    ...actual,
    createPendingAttachmentId: vi.fn(() => `pending-${Math.random().toString(36).slice(2)}`),
    enqueueLocalImageThumbnail: vi.fn(async () => ({
      preview_url: 'blob:pending-thumb',
      _previewObjectUrl: 'blob:pending-thumb',
    })),
  }
})

vi.mock('@/utils/balanceGuard', () => ({
  ensureBalanceOrNotify: vi.fn(() => true),
  isBalanceRequiredForMultimodalProvider: vi.fn((providerCode?: string | null) => String(providerCode || '').trim().toLowerCase() !== 'ollama'),
}))

vi.mock('./MessageList', () => ({
  MessageList: () => <div data-testid="message-list" />,
}))

vi.mock('./PlanCard', () => ({
  PlanCard: () => <div data-testid="plan-card" />,
}))

vi.mock('./SkillLibraryButton', () => ({
  SkillLibraryButton: () => <div data-testid="skill-library-button" />,
}))

vi.mock('../agentMedia/AgentLazyMedia', () => ({
  AgentLazyMedia: ({ src, alt, className, mediaClassName, onClick }: ComponentProps<typeof AgentLazyMedia>) => (
    <div className={className} onClick={onClick}>
      {src ? <img src={src} alt={alt || ''} className={mediaClassName} /> : null}
    </div>
  ),
}))

const newChatMock = vi.fn()

vi.mock('@/store/canvasAgentStore', () => ({
  useChatStore: Object.assign(
    (selector?: (state: unknown) => unknown) => {
      return selector ? selector(chatStoreState) : chatStoreState
    },
    {
      getState: () => ({
        conversationId: chatStoreState.conversationId,
        modelPreferences: chatStoreState.modelPreferences,
        newChat: newChatMock,
      }),
    },
  ),
}))

import { ChatSidebar } from './ChatSidebar'
import { agentApi } from '@/api/endpoints/agent'
import { providersApi } from '@/api/endpoints/providers'
import { ensureBalanceOrNotify } from '@/utils/balanceGuard'
import { __canvasModelCatalogTestUtils } from './canvasModelCatalog'

describe('ChatSidebar append mention behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(chatStoreState, {
      messages: [],
      activePlan: null,
      isStreaming: false,
      mode: 'agent',
      activeSkillId: null,
      streamingBlocks: [],
      conversationSessions: {},
      conversations: [],
      conversationId: 123,
      webSearchEnabled: false,
      modelPreferences: {},
    })
    authStoreState.user = { id: 1, balance_cents: 10 }
    __canvasModelCatalogTestUtils.reset()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    })
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: vi.fn(),
    })
  })

  it('allows sending with zero balance when the canvas multimodal provider is Ollama', async () => {
    authStoreState.user = { id: 1, balance_cents: 0 }
    Object.assign(chatStoreState, {
      modelPreferences: {
        multimodal_model: 'gpt-5.5',
        multimodal_provider: 'ollama',
      },
    })

    const { container, getByLabelText } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable]') as HTMLElement
    editor.textContent = 'hello'
    fireEvent.input(editor)
    fireEvent.click(getByLabelText('Send message'))

    await waitFor(() => {
      expect(chatStoreState.sendMessage).toHaveBeenCalledWith('hello', undefined)
    })
    expect(ensureBalanceOrNotify).not.toHaveBeenCalled()
  })

  it('keeps the chat sidebar selectable even when an ancestor disables selection', () => {
    const { container } = render(
      <div style={{ userSelect: 'none' }}>
        <ChatSidebar
          isOpen
          onClose={vi.fn()}
          projectId={1}
          canvasItems={[]}
          appendMentionRequest={null}
          deletedAgentMediaKeys={[]}
          canvasItemsLoaded
          onFocusItem={vi.fn()}
          marks={[]}
          onRemoveMark={vi.fn()}
          onUpdateMarkLabel={vi.fn()}
          onClearMarks={vi.fn()}
          onOpenAttachmentLibrary={vi.fn()}
          assetLibrarySelection={null}
        />
      </div>,
    )

    const sidebar = container.querySelector('[data-testid="chat-sidebar"]') as HTMLDivElement | null
    expect(sidebar).toBeTruthy()
    expect(sidebar?.style.userSelect).toBe('text')
  })

  it('shows the conversation updated time on the right side of the history list', async () => {
    Object.assign(chatStoreState, {
      conversations: [
        {
          id: 123,
          project_id: 1,
          title: 'Recent runway concept',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          created_at: '2026-04-16T08:00:00',
          updated_at: '2026-04-16T08:09:00',
        },
      ],
    })

    const { container, getByTestId } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    fireEvent.click(container.querySelector('.lucide-history')?.parentElement as Element)

    await waitFor(() => {
      expect(getByTestId('conversation-updated-at-123').textContent).toBe('04-16 08:09')
    })
  })

  it('normalizes stale restored model preferences after the canvas model catalog loads', async () => {
    Object.assign(chatStoreState, {
      mode: 'fast',
      modelPreferences: {
        image_model: 'removed-image',
        image_provider: 'removed-provider',
        video_model: 'removed-video',
        video_provider: 'removed-provider',
        multimodal_model: 'removed-chat',
        multimodal_provider: 'removed-provider',
        auto: false,
      },
    })
    vi.mocked(providersApi.list).mockResolvedValueOnce(providerListResponse({
      data: [
        { code: 'builtin', name: 'Builtin', status: 'authorized', is_builtin: true },
      ],
    }))
    vi.mocked(providersApi.getRegistry).mockResolvedValueOnce(providerRegistryResponse({
      data: {
        builtin: {
          models: {
            text2image: [
              { model_name: 'image-live', label: 'Image Live' },
            ],
            text2video: [
              { model_name: 'video-live', label: 'Video Live' },
            ],
            multimodal: [
              {
                model_name: 'kimi-k2.5',
                label: 'Kimi K2.5',
                config: { supports_fast_mode: true },
              },
            ],
          },
        },
      },
    }))
    vi.mocked(providersApi.listModels).mockResolvedValueOnce(providerModelsResponse({
      data: [
        { model_name: 'image-live', model_type: 'text2image', is_enabled: true },
        { model_name: 'video-live', model_type: 'text2video', is_enabled: true },
        { model_name: 'kimi-k2.5', model_type: 'multimodal', is_enabled: true },
      ],
    }))

    render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    await waitFor(() => {
      expect(chatStoreState.setModelPreferences).toHaveBeenCalledWith({
        image_model: 'image-live',
        image_provider: 'builtin',
        video_model: 'video-live',
        video_provider: 'builtin',
        multimodal_model: 'kimi-k2.5',
        multimodal_provider: 'builtin',
        auto: false,
      })
    })
  })

  it('auto-loads the first conversation in the list when the sidebar opens without an active conversation', async () => {
    Object.assign(chatStoreState, {
      conversationId: null,
      conversations: [
        {
          id: 321,
          project_id: 1,
          title: 'First visible conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          created_at: '2026-04-16T08:00:00',
          updated_at: '2026-04-16T08:09:00',
        },
        {
          id: 123,
          project_id: 1,
          title: 'Second visible conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          created_at: '2026-04-15T08:00:00',
          updated_at: '2026-04-15T08:09:00',
        },
      ],
    })

    render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    await waitFor(() => {
      expect(chatStoreState.loadConversation).toHaveBeenCalledWith(321)
    })
  })

  it('does not auto-load the first conversation after the user starts a new chat', async () => {
    Object.assign(chatStoreState, {
      conversationId: 123,
      conversations: [
        {
          id: 321,
          project_id: 1,
          title: 'First visible conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          created_at: '2026-04-16T08:00:00',
          updated_at: '2026-04-16T08:09:00',
        },
      ],
    })
    newChatMock.mockImplementation(() => {
      chatStoreState.conversationId = null
    })

    const { container, rerender } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    fireEvent.click(container.querySelector('.lucide-plus')?.parentElement as Element)

    rerender(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    await waitFor(() => {
      expect(newChatMock).toHaveBeenCalled()
    })
    expect(chatStoreState.loadConversation).not.toHaveBeenCalledWith(321)
  })

  it('shows a small anchored delete popover before removing a conversation from history', async () => {
    Object.assign(chatStoreState, {
      conversationId: 123,
      conversations: [
        {
          id: 123,
          project_id: 1,
          title: 'Conversation to delete',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          created_at: '2026-04-16T08:00:00',
          updated_at: '2026-04-16T08:09:00',
        },
      ],
    })

    const { container, getByTestId, queryByTestId } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    fireEvent.click(container.querySelector('.lucide-history')?.parentElement as Element)

    const row = await waitFor(() => {
      const node = getByTestId('conversation-history-row-123')
      expect(node).toBeTruthy()
      return node
    })

    fireEvent.mouseEnter(row)
    fireEvent.click(getByTestId('conversation-delete-trigger-123'))

    expect(chatStoreState.deleteConversation).not.toHaveBeenCalled()
    const deletePopover = getByTestId('conversation-delete-popover-123')
    expect(deletePopover).toBeTruthy()
    expect(row.contains(deletePopover)).toBe(false)

    fireEvent.click(getByTestId('conversation-delete-cancel-123'))
    expect(queryByTestId('conversation-delete-popover-123')).toBeNull()
    expect(chatStoreState.deleteConversation).not.toHaveBeenCalled()

    fireEvent.mouseEnter(row)
    fireEvent.click(getByTestId('conversation-delete-trigger-123'))
    const confirmButton = getByTestId('conversation-delete-confirm-button-123')
    fireEvent.mouseDown(confirmButton)
    expect(queryByTestId('conversation-delete-popover-123')).toBeTruthy()
    fireEvent.click(confirmButton)

    expect(chatStoreState.deleteConversation).toHaveBeenCalledWith(123)
  })

  it('appends the mention inside the existing last line container instead of creating a new root-level line', async () => {
    const canvasItems: CanvasItem[] = [
      { x: 0, y: 0,
        id: 'img-1',
        type: 'image',
        name: 'NanoBanana2',
        url: 'https://example.com/apple.png',
      },
    ]

    const { container, rerender } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    expect(editor).toBeTruthy()

    editor.innerHTML = '<div>2321321321</div>'

    rerender(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={{ itemId: 'img-1', nonce: 1 }}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    await waitFor(() => {
      const trailingLine = editor.firstElementChild as HTMLDivElement | null
      expect(trailingLine?.tagName).toBe('DIV')
      expect(trailingLine?.querySelector('[data-mention-id="img-1"]')).toBeTruthy()
    })
  })

  it('keeps a manually selected @ mention inside the trailing line container instead of inserting a new root-level line', async () => {
    const canvasItems: CanvasItem[] = [
      { x: 0, y: 0,
        id: 'img-1',
        type: 'image',
        name: 'NanoBanana2',
        url: 'https://example.com/apple.png',
      },
    ]

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    expect(editor).toBeTruthy()

    editor.innerHTML = '<div>2321321321</div>@Na'

    const trailingTextNode = editor.lastChild
    expect(trailingTextNode?.nodeType).toBe(Node.TEXT_NODE)

    const selection = window.getSelection()
    expect(selection).toBeTruthy()
    const range = document.createRange()
    range.setStart(trailingTextNode!, trailingTextNode!.textContent!.length)
    range.collapse(true)
    selection!.removeAllRanges()
    selection!.addRange(range)

    fireEvent.input(editor)

    const mentionItem = await waitFor(() => {
      const item = container.querySelector('[data-mention-item-id="img-1"]') as HTMLDivElement | null
      expect(item).toBeTruthy()
      return item!
    })

    fireEvent.click(mentionItem)

    await waitFor(() => {
      const trailingLine = editor.firstElementChild as HTMLDivElement | null
      expect(trailingLine?.tagName).toBe('DIV')
      expect(trailingLine?.querySelector('[data-mention-id="img-1"]')).toBeTruthy()
      const rootLevelMention = Array.from(editor.childNodes).find((node) =>
        node instanceof HTMLElement && node.getAttribute('data-mention-id') === 'img-1',
      )
      expect(rootLevelMention).toBeUndefined()
    })
  })

  it('sends canvas mention chips as deduped structured references', async () => {
    const canvasItems: CanvasItem[] = [
      { x: 0, y: 0,
        id: 'img-local-1',
        type: 'image',
        name: '本地上传图',
        url: '/api/v1/uploads/canvas/1/local-source.png',
        asset_origin: 'local_upload',
      },
    ]

    const { container, getByLabelText } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.innerHTML = [
      '照着 ',
      '<span contenteditable="false" data-mention-id="img-local-1" data-mention-name="本地上传图">本地上传图</span>',
      ' 和 ',
      '<span contenteditable="false" data-mention-id="img-local-1" data-mention-name="本地上传图">本地上传图</span>',
      ' 生成一张新图',
    ].join('')
    fireEvent.input(editor)

    fireEvent.click(getByLabelText('Send message'))

    await waitFor(() => {
      expect(chatStoreState.sendMessage).toHaveBeenCalledWith(
        '照着 @[本地上传图](canvas:img-local-1) 和 @[本地上传图](canvas:img-local-1) 生成一张新图',
        undefined,
        {
          references: [
            {
              id: 'canvas:img-local-1',
              kind: 'canvas_item',
              media_type: 'image',
              display_name: '本地上传图',
              source: {
                type: 'canvas_item',
                item_id: 'img-local-1',
              },
            },
          ],
        },
      )
    })
  })

  it('sends canvas mark chips as structured references with region metadata', async () => {
    const canvasItems: CanvasItem[] = [
      { x: 0, y: 0,
        id: 'img-local-1',
        type: 'image',
        name: '本地上传图',
        url: '/api/v1/uploads/canvas/1/local-source.png',
        asset_origin: 'local_upload',
      },
    ]
    const marks: CanvasMark[] = [
      {
        id: 'mark-1',
        imageItemId: 'img-local-1',
        imageUrl: '/api/v1/uploads/canvas/1/local-source.png',
        number: 1,
        relativeX: 0.42,
        relativeY: 0.61,
        selectedLabel: '葡萄',
        customLabel: null,
        aiLabels: ['葡萄'],
        isAnalyzing: false,
      },
    ]

    const { container, getByLabelText } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={marks}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.innerHTML = [
      '只调整 ',
      '<span contenteditable="false" data-mark-id="mark-1" data-mark-image-id="img-local-1" data-mark-label="葡萄" data-mark-number="1" data-mark-rx="0.42" data-mark-ry="0.61">葡萄</span>',
    ].join('')
    fireEvent.input(editor)

    fireEvent.click(getByLabelText('Send message'))

    await waitFor(() => {
      expect(chatStoreState.sendMessage).toHaveBeenCalledWith(
        '只调整 #[葡萄](canvas-mark:mark-1:image:img-local-1:x:0.42:y:0.61)',
        undefined,
        {
          references: [
            {
              id: 'canvas-mark:mark-1',
              kind: 'canvas_mark',
              media_type: 'image',
              display_name: '葡萄',
              source: {
                type: 'canvas_mark',
                mark_id: 'mark-1',
                image_item_id: 'img-local-1',
              },
              mark: {
                id: 'mark-1',
                image_item_id: 'img-local-1',
                number: 1,
                label: '葡萄',
                position: { x: 0.42, y: 0.61 },
              },
            },
          ],
        },
      )
    })
  })

  it('keeps wheel scrolling inside the mention popup instead of bubbling to outer containers', async () => {
    const onWheel = vi.fn()
    const canvasItems: CanvasItem[] = Array.from({ length: 5 }, (_, index) => ({ x: 0, y: 0,
      id: `img-${index + 1}`,
      type: 'image',
      name: `Image ${index + 1}`,
      url: `https://example.com/image-${index + 1}.png`,
    }))

    const { container } = render(
      <div onWheel={onWheel}>
        <ChatSidebar
          isOpen
          onClose={vi.fn()}
          projectId={1}
          canvasItems={canvasItems}
          appendMentionRequest={null}
          deletedAgentMediaKeys={[]}
          canvasItemsLoaded
          onFocusItem={vi.fn()}
          marks={[]}
          onRemoveMark={vi.fn()}
          onUpdateMarkLabel={vi.fn()}
          onClearMarks={vi.fn()}
          onOpenAttachmentLibrary={vi.fn()}
          assetLibrarySelection={null}
        />
      </div>,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.textContent = '@Im'

    const selection = window.getSelection()
    const range = document.createRange()
    range.selectNodeContents(editor)
    range.collapse(false)
    selection!.removeAllRanges()
    selection!.addRange(range)

    fireEvent.input(editor)

    const mentionList = await waitFor(() => {
      const list = container.querySelector('[data-testid="mention-popup-scroll"]') as HTMLDivElement | null
      expect(list).toBeTruthy()
      return list!
    })

    fireEvent.wheel(mentionList, { deltaY: 80 })

    expect(onWheel).not.toHaveBeenCalled()
  })

  it('prevents horizontal overflow in the mention popup for long item names', async () => {
    const canvasItems: CanvasItem[] = [
      { x: 0, y: 0,
        id: 'img-1',
        type: 'image',
        name: 'This is a very long image name that should never create a horizontal scrollbar in the mention popup',
        url: 'https://example.com/image-1.png',
      },
    ]

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.textContent = '@This'

    const selection = window.getSelection()
    const range = document.createRange()
    range.selectNodeContents(editor)
    range.collapse(false)
    selection!.removeAllRanges()
    selection!.addRange(range)

    fireEvent.input(editor)

    const popup = await waitFor(() => {
      const node = container.querySelector('[data-testid="mention-popup"]') as HTMLDivElement | null
      expect(node).toBeTruthy()
      return node!
    })

    const scrollArea = container.querySelector('[data-testid="mention-popup-scroll"]') as HTMLDivElement | null
    const mentionItem = container.querySelector('[data-mention-item-id="img-1"]') as HTMLDivElement | null

    expect(scrollArea?.style.overflowX).toBe('hidden')
    expect(popup.style.overflowX).toBe('hidden')
    expect(mentionItem?.innerHTML).toContain('min-width: 0;')
  })

  it('still inserts the selected mention when the live DOM selection was temporarily lost', async () => {
    const canvasItems: CanvasItem[] = [
      { x: 0, y: 0,
        id: 'img-1',
        type: 'image',
        name: 'NanoBanana2',
        url: 'https://example.com/apple.png',
      },
    ]

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={canvasItems}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.innerHTML = '<div>2321321321</div>@Na'

    const trailingTextNode = editor.lastChild
    const selection = window.getSelection()
    const range = document.createRange()
    range.setStart(trailingTextNode!, trailingTextNode!.textContent!.length)
    range.collapse(true)
    selection!.removeAllRanges()
    selection!.addRange(range)

    fireEvent.input(editor)

    const mentionItem = await waitFor(() => {
      const item = container.querySelector('[data-mention-item-id="img-1"]') as HTMLDivElement | null
      expect(item).toBeTruthy()
      return item!
    })

    window.getSelection()?.removeAllRanges()
    fireEvent.click(mentionItem)

    await waitFor(() => {
      expect(editor.querySelector('[data-mention-id="img-1"]')).toBeTruthy()
    })
  })

  it('removes a trailing mark chip as one unit when pressing Backspace after it', async () => {
    const onRemoveMark = vi.fn()
    const marks: CanvasMark[] = [
      {
        id: 'mark-1',
        imageItemId: 'img-1',
        imageUrl: 'https://example.com/apple.png',
        number: 1,
        relativeX: 0.25,
        relativeY: 0.5,
        selectedLabel: 'apple',
        customLabel: null,
        aiLabels: ['apple'],
        isAnalyzing: false,
      },
    ]

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={marks}
        onRemoveMark={onRemoveMark}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement

    const chip = await waitFor(() => {
      const node = editor.querySelector('[data-mark-id="mark-1"]') as HTMLElement | null
      expect(node).toBeTruthy()
      return node!
    })

    const trailingTextNode = chip.nextSibling
    expect(trailingTextNode?.nodeType).toBe(Node.TEXT_NODE)
    expect(trailingTextNode?.textContent).toBe('\u00A0')

    const selection = window.getSelection()
    const range = document.createRange()
    range.setStart(trailingTextNode!, 1)
    range.collapse(true)
    selection!.removeAllRanges()
    selection!.addRange(range)

    fireEvent.keyDown(editor, { key: 'Backspace' })

    await waitFor(() => {
      expect(onRemoveMark).toHaveBeenCalledWith('mark-1')
      expect(editor.querySelector('[data-mark-id="mark-1"]')).toBeNull()
    })
  })

  it('appends asset library selections into the attachment preview strip', async () => {
    const { container, rerender } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    rerender(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={{
          nonce: 1,
          assets: [
            {
              id: 42,
              type: 'image',
              url: '/api/v1/uploads/canvas/1/sample-image.png',
              origin_kind: 'local_upload',
              source_asset_id: null,
            },
            {
              id: 43,
              type: 'image',
              url: 'https://example.com/library/sample-image-2.png',
              origin_kind: 'local_upload',
              source_asset_id: null,
            },
          ],
        }}
      />,
    )

    await waitFor(() => {
      const previewImage = container.querySelector('img[src="http://localhost:8000/api/v1/uploads/canvas/1/sample-image.png"]')
      const secondPreviewImage = container.querySelector('img[src="https://example.com/library/sample-image-2.png"]')
      expect(previewImage).toBeTruthy()
      expect(secondPreviewImage).toBeTruthy()
    })

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.textContent = 'Use these product references'
    fireEvent.input(editor)
    const sendButton = container.querySelector('.lucide-arrow-up')?.parentElement as HTMLElement
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(chatStoreState.sendMessage).toHaveBeenCalledWith(
        'Use these product references',
        [
          {
            type: 'image',
            url: '/api/v1/uploads/canvas/1/sample-image.png',
            preview_url: '/api/v1/uploads/canvas/1/sample-image.png',
            name: 'sample-image.png',
            reference: {
              id: 'home-asset:/api/v1/uploads/canvas/1/sample-image.png',
              kind: 'home_asset',
              media_type: 'image',
              display_name: 'sample-image.png',
              source: {
                type: 'home_asset',
                url: '/api/v1/uploads/canvas/1/sample-image.png',
              },
            },
          },
          {
            type: 'image',
            url: 'https://example.com/library/sample-image-2.png',
            preview_url: 'https://example.com/library/sample-image-2.png',
            name: 'sample-image-2.png',
            reference: {
              id: 'home-asset:https://example.com/library/sample-image-2.png',
              kind: 'home_asset',
              media_type: 'image',
              display_name: 'sample-image-2.png',
              source: {
                type: 'home_asset',
                url: 'https://example.com/library/sample-image-2.png',
              },
            },
          },
        ],
        {
          references: [
            {
              id: 'home-asset:/api/v1/uploads/canvas/1/sample-image.png',
              kind: 'home_asset',
              media_type: 'image',
              display_name: 'sample-image.png',
              source: {
                type: 'home_asset',
                url: '/api/v1/uploads/canvas/1/sample-image.png',
              },
            },
            {
              id: 'home-asset:https://example.com/library/sample-image-2.png',
              kind: 'home_asset',
              media_type: 'image',
              display_name: 'sample-image-2.png',
              source: {
                type: 'home_asset',
                url: 'https://example.com/library/sample-image-2.png',
              },
            },
          ],
        },
      )
    })
  })

  it('stages dropped image files locally and uploads them only after submit', async () => {
    vi.mocked(agentApi.uploadHarnessAttachment).mockResolvedValue(httpResponse({
      data: {
        type: 'image',
        url: 'https://example.com/dropped-image.png',
        filename: 'dropped-image.png',
        size: 0,
      },
    }))

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    const file = new File(['image-bytes'], 'drop.png', { type: 'image/png' })
    const preventDefault = vi.fn()

    fireEvent.dragOver(editor, {
      preventDefault,
      dataTransfer: {
        files: [file],
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => file }],
      },
    })

    fireEvent.drop(editor, {
      preventDefault,
      dataTransfer: {
        files: [file],
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => file }],
      },
    })

    expect(agentApi.uploadHarnessAttachment).not.toHaveBeenCalled()

    await waitFor(() => {
      const preview = container.querySelector('img')
      expect(preview).toBeTruthy()
      expect(preview).toHaveAttribute('src', 'blob:pending-thumb')
    })

    editor.textContent = 'Please use this image'
    fireEvent.input(editor)
    const sendButton = container.querySelector('.lucide-arrow-up')?.parentElement as HTMLElement
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(agentApi.uploadHarnessAttachment).toHaveBeenCalledWith('123', file)
    })

    await waitFor(() => {
      expect(chatStoreState.sendMessage).toHaveBeenCalledWith('Please use this image', [
        {
          type: 'image',
          url: 'https://example.com/dropped-image.png',
          name: 'dropped-image.png',
        },
      ], {
        references: [
          {
            id: 'home-asset:https://example.com/dropped-image.png',
            kind: 'home_asset',
            media_type: 'image',
            display_name: 'dropped-image.png',
            source: {
              type: 'home_asset',
              url: 'https://example.com/dropped-image.png',
            },
          },
        ],
      })
    })
  })

  it('uses lightweight pending thumbnails for local image files instead of original object URLs', async () => {
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL')

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const imageFile = new File(['large-image'], 'large.png', { type: 'image/png' })
    fireEvent.change(input, {
      target: {
        files: [imageFile],
      },
    })

    await waitFor(() => {
      expect(container.querySelector('img')).toHaveAttribute('src', 'blob:pending-thumb')
    })
    expect(createObjectUrlSpy).not.toHaveBeenCalledWith(imageFile)
  })

  it('loads the original local image only when previewing a pending canvas attachment', async () => {
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:pending-original')
    const revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL')
    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const imageFile = new File(['large-image'], 'large.png', { type: 'image/png' })
    fireEvent.change(input, {
      target: {
        files: [imageFile],
      },
    })

    const preview = await waitFor(() => {
      const image = container.querySelector('img[src="blob:pending-thumb"]') as HTMLImageElement | null
      expect(image).toBeTruthy()
      return image as HTMLImageElement
    })
    expect(createObjectUrlSpy).not.toHaveBeenCalledWith(imageFile)

    fireEvent.click(preview)

    await waitFor(() => {
      expect(createObjectUrlSpy).toHaveBeenCalledWith(imageFile)
      expect(document.body.querySelector('img[src="blob:pending-original"]')).toBeTruthy()
    })

    const closeButton = document.body.querySelector('button svg.lucide-x')?.closest('button') as HTMLButtonElement | null
    expect(closeButton).toBeTruthy()
    fireEvent.click(closeButton as HTMLButtonElement)
    await waitFor(() => {
      expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:pending-original')
    })
  })

  it('stages supported local files from the picker and uploads them together after submit', async () => {
    Object.assign(chatStoreState, {
      conversationId: null,
      createConversation: vi.fn(async () => {
        chatStoreState.conversationId = 'conv-picker'
      }),
    })

    vi.mocked(agentApi.uploadHarnessAttachment).mockResolvedValue(httpResponse({
      data: {
        type: 'file',
        url: 'assets/inputs/upload_001/source.txt',
        filename: 'brief.txt',
        size: 0,
      },
    }))
    vi.mocked(agentApi.uploadHarnessAttachment).mockResolvedValueOnce(httpResponse({
      data: {
        type: 'file',
        url: 'assets/inputs/upload_001/source.txt',
        filename: 'brief.txt',
        size: 0,
      },
    }))
    vi.mocked(agentApi.uploadHarnessAttachment).mockResolvedValueOnce(httpResponse({
      data: {
        type: 'file',
        url: 'assets/inputs/upload_002/source.docx',
        filename: 'brief.docx',
        size: 0,
      },
    }))

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.accept).toContain('image/*')
    expect(input.accept).toContain('.docx')
    expect(input.accept).toContain('.xlsx')
    expect(input.accept).toContain('.txt')
    expect(input.multiple).toBe(true)

    const textFile = new File(['brief'], 'brief.txt', { type: 'text/plain' })
    const docFile = new File(['doc'], 'brief.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })

    fireEvent.change(input, {
      target: {
        files: [textFile, docFile],
      },
    })

    expect(agentApi.uploadHarnessAttachment).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(container.textContent).toContain('brief.txt')
      expect(container.textContent).toContain('brief.docx')
    })

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    editor.textContent = 'Summarize both files'
    fireEvent.input(editor)
    const sendButton = container.querySelector('.lucide-arrow-up')?.parentElement as HTMLElement
    fireEvent.click(sendButton)

    await waitFor(() => {
      expect(chatStoreState.createConversation).toHaveBeenCalledWith(1)
    })

    await waitFor(() => {
      expect(agentApi.uploadHarnessAttachment).toHaveBeenNthCalledWith(1, 'conv-picker', textFile)
      expect(agentApi.uploadHarnessAttachment).toHaveBeenNthCalledWith(2, 'conv-picker', docFile)
    })

    await waitFor(() => {
      expect(chatStoreState.sendMessage).toHaveBeenCalledWith('Summarize both files', [
        {
          type: 'file',
          url: 'assets/inputs/upload_001/source.txt',
          name: 'brief.txt',
        },
        {
          type: 'file',
          url: 'assets/inputs/upload_002/source.docx',
          name: 'brief.docx',
        },
      ])
    })
  })

  it('keeps plain-text paste behavior when no image files are present', () => {
    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={1}
        canvasItems={[]}
        appendMentionRequest={null}
        deletedAgentMediaKeys={[]}
        canvasItemsLoaded
        onFocusItem={vi.fn()}
        marks={[]}
        onRemoveMark={vi.fn()}
        onUpdateMarkLabel={vi.fn()}
        onClearMarks={vi.fn()}
        onOpenAttachmentLibrary={vi.fn()}
        assetLibrarySelection={null}
      />,
    )

    const editor = container.querySelector('[contenteditable="true"]') as HTMLDivElement
    const preventDefault = vi.fn()

    fireEvent.paste(editor, {
      preventDefault,
      clipboardData: {
        getData: vi.fn((type: string) => type === 'text/plain' ? 'hello world' : ''),
        files: [],
        items: [],
      },
    })

    expect(document.execCommand).toHaveBeenCalledWith('insertText', false, 'hello world')
    expect(agentApi.uploadHarnessAttachment).not.toHaveBeenCalled()
  })
})


