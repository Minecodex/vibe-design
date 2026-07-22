import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const createConversationMock = vi.fn()
const createHarnessConversationApiMock = vi.fn()
const streamRespondToAgentMock = vi.fn()
const streamHarnessRespondToAgentMock = vi.fn()
const streamHarnessSendMessageMock = vi.fn()

vi.mock('@/api/endpoints/agent', async () => {
  return {
    agentApi: {
      getHarnessConversation: vi.fn(),
      listWorkspaceFiles: vi.fn(),
      listHarnessConversations: vi.fn(),
      listConversations: vi.fn(),
      getConversation: vi.fn(),
      deleteHarnessConversation: vi.fn(),
      deleteConversation: vi.fn(),
      createConversation: createConversationMock,
      createHarnessConversation: createHarnessConversationApiMock,
    },
    streamSendMessage: vi.fn(),
    streamApprovePlan: vi.fn(),
    streamRespondToAgent: streamRespondToAgentMock,
    streamHarnessRespondToAgent: streamHarnessRespondToAgentMock,
    streamHarnessSendMessage: streamHarnessSendMessageMock,
    streamHarnessConversationEvents: vi.fn(),
  }
})

vi.mock('@/i18n', () => ({
  default: {
    language: 'zh-CN',
  },
}))

vi.mock('./homeHarnessProjection', () => ({
  finalizeHomeHarnessProjection: vi.fn(() => null),
}))

function presentationComplete(
  sequence: number,
  blockKey: string,
  text: string,
  options: Record<string, any> = {},
): any {
  const runId = String(options.run_id || 'run-canvas')
  const messageKey = String(options.message_key || `message:${runId}`)
  const uiKind = String(options.ui_kind || 'text')
  const payload = { text, ...(options.payload || {}) }
  return {
    type: 'presentation.block.complete',
    sequence,
    run_id: runId,
    lane: 'user',
    data: {
      protocol_version: 2,
      type: 'presentation.block.complete',
      op_id: `test:${sequence}:${blockKey}:complete`,
      source_sequence: sequence,
      message_key: messageKey,
      block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      block: {
        id: blockKey,
        block_key: blockKey,
        kind: options.kind || (uiKind === 'text' || uiKind === 'assistant_text' ? 'text' : 'content'),
        order: options.order || 0,
        status: options.status || 'completed',
        visible: true,
        ui_kind: uiKind,
        uiKind,
        render_key: options.render_key,
        renderKey: options.render_key,
        payload,
        revision: sequence,
        source_sequence: sequence,
      },
      payload,
    },
  }
}

