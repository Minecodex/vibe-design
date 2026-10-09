import { wireRecord } from './harnessWireFields'
import type { AgentEvent, MediaReferenceData } from '@/api/endpoints/agent'
// Legacy wire fixtures intentionally use retired tags to check replay and terminal-event guards.
import { httpResponse, conversationDetail, runtimeState, conversationSession, artifactTask } from './testing/harnessStateFixtures'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { __chatStoreTestUtils, type ChatMessage, type MessageBlock, useChatStore } from './canvasAgentStore'
import { EMPTY_MESSAGE_BLOCKS } from './canvasAgentTypes'
import { createGenerationProjectionState } from './generationProjection'
import { resetCanvasGenerationTaskRuntimeForTests } from './canvasGenerationTaskRuntime'
import { agentApi } from '@/api/endpoints/agent'
import * as agentModule from '@/api/endpoints/agent'

import { turnCompleted, presentationDelta, presentationComplete } from './testing/harnessEventFixtures'

describe('canvasAgentStore defaults', () => {
  it('disables web search by default', () => {
    expect(useChatStore.getState().webSearchEnabled).toBe(false)
  })

  it('uses a stable empty streaming block reference for no-output thinking state', () => {
    expect(useChatStore.getState().streamingBlocks).toBe(EMPTY_MESSAGE_BLOCKS)

    useChatStore.setState({
      isStreaming: true,
      streamingBlocks: EMPTY_MESSAGE_BLOCKS,
    })

    const before = useChatStore.getState().streamingBlocks
    useChatStore.getState().newChat()

    expect(before).toBe(EMPTY_MESSAGE_BLOCKS)
    expect(useChatStore.getState().streamingBlocks).toBe(EMPTY_MESSAGE_BLOCKS)
  })

  it('does not notify subscribers for replayed sequence-only events while thinking with no output', () => {
    useChatStore.getState().reset()

    const conversationId = 'conv-canvas-thinking-noop'
    const session = conversationSession({
      messages: [],
      activePlan: null,
      pendingInteraction: null,
      runStatus: 'running',
      isStreaming: true,
      currentStreamText: '',
      currentToolCalls: [],
      streamingBlocks: EMPTY_MESSAGE_BLOCKS,
      workspaceFiles: [],
      abortController: null,
      eventStreamController: null,
      lastSequence: 10,
      appliedPresentationOps: [],
      generationProjection: createGenerationProjectionState(),
      messagesPage: { hasMore: false, oldestSeq: null, loading: false },
    })

    useChatStore.setState({
      conversationId,
      messages: session.messages,
      activePlan: session.activePlan,
      pendingInteraction: session.pendingInteraction,
      isStreaming: session.isStreaming,
      currentStreamText: session.currentStreamText,
      currentToolCalls: session.currentToolCalls,
      streamingBlocks: session.streamingBlocks,
      workspaceFiles: session.workspaceFiles,
      _abortController: session.abortController,
      conversationSessions: {
        [conversationId]: session,
      },
    })

    const before = useChatStore.getState()
    let notifications = 0
    const unsubscribe = useChatStore.subscribe(() => {
      notifications += 1
    })

    __chatStoreTestUtils.handleAgentEventV2(
      ({
        type: 'subagent_completed',
        sequence: 9,
        data: { conversation_id: conversationId },
      } as unknown as AgentEvent),
      useChatStore.setState,
      useChatStore.getState,
      conversationId,
    )

    unsubscribe()
    const after = useChatStore.getState()

    expect(notifications).toBe(0)
    expect(after).toBe(before)
    expect(after.conversationSessions).toBe(before.conversationSessions)
    expect(after.messages).toBe(before.messages)
    expect(after.streamingBlocks).toBe(EMPTY_MESSAGE_BLOCKS)

    useChatStore.getState().reset()
  })

  it('treats design_workflow as an implicit canvas default instead of an explicit selected skill', () => {
    expect(__chatStoreTestUtils.normalizeCanvasSelectedSkillId('design_workflow')).toBeNull()
    expect(__chatStoreTestUtils.resolveCanvasRequestSkillId('design_workflow')).toBeNull()
    expect(__chatStoreTestUtils.normalizeCanvasSelectedSkillId('brand_strategy_architect')).toBe('brand_strategy_architect')
    expect(__chatStoreTestUtils.normalizeCanvasSelectedSkillId('vi-design-guide')).toBe('vi-design-guide')
  })

  it('normalizes the legacy product hero canvas skill id', () => {
    const legacyPolicy = {
      hiddenToolCalls: [],
      canvasDefaultSkillId: 'design_workflow',
      canvasExplicitSkillIds: ['product-hero'],
    }

    expect(__chatStoreTestUtils.normalizeCanvasSelectedSkillId('product-hero', legacyPolicy)).toBe('menswear-ecommerce-hero')
    expect(__chatStoreTestUtils.resolveCanvasRequestSkillId('product-hero', legacyPolicy)).toBe('menswear-ecommerce-hero')
  })

  it('does not send design_workflow as an explicit canvas skill when creating a harness conversation', async () => {
    const createHarnessConversationMock = vi
      .spyOn(agentApi, 'createHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-default-skill',
          title: '新会话',
          skill_id: 'design_workflow',
          runtime_profile: 'canvas',
          project_id: 64,
          phase: 'discovery',
          mode: 'fast',
          web_search_enabled: false,
          status: 'idle',
          runtime_status: 'idle',
          engine_version: 'harness',
          created_at: '2026-05-11T00:00:00Z',
          updated_at: '2026-05-11T00:00:00Z',
        }),
      }))

    useChatStore.setState({
      projectId: 64,
      activeSkillId: 'design_workflow',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
    })

    await useChatStore.getState().createHarnessConversation(undefined, undefined)

    expect(createHarnessConversationMock).toHaveBeenCalledWith(
      expect.objectContaining({
        runtime_profile: 'canvas',
        project_id: 64,
        skill_id: null,
      }),
    )
    expect(useChatStore.getState().activeSkillId).toBeNull()

    createHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('uses the backend canvas skill policy when creating a harness conversation', async () => {
    const getUiConfigMock = vi
      .spyOn(agentApi, 'getUiConfig')
      .mockResolvedValue(httpResponse({
        data: {
          hidden_tool_calls: [],
          canvas_default_skill_id: 'custom_canvas_default',
          canvas_explicit_skill_ids: ['poster'],
        },
      }))
    const createHarnessConversationMock = vi
      .spyOn(agentApi, 'createHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-policy',
          title: '新会话',
          skill_id: 'custom_canvas_default',
          runtime_profile: 'canvas',
          project_id: 64,
          phase: 'discovery',
          mode: 'fast',
          web_search_enabled: false,
          status: 'idle',
          runtime_status: 'idle',
          engine_version: 'harness',
          created_at: '2026-05-11T00:00:00Z',
          updated_at: '2026-05-11T00:00:00Z',
        }),
      }))
    const listHarnessSkillsMock = vi
      .spyOn(agentApi, 'listHarnessSkills')
      .mockResolvedValue(httpResponse({
        data: [
          {
            id: 'poster',
            name: 'Poster',
            name_en: 'Poster',
            name_zh: '海报',
            description: '',
            icon: 'image',
            color: '#1677ff',
            triggers: [],
            mode: 'image',
            default_for: [],
            preview_type: 'none',
            capabilities: {
              canvas_explicit: true,
            },
          },
        ],
      }))

    await useChatStore.getState().loadUiConfig()
    expect(useChatStore.getState().uiConfig.canvasSkills?.map(skill => skill.id)).toEqual(['poster'])
    useChatStore.setState({
      projectId: 64,
      activeSkillId: 'custom_canvas_default',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
    })

    await useChatStore.getState().createHarnessConversation(undefined, undefined)

    expect(createHarnessConversationMock).toHaveBeenCalledWith(
      expect.objectContaining({
        skill_id: null,
      }),
    )

    useChatStore.setState({ activeSkillId: 'poster' })
    await useChatStore.getState().createHarnessConversation(undefined, undefined)

    expect(createHarnessConversationMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        skill_id: 'poster',
      }),
    )

    getUiConfigMock.mockRestore()
    listHarnessSkillsMock.mockRestore()
    createHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('force reloads the backend canvas skill policy for the tools panel', async () => {
    const getUiConfigMock = vi
      .spyOn(agentApi, 'getUiConfig')
      .mockResolvedValueOnce(httpResponse({
        data: {
          hidden_tool_calls: [],
          canvas_default_skill_id: 'design_workflow',
          canvas_explicit_skill_ids: ['logo'],
        },
      }))
      .mockResolvedValueOnce(httpResponse({
        data: {
          hidden_tool_calls: [],
          canvas_default_skill_id: 'design_workflow',
          canvas_explicit_skill_ids: ['logo', 'menswear-ecommerce-hero'],
        },
      }))
    const listHarnessSkillsMock = vi
      .spyOn(agentApi, 'listHarnessSkills')
      .mockResolvedValue(httpResponse({ data: [] }))

    await useChatStore.getState().loadUiConfig()
    expect(__chatStoreTestUtils.normalizeCanvasSelectedSkillId('menswear-ecommerce-hero', useChatStore.getState().uiConfig)).toBeNull()

    await useChatStore.getState().loadUiConfig({ force: true })

    expect(getUiConfigMock).toHaveBeenCalledTimes(2)
    expect(__chatStoreTestUtils.normalizeCanvasSelectedSkillId('menswear-ecommerce-hero', useChatStore.getState().uiConfig)).toBe('menswear-ecommerce-hero')

    getUiConfigMock.mockRestore()
    listHarnessSkillsMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('sends structured canvas item references with canvas messages', async () => {
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {})
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-local-ref',
          title: 'Canvas',
          runtime_status: 'completed',
          status: 'completed',
          messages: [],
        }),
      }))

    useChatStore.setState({
      conversationId: 'conv-canvas-local-ref',
      projectId: 88,
      activeSkillId: 'canvas_agent',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: { hiddenToolCalls: [] },
    })

    await useChatStore.getState().sendMessage(
      '照着 @[本地上传图](canvas:img-local-1) 生成一张新图',
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

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-canvas-local-ref',
      expect.objectContaining({
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
      }),
      expect.any(AbortSignal),
      0,
    )

    streamHarnessSendMessageMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('sends product hero as a normal canvas skill without a prompt id', async () => {
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {})
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-null-product-prompt',
          title: 'Canvas',
          runtime_status: 'completed',
          status: 'completed',
          messages: [],
        }),
      }))

    useChatStore.setState({
      conversationId: 'conv-canvas-menswear-ecommerce-hero',
      projectId: 88,
      activeSkillId: 'menswear-ecommerce-hero',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: {
        hiddenToolCalls: [],
        canvasDefaultSkillId: 'design_workflow',
        canvasExplicitSkillIds: ['menswear-ecommerce-hero'],
      },
    })

    await useChatStore.getState().sendMessage('生成一张商品图')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-canvas-menswear-ecommerce-hero',
      expect.objectContaining({
        skill_id: 'menswear-ecommerce-hero',
        skill_selection_mode: 'manual',
        artifact_mode: 'image',
      }),
      expect.any(AbortSignal),
      0,
    )
    expect(Object.keys(streamHarnessSendMessageMock.mock.calls[0]?.[1] || {})).not.toContain(['prompt', 'id'].join('_'))

    streamHarnessSendMessageMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('keeps attachment references on the optimistic user message', async () => {
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {
        yield turnCompleted('completed', { conversation_id: 'conv-attachment-ref' })
      })

    useChatStore.setState({
      conversationId: 'conv-attachment-ref',
      projectId: 88,
      activeSkillId: 'canvas_agent',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: { hiddenToolCalls: [] },
    })

    const reference: MediaReferenceData = {
      id: 'upload:references/inputs/upload_001/source.jpeg',
      kind: 'upload_attachment',
      media_type: 'image',
      display_name: 'source.jpeg',
      source: {
        type: 'harness_input',
        path: 'references/inputs/upload_001/source.jpeg',
      },
    }

    await useChatStore.getState().sendMessage(
      'Use this image',
      [
        {
          type: 'image',
          url: 'references/inputs/upload_001/source.jpeg',
          name: 'source.jpeg',
          reference,
        },
      ],
      { references: [reference] },
    )

    expect(useChatStore.getState().messages[0].attachments?.[0]).toMatchObject({
      type: 'image',
      url: 'references/inputs/upload_001/source.jpeg',
      name: 'source.jpeg',
      reference,
    })
    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-attachment-ref',
      expect.objectContaining({
        attachments: [
          {
            type: 'image',
            url: 'references/inputs/upload_001/source.jpeg',
            name: 'source.jpeg',
            reference,
          },
        ],
        references: [reference],
      }),
      expect.any(AbortSignal),
      0,
    )

    streamHarnessSendMessageMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('keeps pending preview URLs local when sending canvas attachments', async () => {
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {
        yield turnCompleted('completed', { conversation_id: 'conv-canvas-pending-preview' })
      })

    useChatStore.setState({
      conversationId: 'conv-canvas-pending-preview',
      projectId: 1,
      activeSkillId: 'canvas_agent',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: { hiddenToolCalls: [] },
    })

    await useChatStore.getState().sendMessage(
      'Use this image',
      [
        {
          type: 'image',
          url: 'references/inputs/upload_001/source.jpeg',
          name: 'source.jpeg',
          preview_url: 'blob:pending-thumb',
          _previewObjectUrl: 'blob:pending-thumb',
          _clientAttachmentId: 'pending-1',
        },
      ],
    )

    expect(useChatStore.getState().messages[0].attachments?.[0]).toMatchObject({
      type: 'image',
      url: 'references/inputs/upload_001/source.jpeg',
      name: 'source.jpeg',
      preview_url: 'blob:pending-thumb',
    })
    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-canvas-pending-preview',
      expect.objectContaining({
        attachments: [
          {
            type: 'image',
            url: 'references/inputs/upload_001/source.jpeg',
            name: 'source.jpeg',
          },
        ],
      }),
      expect.any(AbortSignal),
      0,
    )

    streamHarnessSendMessageMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('continues from the detail snapshot event cursor after a failed canvas run is refreshed', async () => {
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {
        yield turnCompleted('failed', {
          sequence: 3,
          conversation_id: 'conv-canvas-failed-cursor',
          run_id: 'run-canvas-failed-cursor',
          message: '余额不足',
          summary: '余额不足',
        })
        yield presentationComplete(4, 'assistant-new-output', '充值后的新输出', {
          run_id: 'run-canvas-failed-cursor',
        })
        yield ({
          type: 'message_done',
          sequence: 5,
          data: {
            conversation_id: 'conv-canvas-failed-cursor',
          },
        } as unknown as AgentEvent)
      })
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* () {})
    const listWorkspaceFilesMock = vi
      .spyOn(agentApi, 'listWorkspaceFiles')
      .mockResolvedValue(httpResponse({ data: [] }))
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValueOnce(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-failed-cursor',
          title: 'Canvas',
          runtime_profile: 'canvas',
          project_id: 64,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'failed',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-20T00:00:00.000Z',
          finished_at: '2026-04-20T00:00:02.000Z',
          created_at: '2026-04-20T00:00:00.000Z',
          updated_at: '2026-04-20T00:00:02.000Z',
          projection: {
            event_last_sequence: 3,
          },
          messages: [
            {
              id: 'user-first',
              role: 'user',
              content: '第一次',
              created_at: '2026-04-20T00:00:01.000Z',
            },
            {
              id: 'assistant-old-error',
              role: 'assistant',
              content: '余额不足',
              created_at: '2026-04-20T00:00:02.000Z',
            },
          ],
        }),
      }))
      .mockResolvedValueOnce(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-failed-cursor',
          title: 'Canvas',
          runtime_profile: 'canvas',
          project_id: 64,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'completed',
          runtime_status: 'completed',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-20T00:01:00.000Z',
          finished_at: '2026-04-20T00:01:02.000Z',
          created_at: '2026-04-20T00:00:00.000Z',
          updated_at: '2026-04-20T00:01:02.000Z',
          projection: {
            event_last_sequence: 5,
          },
          messages: [
            {
              id: 'user-second',
              role: 'user',
              content: '第二次',
              created_at: '2026-04-20T00:01:01.000Z',
            },
            {
              id: 'assistant-new-output',
              role: 'assistant',
              content: '充值后的新输出',
              created_at: '2026-04-20T00:01:02.000Z',
            },
          ],
        }),
      }))

    useChatStore.setState({
      projectId: 64,
      uiConfig: { hiddenToolCalls: [] },
      modelPreferences: { auto: false },
    })

    await useChatStore.getState().loadConversation('conv-canvas-failed-cursor')
    await useChatStore.getState().sendMessage('第二次')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-canvas-failed-cursor',
      expect.objectContaining({ content: '第二次' }),
      expect.any(AbortSignal),
      3,
    )
    const session = useChatStore.getState().conversationSessions['conv-canvas-failed-cursor']
    expect(session?.messages.filter((message) => String(message.content).includes('余额不足')).length).toBeLessThanOrEqual(1)
    expect(session?.messages.some((message) => String(message.content).includes('充值后的新输出'))).toBe(true)
    expect(session?.lastSequence).toBe(5)

    await new Promise((resolve) => setTimeout(resolve, 400))

    streamHarnessSendMessageMock.mockRestore()
    streamHarnessConversationEventsMock.mockRestore()
    listWorkspaceFilesMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('surfaces a protocol error when a terminal canvas snapshot arrives without turn_completed', async () => {
    type SnapshotResponse = Awaited<ReturnType<typeof agentApi.getHarnessConversation>>
    let resolveSnapshot: ((value: SnapshotResponse) => void) | null = null
    const snapshotPromise = new Promise<SnapshotResponse>((resolve) => {
      resolveSnapshot = resolve
    })
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {
        yield presentationDelta(31, 'canvas-final', '', { run_id: 'run-canvas-live-snapshot' })
        resolveSnapshot?.(httpResponse({
          data: conversationDetail({
            id: 'conv-canvas-live-snapshot',
            title: 'Canvas',
            runtime_profile: 'canvas',
            project_id: 64,
            skill_id: 'design_workflow',
            phase: 'executing',
            mode: 'fast',
            web_search_enabled: false,
            status: 'completed',
            runtime_status: 'completed',
            engine_version: 'harness',
            run_id: null,
            started_at: '2026-04-20T00:00:00.000Z',
            finished_at: '2026-04-20T00:00:02.000Z',
            created_at: '2026-04-20T00:00:00.000Z',
            updated_at: '2026-04-20T00:00:02.000Z',
            projection: {
              event_last_sequence: 40,
            },
            messages: [],
          }),
        }))
        await snapshotPromise
        yield presentationComplete(32, 'canvas-final', '画布正文', { run_id: 'run-canvas-live-snapshot' })
        yield ({
          type: 'message_done',
          sequence: 33,
          data: {
            conversation_id: 'conv-canvas-live-snapshot',
          },
        } as unknown as AgentEvent)
      })
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* () {})
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockImplementationOnce(() => snapshotPromise)
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-live-snapshot',
          title: 'Canvas',
          runtime_profile: 'canvas',
          project_id: 64,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'completed',
          runtime_status: 'completed',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-20T00:00:00.000Z',
          finished_at: '2026-04-20T00:00:02.000Z',
          created_at: '2026-04-20T00:00:00.000Z',
          updated_at: '2026-04-20T00:00:02.000Z',
          projection: {
            event_last_sequence: 40,
          },
          messages: [],
        }),
      }))
    const listWorkspaceFilesMock = vi
      .spyOn(agentApi, 'listWorkspaceFiles')
      .mockResolvedValue(httpResponse({ data: [] }))

    useChatStore.setState({
      conversationId: 'conv-canvas-live-snapshot',
      projectId: 64,
      activeSkillId: 'design_workflow',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: { hiddenToolCalls: [] },
      conversationSessions: {
        'conv-canvas-live-snapshot': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 30,
          runStatus: 'idle',
        }),
      },
    })

    const sendPromise = useChatStore.getState().sendMessage('把标题调大')
    await Promise.resolve()
    await useChatStore.getState().loadConversation('conv-canvas-live-snapshot')
    await sendPromise

    const session = useChatStore.getState().conversationSessions['conv-canvas-live-snapshot']
    expect(session?.messages.some((message) => String(message.content).includes('画布正文'))).toBe(true)
    expect(session?.runStatus).toBe('failed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.abortController).toBeNull()
    expect(session?.lastSequence).toBe(40)
    expect(session?.messages.some((message) => String(message.content).includes('turn_completed'))).toBe(true)

    await new Promise((resolve) => setTimeout(resolve, 400))

    streamHarnessSendMessageMock.mockRestore()
    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    listWorkspaceFilesMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('surfaces a protocol error when a canvas POST stream closes after message_done without turn_completed', async () => {
    const streamHarnessSendMessageMock = vi
      .spyOn(agentModule, 'streamHarnessSendMessage')
      .mockImplementation(async function* () {
        yield presentationComplete(41, 'canvas-final-answer', '已生成 3 个方向，请选择 A/B/C。', {
          run_id: 'run-message-done-completed',
        })
        yield ({
          type: 'message_done',
          sequence: 42,
          data: {
            conversation_id: 'conv-canvas-message-done-completed',
            status: 'completed',
          },
        } as unknown as AgentEvent)
      })
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* () {})
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-message-done-completed',
          title: '鹦鹉咖啡',
          runtime_profile: 'canvas',
          project_id: 64,
          skill_id: 'vi-design-guide',
          phase: 'completed',
          mode: 'fast',
          web_search_enabled: false,
          status: 'completed',
          runtime_status: 'completed',
          engine_version: 'harness',
          run_id: 'run-message-done-completed',
          started_at: '2026-05-22T21:13:15.000Z',
          finished_at: '2026-05-22T21:15:50.000Z',
          created_at: '2026-05-22T21:13:09.000Z',
          updated_at: '2026-05-22T21:15:50.000Z',
          projection: {
            event_last_sequence: 42,
          },
          messages: [
            {
              id: 'assistant-final',
              role: 'assistant',
              content: '已生成 3 个方向，请选择 A/B/C。',
              created_at: '2026-05-22T21:15:50.000Z',
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'completed',
            run_state: 'completed',
            run_status: 'running',
            current_action: 'running:generate_image',
            user_interaction: null,
          }),
        }),
      }))
    const listWorkspaceFilesMock = vi
      .spyOn(agentApi, 'listWorkspaceFiles')
      .mockResolvedValue(httpResponse({ data: [] }))

    useChatStore.setState({
      conversationId: 'conv-canvas-message-done-completed',
      projectId: 64,
      activeSkillId: 'vi-design-guide',
      mode: 'fast',
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: { hiddenToolCalls: [] },
      conversationSessions: {
        'conv-canvas-message-done-completed': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 40,
          runStatus: 'idle',
        }),
      },
    })

    await useChatStore.getState().sendMessage('继续')

    const session = useChatStore.getState().conversationSessions['conv-canvas-message-done-completed']
    expect(session?.runStatus).toBe('failed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.abortController).toBeNull()
    expect(session?.messages.some((message) => String(message.content).includes('turn_completed'))).toBe(true)
    expect(session?.eventStreamController).toBeNull()
    expect(session?.messages.some((message) => String(message.content).includes('请选择 A/B/C'))).toBe(true)
    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()

    await new Promise((resolve) => setTimeout(resolve, 400))

    streamHarnessSendMessageMock.mockRestore()
    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    listWorkspaceFilesMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('restores persisted model preferences when loading a canvas harness conversation', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-model-prefs',
          title: 'Canvas model prefs',
          runtime_profile: 'canvas',
          project_id: 64,
          skill_id: null,
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'completed',
          runtime_status: 'idle',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-05-11T00:00:00Z',
          finished_at: '2026-05-11T00:10:00Z',
          created_at: '2026-05-11T00:00:00Z',
          updated_at: '2026-05-11T00:10:00Z',
          messages: [],
          model_preferences: {
            image_model: 'history-image',
            image_provider: 'builtin',
            video_model: 'history-video',
            video_provider: 'builtin',
            multimodal_model: 'history-chat',
            multimodal_provider: 'builtin',
            auto: false,
          },
        }),
      }))

    useChatStore.setState({
      projectId: 64,
      modelPreferences: {
        image_model: 'current-image',
        image_provider: 'current-provider',
        video_model: 'current-video',
        video_provider: 'current-provider',
        multimodal_model: 'current-chat',
        multimodal_provider: 'current-provider',
        auto: false,
      },
    })

    await useChatStore.getState().loadConversation('conv-canvas-model-prefs')

    expect(useChatStore.getState().modelPreferences).toEqual({
      image_model: 'history-image',
      image_provider: 'builtin',
      video_model: 'history-video',
      video_provider: 'builtin',
      multimodal_model: 'history-chat',
      multimodal_provider: 'builtin',
      auto: false,
    })

    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('prepends an older page and advances the pagination cursor on loadOlderMessages', async () => {
    const listMessagesMock = vi
      .spyOn(agentApi, 'listHarnessConversationMessages')
      .mockResolvedValue(httpResponse({
        data: {
          messages: [
            { id: 'older-1', role: 'user', content: '更早的问题', created_at: '2026-01-01T00:00:00Z' },
            { id: 'older-2', role: 'assistant', content: '更早的回答', created_at: '2026-01-01T00:00:01Z' },
          ],
          messages_page: { has_more: false, oldest_seq: 5 },
        },
      }))

    useChatStore.setState({
      conversationId: 'conv-older',
      projectId: 1,
      messages: [{ id: 'recent-1', role: 'user', content: '最近', createdAt: '2026-01-02T00:00:00Z' }],
      conversationSessions: {
        'conv-older': conversationSession({
          messages: [{ id: 'recent-1', role: 'user', content: '最近', createdAt: '2026-01-02T00:00:00Z' }],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'idle',
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          messagesPage: { hasMore: true, oldestSeq: 42, loading: false },
        }),
      },
    })

    await useChatStore.getState().loadOlderMessages()

    expect(listMessagesMock).toHaveBeenCalledWith('conv-older', 42, 80)
    const session = useChatStore.getState().conversationSessions['conv-older']
    expect(session?.messages.map((message) => String(message.id))).toEqual(['older-1', 'older-2', 'recent-1'])
    expect(session?.messagesPage?.hasMore).toBe(false)
    expect(session?.messagesPage?.oldestSeq).toBe(5)
    expect(session?.messagesPage?.loading).toBe(false)
    // Active-conversation mirror stays in sync.
    expect(useChatStore.getState().messages.map((message) => String(message.id))).toEqual(['older-1', 'older-2', 'recent-1'])

    listMessagesMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('skips loadOlderMessages when there is no older page', async () => {
    const listMessagesMock = vi.spyOn(agentApi, 'listHarnessConversationMessages')

    useChatStore.setState({
      conversationId: 'conv-no-older',
      projectId: 1,
      conversationSessions: {
        'conv-no-older': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'idle',
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          messagesPage: { hasMore: false, oldestSeq: null, loading: false },
        }),
      },
    })

    await useChatStore.getState().loadOlderMessages()

    expect(listMessagesMock).not.toHaveBeenCalled()

    listMessagesMock.mockRestore()
    useChatStore.getState().reset()
  })
})

