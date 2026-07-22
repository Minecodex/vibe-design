import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import './index.testSetup'
import { ChatHomePage } from './index'
import {
  fetchWorkspaceFileBlobMock,
  fetchWorkspaceFileVersionBlobMock,
  getHarnessDesignSystemMock,
  getHarnessDesignSystemPreviewHtmlUrlMock,
  getHarnessSkillExampleHtmlMock,
  getWorkspaceFileUrlMock,
  listHarnessDesignSystemsMock,
  listHarnessSkillsMock,
  providersListMock,
  providersModelsMock,
  providersRegistryMock,
  scrollToMock,
  setMockLanguage,
  toastErrorMock,
  upsertWorkspaceFileMock,
  sharedStoreSetStateMock,
  storeState,
  uploadAttachmentMock,
  authStoreState,
} from './index.testSetup'
describe('ChatHomePage', () => {
  it('positions a loaded conversation at the latest message', async () => {
    storeState.messages = [{
      id: 'assistant-latest',
      role: 'assistant',
      content: 'Latest response',
      createdAt: '2026-06-02T14:00:00Z',
    }] as any

    render(<ChatHomePage />)

    const messagePane = screen.getByTestId('home-chat-message-scroll')
    await waitFor(() => {
      expect(scrollToMock).toHaveBeenCalledWith({
        top: messagePane.scrollHeight,
        behavior: 'auto',
      })
    })
  })

  it('loads older messages when the user scrolls near the top of the conversation', async () => {
    Object.assign(storeState, {
      olderMessagesHasMore: true,
      messages: [{
        id: 'assistant-latest',
        role: 'assistant',
        content: 'Latest response',
        createdAt: '2026-06-02T14:00:00Z',
      }],
    })
    storeState.loadOlderMessages.mockResolvedValue(undefined)

    render(<ChatHomePage />)

    const messagePane = screen.getByTestId('home-chat-message-scroll')
    Object.defineProperties(messagePane, {
      scrollTop: { configurable: true, value: 0, writable: true },
      scrollHeight: { configurable: true, value: 800, writable: true },
      clientHeight: { configurable: true, value: 400, writable: true },
    })
    fireEvent.scroll(messagePane)

    await waitFor(() => {
      expect(storeState.loadOlderMessages).toHaveBeenCalledTimes(1)
    })
  })

  it('does not render the deprecated top-level plan/runtime summary strip', () => {
    storeState.conversations = [{
      id: 42,
      title: 'Conversation',
      skill_id: null,
      phase: 'executing',
      mode: 'fast',
      status: 'active',
      runtime_status: 'completed',
      run_state: 'completed',
      last_activity_at: '2026-04-27T10:32:18+08:00',
      plan_state: { current_step: 'step-2' },
      engine_version: 'harness',
      run_id: 'run-1',
      started_at: '2026-04-27T10:30:00+08:00',
      finished_at: '2026-04-27T10:35:00+08:00',
    user_interaction: null,
      created_at: '2026-04-27T10:30:00+08:00',
      updated_at: '2026-04-27T10:35:00+08:00',
    }] as any
    storeState.messages = [{
      id: 'assistant-plan',
      role: 'assistant',
      content: null,
      createdAt: '2026-04-27T10:30:00+08:00',
      blocks: [{
        id: 'plan-artifact',
        kind: 'content',
        order: 0,
        status: 'in_progress',
        visible: true,
        uiKind: 'plan_artifact',
        payload: {
          title: 'Task Plan',
          status: 'in_progress',
          current_step: 'step-2',
          steps: [
            { id: 'step-1', order: 1, title: 'Collect evidence', status: 'completed', elapsed_ms: 65000 },
            { id: 'step-2', order: 2, title: 'Draft response', status: 'in_progress', last_activity_at: '2026-04-27T10:32:18+08:00' },
          ],
        },
      }],
    }] as any

    render(<ChatHomePage />)

    expect(screen.queryByText(/计划步骤：/)).not.toBeInTheDocument()
    expect(screen.queryByText(/实际运行：/)).not.toBeInTheDocument()
    expect(screen.queryByText(/最后活动：/)).not.toBeInTheDocument()
  })

  it('does not mutate the shared chat store engine mode on mount', () => {
    render(<ChatHomePage />)

    expect(sharedStoreSetStateMock).not.toHaveBeenCalled()
  })

  it('shows open-design lint warnings from the published artifact manifest', () => {
    ;(storeState as any).runtimeState = {
      artifact_manifest: {
        title: 'Landing',
        kind: 'html',
        entry: 'landing/index.html',
        publication: {
          status: 'published',
          payload: {
            open_design_lint: {
              p0_count: 0,
              p1_count: 1,
              p2_count: 1,
              findings: [
                { severity: 'P1', id: 'all-caps-no-tracking', message: 'Uppercase text needs tracking.' },
                { severity: 'P2', id: 'excessive-icons', message: 'Too many decorative icons.' },
              ],
            },
          },
        },
      },
    }

    render(<ChatHomePage />)

    expect(screen.getByText('P1/P2 lint warnings')).toBeInTheDocument()
    expect(screen.getByText('1 P1, 1 P2')).toBeInTheDocument()
    expect(screen.getByText(/\[P1\] all-caps-no-tracking/)).toBeInTheDocument()
  })

  it('shows the top error banner only for terminal visible runtime failures', () => {
    storeState.conversations = [{
      id: 42,
      title: 'Conversation',
      skill_id: null,
      phase: 'executing',
      mode: 'fast',
      status: 'active',
      runtime_status: 'failed',
      run_state: 'failed',
      runtime_state: {
        conversation_id: '42',
        phase: 'executing',
        run_status: 'failed',
        failure: {
          failure_kind: 'timeout',
          failure_stage: 'executing',
          user_visible: true,
          summary: '模型调用超时',
        },
      },
      engine_version: 'harness',
      run_id: 'run-2',
      started_at: '2026-04-27T10:30:00+08:00',
      finished_at: '2026-04-27T10:35:00+08:00',
      user_interaction: null,
      created_at: '2026-04-27T10:30:00+08:00',
      updated_at: '2026-04-27T10:35:00+08:00',
    }] as any

    render(<ChatHomePage />)

    expect(screen.getByText('最近错误：模型调用超时')).toBeInTheDocument()
  })

  it('hides the top error banner for internal-only failures even when last_error_summary exists', () => {
    storeState.conversations = [{
      id: 42,
      title: 'Conversation',
      skill_id: null,
      phase: 'revising_plan',
      mode: 'fast',
      status: 'active',
      runtime_status: 'failed',
      run_state: 'failed',
      last_error_summary: '执行失败',
      runtime_state: {
        conversation_id: '42',
        phase: 'revising_plan',
        run_status: 'failed',
        failure: {
          failure_kind: 'phase_tool_blocked',
          failure_stage: 'revising_plan',
          user_visible: false,
          summary: '执行失败',
        },
      },
      engine_version: 'harness',
      run_id: 'run-3',
      started_at: '2026-04-27T10:30:00+08:00',
      finished_at: '2026-04-27T10:35:00+08:00',
      user_interaction: null,
      created_at: '2026-04-27T10:30:00+08:00',
      updated_at: '2026-04-27T10:35:00+08:00',
    }] as any

    render(<ChatHomePage />)

    expect(screen.queryByText(/最近错误：/)).not.toBeInTheDocument()
  })

  it('shows the top error banner from persisted failure fallback fields', () => {
    storeState.conversations = [{
      id: 42,
      title: 'Conversation',
      skill_id: null,
      phase: 'executing',
      mode: 'fast',
      status: 'active',
      runtime_status: 'failed',
      run_state: 'failed',
      last_error_summary: '模型服务暂时不可用',
      failure: {
        error_type: 'ModelTurnError',
        summary: '模型服务暂时不可用',
      },
      runtime_state: {
        conversation_id: '42',
        phase: 'executing',
        run_status: 'failed',
      },
      engine_version: 'harness',
      run_id: 'run-4',
      started_at: '2026-04-27T10:30:00+08:00',
      finished_at: '2026-04-27T10:35:00+08:00',
      user_interaction: null,
      created_at: '2026-04-27T10:30:00+08:00',
      updated_at: '2026-04-27T10:35:00+08:00',
    }] as any

    render(<ChatHomePage />)

    expect(screen.getByText('最近错误：模型服务暂时不可用')).toBeInTheDocument()
  })

  it('loads homepage ui config on mount', () => {
    render(<ChatHomePage />)

    expect(storeState.loadUiConfig).toHaveBeenCalledTimes(1)
  })

  it('resets to web mode after starting a new chat from a docx conversation', async () => {
    const user = userEvent.setup()

    Object.assign(storeState, {
      conversationId: 'conv-docx-active',
      activeSkillId: 'docx',
      conversations: [
        {
          id: 'conv-docx-active',
          title: 'Document Conversation',
          skill_id: 'docx',
          mode: 'fast',
          status: 'active',
          runtime_status: 'idle',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
    user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
      ],
    })

    storeState.newChat.mockImplementation(() => {
      storeState.conversationId = null as any
      storeState.messages = []
      storeState.conversations = []
    })
    storeState.createHarnessConversation.mockResolvedValue(undefined)
    storeState.sendMessage.mockResolvedValue(undefined)

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: /new chat/i }))
    await user.type(screen.getByPlaceholderText('Please enter your thoughts'), 'hello')
    await user.click(screen.getByTestId('home-chat-composer-submit-button'))

    await waitFor(() => {
      expect(storeState.createHarnessConversation).toHaveBeenCalledWith(
        undefined,
        expect.objectContaining({
          artifactMode: 'web',
        }),
      )
    })
  })

  it('hides debug-only assistant blocks from the homepage', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-debug',
          role: 'assistant',
          content: null,
          createdAt: '2026-04-20T00:00:00.000Z',
          blocks: [
            {
              id: 'debug-progress',
              kind: 'content',
              order: 0,
              status: 'running',
              visible: true,
              debugOnly: true,
              uiKind: 'compact_tool',
              payload: {
                toolName: 'file_read',
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByText(/Read File/i)).not.toBeInTheDocument()
  })

  it('hides tool cards configured as internal-only', () => {
    Object.assign(storeState, {
      uiConfig: {
        hiddenToolCalls: ['file_read'],
      },
      messages: [
        {
          id: 'assistant-hidden-tool',
          role: 'assistant',
          content: null,
          createdAt: '2026-04-20T00:00:00.000Z',
          blocks: [
            {
              id: 'hidden-tool-card',
              kind: 'tool',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'compact_tool',
              payload: {
                toolName: 'lc_file_read',
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByText(/Read File/i)).not.toBeInTheDocument()
  })

  it('uses solid white surfaces for the sidebar and composer cards', () => {
    const { container } = render(<ChatHomePage />)

    const surfaces = Array.from(container.querySelectorAll('div')).filter((element) => {
      const className = element.className
      return typeof className === 'string' && className.includes('bg-white') && className.includes('rounded')
    })

    const sidebarSurface = surfaces.find((element) => {
      const className = element.className as string
      return className.includes('w-[280px]') && className.includes('rounded-[32px]')
    })

    const composerSurface = Array.from(container.querySelectorAll('div')).find((element) => {
      const className = element.className
      return (
        typeof className === 'string' &&
        className.includes('w-full rounded-2xl border') &&
        className.includes('bg-white')
      )
    })

    expect(sidebarSurface?.className).toContain('bg-white')
    expect(sidebarSurface?.className).not.toContain('bg-white/40')

    expect(composerSurface?.className).toContain('bg-white')
    expect(composerSurface?.className).not.toContain('bg-white/80')
  })

  it('toggles the homepage composer between default and expanded heights', async () => {
    const user = userEvent.setup()

    render(<ChatHomePage />)

    const composerInput = screen.getByTestId('home-chat-composer-input')
    const expandButton = screen.getByTestId('home-chat-composer-expand-button')

    expect(composerInput.className).toContain('min-h-[110px]')
    expect(expandButton).toHaveAttribute('aria-label', 'Expand composer')

    await user.click(expandButton)

    expect(composerInput.className).toContain('min-h-[240px]')
    expect(expandButton).toHaveAttribute('aria-label', 'Collapse composer')

    await user.click(expandButton)

    expect(composerInput.className).toContain('min-h-[110px]')
    expect(expandButton).toHaveAttribute('aria-label', 'Expand composer')
  })

  it('loads the selected conversation from the sidebar history list', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversations: [
        {
          id: 'conv-running',
          title: 'Running Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'running',
          engine_version: 'harness',
          run_id: 'run-1',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
    user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByText('Running Conversation'))

    expect(storeState.loadConversation).toHaveBeenCalledWith('conv-running')
  })

  it('clears an unsent composer draft before switching to another conversation', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      conversations: [
        {
          id: 'conv-completed',
          title: 'Completed Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'completed',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-18T00:00:00Z',
          finished_at: '2026-04-18T00:10:00Z',
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:10:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    const composer = screen.getByTestId('home-chat-composer-input')
    await user.type(composer, 'draft that should stay out of history')
    await user.click(screen.getByText('Completed Conversation'))

    expect(composer).toHaveValue('')
    expect(storeState.loadConversation).toHaveBeenCalledWith('conv-completed')
  })

  it('renders history cards with the title on top and mode/status split below', () => {
    setMockLanguage('zh-CN')
    Object.assign(storeState, {
      conversations: [
        {
          id: 'conv-slides-waiting',
          title: '生成一个四页的设计行业的PPT',
          artifact_mode: 'slides',
          skill_id: 'pptx',
          mode: 'fast',
          status: 'active',
          runtime_status: 'waiting_input',
          engine_version: 'harness',
          run_id: 'run-2',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
      ],
    })

    const { container } = render(<ChatHomePage />)

    const title = screen.getByText('生成一个四页的设计行业的PPT')
    const historyButton = title.closest('button')
    expect(historyButton).not.toBeNull()

    expect(within(historyButton as HTMLElement).getByText('幻灯片')).toBeInTheDocument()
    expect(within(historyButton as HTMLElement).getByText('等待输入')).toBeInTheDocument()

    const titleRow = title.parentElement
    const metaRow = within(historyButton as HTMLElement).getByText('幻灯片').parentElement

    expect(titleRow).not.toBeNull()
    expect(metaRow).not.toBeNull()
    const titleNode = titleRow as Node
    const metaNode = metaRow as Node
    expect(titleNode.compareDocumentPosition(metaNode) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    const iconContainer = container.querySelector('button > div[class*="w-9"][class*="h-9"]')
    expect(iconContainer).not.toBeNull()
  })

  it('keeps history mode icons tinted with the same mode color even when the conversation is not selected', () => {
    Object.assign(storeState, {
      conversationId: 'conv-web-active',
      conversations: [
        {
          id: 'conv-web-active',
          title: 'Build a landing page',
          artifact_mode: 'web',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'running',
          engine_version: 'harness',
          run_id: 'run-web',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
        {
          id: 'conv-slides-idle',
          title: 'Generate a keynote',
          artifact_mode: 'slides',
          skill_id: 'pptx',
          mode: 'fast',
          status: 'active',
          runtime_status: 'idle',
          engine_version: 'harness',
          run_id: 'run-slides',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    const slidesHistoryButton = screen.getByText('Generate a keynote').closest('button')
    expect(slidesHistoryButton).not.toBeNull()

    const slidesIcon = within(slidesHistoryButton as HTMLElement).getByTestId('home-chat-history-mode-icon-slides')
    expect(slidesIcon.className).toContain('bg-rose-50')
    expect(slidesIcon.className).toContain('text-rose-500')
  })

  it('renders localized english mode labels in history cards', () => {
    setMockLanguage('en-US')
    Object.assign(storeState, {
      conversations: [
        {
          id: 'conv-web-running',
          title: 'Build a landing page',
          artifact_mode: 'web',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'running',
          engine_version: 'harness',
          run_id: 'run-3',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    const historyButton = screen.getByText('Build a landing page').closest('button')
    expect(historyButton).not.toBeNull()
    expect(within(historyButton as HTMLElement).getByText('Web Mode')).toBeInTheDocument()
    expect(within(historyButton as HTMLElement).getByText('Running')).toBeInTheDocument()
  })

  it('localizes history runtime status from status codes even when display_status is returned in another language', () => {
    setMockLanguage('en-US')
    Object.assign(storeState, {
      conversations: [
        {
          id: 'conv-completed-zh-display',
          title: 'hello',
          artifact_mode: 'web',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'completed',
          display_status: '已完成',
          engine_version: 'harness',
          run_id: 'run-4',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: '2026-04-18T00:10:00Z',
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:10:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    const historyButton = screen.getByText('hello').closest('button')
    expect(historyButton).not.toBeNull()
    expect(within(historyButton as HTMLElement).getByText('Completed')).toBeInTheDocument()
    expect(within(historyButton as HTMLElement).queryByText('已完成')).not.toBeInTheDocument()
  })

  it('localizes history runtime status to chinese when the current language is zh-CN', () => {
    setMockLanguage('zh-CN')
    Object.assign(storeState, {
      conversations: [
        {
          id: 'conv-completed-en-display',
          title: 'hello',
          artifact_mode: 'web',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'completed',
          display_status: 'Completed',
          engine_version: 'harness',
          run_id: 'run-5',
          started_at: '2026-04-18T00:00:00Z',
          finished_at: '2026-04-18T00:10:00Z',
          user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:10:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    const historyButton = screen.getByText('hello').closest('button')
    expect(historyButton).not.toBeNull()
    expect(within(historyButton as HTMLElement).getByText('已完成')).toBeInTheDocument()
    expect(within(historyButton as HTMLElement).queryByText('Completed')).not.toBeInTheDocument()
  })

  it('shows the document mode label for the active docx conversation even if the local skill state is stale', () => {
    Object.assign(storeState, {
      conversationId: 'conv-docx-active',
      activeSkillId: null,
      conversations: [
        {
          id: 'conv-docx-active',
          title: 'Document Conversation',
          skill_id: 'docx',
          mode: 'fast',
          status: 'active',
          runtime_status: 'idle',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-18T00:00:00Z',
          finished_at: null,
    user_interaction: null,
          created_at: '2026-04-18T00:00:00Z',
          updated_at: '2026-04-18T00:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByText('Agent')).not.toBeInTheDocument()
    const historyButton = screen.getByText('Document Conversation').closest('button')
    expect(historyButton).not.toBeNull()
    expect(within(historyButton as HTMLElement).getByText('Document Mode')).toBeInTheDocument()
  })

  it('filters homepage multimodal models by the thinking toggle', async () => {
    const user = userEvent.setup()

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Model Settings' }))
    await user.click(await screen.findByRole('tab', { name: 'Multimodal' }))

    expect(await screen.findByText('Fast Vision')).toBeInTheDocument()
    expect(screen.queryByText('Think Vision')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Close' }))
    await user.click(screen.getByRole('button', { name: 'Thinking Mode' }))
    await user.click(await screen.findByRole('button', { name: 'Thinking Mode Option' }))

    await user.click(screen.getByRole('button', { name: 'Model Settings' }))
    await user.click(await screen.findByRole('tab', { name: 'Multimodal' }))

    expect(await screen.findByText('Think Vision')).toBeInTheDocument()
    expect(screen.queryByText('Fast Vision')).not.toBeInTheDocument()
  })

  it('toggles the homepage web search button into the blue selected state', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ChatHomePage />)

    const webSearchButton = screen.getByRole('button', { name: 'Web Search' })
    await user.click(webSearchButton)

    expect(storeState.setWebSearchEnabled).toHaveBeenCalledWith(true)

    storeState.webSearchEnabled = true
    rerender(<ChatHomePage />)

    expect(screen.getByRole('button', { name: 'Web Search' }).className).toContain('text-blue-500')
    expect(screen.getByRole('button', { name: 'Web Search' }).className).toContain('bg-blue-500/10')
  })

  it('shows the current selected models when hovering the homepage model trigger', async () => {
    const user = userEvent.setup()
    storeState.modelPreferences = {
      image_model: 'img-fast',
      image_provider: 'builtin',
      video_model: 'vid-fast',
      video_provider: 'builtin',
      multimodal_model: 'mm-fast',
      multimodal_provider: 'builtin',
    }

    render(<ChatHomePage />)

    await user.hover(screen.getByRole('button', { name: 'Model Settings' }))

    expect(await screen.findByText('Current image model')).toBeInTheDocument()
    expect(screen.getByText('Image Fast')).toBeInTheDocument()
    expect(screen.getByText('Video Fast')).toBeInTheDocument()
    expect(screen.getByText('Fast Vision')).toBeInTheDocument()
  })

  it('shows the localized builtin provider brand in the model picker for English UI', async () => {
    const user = userEvent.setup()
    storeState.modelPreferences = {
      image_model: 'img-fast',
      image_provider: 'builtin',
    }

    providersRegistryMock.mockResolvedValue({
      data: {
        builtin: {
          models: {
            text2image: [
              { model_name: 'img-fast', label: 'Image Fast' },
            ],
          },
        },
      },
    })
    providersModelsMock.mockResolvedValue({
      data: [{ model_name: 'img-fast', model_type: 'text2image', is_enabled: true }],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Model Settings' }))
    await user.click(await screen.findByRole('tab', { name: 'Image' }))

    expect(await screen.findByText('Pixel Reorganization')).toBeInTheDocument()
    expect(screen.queryByText('像素重组')).not.toBeInTheDocument()
  })

  it('blocks homepage agent sends when the local balance is empty', async () => {
    const user = userEvent.setup()
    authStoreState.user.balance_cents = 0
    Object.assign(storeState, {
      conversationId: null,
    })
    storeState.createHarnessConversation.mockResolvedValue(undefined)
    storeState.sendMessage.mockResolvedValue(undefined)

    render(<ChatHomePage />)

    await user.type(screen.getByPlaceholderText('Please enter your thoughts'), 'build a landing page')
    await user.click(screen.getByTestId('home-chat-composer-submit-button'))

    expect(toastErrorMock).toHaveBeenCalledWith('余额不足，无法发起新对话')
    expect(storeState.createHarnessConversation).not.toHaveBeenCalled()
    expect(storeState.sendMessage).not.toHaveBeenCalled()
  })

  it('allows homepage agent sends with empty local balance when the selected multimodal provider is Ollama', async () => {
    const user = userEvent.setup()
    authStoreState.user.balance_cents = 0
    providersListMock.mockResolvedValue({
      data: [
        { code: 'builtin', name: 'Builtin', status: 'authorized', is_builtin: true },
        { code: 'ollama', name: 'Ollama', status: 'authorized', is_builtin: true },
      ],
    })
    providersRegistryMock.mockResolvedValue({
      data: {
        builtin: {
          models: {
            text2image: [{ model_name: 'img-fast', label: 'Image Fast' }],
            text2video: [{ model_name: 'vid-fast', label: 'Video Fast' }],
            multimodal: [{ model_name: 'mm-fast', label: 'Fast Vision', config: { supports_fast_mode: true } }],
          },
        },
        ollama: {
          models: {
            multimodal: [{ model_name: 'local-vision', label: 'Local Vision' }],
          },
        },
      },
    })
    providersModelsMock.mockImplementation(async (providerCode: string) => ({
      data: providerCode === 'ollama'
        ? [{ model_name: 'local-vision', model_type: 'multimodal', is_enabled: true }]
        : [
          { model_name: 'img-fast', model_type: 'text2image', is_enabled: true },
          { model_name: 'vid-fast', model_type: 'text2video', is_enabled: true },
          { model_name: 'mm-fast', model_type: 'multimodal', is_enabled: true },
        ],
    }))
    Object.assign(storeState, {
      conversationId: null,
      modelPreferences: {
        auto: false,
        image_model: 'img-fast',
        image_provider: 'builtin',
        video_model: 'vid-fast',
        video_provider: 'builtin',
        multimodal_model: 'local-vision',
        multimodal_provider: 'ollama',
      },
    })
    storeState.createHarnessConversation.mockResolvedValue(undefined)
    storeState.sendMessage.mockResolvedValue(undefined)

    render(<ChatHomePage />)

    await user.type(screen.getByPlaceholderText('Please enter your thoughts'), 'build a landing page')
    await user.click(screen.getByTestId('home-chat-composer-submit-button'))

    await waitFor(() => {
      expect(storeState.createHarnessConversation).toHaveBeenCalledWith(undefined, {
        artifactMode: 'web',
        modelPreferences: {
          auto: false,
          image_model: 'img-fast',
          image_provider: 'builtin',
          video_model: 'vid-fast',
          video_provider: 'builtin',
          multimodal_model: 'local-vision',
          multimodal_provider: 'ollama',
        },
      })
    })
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(storeState.sendMessage).toHaveBeenCalled()
  })

  it('hides image and video mode entry buttons on a new homepage conversation', () => {
    render(<ChatHomePage />)

    expect(screen.queryByText('图片模式')).not.toBeInTheDocument()
    expect(screen.queryByText('视频模式')).not.toBeInTheDocument()
  })

  it('fills default homepage model preferences before creating a new harness conversation', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      modelPreferences: {
        auto: false,
      },
    })

    render(<ChatHomePage />)

    const textarea = screen.getByPlaceholderText('Please enter your thoughts')
    await user.type(textarea, '分析下图片内容{Enter}')

    await waitFor(() => {
      expect(storeState.createHarnessConversation).toHaveBeenCalledWith(undefined, {
        artifactMode: 'web',
        modelPreferences: {
          auto: false,
          image_model: 'img-fast',
          image_provider: 'builtin',
          video_model: 'vid-fast',
          video_provider: 'builtin',
          multimodal_model: 'mm-fast',
          multimodal_provider: 'builtin',
        },
      })
    })

    expect(storeState.setModelPreferences).toHaveBeenCalledWith({
      auto: false,
      image_model: 'img-fast',
      image_provider: 'builtin',
      video_model: 'vid-fast',
      video_provider: 'builtin',
      multimodal_model: 'mm-fast',
      multimodal_provider: 'builtin',
    })
  })

  it('creates a slides conversation after selecting the slides mode', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      modelPreferences: {
        auto: false,
      },
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: /slides/i }))

    const textarea = screen.getByPlaceholderText('Please enter your thoughts')
    await user.type(textarea, 'Create a quarterly review deck{Enter}')

    await waitFor(() => {
      expect(storeState.createHarnessConversation).toHaveBeenCalledWith(undefined, {
        artifactMode: 'slides',
        modelPreferences: {
          auto: false,
          image_model: 'img-fast',
          image_provider: 'builtin',
          video_model: 'vid-fast',
          video_provider: 'builtin',
          multimodal_model: 'mm-fast',
          multimodal_provider: 'builtin',
        },
      })
    })
  })

  it('loads harness skills and design systems metadata on mount', async () => {
    listHarnessSkillsMock.mockResolvedValue({ data: [] })
    listHarnessDesignSystemsMock.mockResolvedValue({ data: [] })

    render(<ChatHomePage />)

    await waitFor(() => {
      expect(listHarnessSkillsMock).toHaveBeenCalledTimes(1)
      expect(listHarnessDesignSystemsMock).toHaveBeenCalledTimes(1)
    })
  })

  it('renders the primary skill selector in the composer header and removes the empty-state cards', async () => {
    const user = userEvent.setup()
    const clipboardWriteTextMock = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWriteTextMock },
    })
    Object.assign(storeState, {
      conversationId: null,
      artifactMode: 'web',
      activeSkillId: null,
    })

    listHarnessSkillsMock.mockResolvedValue({
      data: [
        {
          id: 'dashboard',
          name: 'SaaS Dashboard',
          name_en: 'SaaS Dashboard',
          name_zh: '数据看板',
          description: 'Design a dense SaaS analytics dashboard.',
          description_en: 'Design a dense SaaS analytics dashboard.',
          description_zh: '为 SaaS 产品设计一个信息密度较高的数据分析后台。',
          icon: 'layout',
          color: '#f59e0b',
          triggers: [],
          mode: 'prototype',
          surface: 'web',
          platform: 'desktop',
          scenario: 'data',
          artifact_mode: 'web',
          default_for: ['web'],
          featured: 1,
          preview_type: 'html',
          preview_entry: 'index.html',
          protocol_provider: 'open_design',
          protocol_family: 'open_design_free_web',
          protocol_metadata: {},
          capabilities: {},
          example_prompt: 'Build a SaaS dashboard for developer analytics.',
          has_example_html: true,
        },
        {
          id: 'pricing-page',
          name: 'Pricing Page',
          name_en: 'Pricing Page',
          name_zh: '定价页',
          description: 'Design a pricing page.',
          description_en: 'Design a pricing page.',
          description_zh: '设计一个定价页面。',
          icon: 'layout',
          color: '#f97316',
          triggers: [],
          mode: 'prototype',
          surface: 'web',
          platform: 'desktop',
          scenario: 'marketing',
          artifact_mode: 'web',
          default_for: [],
          featured: 2,
          preview_type: 'html',
          preview_entry: 'index.html',
          protocol_provider: 'open_design',
          protocol_family: 'open_design_free_web',
          protocol_metadata: {},
          capabilities: {},
          example_prompt: 'Build a pricing page.',
          has_example_html: false,
        },
      ],
    })
    getHarnessSkillExampleHtmlMock.mockResolvedValue({
      data: '<!doctype html><html><body><main>dashboard example</main></body></html>',
    })
    listHarnessDesignSystemsMock.mockResolvedValue({
      data: [
        {
          id: 'application',
          title: 'Application',
          description: 'Structured product design system.',
          category: 'Product & SaaS',
          sections: ['Color', 'Typography'],
          palette: ['#FFFFFF', '#111827'],
          is_default: false,
        },
      ],
    })
    getHarnessDesignSystemMock.mockResolvedValue({
      data: {
        id: 'application',
        title: 'Application',
        description: 'Structured product design system.',
        category: 'Product & SaaS',
        sections: ['Color', 'Typography'],
        palette: ['#FFFFFF', '#111827', '#2563EB', '#7C3AED'],
        preview: null,
        featured: 1,
        is_default: false,
        body: '# Design System Inspired by Application\\n\\n## 1. Visual Theme\\n- Primary color #2563EB',
      },
    })
    render(<ChatHomePage />)

    expect(screen.queryByRole('heading', { name: 'Agent' })).not.toBeInTheDocument()
    expect(screen.queryByText('Please enter your thoughts')).not.toBeInTheDocument()
    expect(await screen.findByText(/技能:?|Skill:?/)).toBeInTheDocument()
    expect(screen.getByText(/设计体系:?|Design System:?/)).toBeInTheDocument()
    expect(screen.getAllByRole('combobox')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /SaaS Dashboard/i })).not.toBeInTheDocument()
    expect(listHarnessSkillsMock).toHaveBeenCalled()

    const [skillCombobox] = screen.getAllByRole('combobox')
    await user.click(skillCombobox)
    expect(await screen.findByText('SaaS Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Pricing Page')).toBeInTheDocument()
    const skillSearchInput = screen.getByPlaceholderText('Search skills')
    await user.type(skillSearchInput, 'pricing')
    expect(screen.queryByText('SaaS Dashboard')).not.toBeInTheDocument()
    expect(screen.getByText('Pricing Page')).toBeInTheDocument()
    await user.clear(skillSearchInput)
    expect(await screen.findByText('SaaS Dashboard')).toBeInTheDocument()
    const skillDescription = screen.getByText('Design a dense SaaS analytics dashboard.')
    expect(skillDescription).toBeInTheDocument()
    expect(skillDescription).toHaveAttribute('title', 'Design a dense SaaS analytics dashboard.')
    expect(screen.getByRole('button', { name: 'Preview SaaS Dashboard' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Preview Pricing Page' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Preview SaaS Dashboard' }))

    await waitFor(() => {
      expect(getHarnessSkillExampleHtmlMock).toHaveBeenCalledWith('dashboard')
    })
    expect(await screen.findByTestId('home-skill-example-preview-frame')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'SaaS Dashboard' })).toBeInTheDocument()
    expect(screen.getByText('输入内容')).toBeInTheDocument()

    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /Copy example prompt|复制示例输入/ }))
    await waitFor(() => {
      expect(clipboardWriteTextMock).toHaveBeenCalledWith('Build a SaaS dashboard for developer analytics.')
    })
    expect(within(dialog).getByText(/Copied|已复制/)).toBeInTheDocument()
    expect(screen.getByTestId('home-design-system-swatch-auto')).toBeInTheDocument()
  })

  it('renders the design system selector and lets users choose a manual design system', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      artifactMode: 'web',
      selectedDesignSystemId: null,
    })

    listHarnessSkillsMock.mockResolvedValue({ data: [] })
    listHarnessDesignSystemsMock.mockResolvedValue({
      data: [
        {
          id: 'application',
          title: 'Application',
          description: 'Structured product design system.',
          category: 'Product & SaaS',
          sections: ['Color', 'Typography'],
          palette: ['#FFFFFF', '#111827'],
          is_default: false,
        },
      ],
    })
    getHarnessDesignSystemMock.mockResolvedValue({
      data: {
        id: 'application',
        title: 'Application',
        description: 'Structured product design system.',
        category: 'Product & SaaS',
        sections: ['Color', 'Typography'],
        palette: ['#FFFFFF', '#111827', '#2563EB', '#7C3AED'],
        preview: null,
        featured: 1,
        is_default: false,
        body: '# Design System Inspired by Application\\n\\n## 1. Visual Theme\\n- Primary color #2563EB',
      },
    })

    render(<ChatHomePage />)

    const comboboxes = await screen.findAllByRole('combobox')
    const designSystemCombobox = comboboxes[1]
    await user.click(designSystemCombobox)

    expect(await screen.findByText('Application')).toBeInTheDocument()
    expect(screen.getByText('Product & SaaS')).toBeInTheDocument()
    const designSystemSearchInput = screen.getByPlaceholderText('Search design systems')
    await user.type(designSystemSearchInput, 'application')
    expect(screen.getByText('Application')).toBeInTheDocument()
    expect(screen.getByTestId('home-design-system-swatch-application')).toBeInTheDocument()

    const option = screen.getAllByText('Application')
      .map((element) => element.closest('button[data-state]'))
      .find(Boolean)
    expect(option).not.toBeNull()
    if (option) {
      await user.click(option)
    }

    expect(storeState.selectDesignSystem).toHaveBeenCalledWith('application')
  })

  it('shows only one clean category label in the design system selector', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      artifactMode: 'web',
      selectedDesignSystemId: null,
    })

    listHarnessSkillsMock.mockResolvedValue({ data: [] })
    listHarnessDesignSystemsMock.mockResolvedValue({
      data: [
        {
          id: 'airbnb',
          title: 'Airbnb',
          description: 'Category: E-Commerce & Retail',
          category: 'E-Commerce & Retail',
          sections: ['Color', 'Typography'],
          palette: ['#FFFFFF', '#111827'],
          is_default: false,
        },
      ],
    })

    render(<ChatHomePage />)

    const [, designSystemCombobox] = await screen.findAllByRole('combobox')
    await user.click(designSystemCombobox)

    expect(await screen.findByText('Airbnb')).toBeInTheDocument()
    expect(screen.getByText('E-Commerce & Retail')).toBeInTheDocument()
    expect(screen.queryByText(/Category:\s*E-Commerce & Retail/)).not.toBeInTheDocument()
    expect(screen.queryByText('Category: E-Commerce & Retail · E-Commerce & Retail')).not.toBeInTheDocument()
  })

  it('opens the design system preview dialog with bundled example html', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      artifactMode: 'web',
      selectedDesignSystemId: 'application',
    })

    listHarnessSkillsMock.mockResolvedValue({ data: [] })
    listHarnessDesignSystemsMock.mockResolvedValue({
      data: [
        {
          id: 'application',
          title: 'Application',
          description: 'Structured product design system.',
          category: 'Product & SaaS',
          sections: ['Color', 'Typography'],
          palette: ['#FFFFFF', '#111827', '#2563EB', '#7C3AED'],
          preview: null,
          featured: 1,
          is_default: false,
        },
      ],
    })
    render(<ChatHomePage />)

    const [, designSystemCombobox] = await screen.findAllByRole('combobox')
    await user.click(designSystemCombobox)
    await user.click(await screen.findByRole('button', { name: 'Preview Application' }))

    await waitFor(() => {
      expect(getHarnessDesignSystemPreviewHtmlUrlMock).toHaveBeenCalledWith('application')
    })
    expect(getHarnessDesignSystemMock).not.toHaveBeenCalled()
    const frame = await screen.findByTestId('home-design-system-preview-frame')
    expect(frame).toHaveAttribute(
      'src',
      'http://localhost:8000/api/v1/agent/harness/design-systems/application/preview-html',
    )
  })

  it('highlights the auto-selected skill when opening selectors', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: null,
      artifactMode: 'web',
      activeSkillId: 'dashboard',
      skillSelectionMode: 'auto',
    })

    listHarnessSkillsMock.mockResolvedValue({
      data: [
        {
          id: 'dashboard',
          name: 'SaaS Dashboard',
          name_en: 'SaaS Dashboard',
          name_zh: '数据看板',
          description: 'Design a dense SaaS analytics dashboard.',
          description_en: 'Design a dense SaaS analytics dashboard.',
          description_zh: '为 SaaS 产品设计一个信息密度较高的数据分析后台。',
          icon: 'layout',
          color: '#f59e0b',
          triggers: [],
          mode: 'prototype',
          surface: 'web',
          platform: 'desktop',
          scenario: 'data',
          artifact_mode: 'web',
          default_for: ['web'],
          featured: 1,
          preview_type: 'html',
          preview_entry: 'index.html',
          protocol_provider: 'open_design',
          protocol_family: 'open_design_free_web',
          protocol_metadata: {},
          capabilities: {},
          example_prompt: 'Build a SaaS dashboard for developer analytics.',
        },
      ],
    })
    render(<ChatHomePage />)

    const [skillCombobox] = screen.getAllByRole('combobox')

    await user.click(skillCombobox)
    const skillOption = (await screen.findAllByText('SaaS Dashboard'))
      .map((element) => element.closest('button[data-state]'))
      .find(Boolean)
    expect(skillOption).toHaveAttribute('data-state', 'checked')
  })

  it('switches skill name and description with the current language', async () => {
    setMockLanguage('zh-CN')
    const user = userEvent.setup()

    listHarnessSkillsMock.mockResolvedValue({
      data: [
        {
          id: 'dashboard',
          name: 'SaaS Dashboard',
          name_en: 'SaaS Dashboard',
          name_zh: '数据看板',
          description: 'Design a dense SaaS analytics dashboard.',
          description_en: 'Design a dense SaaS analytics dashboard.',
          description_zh: '为 SaaS 产品设计一个信息密度较高的数据分析后台。',
          icon: 'layout',
          color: '#f59e0b',
          triggers: [],
          mode: 'prototype',
          surface: 'web',
          platform: 'desktop',
          scenario: 'data',
          artifact_mode: 'web',
          default_for: ['web'],
          featured: 1,
          preview_type: 'html',
          preview_entry: 'index.html',
          protocol_provider: 'open_design',
          protocol_family: 'open_design_seed_template',
          protocol_metadata: {
            design_system: { requires: true, sections: [] },
          },
          capabilities: {},
          example_prompt: 'Build a SaaS dashboard for developer analytics.',
        },
      ],
    })
    render(<ChatHomePage />)

    const [skillCombobox] = await screen.findAllByRole('combobox')
    await user.click(skillCombobox)

    expect(await screen.findByText('数据看板')).toBeInTheDocument()
    const zhDescription = screen.getByText('为 SaaS 产品设计一个信息密度较高的数据分析后台。')
    expect(zhDescription).toBeInTheDocument()
    expect(zhDescription).toHaveAttribute('title', '为 SaaS 产品设计一个信息密度较高的数据分析后台。')
  })

  it('adds a pending attachment after local upload from the homepage picker', async () => {
    const user = userEvent.setup()

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Attachment Sources' }))
    const input = screen.getByTestId('home-chat-local-upload-input') as HTMLInputElement
    expect(input.accept).toContain('image/*')
    expect(input.accept).toContain('.docx')
    expect(input.accept).toContain('.xlsx')
    expect(input.accept).toContain('.txt')
    await user.upload(input, new File(['demo'], 'demo.png', { type: 'image/png' }))

    await waitFor(() => {
      expect(uploadAttachmentMock).toHaveBeenCalled()
    })

    expect(await screen.findByAltText('demo.png')).toBeInTheDocument()
  })

  it('uploads supported text files as compact attachment cards without image previews', async () => {
    const user = userEvent.setup()
    uploadAttachmentMock.mockResolvedValueOnce({
      data: {
        url: 'references/inputs/upload_txt/source.txt',
        filename: 'notes.txt',
        type: 'file',
        size: 42,
        asset_id: 'upload_txt',
      },
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Attachment Sources' }))
    const input = screen.getByTestId('home-chat-local-upload-input') as HTMLInputElement
    await user.upload(input, new File(['line one'], 'notes.txt', { type: 'text/plain' }))

    await waitFor(() => {
      expect(uploadAttachmentMock).toHaveBeenCalledWith('42', expect.any(File))
    })

    expect(screen.getByText('notes.txt')).toBeInTheDocument()
    expect(screen.getByTestId('attachment-kind-text')).toBeInTheDocument()
    expect(upsertWorkspaceFileMock).toHaveBeenCalledWith(42, expect.objectContaining({
      file_id: 'upload_txt',
      name: 'notes.txt',
      path: 'references/inputs/upload_txt/source.txt',
      source: 'input_asset',
      type: 'text',
      size: 42,
    }))
    expect(storeState.workspaceFiles).toEqual(expect.arrayContaining([
      expect.objectContaining({
        file_id: 'upload_txt',
        name: 'notes.txt',
        path: 'references/inputs/upload_txt/source.txt',
        source: 'input_asset',
        type: 'text',
        size: 42,
      }),
    ]))
    expect(fetchWorkspaceFileBlobMock).not.toHaveBeenCalled()
  })

  it('blocks unsupported local uploads on the homepage composer', async () => {
    const user = userEvent.setup()

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Attachment Sources' }))
    const input = screen.getByTestId('home-chat-local-upload-input') as HTMLInputElement
    const unsupportedFile = new File(['zip'], 'archive.zip', { type: 'application/zip' })
    fireEvent.change(input, { target: { files: [unsupportedFile] } })

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Only supported text and Office files can be uploaded.')
    })
    expect(uploadAttachmentMock).not.toHaveBeenCalled()
  })

  it('adds a pending attachment after selecting from the homepage asset library modal', async () => {
    const user = userEvent.setup()

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Attachment Sources' }))
    await user.click(screen.getByRole('button', { name: 'Asset Library' }))

    await user.click(await screen.findByRole('button', { name: /Brand Refresh/i }))
    await user.click(await screen.findByAltText('asset-1'))
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await screen.findByAltText('library-asset.png')).toBeInTheDocument()
  })

  it('shows the session files button above the composer and opens the modal without duplicating the list inline', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Ready',
          createdAt: '2026-04-17T10:00:00Z',
        },
      ],
      workspaceFiles: [
        {
          name: 'requirements.md',
          path: 'requirements.md',
          type: 'text',
          size: 12,
          created_at: '2026-04-17T09:00:00Z',
          updated_at: '2026-04-17T09:00:00Z',
          version: 1,
        },
        {
          name: 'design.png',
          path: 'design.png',
          type: 'image',
          size: 24,
          created_at: '2026-04-17T09:05:00Z',
          updated_at: '2026-04-17T09:05:00Z',
          version: 1,
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getAllByText('Files (2)')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Files (2)' }))

    expect(await screen.findByText('requirements.md')).toBeInTheDocument()
    expect(screen.getByText('design.png')).toBeInTheDocument()
  })

  it('opens plan markdown in a right-side preview panel instead of a raw unauthenticated link', async () => {
    const user = userEvent.setup()
    fetchWorkspaceFileBlobMock.mockResolvedValue(new Blob(['Plan preview body'], { type: 'text/markdown' }))
    fetchWorkspaceFileVersionBlobMock.mockResolvedValue(new Blob(['Plan preview body'], { type: 'text/markdown' }))
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-plan-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-04-19T10:00:00Z',
          blocks: [
            {
              id: 'plan-artifact-0',
              kind: 'content',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'plan_artifact',
              payload: {
                title: 'Task Plan',
                filePath: 'plan.md',
                summary: 'Finish the task in three steps.',
                currentStep: 'step-3',
                steps: [
                  { id: 'step-1', order: 1, title: 'Understand request', status: 'completed' },
                  { id: 'step-2', order: 2, title: 'Draft output', status: 'completed' },
                  { id: 'step-3', order: 3, title: 'Deliver result', status: 'completed' },
                ],
              },
            },
          ],
        },
      ],
      conversations: [
        {
          id: 'conv-plan',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          runtime_status: 'completed',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: '2026-04-19T10:01:00Z',
    user_interaction: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
        },
      ],
    })

    const { container } = render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Open plan' }))

    await waitFor(() => {
      expect(
        fetchWorkspaceFileBlobMock.mock.calls.length + fetchWorkspaceFileVersionBlobMock.mock.calls.length,
      ).toBeGreaterThan(0)
    })
    const mainPanel = screen.getByTestId('home-chat-message-scroll').parentElement
    const previewRail = screen.getByTestId('home-chat-markdown-preview')
    const layoutRow = previewRail.parentElement
    expect(mainPanel?.className).toContain('md:w-[980px]')
    expect(mainPanel?.className).not.toContain('flex-1')
    expect(layoutRow?.className).toContain('max-w-none')
    expect(layoutRow?.className).not.toContain('mx-auto')
    expect(layoutRow?.className).not.toContain('max-w-[1840px]')
    expect(previewRail).toBeInTheDocument()
    expect(previewRail.className).toContain('flex-1')
    expect(previewRail.className).not.toContain('w-[900px]')
    expect(container.querySelector('[data-testid="home-chat-history-scroll"]')).not.toBeInTheDocument()
    expect(getWorkspaceFileUrlMock).not.toHaveBeenCalled()
  })

  it('renders planning-ready states for current outline cards', () => {
    Object.assign(storeState, {
      conversationId: 'conv-plan',
      conversations: [
        {
          id: 'conv-plan',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
        },
      ],
      messages: [
        {
          id: 'assistant-plan-awaiting-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-04-19T10:00:00Z',
          blocks: [
            {
              id: 'plan-awaiting-1',
              kind: 'content',
              order: 0,
              status: 'planning_ready',
              visible: true,
              uiKind: 'plan_artifact',
              payload: {
                title: 'Task Plan',
                status: 'planning_ready',
                summary: 'Review the plan before execution starts.',
                currentStep: 'step-2',
                steps: [
                  { id: 'step-1', order: 1, title: 'Understand request', status: 'completed' },
                  { id: 'step-2', order: 2, title: 'Draft output', status: 'in_progress' },
                ],
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getAllByText('Ready to execute').length).toBeGreaterThan(0)
    expect(screen.getByText('Review or adjust the outline, then start execution when ready.')).toBeInTheDocument()
    expect(screen.getByTestId('home-chat-composer-input')).toHaveAttribute(
      'placeholder',
      'Review or adjust the outline in the card below.',
    )
    expect(screen.getByTestId('home-chat-composer-input')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Attachment Sources' })).toBeDisabled()
    expect(screen.queryByPlaceholderText('Type your response...')).not.toBeInTheDocument()
  })

  it('renders interaction forms without duplicating the message content above the card', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'assistant-quick-brief',
          role: 'assistant',
          content: 'Quick brief',
          createdAt: '2026-05-07T00:00:00Z',
          blocks: [
            {
              id: 'interaction-form:quick-brief',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'quick-brief:1',
                kind: 'quick_brief',
                status: 'pending',
                schema: {
                  title: 'Quick brief',
                  description: 'Use the brief before continuing.',
                  submitLabel: 'Continue',
                  fields: [
                    {
                      id: 'output',
                      label: 'Output',
                      type: 'text',
                      required: true,
                    },
                  ],
                },
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText('Quick brief')).toBeInTheDocument()
    expect(screen.queryAllByText('Quick brief')).toHaveLength(1)
    expect(screen.getByText('Use the brief before continuing.')).toBeInTheDocument()
  })

  it('passes structured ask_user form answers through the page submit wrapper', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      userInteraction: {
        request_id: 'functions.ask_user:brand',
        question: 'Brand brief',
        kind: 'ask_user',
        schema: {
          title: 'Brand brief',
          submitLabel: 'Continue',
          fields: [
            {
              id: 'brand',
              label: 'Brand name',
              type: 'text',
              required: true,
            },
            {
              id: 'industry',
              label: 'Industry',
              type: 'text',
              required: true,
            },
          ],
        },
        answers: null,
        status: 'pending',
      },
      messages: [
        {
          id: 'assistant-ask-user',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-18T00:00:00Z',
          blocks: [
            {
              id: 'interaction-form:functions.ask_user:brand',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'functions.ask_user:brand',
                kind: 'ask_user',
                status: 'pending',
                schema: {
                  title: 'Brand brief',
                  submitLabel: 'Continue',
                  fields: [
                    {
                      id: 'brand',
                      label: 'Brand name',
                      type: 'text',
                      required: true,
                    },
                    {
                      id: 'industry',
                      label: 'Industry',
                      type: 'text',
                      required: true,
                    },
                  ],
                },
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    await user.type(screen.getByLabelText('Brand name'), '星图科技')
    await user.type(screen.getByLabelText('Industry'), '科技、AI')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(storeState.respondToAgent).toHaveBeenCalledWith(
      'functions.ask_user:brand',
      JSON.stringify({ brand: '星图科技', industry: '科技、AI' }),
      '星图科技 / 科技、AI',
      undefined,
      { brand: '星图科技', industry: '科技、AI' },
    )
  })

  it('clears a pending interaction submit spinner when starting a new chat', async () => {
    const user = userEvent.setup()
    storeState.respondToAgent.mockImplementationOnce(() => new Promise(() => undefined))
    Object.assign(storeState, {
      userInteraction: {
        request_id: 'functions.ask_user:pending',
        question: 'Brand brief',
        kind: 'ask_user',
        schema: {
          title: 'Brand brief',
          submitLabel: 'Continue',
          fields: [
            {
              id: 'brand',
              label: 'Brand name',
              type: 'text',
              required: true,
            },
          ],
        },
        answers: null,
        status: 'pending',
      },
      messages: [
        {
          id: 'assistant-ask-user-pending',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-18T00:00:00Z',
          blocks: [
            {
              id: 'interaction-form:functions.ask_user:pending',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'functions.ask_user:pending',
                kind: 'ask_user',
                status: 'pending',
                schema: {
                  title: 'Brand brief',
                  submitLabel: 'Continue',
                  fields: [
                    {
                      id: 'brand',
                      label: 'Brand name',
                      type: 'text',
                      required: true,
                    },
                  ],
                },
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    await user.type(screen.getByLabelText('Brand name'), '星图科技')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    await waitFor(() => {
      expect(screen.getByTestId('home-chat-composer-submit-spinner')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /new chat/i }))

    expect(screen.queryByTestId('home-chat-composer-submit-spinner')).not.toBeInTheDocument()
    expect(storeState.newChat).toHaveBeenCalledTimes(1)
  })

  it('renders interaction JSON user replies as a readable summary', () => {
    Object.assign(storeState, {
      messages: [
        {
          id: 'user-json-reply',
          role: 'user',
          content: JSON.stringify({
            output: '设计行业的PPT',
            platform: 'internal_review',
            audience: '管理层',
            tone: 'professional_restrained',
            scale: '5_8',
            speaker_notes: 'light',
          }),
          createdAt: '2026-05-07T00:00:00Z',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText('设计行业的PPT / Internal review / 管理层 / Professional and restrained / 5-8 / Light notes')).toBeInTheDocument()
    expect(screen.queryByText(/^\{"output":/)).not.toBeInTheDocument()
  })

  it('locks the main composer while the current outline is ready', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: 'conv-plan',
      conversations: [
        {
          id: 'conv-plan',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
        },
      ],
    })

    render(<ChatHomePage />)

    const composer = screen.getByTestId('home-chat-composer-input')
    expect(composer).toBeDisabled()
    expect(screen.getByTestId('home-chat-composer-submit-button')).toBeDisabled()
    await user.click(screen.getByTestId('home-chat-composer-submit-button'))

    expect(storeState.respondToAgent).not.toHaveBeenCalled()
    expect(storeState.sendMessage).not.toHaveBeenCalled()
  })

  it('locks the main composer while the active run is still executing', async () => {
    const user = userEvent.setup()
    Object.assign(storeState, {
      conversationId: 'conv-running-active',
      isStreaming: false,
      runStatus: 'running',
      conversations: [
        {
          id: 'conv-running-active',
          title: 'Running Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-active',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'executing',
          runtime_status: 'running',
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByTestId('home-chat-composer-input')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Attachment Sources' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Stop agent response' }))

    expect(storeState.stopStreaming).toHaveBeenCalledTimes(1)
    expect(storeState.sendMessage).not.toHaveBeenCalled()
  })

  it('blocks attachment, paste, and drop uploads while the current outline is ready', async () => {
    Object.assign(storeState, {
      conversationId: 'conv-plan',
      conversations: [
        {
          id: 'conv-plan',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
        },
      ],
    })

    render(<ChatHomePage />)

    const attachmentButton = screen.getByRole('button', { name: 'Attachment Sources' })
    const composer = screen.getByTestId('home-chat-composer-input')
    const dropZone = screen.getByTestId('home-chat-composer-dropzone')

    expect(attachmentButton).toBeDisabled()

    fireEvent.paste(composer, {
      clipboardData: {
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => new File(['paste-image'], 'clipboard.png', { type: 'image/png' }),
          },
        ],
      },
    })

    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [new File(['drop-image'], 'dropped.png', { type: 'image/png' })],
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => new File(['drop-image'], 'dropped.png', { type: 'image/png' }),
          },
        ],
      },
    })

    expect(uploadAttachmentMock).not.toHaveBeenCalled()
  })

  it('starts execution from the current outline card without a confirmation prompt', async () => {
    const user = userEvent.setup()
    storeState.startExecution.mockResolvedValue(undefined)
    Object.assign(storeState, {
      conversationId: 'conv-plan-inline-start',
      conversations: [
        {
          id: 'conv-plan-inline-start',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
        },
      ],
      outlineRuntime: {
        current_outline: {
          artifact_type: 'ppt',
          title: 'Task Plan',
          summary: 'Review the outline before execution starts.',
          status: 'planning_ready',
          items: [{ id: 'step-1', title: 'Confirm direction', summary: '', order: 1, status: 'pending' }],
        },
        revision_session: null,
      },
      messages: [
        {
          id: 'assistant-plan-inline-loading',
          role: 'assistant',
          content: 'I prepared a task plan.',
          createdAt: '2026-04-19T10:12:00Z',
          blocks: [
            {
              id: 'plan-artifact-inline-loading',
              kind: 'content',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'user_plan_card',
              payload: {
                artifactType: 'ppt',
                title: 'Task Plan',
                status: 'planning_ready',
                summary: 'Review the outline before execution starts.',
                outline: [{ id: 'step-1', order: 1, title: 'Confirm direction', summary: '' }],
                items: [
                  { id: 'step-1', order: 1, title: 'Confirm direction', status: 'pending' },
                ],
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByText('Please confirm the plan before execution continues.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start execution' }))

    expect(storeState.startExecution).toHaveBeenCalledTimes(1)
    expect(storeState.respondToAgent).not.toHaveBeenCalled()
  })

  it('blocks starting execution from the current outline card when the local balance is empty', async () => {
    const user = userEvent.setup()
    authStoreState.user.balance_cents = 0
    storeState.startExecution.mockResolvedValue(undefined)
    Object.assign(storeState, {
      conversationId: 'conv-plan-inline-start',
      conversations: [
        {
          id: 'conv-plan-inline-start',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
        },
      ],
      outlineRuntime: {
        current_outline: {
          artifact_type: 'ppt',
          title: 'Task Plan',
          summary: 'Review the outline before execution starts.',
          status: 'planning_ready',
          items: [{ id: 'step-1', title: 'Confirm direction', summary: '', order: 1, status: 'pending' }],
        },
        revision_session: null,
      },
      messages: [
        {
          id: 'assistant-plan-inline-loading',
          role: 'assistant',
          content: 'I prepared a task plan.',
          createdAt: '2026-04-19T10:12:00Z',
          blocks: [
            {
              id: 'plan-artifact-inline-loading',
              kind: 'content',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'user_plan_card',
              payload: {
                artifactType: 'ppt',
                title: 'Task Plan',
                status: 'planning_ready',
                summary: 'Review the outline before execution starts.',
                outline: [{ id: 'step-1', order: 1, title: 'Confirm direction', summary: '' }],
                items: [
                  { id: 'step-1', order: 1, title: 'Confirm direction', status: 'pending' },
                ],
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    await user.click(screen.getByRole('button', { name: 'Start execution' }))

    expect(toastErrorMock).toHaveBeenCalledWith('余额不足，无法发起新对话')
    expect(storeState.startExecution).not.toHaveBeenCalled()
    expect(storeState.respondToAgent).not.toHaveBeenCalled()
  })

  it('shows the readonly execution hint while a current outline is still executing', () => {
    Object.assign(storeState, {
      conversationId: 'conv-plan-inline-executing',
      conversations: [
        {
          id: 'conv-plan-inline-executing',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'active',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: null,
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:01:00Z',
          phase: 'executing',
          runtime_status: 'running',
        },
      ],
      outlineRuntime: {
        current_outline: {
          artifact_type: 'excel',
          title: '人口数据表',
          summary: '整理中日人口数据',
          status: 'executing',
          readonly: true,
          items: [{ id: 'item-1', title: '中国数据', summary: '', order: 1, status: 'completed' }],
        },
      },
      messages: [
        {
          id: 'assistant-plan-inline-executing',
          role: 'assistant',
          content: '执行中',
          createdAt: '2026-04-19T10:12:00Z',
          blocks: [
            {
              id: 'plan-artifact-inline-executing',
              kind: 'content',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'user_plan_card',
              payload: {
                artifactType: 'excel',
                title: '人口数据表',
                status: 'executing',
                readonly: true,
                summary: '整理中日人口数据',
                outline: [{ id: 'item-1', order: 1, title: '中国数据', summary: '' }],
                items: [
                  { id: 'item-1', order: 1, title: '中国数据', status: 'completed' },
                ],
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.getByText('The current plan is executing. Regenerate a new plan if you need to change the outline.')).toBeInTheDocument()
  })

  it('keeps completed plans readonly without showing the execution hint', () => {
    Object.assign(storeState, {
      conversationId: 'conv-plan-inline-completed',
      conversations: [
        {
          id: 'conv-plan-inline-completed',
          title: 'Plan Conversation',
          skill_id: null,
          mode: 'fast',
          status: 'completed',
          engine_version: 'harness',
          run_id: 'run-plan',
          started_at: '2026-04-19T10:00:00Z',
          finished_at: '2026-04-19T10:05:00Z',
          created_at: '2026-04-19T10:00:00Z',
          updated_at: '2026-04-19T10:05:00Z',
          phase: 'completed',
          runtime_status: 'completed',
        },
      ],
      outlineRuntime: {
        current_outline: {
          artifact_type: 'excel',
          title: '人口数据表',
          summary: '整理中日人口数据',
          status: 'completed',
          readonly: true,
          items: [{ id: 'item-1', title: '中国数据', summary: '', order: 1, status: 'completed' }],
        },
      },
      messages: [
        {
          id: 'assistant-plan-inline-completed',
          role: 'assistant',
          content: '已完成',
          createdAt: '2026-04-19T10:12:00Z',
          blocks: [
            {
              id: 'plan-artifact-inline-completed',
              kind: 'content',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'user_plan_card',
              payload: {
                artifactType: 'excel',
                title: '人口数据表',
                status: 'completed',
                readonly: true,
                summary: '整理中日人口数据',
                outline: [{ id: 'item-1', order: 1, title: '中国数据', summary: '' }],
                items: [
                  { id: 'item-1', order: 1, title: '中国数据', status: 'completed' },
                ],
              },
            },
          ],
        },
      ],
    })

    render(<ChatHomePage />)

    expect(screen.queryByText('The current plan is executing. Regenerate a new plan if you need to change the outline.')).not.toBeInTheDocument()
    expect(screen.getByText('中国数据')).toBeInTheDocument()
  })
})



