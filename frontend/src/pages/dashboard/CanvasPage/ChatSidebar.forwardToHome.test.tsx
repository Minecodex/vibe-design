import type { ComponentProps } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const saveHomeForwardTransferMock = vi.fn()
const toastErrorMock = vi.fn()
const authStoreState = {
  user: { id: 1 },
  licenseEdition: 'flagship' as 'flagship' | 'premium',
}

const mockStoreState = {
  messages: [
    {
      id: 'assistant-1',
      role: 'assistant',
      content: 'First selected reply',
      createdAt: '2026-04-23T00:00:00Z',
      blocks: [],
    },
  ],
  activePlan: null,
  isStreaming: false,
  mode: 'fast',
  activeSkillId: null,
  streamingBlocks: [],
  conversations: [],
  conversationId: null as string | number | null,
  conversationSessions: {} as Record<string, { runStatus: 'idle' | 'running' | 'waiting_input' | 'completed' | 'failed' | 'blocked' | 'cancelled' }>,
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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    i18n: { language: 'zh-CN' },
  }),
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => authStoreState,
}))

vi.mock('@/store/appConfigStore', () => ({
  useAppConfigStore: (selector: (state: unknown) => unknown) => selector({ appName: 'Test App', appNameEn: 'Test App' }),
}))

vi.mock('@/api/endpoints/providers', () => ({
  providersApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
    getRegistry: vi.fn().mockResolvedValue({ data: {} }),
    listModels: vi.fn().mockResolvedValue({ data: [] }),
  },
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    uploadAttachment: vi.fn(),
  },
}))

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

vi.mock('../HomeHarnessAgent/homeForwardTransfer', () => ({
  buildHomeForwardTransferReference: (asset: { url: string }) => ({
    id: `home-asset:${asset.url}`,
    kind: 'home_asset',
    media_type: 'image',
    display_name: 'source.png',
    source: {
      type: 'home_asset',
      url: asset.url,
    },
  }),
  saveHomeForwardTransfer: (...args: unknown[]) => saveHomeForwardTransferMock(...args),
}))

vi.mock('./MessageList', () => ({
  MessageList: ({ forwardSelectionMode, selectedForwardMessageIds, onEnterForwardSelectionMode, onToggleForwardMessage }: ComponentProps<typeof import('./MessageList').MessageList>) => (
    <div data-testid="mock-message-list">
      {forwardSelectionMode ? (
        <label>
          <input
            type="checkbox"
            aria-label="mock-forward-checkbox"
            checked={selectedForwardMessageIds?.has('message:assistant-1:content')}
            onChange={() => onToggleForwardMessage?.('message:assistant-1:content')}
          />
          assistant-1
        </label>
      ) : (
        <button type="button" onClick={() => onEnterForwardSelectionMode?.('message:assistant-1:content')}>
          open-forward-mode
        </button>
      )}
    </div>
  ),
}))

vi.mock('./AssetLibraryModal', () => ({
  AssetLibraryModal: ({ open, initialProject, allowEmptySelection, onSelect }: ComponentProps<typeof import('./AssetLibraryModal').AssetLibraryModal>) => (
    open ? (
      <div data-testid="forward-asset-library">
        <span>{`project-${initialProject?.project_id}`}</span>
        <span>{allowEmptySelection ? 'allow-empty' : 'require-selection'}</span>
        <button type="button" onClick={() => onSelect?.([])}>
          confirm-no-assets
        </button>
        <button
          type="button"
          onClick={() => onSelect?.([{
            id: 12,
            url: '/api/v1/uploads/canvas/7/source.png',
            type: 'image',
            origin_kind: 'local_upload',
            source_asset_id: null,
          }])}
        >
          confirm-one-asset
        </button>
      </div>
    ) : null
  ),
}))

vi.mock('@/store/canvasAgentStore', () => ({
  useChatStore: (selector?: (state: typeof mockStoreState) => unknown) =>
    selector ? selector(mockStoreState) : mockStoreState,
}))

import { ChatSidebar } from './ChatSidebar'