describe('canvasAgentStore block deduplication', () => {
  it('does not treat plain text blocks with reused ids as duplicates across messages', () => {
    const history: ChatMessage[] = [
      {
        id: 1,
        role: 'assistant',
        content: 'Earlier step description',
        createdAt: '2026-04-26T14:53:32.000Z',
        blocks: [
          {
            id: 'text-0',
            kind: 'text',
            order: 0,
            status: 'completed',
            visible: true,
            uiKind: 'text',
            payload: { text: 'Earlier step description' },
          },
        ],
      },
    ]

    const incoming: MessageBlock = {
      id: 'text-0',
      kind: 'text',
      order: 0,
      status: 'completed',
      visible: true,
      uiKind: 'text',
      payload: { text: 'New step description' },
    }

    expect(__chatStoreTestUtils.getBlockIdentityKeys(incoming)).toEqual([])
    expect(__chatStoreTestUtils.hasEquivalentBlock(history, incoming)).toBe(false)
  })

  it('still dedupes tool blocks that carry stable call or task identities', () => {
    const history: ChatMessage[] = [
      {
        id: 2,
        role: 'assistant',
        content: null,
        createdAt: '2026-04-26T14:57:12.000Z',
        blocks: [
          {
            id: 'block-functions.generate_image:11',
            kind: 'tool',
            order: 1,
            status: 'completed',
            visible: true,
            uiKind: 'generation_task',
            payload: {
              call_id: 'functions.generate_image:11',
              task_id: 326,
            },
          },
        ],
      },
    ]

    const incoming: MessageBlock = {
      id: 'block-functions.generate_image:11',
      kind: 'tool',
      order: 1,
      status: 'completed',
      visible: true,
      uiKind: 'generation_task',
      payload: {
        call_id: 'functions.generate_image:11',
        task_id: 326,
      },
    }

    expect(__chatStoreTestUtils.getBlockIdentityKeys(incoming)).toContain('call:functions.generate_image:11')
    expect(__chatStoreTestUtils.hasEquivalentBlock(history, incoming)).toBe(true)
  })
})