describe('canvasAgentStore respondToAgent', () => {
  beforeEach(() => {
    createConversationMock.mockReset()
    createHarnessConversationApiMock.mockReset()
    streamRespondToAgentMock.mockReset()
    streamHarnessRespondToAgentMock.mockReset()
    streamHarnessSendMessageMock.mockReset()
    streamRespondToAgentMock.mockImplementation(async function* () {})
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {})
    streamHarnessSendMessageMock.mockImplementation(async function* () {})
  })

  afterEach(async () => {
    const { useChatStore } = await import('./canvasAgentStore')
    useChatStore.getState().reset()
  })

  it('creates canvas conversations through harness with runtime_profile canvas', async () => {
    createHarnessConversationApiMock.mockResolvedValue({
      data: {
        id: 'conv-canvas-1',
        title: '新会话',
        skill_id: 'logo',
        runtime_profile: 'canvas',
        project_id: 88,
        phase: 'executing',
        mode: 'fast',
        web_search_enabled: false,
        status: 'active',
        runtime_status: 'idle',
        engine_version: 'harness',
        run_id: null,
        started_at: null,
        finished_at: null,
        created_at: '2026-05-07T00:00:00.000Z',
        updated_at: '2026-05-07T00:00:00.000Z',
      },
    })

    const { useChatStore } = await import('./canvasAgentStore')
    useChatStore.setState({
      projectId: 88,
      mode: 'fast',
      activeSkillId: 'logo',
      modelPreferences: { auto: false },
      webSearchEnabled: false,
    } as any)

    await useChatStore.getState().createConversation(88, 'logo')

    expect(createHarnessConversationApiMock).toHaveBeenCalledWith({
      mode: 'fast',
      runtime_profile: 'canvas',
      project_id: 88,
      skill_id: 'logo',
      skill_selection_mode: 'manual',
      web_search_enabled: false,
      model_preferences: { auto: false },
    })
    expect(createConversationMock).not.toHaveBeenCalled()
  })

  it('stores the backend default canvas skill when no explicit skill is selected', async () => {
    createHarnessConversationApiMock.mockResolvedValue({
      data: {
        id: 'conv-canvas-default',
        title: '新会话',
        skill_id: 'design_workflow',
        runtime_profile: 'canvas',
        project_id: 88,
        phase: 'executing',
        mode: 'fast',
        web_search_enabled: false,
        status: 'active',
        runtime_status: 'idle',
        engine_version: 'harness',
        run_id: null,
        started_at: null,
        finished_at: null,
        created_at: '2026-05-07T00:00:00.000Z',
        updated_at: '2026-05-07T00:00:00.000Z',
      },
    })

    const { useChatStore } = await import('./canvasAgentStore')
    useChatStore.setState({
      projectId: 88,
      mode: 'fast',
      activeSkillId: null,
      modelPreferences: { auto: false },
      webSearchEnabled: false,
    } as any)

    await useChatStore.getState().createConversation(88)

    expect(createHarnessConversationApiMock).toHaveBeenCalledWith({
      mode: 'fast',
      runtime_profile: 'canvas',
      project_id: 88,
      skill_id: null,
      web_search_enabled: false,
      model_preferences: { auto: false },
    })
    expect(useChatStore.getState().activeSkillId).toBe('design_workflow')
  })

  it('keeps the backend default canvas skill on the first send after auto-creating a conversation', async () => {
    createHarnessConversationApiMock.mockResolvedValue({
      data: {
        id: 'conv-canvas-default',
        title: '新会话',
        skill_id: 'design_workflow',
        runtime_profile: 'canvas',
        project_id: 88,
        phase: 'executing',
        mode: 'fast',
        web_search_enabled: false,
        status: 'active',
        runtime_status: 'idle',
        engine_version: 'harness',
        run_id: null,
        started_at: null,
        finished_at: null,
        created_at: '2026-05-07T00:00:00.000Z',
        updated_at: '2026-05-07T00:00:00.000Z',
      },
    })

    const { useChatStore } = await import('./canvasAgentStore')
    useChatStore.setState({
      conversationId: null,
      projectId: 88,
      mode: 'fast',
      activeSkillId: null,
      modelPreferences: { auto: false },
      webSearchEnabled: false,
      messages: [],
    } as any)

    await useChatStore.getState().sendMessage('帮我创建一个猴子的图片')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-canvas-default',
      expect.objectContaining({
        content: '帮我创建一个猴子的图片',
        skill_id: 'design_workflow',
      }),
      expect.any(AbortSignal),
      0,
    )
  })

  it('responds through harness while keeping the raw answer value and displayed label', async () => {
    const { useChatStore } = await import('./canvasAgentStore')

    useChatStore.setState({
      conversationId: 'conv-canvas-42',
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-07T00:00:00.000Z',
          blocks: [
            {
              id: 'interaction-1',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'choice_prompt',
              payload: {
                requestId: 'req-1',
                question: '选择视觉方向',
                options: [
                  { label: '整体空间氛围图', value: 'main_atmosphere' },
                  { label: '入口迎宾区', value: 'entry_area' },
                ],
              },
            },
          ],
        },
      ],
    })

    await useChatStore.getState().respondToAgent(
      'req-1',
      'main_atmosphere',
      '整体空间氛围图',
    )

    expect(streamRespondToAgentMock).not.toHaveBeenCalled()
    expect(streamHarnessRespondToAgentMock).toHaveBeenCalledWith(
      'conv-canvas-42',
      {
        request_id: 'req-1',
        answer: 'main_atmosphere',
        answers: undefined,
        display_label: '整体空间氛围图',
      },
      expect.any(AbortSignal),
      0,
    )

    const state = useChatStore.getState()
    expect(state.messages.some((message) => (
      message.role === 'user' && message.content === '整体空间氛围图'
    ))).toBe(true)
  })

  it('reconciles the optimistic ask_user reply with the server interaction submission message', async () => {
    const { useChatStore } = await import('./canvasAgentStore')
    const displayLabel = '新品牌创建 / 精品咖啡馆 / 线下门店 / 热带鲜活'

    streamHarnessRespondToAgentMock.mockImplementation(async function* () {
      yield {
        type: 'presentation.message.upsert',
        sequence: 2,
        run_id: 'run-canvas',
        lane: 'user',
        data: {
          protocol_version: 2,
          type: 'presentation.message.upsert',
          op_id: 'server:user-message:req-dup',
          source_sequence: 2,
          message_key: 'interaction-submission:conv-canvas-dup:req-dup:abc123',
          block_key: 'message:interaction-submission:conv-canvas-dup:req-dup:abc123',
          role: 'user',
          status: 'completed',
          content: displayLabel,
          payload: {
            content: displayLabel,
            blocks: [],
            attachments: [],
            metadata: {
              request_id: 'req-dup',
              kind: 'ask_user',
              display_label: displayLabel,
              source: 'interaction_submitted',
            },
          },
        },
      }
    })

    useChatStore.setState({
      conversationId: 'conv-canvas-dup',
      messages: [
        {
          id: 'interaction:req-dup',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-07T00:00:00.000Z',
          blocks: [
            {
              id: 'interaction-form:req-dup',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'req-dup',
                request_id: 'req-dup',
                question: '选择方向',
                kind: 'ask_user',
                status: 'pending',
              },
            },
          ],
        },
      ],
      pendingInteraction: {
        request_id: 'req-dup',
        question: '选择方向',
        kind: 'ask_user',
        status: 'pending',
      },
    } as any)

    await useChatStore.getState().respondToAgent('req-dup', 'new_brand', displayLabel)

    const state = useChatStore.getState()
    const matchingUserMessages = state.messages.filter((message) => (
      message.role === 'user' && message.content === displayLabel
    ))

    expect(matchingUserMessages).toHaveLength(1)
    expect(matchingUserMessages[0]?.id).toBe('interaction-submission:conv-canvas-dup:req-dup:abc123')
  })

  it('uses presentation message keys as stable ids when replaying canvas snapshots', async () => {
    const { buildHarnessUiMessages } = await import('./canvasHarnessProjection')

    const messages = buildHarnessUiMessages([
      {
        id: 'stored-hash-id',
        role: 'user',
        content: '确认继续',
        created_at: '2026-05-07T00:00:00.000Z',
        metadata: {
          render_kind: 'presentation_v2',
          message_key: 'interaction-submission:conv:req:stable',
          request_id: 'req',
          display_label: '确认继续',
        },
      } as any,
    ])

    expect(messages[0]?.id).toBe('interaction-submission:conv:req:stable')
  })

  it('writes submitted interaction_form answers back into the existing card before stream events arrive', async () => {
    const { useChatStore } = await import('./canvasAgentStore')

    useChatStore.setState({
      conversationId: 'conv-canvas-99',
      messages: [
        {
          id: 'assistant-interaction-form-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-07T00:00:00.000Z',
          blocks: [
            {
              id: 'interaction-form-1',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'req-form-1',
                request_id: 'req-form-1',
                question: 'Need a few choices',
                kind: 'ask_user',
                status: 'pending',
                schema: {
                  title: 'Quick brief',
                  fields: [
                    {
                      id: 'direction',
                      label: 'Direction',
                      type: 'radio',
                      options: [
                        { label: 'Option A', value: 'a' },
                        { label: 'Option B', value: 'b' },
                      ],
                    },
                    {
                      id: 'tone',
                      label: 'Tone',
                      type: 'textarea',
                    },
                  ],
                },
              },
            },
          ],
        },
      ],
    } as any)

    const submittedAnswers = {
      direction: {
        type: 'option',
        value: 'a',
        label: 'Option A',
      },
      tone: 'Warm and editorial',
    }

    await useChatStore.getState().respondToAgent(
      'req-form-1',
      JSON.stringify(submittedAnswers),
      'Option A / Warm and editorial',
      submittedAnswers,
    )

    const state = useChatStore.getState()
    const interactionBlock = state.messages[0]?.blocks?.[0]

    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.answers).toEqual(submittedAnswers)
    expect(state.messages.some((message) => (
      message.role === 'user' && message.content === 'Option A / Warm and editorial'
    ))).toBe(true)
    expect(streamHarnessRespondToAgentMock).toHaveBeenCalledWith(
      'conv-canvas-99',
      {
        request_id: 'req-form-1',
        answer: JSON.stringify(submittedAnswers),
        answers: submittedAnswers,
        display_label: 'Option A / Warm and editorial',
      },
      expect.any(AbortSignal),
      0,
    )
  })

  it('keeps submitted interaction_form answers when the resume stream replays the same pending card', async () => {
    const { useChatStore } = await import('./canvasAgentStore')

    const schema = {
      title: '鹦鹉咖啡｜品牌基础信息',
      fields: [
        {
          id: 'brand_stage',
          label: '当前是新建品牌（0-1）还是品牌升级（1-10）？',
          type: 'radio',
          options: [
            { label: '0-1 新建品牌', value: '0-1 新建品牌' },
            { label: '1-10 品牌升级', value: '1-10 品牌升级' },
          ],
        },
        {
          id: 'product_and_value',
          label: '核心产品/服务是什么？',
          type: 'textarea',
        },
      ],
    }
    const submittedAnswers = {
      brand_stage: {
        type: 'option',
        value: '0-1 新建品牌',
        label: '0-1 新建品牌',
      },
      product_and_value: '手冲',
    }
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {
      yield {
        type: 'user_interaction_requested',
        sequence: 2,
        lane: 'user',
        data: {
          request_id: 'call_canvas_ask_user',
          tool_call_id: 'call_canvas_ask_user',
          question: '为推进「鹦鹉咖啡」品牌策划，我先补齐 2 个关键信息。',
          kind: 'ask_user',
          schema,
          answers: null,
          status: 'pending',
        },
      }
      yield presentationComplete(
        3,
        'interaction-form:call_canvas_ask_user',
        '为推进「鹦鹉咖啡」品牌策划，我先补齐 2 个关键信息。',
        {
          message_key: 'assistant-interaction-form-canvas',
          ui_kind: 'interaction_form',
          kind: 'interaction',
          render_key: 'interaction:call_canvas_ask_user',
          payload: {
            request_id: 'call_canvas_ask_user',
            requestId: 'call_canvas_ask_user',
            question: '为推进「鹦鹉咖啡」品牌策划，我先补齐 2 个关键信息。',
            kind: 'ask_user',
            schema,
            answers: null,
            status: 'pending',
          },
        },
      )
    })

    useChatStore.setState({
      conversationId: 'conv-canvas-ask-user',
      messages: [
        {
          id: 'assistant-interaction-form-canvas',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-19T00:00:00.000Z',
          blocks: [
            {
              id: 'interaction-form:call_canvas_ask_user',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              renderKey: 'interaction:call_canvas_ask_user',
              payload: {
                requestId: 'call_canvas_ask_user',
                request_id: 'call_canvas_ask_user',
                question: '为推进「鹦鹉咖啡」品牌策划，我先补齐 2 个关键信息。',
                kind: 'ask_user',
                schema,
                answers: null,
                status: 'pending',
              },
            },
          ],
        },
      ],
      pendingInteraction: {
        request_id: 'call_canvas_ask_user',
        question: '为推进「鹦鹉咖啡」品牌策划，我先补齐 2 个关键信息。',
        kind: 'ask_user',
        schema,
        answers: null,
        status: 'pending',
      },
    } as any)

    await useChatStore.getState().respondToAgent(
      'call_canvas_ask_user',
      JSON.stringify(submittedAnswers),
      '0-1 新建品牌 / 手冲',
      submittedAnswers,
    )

    const state = useChatStore.getState()
    const interactionBlock = state.messages
      .flatMap((message) => message.blocks || [])
      .find((block) => block.uiKind === 'interaction_form')

    expect(state.pendingInteraction).toBeNull()
    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.answers).toEqual(submittedAnswers)
    expect(interactionBlock?.payload.submittedLabel).toBe('0-1 新建品牌 / 手冲')
  })

  it('updates an existing processing media card in place when the same artifact completes after ask_user submission', async () => {
    const { useChatStore } = await import('./canvasAgentStore')

    let releaseStream: () => void = () => {}
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {
      yield presentationComplete(
        1,
        'media-artifact-art-1',
        '',
        {
          message_key: 'assistant-media-1',
          ui_kind: 'media_card',
          kind: 'content',
          render_key: 'media:artifact:artifact_ref:art-1',
          payload: {
            tool_name: 'generate_image',
            call_id: 'task-1',
            media_type: 'image_generation',
            title: '图片生成',
            status: 'completed',
            artifact_ref: 'artifact_ref:art-1',
            task_id: 'task-1',
            result_url: '/api/v1/uploads/canvas/67/logo-finished.png',
            canvas_item: {
              id: 'canvas-item-1',
              type: 'image_generator',
              task_id: 'task-1',
              status: 'completed',
              url: '/api/v1/uploads/canvas/67/logo-finished.png',
            },
          },
        },
      )
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
    })

    useChatStore.setState({
      conversationId: 'conv-canvas-media-update',
      pendingInteraction: {
        request_id: 'req-media-1',
        question: '继续下一步？',
        kind: 'ask_user',
        schema: null,
      },
      messages: [
        {
          id: 'assistant-media-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-07T00:00:00.000Z',
          blocks: [
            {
              id: 'media-artifact-art-1',
              kind: 'content',
              order: 0,
              status: 'processing',
              visible: true,
              uiKind: 'media_card',
              renderKey: 'media:artifact:artifact_ref:art-1',
              payload: {
                tool_name: 'generate_image',
                call_id: 'call-generate-1',
                media_type: 'image_generation',
                title: '图片生成',
                status: 'processing',
                artifact_ref: 'artifact_ref:art-1',
                task_id: 'task-1',
                result_url: null,
                canvas_item: {
                  id: 'canvas-item-1',
                  type: 'image_generator',
                  task_id: 'task-1',
                  status: 'generating',
                  url: '',
                },
              },
            },
            {
              id: 'interaction-form:req-media-1',
              kind: 'interaction',
              order: 1,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'req-media-1',
                request_id: 'req-media-1',
                question: '继续下一步？',
                kind: 'ask_user',
                status: 'pending',
              },
            },
          ],
        },
      ],
      streamingBlocks: [],
      currentToolCalls: [],
      isStreaming: false,
    } as any)

    const respondPromise = useChatStore.getState().respondToAgent(
      'req-media-1',
      'confirm',
      '确认继续',
    )

    await new Promise((resolve) => setTimeout(resolve, 0))

    const stateDuringStream = useChatStore.getState()
    const mediaBlock = stateDuringStream.messages[0]?.blocks?.find((block: any) => block.id === 'media-artifact-art-1')

    expect(stateDuringStream.streamingBlocks).toEqual([])
    expect(mediaBlock?.payload.status).toBe('completed')
    expect(mediaBlock?.payload.result_url).toBe('/api/v1/uploads/canvas/67/logo-finished.png')

    releaseStream()
    await respondPromise
  })
})