describe('ChatSidebar forward to home flow', () => {
  beforeEach(() => {
    saveHomeForwardTransferMock.mockReset()
    toastErrorMock.mockReset()
    mockStoreState.conversationId = null
    mockStoreState.conversationSessions = {}
    authStoreState.licenseEdition = 'flagship'
    vi.stubGlobal('open', vi.fn(() => ({ closed: false })))
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'test-key') })
  })

  it('shows generate buttons in selection mode, keeps them visible when nothing is selected, and forwards selected text without images', async () => {
    const user = userEvent.setup()

    render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    await user.click(screen.getByRole('button', { name: 'open-forward-mode' }))

    const documentButton = screen.getByRole('button', { name: 'Document Generate' })
    expect(documentButton).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'PPT Generate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Spreadsheet Generate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Web Generate' })).toBeInTheDocument()
    expect(screen.queryByText('General Mode')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel forward selection' })).toBeInTheDocument()
    expect(documentButton).not.toBeDisabled()

    await user.click(screen.getByRole('checkbox', { name: 'mock-forward-checkbox' }))

    expect(screen.getByRole('button', { name: 'Document Generate' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'PPT Generate' })).toBeDisabled()

    await user.click(screen.getByRole('checkbox', { name: 'mock-forward-checkbox' }))
    await user.click(screen.getByRole('button', { name: 'Document Generate' }))

    expect(screen.getByTestId('forward-asset-library')).toBeInTheDocument()
    expect(screen.getByText('project-7')).toBeInTheDocument()
    expect(screen.getByText('allow-empty')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'confirm-no-assets' }))

    expect(saveHomeForwardTransferMock).toHaveBeenCalledWith(expect.objectContaining({
      key: 'home-forward-transfer:test-key',
      projectId: 7,
      mode: 'document',
      text: 'First selected reply',
      attachments: [],
    }))
    expect(window.open).toHaveBeenCalledWith('', '_blank')
  })

  it('supports Escape to exit selection mode and resets when the conversation changes', async () => {
    const user = userEvent.setup()
    const view = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    await user.click(screen.getByRole('button', { name: 'open-forward-mode' }))
    expect(screen.getByRole('button', { name: 'Cancel forward selection' })).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('button', { name: 'Cancel forward selection' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'open-forward-mode' }))
    mockStoreState.conversationId = 99
    view.rerender(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    expect(screen.queryByRole('button', { name: 'Cancel forward selection' })).not.toBeInTheDocument()
  })

  it('forwards selected canvas assets with structured homepage references', async () => {
    const user = userEvent.setup()

    render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    await user.click(screen.getByRole('button', { name: 'open-forward-mode' }))
    await user.click(screen.getByRole('button', { name: 'Document Generate' }))
    await user.click(screen.getByRole('button', { name: 'confirm-one-asset' }))

    expect(saveHomeForwardTransferMock).toHaveBeenCalledWith(expect.objectContaining({
      attachments: [
        expect.objectContaining({
          id: 12,
          url: '/api/v1/uploads/canvas/7/source.png',
          reference: {
            id: 'home-asset:/api/v1/uploads/canvas/7/source.png',
            kind: 'home_asset',
            media_type: 'image',
            display_name: 'source.png',
            source: {
              type: 'home_asset',
              url: '/api/v1/uploads/canvas/7/source.png',
            },
          },
        }),
      ],
    }))
  })

  it('does not show home forwarding generate actions for premium edition', async () => {
    authStoreState.licenseEdition = 'premium'
    const user = userEvent.setup()

    render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    await user.click(screen.getByRole('button', { name: 'open-forward-mode' }))

    expect(screen.queryByRole('button', { name: 'Document Generate' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'PPT Generate' })).not.toBeInTheDocument()
  })

  it('keeps the composer locked while the canvas agent is still running even when the transport is not streaming', () => {
    mockStoreState.isStreaming = false
    mockStoreState.conversationId = 'conv-running'
    mockStoreState.conversationSessions = {
      'conv-running': {
        runStatus: 'running',
      },
    }

    const { container } = render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    const composer = container.querySelector('[contenteditable]')
    expect(composer).toHaveAttribute('contenteditable', 'false')
  })

  it('keeps the stop control available while the canvas agent is still running even when the transport is not streaming', async () => {
    const user = userEvent.setup()
    mockStoreState.isStreaming = false
    mockStoreState.conversationId = 'conv-running'
    mockStoreState.conversationSessions = {
      'conv-running': {
        runStatus: 'running',
      },
    }

    render(
      <ChatSidebar
        isOpen
        onClose={vi.fn()}
        projectId={7}
        canvasItems={[]}
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

    const stopButton = screen.getByRole('button', { name: 'Stop agent response' })
    await user.click(stopButton)

    expect(mockStoreState.stopStreaming).toHaveBeenCalledTimes(1)
  })
})