describe('canvasAgentStore history replay', () => {
  it('omits implicit canvas auto-selection announcement messages from replayed history', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-auto-skill',
        role: 'assistant',
        content: '已自动选择技能：Design Workflow。',
        created_at: '2026-05-11T05:49:00.000Z',
        metadata: {
          source: 'auto_selection_announcement',
          selected_skill_id: 'design_workflow',
          previous_skill_id: null,
        },
      },
      {
        id: 'assistant-reply',
        role: 'assistant',
        content: '我来为您生成一张猴子吃葡萄的照片，然后分析其内容。',
        created_at: '2026-05-11T05:50:00.000Z',
      },
    ])

    expect(messages).toHaveLength(1)
    expect(messages[0]?.id).toBe('assistant-reply')
    expect(messages[0]?.content).toBe('我来为您生成一张猴子吃葡萄的照片，然后分析其内容。')
  })

  it('omits agent context user-intent messages from replayed history', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'msg:v2:user-visible',
        role: 'user',
        content: '基于这个背景图和基准图帮我生成一个电商平铺图',
        created_at: '2026-06-21T14:09:03.000Z',
        metadata: {
          render_kind: 'presentation_v2',
          message_key: 'conv:user-visible',
          source_event_sequence: 107,
        },
      },
      {
        id: 'agent-context:user-intent',
        role: 'user',
        content: '基于这个背景图和基准图帮我生成一个电商平铺图',
        created_at: '2026-06-21T14:09:02.000Z',
        metadata: {
          message_kind: 'agent_context',
          agent_context_kind: 'user_intent',
          ui_visible: false,
          model_visible: true,
        },
      },
    ])

    expect(messages).toHaveLength(1)
    expect(messages[0]?.id).toBe('conv:user-visible')
    expect(messages[0]?.content).toBe('基于这个背景图和基准图帮我生成一个电商平铺图')
  })

  it('keeps projected assistant summaries even when persisted with agent-context metadata', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'run:summary',
        role: 'assistant',
        content: '电商平铺图已生成完成，可以继续基于这张图调整构图或替换背景。',
        created_at: '2026-06-21T14:12:25.000Z',
        blocks: [
          {
            id: 'summary-text',
            kind: 'text',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'assistant_text',
            payload: {
              text: '电商平铺图已生成完成，可以继续基于这张图调整构图或替换背景。',
            },
          },
        ],
        metadata: {
          render_kind: 'presentation_v2',
          message_kind: 'agent_context',
          ui_visible: false,
          model_visible: true,
          source_event_sequence: 138,
        },
      },
    ])

    expect(messages).toHaveLength(1)
    expect(messages[0]?.id).toBe('run:summary')
    expect(messages[0]?.content).toBe('电商平铺图已生成完成，可以继续基于这张图调整构图或替换背景。')
    expect(messages[0]?.blocks?.[0]?.uiKind).toBe('assistant_text')
  })

  it('keeps render blocks from harness snapshots and omits raw tool payload messages', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-render-media',
        role: 'assistant',
        content: '图片生成',
        created_at: '2026-05-11T05:50:43.252Z',
        blocks: [
          {
            id: 'media-functions.generate_image:1',
            kind: 'content',
            order: 0,
            status: 'running',
            visible: true,
            ui_kind: 'media_card',
            payload: {
              tool_name: 'generate_image',
              call_id: 'functions.generate_image:1',
              title: '图片生成',
              status: 'processing',
              task_id: 'task-1',
            },
            user_visible: true,
            debug_only: false,
          },
        ],
        metadata: {
          render_only: true,
        },
      },
      {
        id: 'tool-generate-image',
        role: 'tool',
        tool_name: 'generate_image',
        tool_call_id: 'functions.generate_image:1',
        content: '{"status":"processing","task_id":"task-1","message":"图片生成任务已异步提交"}',
        created_at: '2026-05-11T05:50:45.301Z',
      },
    ])

    expect(messages).toHaveLength(1)
    expect(messages[0]?.role).toBe('assistant')
    expect(messages[0]?.content).toBeNull()
    expect(messages[0]?.blocks?.[0]?.uiKind).toBe('media_card')
    expect(messages[0]?.blocks?.[0]?.payload?.task_id).toBe('task-1')
    expect(messages.some((message) => message.role === 'tool')).toBe(false)
  })

  it.each([
    ['image analysis', 'media_card', { tool_name: 'analyze_image', media_type: 'image_analysis' }],
    ['image generation', 'media_card', { tool_name: 'generate_image', media_type: 'image_generation' }],
    ['video generation', 'media_card', { tool_name: 'generate_video', media_type: 'video_generation' }],
    ['generation status', 'generation_card', { tool_name: 'generate_image' }],
    ['web search', 'web_search_card', { query: 'canvas agent render order' }],
  ])('keeps render-only %s cards before later assistant summaries on replay', (_label, uiKind, payload) => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: `assistant-render-${uiKind}`,
        role: 'assistant',
        content: null,
        created_at: '2026-06-16T08:00:00.000Z',
        blocks: [
          {
            id: `card-${uiKind}`,
            kind: 'content',
            order: 2,
            status: 'completed',
            visible: true,
            ui_kind: uiKind,
            payload,
            user_visible: true,
            debug_only: false,
          },
        ],
        metadata: {
          render_kind: 'presentation_v2',
          render_only: true,
          message_key: `run:render:${uiKind}`,
        },
      },
      {
        id: 'assistant-final-summary',
        role: 'assistant',
        content: '最终总结',
        created_at: '2026-06-16T08:01:00.000Z',
        blocks: [
          {
            id: 'final-summary-text',
            kind: 'text',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'assistant_final_answer',
            payload: { text: '最终总结' },
          },
        ],
      },
    ])

    expect(messages).toHaveLength(2)
    expect(messages[0]?.id).toBe(`run:render:${uiKind}`)
    expect(messages[0]?.blocks?.[0]?.uiKind).toBe(uiKind)
    expect(messages[1]?.id).toBe('assistant-final-summary')
    expect(messages[1]?.blocks?.[0]?.uiKind).toBe('assistant_final_answer')
  })

  it('replays submitted interaction answers from persisted user message metadata back into prior interaction cards', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-interaction-render',
        role: 'assistant',
        content: null,
        created_at: '2026-05-12T09:00:00.000Z',
        blocks: [
          {
            id: 'interaction-form:functions.ask_user:11',
            kind: 'interaction',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'interaction_form',
            payload: {
              request_id: 'functions.ask_user:11',
              requestId: 'functions.ask_user:11',
              question: '请选择两岸表达方向',
              kind: 'ask_user',
              schema: {
                title: '方向确认',
                fields: [
                  {
                    id: 'direction',
                    label: 'Direction',
                    type: 'radio',
                    options: [
                      { label: '历史怀旧交融', value: 'historic_mix' },
                      { label: '现代文创简约', value: 'modern_minimal' },
                    ],
                  },
                ],
              },
              answers: null,
              status: 'pending',
            },
            user_visible: true,
            debug_only: false,
          },
        ],
      },
      {
        id: 'user-interaction-submission',
        role: 'user',
        content: '商务与深度社交 / 历史怀旧交融',
        created_at: '2026-05-12T09:00:10.000Z',
        metadata: {
          source: 'preflight_interaction_submission',
          request_id: 'functions.ask_user:11',
          answer: '{"scene":"business_social","direction":{"type":"option","value":"historic_mix","label":"历史怀旧交融"}}',
          display_label: '商务与深度社交 / 历史怀旧交融',
          answers: {
            scene: {
              type: 'option',
              value: 'business_social',
              label: '商务与深度社交',
            },
            direction: {
              type: 'option',
              value: 'historic_mix',
              label: '历史怀旧交融',
            },
          },
        },
      },
      {
        id: 'assistant-next-question',
        role: 'assistant',
        content: '继续确认后续产品方向',
        created_at: '2026-05-12T09:00:20.000Z',
      },
    ])

    const interactionBlock = messages[0]?.blocks?.[0]
    expect(interactionBlock?.uiKind).toBe('interaction_form')
    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.answers).toEqual({
      scene: {
        type: 'option',
        value: 'business_social',
        label: '商务与深度社交',
      },
      direction: {
        type: 'option',
        value: 'historic_mix',
        label: '历史怀旧交融',
      },
    })
    expect(interactionBlock?.payload.submittedLabel).toBe('商务与深度社交 / 历史怀旧交融')
    expect(messages[1]?.role).toBe('user')
    expect(messages[2]?.role).toBe('assistant')
  })

  it('restores user message skill ids from persisted metadata during history replay', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'user-with-explicit-skill',
        role: 'user',
        content: '先做品牌策略',
        created_at: '2026-05-12T09:00:00.000Z',
        metadata: {
          skill_id: 'brand_strategy_architect',
        },
      },
      {
        id: 'user-with-selected-skill',
        role: 'user',
        content: '继续做 logo',
        created_at: '2026-05-12T09:00:10.000Z',
        metadata: {
          selected_skill_id: 'logo',
        },
      },
    ])

    expect(messages[0]?.role).toBe('user')
    expect(messages[0]?.skillId).toBe('brand_strategy_architect')
    expect(messages[1]?.role).toBe('user')
    expect(messages[1]?.skillId).toBe('logo')
  })

  it('replaces a stale streaming canvas session with persisted interaction messages once the snapshot is waiting for input', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-runtime-interaction',
          title: '阿旭咖啡',
          runtime_profile: 'canvas',
          project_id: 64,
          skill_id: 'brand_strategy_architect',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'waiting_input',
          created_at: '2026-05-12T15:35:35.000Z',
          updated_at: '2026-05-12T15:35:51.000Z',
          started_at: '2026-05-12T15:35:35.000Z',
          finished_at: null,
          run_id: 'run-ask-user',
          messages: [
            {
              id: 'assistant-ask-user-render',
              role: 'assistant',
              content: '阿旭咖啡 - 0-1 阶段品牌基础信息确认',
              created_at: '2026-05-12T15:35:52.000Z',
              blocks: [
                {
                  id: 'interaction-form:functions.ask_user:restore',
                  kind: 'interaction',
                  order: 0,
                  status: 'completed',
                  visible: true,
                  ui_kind: 'interaction_form',
                  payload: {
                    request_id: 'functions.ask_user:restore',
                    requestId: 'functions.ask_user:restore',
                    tool_call_id: 'functions.ask_user:restore',
                    toolCallId: 'functions.ask_user:restore',
                    question: '青岛阿旭咖啡品牌战略确认',
                    content: '### Gate A\n\n- 两岸人文融合\n- 第三空间定位',
                    kind: 'ask_user',
                    status: 'pending',
                    schema: {
                      title: '青岛阿旭咖啡品牌战略确认',
                      submit_label: '确认并继续',
                      fields: [
                        {
                          id: 'brand_stage',
                          label: '品牌阶段',
                          type: 'radio',
                          options: [{ label: '0-1 新建品牌', value: 'new' }],
                        },
                      ],
                    },
                    answers: null,
                  },
                  render_key: 'interaction:functions.ask_user:restore',
                  user_visible: true,
                  debug_only: false,
                },
              ],
              metadata: {
                render_key: 'interaction:functions.ask_user:restore',
              },
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'waiting_input',
            run_state: 'waiting_input',
            user_interaction: {
              request_id: 'functions.ask_user:restore',
              tool_call_id: 'functions.ask_user:restore',
              question: '青岛阿旭咖啡品牌战略确认',
              content: '### Gate A\n\n- 两岸人文融合\n- 第三空间定位',
              kind: 'ask_user',
              status: 'pending',
              schema: {
                title: '青岛阿旭咖啡品牌战略确认',
                submit_label: '确认并继续',
                fields: [
                  {
                    id: 'brand_stage',
                    label: '品牌阶段',
                    type: 'radio',
                    options: [{ label: '0-1 新建品牌', value: 'new' }],
                  },
                ],
              },
            },
          }),
        }),
      }))

    useChatStore.setState({
      projectId: 64,
      viewerUserId: null,
      conversationId: 'conv-runtime-interaction',
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: '计一个阿旭咖啡的品牌在青岛，300平米大小，然后关于两岸主体',
          createdAt: '2026-05-12T15:35:36.000Z',
        },
      ],
      pendingInteraction: null,
      isStreaming: true,
      currentStreamText: '',
      streamingBlocks: [],
      conversationSessions: {
        'conv-runtime-interaction': conversationSession({
          messages: [
            {
              id: 'user-1',
              role: 'user',
              content: '计一个阿旭咖啡的品牌在青岛，300平米大小，然后关于两岸主体',
              createdAt: '2026-05-12T15:35:36.000Z',
            },
          ],
          activePlan: null,
          pendingInteraction: null,
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
        }),
      },
      conversations: [],
    })

    await useChatStore.getState().loadConversation('conv-runtime-interaction')

    const state = useChatStore.getState()
    expect(state.pendingInteraction?.request_id).toBe('functions.ask_user:restore')
    expect(state.isStreaming).toBe(false)
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.blocks).toHaveLength(1)
    expect(state.messages[0]?.blocks?.[0]?.uiKind).toBe('interaction_form')
    expect(state.messages[0]?.blocks?.[0]?.payload?.content).toBe('### Gate A\n\n- 两岸人文融合\n- 第三空间定位')
    expect(wireRecord(state.messages[0]?.blocks?.[0]?.payload?.schema)?.title).toBe('青岛阿旭咖啡品牌战略确认')

    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('persists cancellation when stopping a running canvas conversation', async () => {
    const cancelHarnessConversationRunMock = vi
      .spyOn(agentApi, 'cancelHarnessConversationRun')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-cancel',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'cancelled',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:01:00.000Z',
          started_at: '2026-05-13T07:00:00.000Z',
          finished_at: '2026-05-13T07:01:00.000Z',
          run_id: 'run-cancelled',
          messages: [
            {
              id: 'assistant-image-failed',
              role: 'assistant',
              content: null,
              created_at: '2026-05-13T07:00:40.000Z',
              blocks: [
                {
                  id: 'media-card-1',
                  kind: 'content',
                  order: 0,
                  status: 'failed',
                  visible: true,
                  ui_kind: 'media_card',
                  payload: {
                    tool_name: 'generate_image',
                    title: '图片生成',
                    status: 'failed',
                  },
                },
              ],
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'cancelled',
            run_state: 'cancelled',
            user_interaction: null,
          }),
        }),
      }))

    const abortController = new AbortController()
    const eventStreamController = new AbortController()
    useChatStore.setState({
      conversationId: 'conv-canvas-cancel',
      projectId: 70,
      viewerUserId: null,
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: '生成一个猴子的图片，然后分析下这个图片的内容',
          createdAt: '2026-05-13T07:00:00.000Z',
        },
      ],
      pendingInteraction: null,
      isStreaming: true,
      currentStreamText: '',
      streamingBlocks: [],
      conversations: [
        conversationDetail({
          id: 'conv-canvas-cancel',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:00:30.000Z',
        }),
      ],
      conversationSessions: {
        'conv-canvas-cancel': conversationSession({
          messages: [
            {
              id: 'user-1',
              role: 'user',
              content: '生成一个猴子的图片，然后分析下这个图片的内容',
              createdAt: '2026-05-13T07:00:00.000Z',
            },
          ],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'running',
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController,
          eventStreamController,
          lastSequence: 0,
        }),
      },
    })

    useChatStore.getState().stopStreaming()
    await new Promise((resolve) => setTimeout(resolve, 0))

    const state = useChatStore.getState()
    expect(cancelHarnessConversationRunMock).toHaveBeenCalledWith('conv-canvas-cancel')
    expect(abortController.signal.aborted).toBe(true)
    expect(eventStreamController.signal.aborted).toBe(true)
    expect(state.conversationSessions['conv-canvas-cancel']?.runStatus).toBe('cancelled')
    expect(state.conversationSessions['conv-canvas-cancel']?.isStreaming).toBe(false)
    expect(state.conversations[0]?.runtime_status).toBe('cancelled')

    cancelHarnessConversationRunMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('keeps the canvas session cancelled when the cancel endpoint only acknowledges a healthy foreign owner request', async () => {
    const cancelHarnessConversationRunMock = vi
      .spyOn(agentApi, 'cancelHarnessConversationRun')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-cancel-requested',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          run_state: 'executing',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:01:00.000Z',
          started_at: '2026-05-13T07:00:00.000Z',
          finished_at: null,
          run_id: 'run-cancel-requested',
          messages: [],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'running',
            run_state: 'executing',
            user_interaction: null,
          }),
        }),
      }))

    const abortController = new AbortController()
    const eventStreamController = new AbortController()
    useChatStore.setState({
      conversationId: 'conv-canvas-cancel-requested',
      projectId: 70,
      viewerUserId: null,
      messages: [],
      pendingInteraction: null,
      isStreaming: true,
      currentStreamText: '',
      streamingBlocks: [],
      conversations: [
        conversationDetail({
          id: 'conv-canvas-cancel-requested',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:00:30.000Z',
        }),
      ],
      conversationSessions: {
        'conv-canvas-cancel-requested': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'running',
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController,
          eventStreamController,
          lastSequence: 0,
        }),
      },
    })

    useChatStore.getState().stopStreaming()
    await new Promise((resolve) => setTimeout(resolve, 0))

    const state = useChatStore.getState()
    expect(state.conversationSessions['conv-canvas-cancel-requested']?.runStatus).toBe('cancelled')
    expect(state.conversationSessions['conv-canvas-cancel-requested']?.isStreaming).toBe(false)
    expect(state.conversations[0]?.runtime_status).toBe('cancelled')

    cancelHarnessConversationRunMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('replays a cancelled canvas conversation without resubscribing to SSE', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-detail-cancelled',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'cancelled',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:01:00.000Z',
          started_at: '2026-05-13T07:00:00.000Z',
          finished_at: '2026-05-13T07:01:00.000Z',
          run_id: 'run-cancelled',
          messages: [
            {
              id: 'assistant-cancelled',
              role: 'assistant',
              content: '图片生成已取消',
              created_at: '2026-05-13T07:01:00.000Z',
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'cancelled',
            run_state: 'cancelled',
            user_interaction: null,
          }),
        }),
      }))
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* () {})

    await useChatStore.getState().loadConversation('conv-canvas-detail-cancelled')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().isStreaming).toBe(false)

    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('applies a turn_completed(cancelled) SSE event immediately without waiting for a detail refresh', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-live-cancelled',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:00:30.000Z',
          started_at: '2026-05-13T07:00:00.000Z',
          finished_at: null,
          run_id: 'run-live-cancelled',
          messages: [
            {
              id: 'assistant-main',
              role: 'assistant',
              content: 'Preparing response',
              created_at: '2026-05-13T07:00:02.000Z',
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'running',
            run_state: 'executing',
            user_interaction: null,
          }),
        }),
      }))
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* () {
        yield turnCompleted('cancelled', {
          sequence: 3,
          conversation_id: 'conv-canvas-live-cancelled',
          run_id: 'run-live-cancelled',
        })
      })

    useChatStore.setState({ projectId: 70, viewerUserId: null })
    await useChatStore.getState().loadConversation('conv-canvas-live-cancelled')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-canvas-live-cancelled']
    expect(session?.runStatus).toBe('cancelled')
    expect(session?.isStreaming).toBe(false)
    expect(useChatStore.getState().conversations[0]?.runtime_status).toBe('cancelled')

    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('keeps a newer canvas run active when an older turn_completed(cancelled) event arrives late', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-run-race',
          title: '鹦鹉咖啡',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'brand_strategy_architect',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          created_at: '2026-05-19T14:44:42.000Z',
          updated_at: '2026-05-19T14:44:51.000Z',
          started_at: '2026-05-19T14:44:51.000Z',
          finished_at: null,
          run_id: 'run-old',
          messages: [
            {
              id: 'user-first',
              role: 'user',
              content: '你好',
              created_at: '2026-05-19T14:44:43.000Z',
            },
            {
              id: 'user-second',
              role: 'user',
              content: '鹦鹉咖啡',
              created_at: '2026-05-19T14:44:51.000Z',
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'running',
            run_status: 'running',
            run_state: 'executing',
            run_id: 'run-old',
            user_interaction: null,
          }),
        }),
      }))
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* (
        _conversationId: string | number,
        afterSequenceOrSignal?: number | AbortSignal,
        signal?: AbortSignal,
      ) {
        const activeSignal = afterSequenceOrSignal instanceof AbortSignal
          ? afterSequenceOrSignal
          : signal
        yield {
          type: 'turn_started',
          sequence: 3,
          run_id: 'run-new',
          data: {
            conversation_id: 'conv-canvas-run-race',
            runtime_status: 'running',
          },
        }
        yield turnCompleted('cancelled', {
          sequence: 4,
          conversation_id: 'conv-canvas-run-race',
          run_id: 'run-old',
        })
        await new Promise<void>((resolve) => {
          activeSignal?.addEventListener('abort', () => resolve(), { once: true })
        })
      })

    useChatStore.setState({ projectId: 70, viewerUserId: null })
    await useChatStore.getState().loadConversation('conv-canvas-run-race')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-canvas-run-race']
    expect(session?.runStatus).toBe('running')
    expect(session?.isStreaming).toBe(true)
    expect(session?.lastSequence).toBe(4)

    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('applies a turn_completed(failed) SSE event immediately without waiting for a detail refresh', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValue(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-live-failed',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:00:30.000Z',
          started_at: '2026-05-13T07:00:00.000Z',
          finished_at: null,
          run_id: 'run-live-failed',
          messages: [
            {
              id: 'assistant-main',
              role: 'assistant',
              content: 'Preparing response',
              created_at: '2026-05-13T07:00:02.000Z',
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'running',
            run_state: 'executing',
            user_interaction: null,
          }),
        }),
      }))
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation(async function* () {
        yield turnCompleted('failed', {
          sequence: 3,
          conversation_id: 'conv-canvas-live-failed',
          run_id: 'run-live-failed',
          terminal_error: 'tool crashed',
          summary: 'tool crashed',
          failure_signature: 'sig-canvas-live-failed',
        })
      })

    useChatStore.setState({ projectId: 70, viewerUserId: null })
    await useChatStore.getState().loadConversation('conv-canvas-live-failed')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-canvas-live-failed']
    expect(session?.runStatus).toBe('failed')
    expect(session?.isStreaming).toBe(false)
    expect(useChatStore.getState().conversations[0]?.runtime_status).toBe('failed')
    expect(session?.messages[session.messages.length - 1]?.content).toContain('tool crashed')

    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })

  it('keeps a running canvas harness conversation alive when the SSE transport detaches and resubscribes after the shared delay', async () => {
    const getHarnessConversationMock = vi
      .spyOn(agentApi, 'getHarnessConversation')
      .mockResolvedValueOnce(httpResponse({
        data: conversationDetail({
          id: 'conv-canvas-live-running',
          title: '生成一个猴子的图片',
          runtime_profile: 'canvas',
          project_id: 70,
          skill_id: 'design_workflow',
          phase: 'executing',
          mode: 'fast',
          web_search_enabled: false,
          status: 'active',
          runtime_status: 'running',
          created_at: '2026-05-13T07:00:00.000Z',
          updated_at: '2026-05-13T07:00:30.000Z',
          started_at: '2026-05-13T07:00:00.000Z',
          finished_at: null,
          run_id: 'run-live-running',
          messages: [
            {
              id: 'assistant-main',
              role: 'assistant',
              content: 'Preparing response',
              created_at: '2026-05-13T07:00:02.000Z',
            },
          ],
          workspace_files: [],
          runtime_state: runtimeState({
            runtime_status: 'running',
            run_state: 'executing',
            user_interaction: null,
          }),
        }),
      }))
    getHarnessConversationMock.mockResolvedValueOnce(httpResponse({
      data: conversationDetail({
        id: 'conv-canvas-live-running',
        title: '生成一个猴子的图片',
        runtime_profile: 'canvas',
        project_id: 70,
        skill_id: 'design_workflow',
        phase: 'executing',
        mode: 'fast',
        web_search_enabled: false,
        status: 'active',
        runtime_status: 'running',
        created_at: '2026-05-13T07:00:00.000Z',
        updated_at: '2026-05-13T07:00:45.000Z',
        started_at: '2026-05-13T07:00:00.000Z',
        finished_at: null,
        run_id: 'run-live-running',
        messages: [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Preparing response',
            created_at: '2026-05-13T07:00:02.000Z',
          },
        ],
        workspace_files: [],
        runtime_state: runtimeState({
          runtime_status: 'running',
          run_state: 'executing',
          user_interaction: null,
        }),
      }),
    }))

    let streamCalls = 0
    const streamHarnessConversationEventsMock = vi
      .spyOn(agentModule, 'streamHarnessConversationEvents')
      .mockImplementation((() => {
        return async function* (
          _conversationId: string | number,
          afterSequenceOrSignal?: number | AbortSignal,
          signal?: AbortSignal,
        ) {

          const activeSignal = afterSequenceOrSignal instanceof AbortSignal
            ? afterSequenceOrSignal
            : signal
          streamCalls += 1
          if (streamCalls === 1) {
            return
          }
          await new Promise<void>((resolve) => {
            activeSignal?.addEventListener('abort', () => resolve(), { once: true })
          })
          yield* [] // This fixture intentionally emits no events.
        }
      })())

    useChatStore.setState({ projectId: 70, viewerUserId: null })
    await useChatStore.getState().loadConversation('conv-canvas-live-running')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 800))

    const session = useChatStore.getState().conversationSessions['conv-canvas-live-running']
    expect(streamHarnessConversationEventsMock).toHaveBeenCalledTimes(2)
    expect(session?.runStatus).toBe('running')
    expect(session?.isStreaming).toBe(true)

    streamHarnessConversationEventsMock.mockRestore()
    getHarnessConversationMock.mockRestore()
    useChatStore.getState().reset()
  })
})

describe('canvasAgentStore stream delta batching', () => {
  beforeEach(() => {
    useChatStore.setState({
      conversationId: 183,
      projectId: 1,
      viewerUserId: null,
      messages: [],
      activePlan: null,
      pendingInteraction: null,
      isStreaming: true,
      mode: 'fast',
      activeSkillId: null,
      webSearchEnabled: false,
      modelPreferences: { auto: false },
      uiConfig: { hiddenToolCalls: [] },
      currentStreamText: '',
      currentToolCalls: [],
      streamingBlocks: [],
      conversations: [],
      conversationsHasMore: false,
      conversationsPage: 1,
      engineVersion: 'harness',
      workspaceFiles: [],
      _abortController: null,
      conversationSessions: {
        '183': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [
            {
              id: 'assistant-stream-text',
              kind: 'text',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'text',
              payload: {
                text: '',
              },
            },
          ],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
        }),
      },
    })
  })

  afterEach(() => {
    useChatStore.getState().reset()
  })

  it('applies repeated presentation delta events through the shared projection core', () => {
    const { flushPendingStreamBlockDeltas, handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState

    handleAgentEventV2(
      presentationDelta(11, 'assistant-stream-text', 'Hello '),
      set,
      get,
      183,
    )
    handleAgentEventV2(
      presentationDelta(12, 'assistant-stream-text', 'world'),
      set,
      get,
      183,
    )

    flushPendingStreamBlockDeltas(set, get, 183)

    expect(useChatStore.getState().conversationSessions['183']?.messages[0]?.content).toBe('Hello world')
    expect(useChatStore.getState().conversationSessions['183']?.lastSequence).toBe(12)
  })

  it('ignores replayed presentation delta events by source sequence and op id', () => {
    const { flushPendingStreamBlockDeltas, handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState

    useChatStore.setState((state) => ({
      ...state,
      conversationSessions: {
        ...state.conversationSessions,
        '183': conversationSession({
          ...state.conversationSessions['183'],
          lastSequence: 11,
        }),
      },
    }))

    const replayed = presentationDelta(11, 'assistant-stream-text', 'old replay')
    useChatStore.setState((state) => ({
      ...state,
      conversationSessions: {
        ...state.conversationSessions,
        '183': conversationSession({
          ...state.conversationSessions['183'],
          appliedPresentationOps: [replayed.data.op_id],
        }),
      },
    }))

    handleAgentEventV2(replayed, set, get, 183)
    flushPendingStreamBlockDeltas(set, get, 183)

    expect(useChatStore.getState().conversationSessions['183']?.messages[0]?.content || '').toBe('')

    handleAgentEventV2(presentationDelta(12, 'assistant-stream-text', 'new text'), set, get, 183)
    flushPendingStreamBlockDeltas(set, get, 183)

    expect(useChatStore.getState().conversationSessions['183']?.messages[0]?.content).toBe('new text')
    expect(useChatStore.getState().conversationSessions['183']?.lastSequence).toBe(12)
  })

  it('applies same-sequence turn_completed while a stream is still open even when blocks have no source sequence', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState

    useChatStore.setState((state) => ({
      ...state,
      conversationSessions: {
        ...state.conversationSessions,
        '183': conversationSession({
          ...state.conversationSessions['183'],
          isStreaming: true,
          runStatus: 'running',
          lastSequence: 94,
          messages: [
            {
              id: 'assistant-terminal-text',
              role: 'assistant',
              content: '最终回答',
              createdAt: '2026-06-07T18:47:02.000Z',
              blocks: [
                {
                  id: 'assistant-terminal-text',
                  kind: 'text',
                  order: 0,
                  status: 'completed',
                  visible: true,
                  uiKind: 'text',
                  payload: { text: '最终回答' },
                  revision: 0,
                  sourceSequence: 0,
                },
              ],
            },
          ],
          streamingBlocks: [],
        }),
      },
    }))

    handleAgentEventV2(
      turnCompleted('completed', {
        sequence: 94,
        conversation_id: '183',
        run_id: 'run-canvas-terminal-cursor',
      }),
      set,
      get,
      183,
    )

    const session = useChatStore.getState().conversationSessions['183']
    expect(session?.runStatus).toBe('completed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.lastSequence).toBe(94)
  })

  it('dispatches canvas_update generated media events through the store', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'canvas_update',
      sequence: 25,
      data: {
        action: 'add_generated_media',
        item: {
          id: 'media-1',
          type: 'image',
          url: '/api/v1/uploads/generated/media-1.png',
          status: 'completed',
          task_id: 347,
        },
        message_id: 'assistant-message-1',
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledTimes(1)
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'add_generated_media',
      expect.objectContaining({
        id: 'media-1',
        url: '/api/v1/uploads/generated/media-1.png',
        conversationId: 183,
        messageId: 'assistant-message-1',
      }),
    )
    expect(useChatStore.getState().conversationSessions['183']?.lastSequence).toBe(25)
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('dispatches canvas revision meta with direct canvas_update events', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'canvas_update',
      sequence: 26,
      data: {
        action: 'add_generated_media',
        canvas_revision: 41,
        canvas_item_deleted: false,
        item: {
          id: 'media-revision-1',
          type: 'image',
          url: '/api/v1/uploads/generated/media-revision-1.png',
          status: 'completed',
          task_id: 348,
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'sync_canvas_revision',
      {},
      { canvasRevision: 41, canvasItemDeleted: false },
    )
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'add_generated_media',
      expect.objectContaining({
        id: 'media-revision-1',
        canvas_revision: 41,
      }),
      { canvasRevision: 41, canvasItemDeleted: false },
    )
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('dispatches canvas revision meta from nested canvas_update payloads', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'canvas_update',
      sequence: 27,
      data: {
        payload: {
          action: 'add_generated_media',
          canvas_revision: 43,
          canvas_item: {
            id: 'media-revision-payload',
            type: 'image',
            url: '/api/v1/uploads/generated/media-revision-payload.png',
            status: 'completed',
          },
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'sync_canvas_revision',
      {},
      { canvasRevision: 43, canvasItemDeleted: false },
    )
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'add_generated_media',
      expect.objectContaining({
        id: 'media-revision-payload',
        canvas_revision: 43,
      }),
      { canvasRevision: 43, canvasItemDeleted: false },
    )
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('dispatches canvas revision meta with completed generation events', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'generation_completed',
      sequence: 28,
      data: {
        result: {
          task_id: 349,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/media-revision-2.png',
          artifact_ref: 'artifact_ref:media-revision-2',
          canvas_revision: 42,
          canvas_item_deleted: false,
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'sync_canvas_revision',
      {},
      { canvasRevision: 42, canvasItemDeleted: false },
    )
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'add_generated_media',
      expect.objectContaining({
        url: '/api/v1/uploads/generated/media-revision-2.png',
        canvas_revision: 42,
      }),
      { canvasRevision: 42, canvasItemDeleted: false },
    )
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('syncs canvas revision before dispatching completed video generation replacements once', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'generation_completed',
      sequence: 29,
      data: {
        result: {
          task_id: 350,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/video-revision-1.mp4',
          artifact_ref: 'artifact_ref:video-revision-1',
          canvas_revision: 44,
          canvas_item_deleted: false,
          canvas_item: {
            id: 'agent-generated-video-revision-1',
            type: 'video',
            task_id: '350',
            artifact_ref: 'artifact_ref:video-revision-1',
            url: '/api/v1/uploads/generated/video-revision-1.mp4',
          },
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenNthCalledWith(
      1,
      'sync_canvas_revision',
      {},
      { canvasRevision: 44, canvasItemDeleted: false },
    )
    const mediaCalls = onCanvasUpdate.mock.calls.filter(([action]) => action === 'add_generated_media')
    expect(mediaCalls).toHaveLength(1)
    expect(mediaCalls[0]).toEqual([
      'add_generated_media',
      expect.objectContaining({
        id: 'agent-generated-video-revision-1',
        type: 'video',
        url: '/api/v1/uploads/generated/video-revision-1.mp4',
        canvas_revision: 44,
      }),
      { canvasRevision: 44, canvasItemDeleted: false },
    ])
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('syncs canvas revision from failed generation events even when no canvas update is emitted', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'generation_failed',
      sequence: 29,
      data: {
        result: {
          task_id: 350,
          status: 'failed',
          artifact_ref: 'artifact_ref:failed-no-insert',
          canvas_revision: 44,
          canvas_item_deleted: false,
          error_message: 'Provider failed',
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledTimes(1)
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'sync_canvas_revision',
      {},
      { canvasRevision: 44, canvasItemDeleted: false },
    )
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('syncs canvas revision from live item_completed generation task events', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'item_completed',
      sequence: 32,
      data: {
        conversation_id: '183',
        item_type: 'generation_task',
        item_id: 'artifact_ref:item-completed-image',
        status: 'completed',
        payload: {
          task_id: '353',
          artifact_ref: 'artifact_ref:item-completed-image',
          kind: 'image',
          status: 'completed',
          result_url: '/api/v1/uploads/generated/item-completed-image.png',
          canvas_revision: 47,
          canvas_item_deleted: false,
          canvas_item: {
            id: 'agent-generated-item-completed-image',
            type: 'image',
            task_id: '353',
            artifact_ref: 'artifact_ref:item-completed-image',
            url: '/api/v1/uploads/generated/item-completed-image.png',
          },
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenNthCalledWith(
      1,
      'sync_canvas_revision',
      {},
      { canvasRevision: 47, canvasItemDeleted: false },
    )
    expect(onCanvasUpdate.mock.calls.filter(([action]) => action === 'add_generated_media')).toHaveLength(1)
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'add_generated_media',
      expect.objectContaining({
        id: 'agent-generated-item-completed-image',
        url: '/api/v1/uploads/generated/item-completed-image.png',
        canvas_revision: 47,
      }),
    )
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('syncs deleted backend canvas revision tombstones without resolving stale', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'generation_completed',
      sequence: 30,
      data: {
        result: {
          task_id: 351,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/deleted.png',
          artifact_ref: 'artifact_ref:deleted-sync',
          canvas_revision: 45,
          canvas_item_deleted: true,
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'sync_canvas_revision',
      {},
      { canvasRevision: 45, canvasItemDeleted: true },
    )
    expect(onCanvasUpdate).not.toHaveBeenCalledWith(
      'add_generated_media',
      expect.anything(),
      expect.anything(),
    )
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('syncs canvas revision from presentation media blocks before projection handling', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2(
      presentationComplete(31, 'media-task-failed', '', {
        ui_kind: 'media_card',
        status: 'failed',
        payload: {
          tool_name: 'generate_image',
          status: 'failed',
          task_id: '352',
          artifact_ref: 'artifact_ref:presentation-failed',
          canvas_revision: 46,
          canvas_item_deleted: false,
          error_message: 'Provider failed',
          canvas_item: {
            id: 'agent-generated-presentation-failed',
            type: 'image_generator',
            status: 'failed',
            task_id: '352',
          },
        },
      }),
      set,
      get,
      183,
    )

    expect(onCanvasUpdate).toHaveBeenCalledTimes(1)
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'sync_canvas_revision',
      {},
      { canvasRevision: 46, canvasItemDeleted: false },
    )
    expect(useChatStore.getState().conversationSessions['183']?.messages[0]?.blocks?.[0]).toMatchObject({
      id: 'media-task-failed',
      status: 'failed',
      uiKind: 'media_card',
    })
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('ignores invalid or inactive canvas revision metadata', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)

    handleAgentEventV2({
      type: 'generation_failed',
      sequence: 32,
      data: {
        result: {
          task_id: 353,
          status: 'failed',
          artifact_ref: 'artifact_ref:invalid-revision',
          canvas_revision: -1,
        },
      },
    }, set, get, 183)

    handleAgentEventV2({
      type: 'generation_failed',
      sequence: 33,
      data: {
        result: {
          task_id: 354,
          status: 'failed',
          artifact_ref: 'artifact_ref:inactive-revision',
          canvas_revision: 47,
        },
      },
    }, set, get, 184)

    expect(onCanvasUpdate).not.toHaveBeenCalled()
    useChatStore.getState().setOnCanvasUpdate(null)
  })

  it('ignores replayed canvas side-effect events but accepts newer generation events', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.getState().setOnCanvasUpdate(onCanvasUpdate)
    useChatStore.setState((state) => ({
      ...state,
      conversationSessions: {
        ...state.conversationSessions,
        '183': conversationSession({
          ...state.conversationSessions['183'],
          lastSequence: 25,
        }),
      },
    }))

    handleAgentEventV2({
      type: 'canvas_update',
      sequence: 25,
      data: {
        action: 'add_generated_media',
        item: {
          id: 'old-media',
          type: 'image',
          url: '/old.png',
        },
      },
    }, set, get, 183)

    handleAgentEventV2({
      type: 'generation_completed',
      sequence: 26,
      data: {
        task_id: 348,
        result: {
          task_id: 348,
          status: 'completed',
          result_url: '/api/v1/uploads/generated/new-media.png',
          artifact_id: 'new-media',
        },
      },
    }, set, get, 183)

    expect(onCanvasUpdate).toHaveBeenCalledTimes(1)
    expect(onCanvasUpdate).toHaveBeenCalledWith(
      'add_generated_media',
      expect.objectContaining({
        id: 'new-media',
        url: '/api/v1/uploads/generated/new-media.png',
        conversationId: 183,
      }),
    )
    expect(useChatStore.getState().conversationSessions['183']?.lastSequence).toBe(26)
    useChatStore.getState().setOnCanvasUpdate(null)
  })
})

describe('canvasAgentStore updateToolCall', () => {
  it('updates active nested generation blocks even when the conversation session has not been initialized yet', () => {
    const assistantMessage: ChatMessage = {
      id: 'assistant-2',
      role: 'assistant',
      content: null,
      createdAt: '2026-05-02T05:07:04.741Z',
      blocks: [
        {
          id: 'subagent-subagent_c841054f508f',
          kind: 'tool',
          order: 0,
          status: 'completed',
          visible: true,
          uiKind: 'subagent_card',
          payload: {
            task_id: 'subagent_c841054f508f',
            label: '卫生巾品牌设计',
            status: 'completed',
          },
          children: [
            {
              id: 'subagent_c841054f508f-functions.generate_image:7',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                tool_name: 'generate_image',
                call_id: 'functions.generate_image:7',
                status: 'processing',
                progress: 0,
                task_id: 347,
                result: {
                  task_id: 347,
                  status: 'processing',
                  progress: 0,
                },
              },
            },
          ],
        },
      ],
    }

    useChatStore.setState({
      conversationId: 164,
      messages: [assistantMessage],
      conversationSessions: {},
    })

    useChatStore.getState().updateToolCall('assistant-2', 'functions.generate_image:7', {
      status: 'completed',
      result: {
        task_id: 347,
        status: 'completed',
        progress: 100,
        result_url: '/api/v1/uploads/generated/6874683b-e568-4d50-b260-0c53f17ae966.png',
      },
    })

    const state = useChatStore.getState()
    const rootChild = state.messages[0]?.blocks?.[0]?.children?.[0]
    const sessionChild = state.conversationSessions['164']?.messages?.[0]?.blocks?.[0]?.children?.[0]

    expect(rootChild?.status).toBe('completed')
    expect(rootChild?.payload.progress).toBe(100)
    expect(rootChild?.payload.result_url).toBe('/api/v1/uploads/generated/6874683b-e568-4d50-b260-0c53f17ae966.png')

    expect(sessionChild?.status).toBe('completed')
    expect(sessionChild?.payload.progress).toBe(100)
    expect(sessionChild?.payload.result_url).toBe('/api/v1/uploads/generated/6874683b-e568-4d50-b260-0c53f17ae966.png')

    useChatStore.getState().reset()
  })

  it('matches nested generation blocks when task ids differ only by string vs number', () => {
    const assistantMessage: ChatMessage = {
      id: 'assistant-3',
      role: 'assistant',
      content: null,
      createdAt: '2026-05-02T05:07:04.741Z',
      blocks: [
        {
          id: 'subagent-subagent_c841054f508f',
          kind: 'tool',
          order: 0,
          status: 'completed',
          visible: true,
          uiKind: 'subagent_card',
          payload: {
            task_id: 'subagent_c841054f508f',
            label: '卫生巾品牌设计',
            status: 'completed',
          },
          children: [
            {
              id: 'subagent_c841054f508f-functions.generate_image:7',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                tool_name: 'generate_image',
                call_id: 'functions.generate_image:7',
                status: 'processing',
                progress: 0,
                task_id: '347',
                result: {
                  task_id: '347',
                  status: 'processing',
                  progress: 0,
                },
              },
            },
          ],
        },
      ],
    }

    useChatStore.setState({
      conversationId: 164,
      messages: [assistantMessage],
      conversationSessions: {
        '164': conversationSession({
          messages: [assistantMessage],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'idle',
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          generationProjection: createGenerationProjectionState(),
        }),
      },
    })

    useChatStore.getState().updateToolCall('assistant-3', 'functions.generate_image:7', {
      status: 'completed',
      result: {
        task_id: 347,
        status: 'completed',
        progress: 100,
        result_url: '/api/v1/uploads/generated/6874683b-e568-4d50-b260-0c53f17ae966.png',
      },
    })

    const state = useChatStore.getState()
    const rootChild = state.messages[0]?.blocks?.[0]?.children?.[0]

    expect(rootChild?.status).toBe('completed')
    expect(rootChild?.payload.progress).toBe(100)
    expect(rootChild?.payload.result_url).toBe('/api/v1/uploads/generated/6874683b-e568-4d50-b260-0c53f17ae966.png')

    useChatStore.getState().reset()
  })

  it('keeps the active conversation session in sync for nested generation blocks', () => {
    const assistantMessage: ChatMessage = {
      id: 'assistant-1',
      role: 'assistant',
      content: null,
      createdAt: '2026-04-29T01:54:43.000Z',
      blocks: [
        {
          id: 'subagent-subagent_1e0fedfd7f0f',
          kind: 'tool',
          order: 0,
          status: 'completed',
          visible: true,
          uiKind: 'subagent_card',
          payload: {
            task_id: 'subagent_1e0fedfd7f0f',
            label: '卫生巾商品详情图',
            status: 'completed',
          },
          children: [
            {
              id: 'subagent_1e0fedfd7f0f-functions.generate_image:2',
              kind: 'tool',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'generation_task',
              payload: {
                tool_name: 'generate_image',
                call_id: 'functions.generate_image:2',
                status: 'processing',
                progress: 0,
                task_id: 122,
                result: {
                  task_id: 122,
                  status: 'processing',
                  progress: 0,
                },
              },
            },
          ],
        },
      ],
    }

    useChatStore.setState({
      conversationId: 28,
      messages: [assistantMessage],
      conversationSessions: {
        '28': conversationSession({
          messages: [assistantMessage],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'idle',
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          generationProjection: createGenerationProjectionState(),
        }),
      },
    })

    useChatStore.getState().updateToolCall('assistant-1', 'functions.generate_image:2', {
      status: 'completed',
      result: {
        task_id: 122,
        status: 'completed',
        progress: 100,
        result_url: '/api/v1/uploads/generated/f4fe3f91af5c4f998c203b.png',
      },
    })

    const state = useChatStore.getState()
    const rootChild = state.messages[0]?.blocks?.[0]?.children?.[0]
    const sessionChild = state.conversationSessions['28']?.messages?.[0]?.blocks?.[0]?.children?.[0]

    expect(rootChild?.status).toBe('completed')
    expect(rootChild?.payload.progress).toBe(100)
    expect(rootChild?.payload.result_url).toBe('/api/v1/uploads/generated/f4fe3f91af5c4f998c203b.png')

    expect(sessionChild?.status).toBe('completed')
    expect(sessionChild?.payload.progress).toBe(100)
    expect(sessionChild?.payload.result_url).toBe('/api/v1/uploads/generated/f4fe3f91af5c4f998c203b.png')

    useChatStore.getState().reset()
  })

  it('keeps a completed canvas conversation terminal when async media block completion arrives late', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const assistantMessage: ChatMessage = {
      id: 'assistant-media',
      role: 'assistant',
      content: '图片生成',
      createdAt: '2026-05-23T08:44:41.000Z',
      blocks: [
        {
          id: 'media-artifact-1',
          kind: 'content',
          order: 0,
          status: 'processing',
          uiKind: 'media_card',
          visible: true,
          payload: {
            title: '图片生成',
            status: 'processing',
            artifactRef: 'artifact_ref:1',
            resultUrl: null,
          },
        },
      ],
    }

    useChatStore.setState({
      conversationId: 'conv-canvas-late-media',
      messages: [assistantMessage],
      isStreaming: false,
      conversationSessions: {
        'conv-canvas-late-media': conversationSession({
          messages: [assistantMessage],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'completed',
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 19,
          generationProjection: createGenerationProjectionState(),
        }),
      },
    })

    handleAgentEventV2(presentationComplete(
      20,
      'media-artifact-1',
      '',
      {
        run_id: 'generation-task-poller',
        message_key: 'assistant-media',
        ui_kind: 'media_card',
        kind: 'content',
        payload: {
          title: '图片生成',
          status: 'completed',
          artifact_ref: 'artifact_ref:1',
          result_url: 'references/generated/image/original.png',
        },
      },
    ), set, get, 'conv-canvas-late-media')

    const state = useChatStore.getState()
    const session = state.conversationSessions['conv-canvas-late-media']
    expect(session?.runStatus).toBe('completed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.lastSequence).toBe(20)
    expect(session?.messages[0]?.blocks?.[0]).toMatchObject({
      id: 'media-artifact-1',
      status: 'completed',
      payload: expect.objectContaining({
        result_url: 'references/generated/image/original.png',
      }),
    })
    expect(state.isStreaming).toBe(false)

    useChatStore.getState().reset()
  })

  it.each([
    ['image', 'generate_image', 'image_generation', 'image_generator', '/api/v1/uploads/canvas/1/final-image.png'],
    ['video', 'generate_video', 'video_generation', 'video_generator', '/api/v1/uploads/canvas/1/final-video.mp4'],
  ])('continues polling pending %s media cards after turn_completed', async (_kind, toolName, mediaType, canvasType, resultUrl) => {
    vi.useFakeTimers()
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const taskId = `${_kind}-task-1`
    const artifactRef = `artifact_ref:${_kind}-artifact-1`
    const assistantMessage: ChatMessage = {
      id: `assistant-${_kind}-media`,
      role: 'assistant',
      content: null,
      createdAt: '2026-05-23T08:44:41.000Z',
      blocks: [
        {
          id: `media-${_kind}-artifact-1`,
          kind: 'content',
          order: 0,
          status: 'processing',
          uiKind: 'media_card',
          visible: true,
          payload: {
            title: `${_kind} generation`,
            tool_name: toolName,
            media_type: mediaType,
            status: 'processing',
            progress: 0,
            task_id: taskId,
            artifact_ref: artifactRef,
            result_url: null,
            canvas_item: {
              id: `canvas-${_kind}-1`,
              type: canvasType,
              task_id: taskId,
              status: 'generating',
              url: '',
            },
          },
        },
      ],
    }
    const getHarnessGenerationArtifactTaskMock = vi
      .spyOn(agentApi, 'getHarnessGenerationArtifactTask')
      .mockResolvedValue(httpResponse({
        data: artifactTask({
          task_id: taskId,
          artifact_ref: artifactRef,
          status: 'completed',
          progress: 100,
          result_url: resultUrl,
          canvas_item: {
            id: `canvas-${_kind}-1`,
            type: canvasType,
            task_id: taskId,
            status: 'completed',
            url: resultUrl,
          },
        }),
      }))

    useChatStore.setState({
      conversationId: 'conv-canvas-terminal-media-poll',
      messages: [assistantMessage],
      isStreaming: true,
      conversationSessions: {
        'conv-canvas-terminal-media-poll': conversationSession({
          messages: [assistantMessage],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'running',
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 18,
          generationProjection: createGenerationProjectionState(),
        }),
      },
    })

    handleAgentEventV2(turnCompleted('completed', {
      conversation_id: 'conv-canvas-terminal-media-poll',
      run_id: 'run-terminal-media-poll',
      sequence: 19,
    }), set, get, 'conv-canvas-terminal-media-poll')

    await vi.advanceTimersByTimeAsync(0)

    const session = useChatStore.getState().conversationSessions['conv-canvas-terminal-media-poll']
    const block = session?.messages[0]?.blocks?.[0]
    expect(getHarnessGenerationArtifactTaskMock).toHaveBeenCalledWith('conv-canvas-terminal-media-poll', artifactRef)
    expect(session?.runStatus).toBe('completed')
    expect(session?.isStreaming).toBe(false)
    expect(block?.status).toBe('completed')
    expect(block?.payload.status).toBe('completed')
    expect(block?.payload.progress).toBe(100)
    expect(block?.payload.result_url).toBe(resultUrl)
    expect(block?.payload.canvas_item).toMatchObject({
      status: 'completed',
      url: resultUrl,
    })

    getHarnessGenerationArtifactTaskMock.mockRestore()
    resetCanvasGenerationTaskRuntimeForTests()
    vi.useRealTimers()
    useChatStore.getState().reset()
  })

  it('recovers polling from live presentation media cards without requiring an item_started event', async () => {
    vi.useFakeTimers()
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const getHarnessGenerationArtifactTaskMock = vi
      .spyOn(agentApi, 'getHarnessGenerationArtifactTask')
      .mockResolvedValue(httpResponse({
        data: artifactTask({
          task_id: 'presentation-task-1',
          artifact_ref: 'artifact_ref:presentation-media-1',
          status: 'completed',
          progress: 100,
          result_url: '/api/v1/uploads/canvas/1/presentation-final.png',
          canvas_item: {
            id: 'canvas-presentation-1',
            type: 'image_generator',
            task_id: 'presentation-task-1',
            status: 'completed',
            url: '/api/v1/uploads/canvas/1/presentation-final.png',
          },
        }),
      }))

    useChatStore.setState({
      conversationId: 'conv-canvas-presentation-media-poll',
      messages: [],
      isStreaming: true,
      conversationSessions: {
        'conv-canvas-presentation-media-poll': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'running',
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 7,
          generationProjection: createGenerationProjectionState(),
        }),
      },
    })

    handleAgentEventV2(presentationComplete(
      8,
      'media-presentation-1',
      '',
      {
        run_id: 'run-presentation-media-poll',
        message_key: 'assistant-presentation-media',
        ui_kind: 'media_card',
        kind: 'content',
        status: 'processing',
        payload: {
          title: '图片生成',
          tool_name: 'generate_image',
          media_type: 'image_generation',
          status: 'processing',
          progress: 0,
          task_id: 'presentation-task-1',
          artifact_ref: 'artifact_ref:presentation-media-1',
          result_url: null,
          canvas_item: {
            id: 'canvas-presentation-1',
            type: 'image_generator',
            task_id: 'presentation-task-1',
            status: 'generating',
            url: '',
          },
        },
      },
    ), set, get, 'conv-canvas-presentation-media-poll')

    await vi.advanceTimersByTimeAsync(0)

    const session = useChatStore.getState().conversationSessions['conv-canvas-presentation-media-poll']
    const block = session?.messages[0]?.blocks?.[0]
    expect(getHarnessGenerationArtifactTaskMock).toHaveBeenCalledWith('conv-canvas-presentation-media-poll', 'artifact_ref:presentation-media-1')
    expect(block?.status).toBe('completed')
    expect(block?.payload.result_url).toBe('/api/v1/uploads/canvas/1/presentation-final.png')
    expect(block?.payload.canvas_item).toMatchObject({
      status: 'completed',
      url: '/api/v1/uploads/canvas/1/presentation-final.png',
    })

    getHarnessGenerationArtifactTaskMock.mockRestore()
    resetCanvasGenerationTaskRuntimeForTests()
    vi.useRealTimers()
    useChatStore.getState().reset()
  })

  it('does not dispatch late canvas updates from an inactive conversation', () => {
    const { handleAgentEventV2 } = __chatStoreTestUtils
    const set = useChatStore.setState
    const get = useChatStore.getState
    const onCanvasUpdate = vi.fn()
    useChatStore.setState((state) => ({
      ...state,
      conversationId: 184,
      projectId: 8,
      onCanvasUpdate,
      conversationSessions: {
        ...state.conversationSessions,
        '183': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'running',
          isStreaming: true,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 24,
        }),
        '184': conversationSession({
          messages: [],
          activePlan: null,
          pendingInteraction: null,
          runStatus: 'idle',
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
        }),
      },
    }))

    handleAgentEventV2({
      type: 'canvas_update',
      sequence: 25,
      data: {
        action: 'add_generated_media',
        item: {
          id: 'project-7-media',
          type: 'image',
          url: '/api/v1/uploads/generated/project-7-media.png',
          status: 'completed',
          task_id: 347,
        },
        message_id: 'assistant-message-project-7',
      },
    }, set, get, 183)

    expect(onCanvasUpdate).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversationSessions['183']?.lastSequence).toBe(25)
    useChatStore.getState().reset()
  })
})
