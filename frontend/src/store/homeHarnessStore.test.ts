import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  applyHomeHarnessEvent,
  createHomeHarnessProjectionState,
} from './homeHarnessProjection'
import { replayHomeHarnessEvents } from './__tests__/harnessProjectionReplay'
import { buildSnapshotProjectionFromDetail, createEmptyConversationSession } from './homeHarnessStoreSession'

function turnCompleted(
  status: 'completed' | 'failed' | 'blocked' | 'cancelled' | 'waiting_input',
  data: Record<string, any> = {},
): any {
  const conversationId = String(data.conversation_id || 'conv-1')
  const runId = String(data.run_id || 'run-1')
  const summary = String(data.summary || data.message || data.terminal_error || '')
  return {
    type: 'turn_completed',
    sequence: data.sequence,
    run_id: runId,
    lane: 'user',
    data: {
      conversation_id: conversationId,
      run_id: runId,
      turn_id: runId,
      status,
      error: status === 'failed' || status === 'blocked'
        ? {
          error_type: data.error_type || 'Failed',
          summary,
          user_visible: data.user_visible !== false,
          failure_signature: data.failure_signature ?? null,
        }
        : null,
      runtime_snapshot: {
        runtime_status: status,
        run_state: status,
        turn_status: status,
        ...(data.runtime_snapshot || {}),
      },
      completed_at: '2026-05-01T00:00:00.000Z',
      duration_ms: null,
    },
  }
}

function presentationDelta(
  sequence: number,
  blockKey: string,
  delta: string,
  options: Record<string, any> = {},
): any {
  const runId = String(options.run_id || 'run-home')
  const messageKey = String(options.message_key || `message:${runId}`)
  return {
    type: 'presentation.block.delta',
    sequence,
    run_id: runId,
    lane: 'user',
    data: {
      protocol_version: 2,
      type: 'presentation.block.delta',
      op_id: `test:${sequence}:${blockKey}:delta`,
      source_sequence: sequence,
      message_key: messageKey,
      block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      payload: { field: options.field || 'text', delta },
    },
  }
}

function presentationComplete(
  sequence: number,
  blockKey: string,
  text: string,
  options: Record<string, any> = {},
): any {
  const runId = String(options.run_id || 'run-home')
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
        kind: options.kind || (uiKind === 'text' ? 'text' : 'content'),
        order: options.order || 0,
        status: options.status || 'completed',
        visible: true,
        ui_kind: uiKind,
        uiKind,
        task_id: options.task_id,
        taskId: options.taskId ?? options.task_id,
        label: options.label,
        summary: options.summary,
        payload,
        children: options.children || [],
        revision: sequence,
        source_sequence: sequence,
      },
      payload,
    },
  }
}

function presentationPatch(
  sequence: number,
  blockKey: string,
  patch: Record<string, any>,
  options: Record<string, any> = {},
): any {
  const runId = String(options.run_id || 'run-home')
  const messageKey = String(options.message_key || `message:${runId}`)
  const status = String(options.status || patch.status || 'running')
  return {
    type: 'presentation.block.patch',
    sequence,
    run_id: runId,
    lane: 'user',
    data: {
      protocol_version: 2,
      type: 'presentation.block.patch',
      op_id: `test:${sequence}:${blockKey}:patch`,
      source_sequence: sequence,
      message_key: messageKey,
      block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      status,
      payload: patch,
    },
  }
}

const {
  createHarnessConversationApiMock,
  getConversationMock,
  getHarnessConversationMock,
  getUiConfigMock,
  listConversationsMock,
  listHarnessConversationsMock,
  listWorkspaceFilesMock,
  cancelHarnessConversationRunMock,
  resolveHarnessSelectionMock,
  streamSendMessageMock,
  streamRespondToAgentMock,
  streamHarnessSendMessageMock,
  streamHarnessRespondToAgentMock,
  streamHarnessStartExecutionMock,
  streamHarnessRevisePlanMock,
  streamHarnessConversationEventsMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  createHarnessConversationApiMock: vi.fn(),
  getConversationMock: vi.fn(),
  getHarnessConversationMock: vi.fn(),
  getUiConfigMock: vi.fn(),
  listConversationsMock: vi.fn(),
  listHarnessConversationsMock: vi.fn(),
  listWorkspaceFilesMock: vi.fn(),
  cancelHarnessConversationRunMock: vi.fn(),
  resolveHarnessSelectionMock: vi.fn(),
  streamSendMessageMock: vi.fn(),
  streamRespondToAgentMock: vi.fn(),
  streamHarnessSendMessageMock: vi.fn(),
  streamHarnessRespondToAgentMock: vi.fn(),
  streamHarnessStartExecutionMock: vi.fn(),
  streamHarnessRevisePlanMock: vi.fn(),
  streamHarnessConversationEventsMock: vi.fn(),
  toastErrorMock: vi.fn(),
}))

vi.mock('@/i18n', () => ({
  default: {
    t: (
      key: string,
      options?: string | { defaultValue?: string; [key: string]: unknown },
    ) => {
      if (typeof options === 'string') {
        return options
      }
      if (options?.defaultValue) {
        return Object.entries(options).reduce((text, [placeholder, value]) => (
          placeholder === 'defaultValue'
            ? text
            : text.split(`{{${placeholder}}}`).join(String(value ?? ''))
        ), options.defaultValue)
      }
      return key
    },
  },
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    createConversation: vi.fn(),
    listConversations: listConversationsMock,
    getConversation: getConversationMock,
    deleteConversation: vi.fn(),
    getUiConfig: getUiConfigMock,
    createHarnessConversation: createHarnessConversationApiMock,
    listHarnessConversations: listHarnessConversationsMock,
    getHarnessConversation: getHarnessConversationMock,
    resolveHarnessSelection: resolveHarnessSelectionMock,
    deleteHarnessConversation: vi.fn(),
    cancelHarnessConversationRun: cancelHarnessConversationRunMock,
    listHarnessSkills: vi.fn(),
    listWorkspaceFiles: listWorkspaceFilesMock,
    rejectPlan: vi.fn(),
  },
  streamSendMessage: streamSendMessageMock,
  streamRespondToAgent: streamRespondToAgentMock,
  streamHarnessSendMessage: streamHarnessSendMessageMock,
  streamHarnessRespondToAgent: streamHarnessRespondToAgentMock,
  streamHarnessStartExecution: streamHarnessStartExecutionMock,
  streamHarnessRevisePlan: streamHarnessRevisePlanMock,
  streamHarnessConversationEvents: streamHarnessConversationEventsMock,
}))

vi.mock('sonner', () => ({
  toast: {
    error: toastErrorMock,
  },
}))

import { __chatStoreTestUtils, useChatStore } from './homeHarnessStore'

function buildProjectionReplayEvents() {
  return [
    {
      type: 'message_appended',
      sequence: 1,
      data: {
        message: {
          id: 'assistant-main',
          role: 'assistant',
          content: 'Main assistant summary',
          created_at: '2026-04-20T00:00:01.000Z',
          metadata: {
            protocol_version: 2,
            message_key: 'message:run-home-replay',
          },
          blocks: [
            {
              id: 'assistant-main-text',
              kind: 'text',
              order: 0,
              status: 'completed',
              visible: true,
              ui_kind: 'text',
              payload: {
                text: 'Main assistant summary',
              },
            },
            {
              id: 'subagent-task-research',
              kind: 'tool',
              order: 1,
              status: 'completed',
              visible: true,
              ui_kind: 'subagent_card',
              task_id: 'task-research',
              label: 'Research competitor notes',
              summary: 'Subagent found the supporting facts.',
              payload: {
                task_id: 'task-research',
                taskId: 'task-research',
                label: 'Research competitor notes',
                purpose: 'Research competitor notes',
                status: 'completed',
                usage: {
                  input_tokens: 7,
                  output_tokens: 3,
                },
              },
              children: [
                {
                  id: 'subagent-text',
                  kind: 'text',
                  order: 0,
                  status: 'completed',
                  visible: true,
                  ui_kind: 'text',
                  payload: {
                    text: 'Subagent found the supporting facts.',
                  },
                },
              ],
            },
            {
              id: 'media-call-image-1',
              kind: 'content',
              order: 2,
              status: 'completed',
              visible: true,
              ui_kind: 'media_card',
              payload: {
                media_type: 'image_analysis',
                title: 'Analyze Image',
                text: 'Image analysis says the chart trends upward.',
                status: 'completed',
                task_id: 'call-image-1',
              },
            },
          ],
        },
      },
    },
    {
      type: 'artifact_plan_updated',
      sequence: 2,
      data: {
        artifact_id: 'plan-artifact',
        title: 'Task plan',
        summary: 'Summarize findings before drafting',
        status: 'completed',
        current_step: 'step-2',
        steps: [
          {
            id: 'step-1',
            title: 'Collect evidence',
            status: 'completed',
          },
          {
            id: 'step-2',
            title: 'Draft response',
            status: 'completed',
          },
        ],
        file_path: 'plan.md',
      },
    },
    turnCompleted('completed', { sequence: 3, conversation_id: 'conv-home-replay', run_id: 'run-home-replay' }),
  ] as any[]
}

function buildHarnessConversationDetail(overrides: Record<string, any> = {}, messages: any[] = []) {
  return {
    id: 'conv-home-detail',
    title: 'Harness Detail',
    skill_id: null,
    phase: 'executing',
    mode: 'fast',
    status: 'completed',
    runtime_status: 'idle',
    run_id: null,
    started_at: '2026-04-20T00:00:00.000Z',
    finished_at: '2026-04-20T00:10:00.000Z',
    user_interaction: null,
    created_at: '2026-04-20T00:00:00.000Z',
    updated_at: '2026-04-20T00:10:00.000Z',
    messages,
    ...overrides,
  }
}

describe('homeHarnessStore', () => {
    it('restores critique cards from detail runtime_state snapshots', () => {
    const projection = buildSnapshotProjectionFromDetail(buildHarnessConversationDetail({
      runtime_status: 'completed',
      runtime_state: {
        critique: {
          critique_run_id: 'critique-1',
          status: 'shipped',
          round: 1,
          max_rounds: 3,
          score_threshold: 8,
          score_scale: 10,
          composite: 8.6,
          scores: {
            critic: 8.6,
            brand: 8.9,
            a11y: 8.2,
            copy: 8.7,
          },
          dimensions: [
            { role: 'critic', name: 'visual-quality', score: 8.6, note: 'Strong visual hierarchy.' },
          ],
          findings: [],
          warnings: [],
          selected_round: 1,
          selected_score: 8.6,
          publish_fallback: false,
          reason: null,
        },
      },
    }) as any)

    expect(projection.critique?.critiqueRunId).toBe('critique-1')
    expect(projection.critique?.status).toBe('shipped')
    expect(projection.critique?.scores.critic).toBe(8.6)
    expect(projection.critique?.dimensions[0]?.name).toBe('visual-quality')
  })

    it('restores submitted interaction answers from persisted user message metadata in detail snapshots', () => {
    const projection = buildSnapshotProjectionFromDetail(buildHarnessConversationDetail({
      runtime_status: 'completed',
      runtime_state: {
        user_interaction: null,
      },
    }, [
      {
        id: 'assistant-interaction-1',
        role: 'assistant',
        content: null,
        created_at: '2026-05-12T10:08:58.000Z',
        blocks: [
          {
            id: 'interaction-form:functions.ask_user:11',
            kind: 'interaction',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'interaction_form',
            render_key: 'interaction:functions.ask_user:11',
            payload: {
              request_id: 'functions.ask_user:11',
              requestId: 'functions.ask_user:11',
              tool_call_id: 'functions.ask_user:11',
              toolCallId: 'functions.ask_user:11',
              question: 'Gate A: confirm strategy?',
              kind: 'ask_user',
              schema: {
                title: 'Gate A',
                fields: [
                  {
                    id: 'strategy_confirmation',
                    label: '确认状态',
                    type: 'radio',
                    options: [
                      { label: '确认，请进入下一步视觉方向设计', value: 'confirm' },
                      { label: '需要调整', value: 'adjust' },
                    ],
                  },
                  {
                    id: 'adjustment_notes',
                    label: '补充意见',
                    type: 'textarea',
                  },
                ],
              },
              answers: null,
              status: 'pending',
            },
          },
        ],
      },
      {
        id: 'user-reply-1',
        role: 'user',
        content: '确认，请进入下一步视觉方向设计',
        created_at: '2026-05-12T10:09:44.000Z',
        metadata: {
          request_id: 'functions.ask_user:11',
          answer: '{"strategy_confirmation":{"type":"option","value":"confirm","label":"确认，请进入下一步视觉方向设计"},"adjustment_notes":""}',
          display_label: '确认，请进入下一步视觉方向设计',
          answers: {
            strategy_confirmation: {
              type: 'option',
              value: 'confirm',
              label: '确认，请进入下一步视觉方向设计',
            },
            adjustment_notes: '',
          },
          source: 'preflight_interaction_submission',
        },
      },
    ]) as any)

    const interactionBlocks = projection.messages.flatMap((message) =>
      message.blocks?.filter((block) => block.uiKind === 'interaction_form') || [],
    )
    const interactionBlock = interactionBlocks[0]

    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.submittedLabel).toBe('确认，请进入下一步视觉方向设计')
    expect(interactionBlock?.payload.submittedAnswer).toBe('{"strategy_confirmation":{"type":"option","value":"confirm","label":"确认，请进入下一步视觉方向设计"},"adjustment_notes":""}')
    expect(interactionBlock?.payload.answers).toEqual({
      strategy_confirmation: {
        type: 'option',
        value: 'confirm',
        label: '确认，请进入下一步视觉方向设计',
      },
      adjustment_notes: '',
    })
  })

    it('restores structured interaction submissions directly from the persisted interaction card snapshot', () => {
    const projection = buildSnapshotProjectionFromDetail(buildHarnessConversationDetail({
      runtime_status: 'completed',
      runtime_state: {
        user_interaction: null,
      },
    }, [
      {
        id: 'assistant-design-system-1',
        role: 'assistant',
        content: null,
        created_at: '2026-05-12T10:08:58.000Z',
        blocks: [
          {
            id: 'interaction-form:design-system:conv-home-detail:abcd1234',
            kind: 'interaction',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'interaction_form',
            render_key: 'interaction:design-system:conv-home-detail:abcd1234',
            payload: {
              request_id: 'design-system:conv-home-detail:abcd1234',
              requestId: 'design-system:conv-home-detail:abcd1234',
              question: '选择设计体系',
              kind: 'design_system_picker',
              answers: {
                design_system_id: 'arc-browser',
              },
              status: 'submitted',
              submitted_label: 'Arc Browser',
              submittedLabel: 'Arc Browser',
              submitted_answer: '{"design_system_id":"arc-browser"}',
              submittedAnswer: '{"design_system_id":"arc-browser"}',
            },
          },
        ],
      },
      {
        id: 'user-design-system-submission',
        role: 'user',
        content: 'Arc Browser',
        created_at: '2026-05-12T10:09:44.000Z',
        metadata: {
          request_id: 'design-system:conv-home-detail:abcd1234',
          kind: 'design_system_picker',
          answer: '{"design_system_id":"arc-browser"}',
          display_label: 'Arc Browser',
          answers: {
            design_system_id: 'arc-browser',
          },
          source: 'preflight_interaction_submission',
        },
      },
    ]) as any)

    const interactionBlock = projection.messages
      .flatMap((message) => message.blocks || [])
      .find((block) => block.uiKind === 'interaction_form')

    expect(projection.messages.filter((message) => message.role === 'user' && message.content === 'Arc Browser')).toHaveLength(1)
    expect(interactionBlock?.payload.kind).toBe('design_system_picker')
    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.submittedLabel).toBe('Arc Browser')
    expect(interactionBlock?.payload.submittedAnswer).toBe('{"design_system_id":"arc-browser"}')
    expect(interactionBlock?.payload.answers).toEqual({
      design_system_id: 'arc-browser',
    })
  })

  beforeEach(() => {
    useChatStore.getState().reset()
    createHarnessConversationApiMock.mockReset()
    getConversationMock.mockReset()
    getHarnessConversationMock.mockReset()
    listConversationsMock.mockReset()
    listHarnessConversationsMock.mockReset()
    getUiConfigMock.mockReset()
    cancelHarnessConversationRunMock.mockReset()
    resolveHarnessSelectionMock.mockReset()
    streamSendMessageMock.mockReset()
    streamRespondToAgentMock.mockReset()
    streamHarnessSendMessageMock.mockReset()
    streamHarnessRespondToAgentMock.mockReset()
    streamHarnessStartExecutionMock.mockReset()
    streamHarnessRevisePlanMock.mockReset()
    streamHarnessConversationEventsMock.mockReset()
    listWorkspaceFilesMock.mockReset()
    toastErrorMock.mockReset()
    streamHarnessConversationEventsMock.mockImplementation(async function* () {})
    listWorkspaceFilesMock.mockResolvedValue({ data: [] })
    resolveHarnessSelectionMock.mockResolvedValue({
      data: {
        skill: {
          id: null,
          confidence: 0,
          reasoning_summary: '',
          should_replace_current: false,
        },
        design_system_recommendations: [],
      },
    })
    createHarnessConversationApiMock.mockResolvedValue({
      data: {
        id: 'conv-created-default',
        title: 'New Conversation',
        skill_id: null,
        mode: 'fast',
        status: 'active',
        runtime_status: 'idle',
        engine_version: 'harness',
        run_id: null,
        started_at: '2026-04-20T00:00:00.000Z',
        finished_at: null,
    user_interaction: null,
        created_at: '2026-04-20T00:00:00.000Z',
        updated_at: '2026-04-20T00:00:00.000Z',
      },
    })
    getConversationMock.mockResolvedValue({ data: {} })
    getHarnessConversationMock.mockResolvedValue({
      data: {
        id: 'conv-home-detail',
        title: 'Harness Detail',
        skill_id: null,
        mode: 'fast',
        status: 'completed',
        runtime_status: 'idle',
        run_id: null,
        started_at: '2026-04-20T00:00:00.000Z',
        finished_at: '2026-04-20T00:10:00.000Z',
    user_interaction: null,
        created_at: '2026-04-20T00:00:00.000Z',
        updated_at: '2026-04-20T00:10:00.000Z',
        messages: [],
      },
    })
    listConversationsMock.mockResolvedValue({ data: [] })
    getUiConfigMock.mockResolvedValue({
      data: {
        hidden_tool_calls: ['debug_tool'],
      },
    })
    listHarnessConversationsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 'conv-home-2',
            title: 'Harness Conversation',
            skill_id: null,
            mode: 'fast',
            status: 'active',
            runtime_status: 'idle',
            engine_version: 'harness',
            run_id: null,
            started_at: '2026-04-20T00:00:00.000Z',
            finished_at: null,
    user_interaction: null,
            created_at: '2026-04-20T00:00:00.000Z',
            updated_at: '2026-04-20T00:00:00.000Z',
          },
        ],
        has_more: false,
      },
    })

    useChatStore.setState({
      conversationId: 'conv-home-1',
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: 'hello',
          createdAt: '2026-04-20T00:00:00.000Z',
        },
      ],
      activePlan: null,
  userInteraction: null,
      isStreaming: true,
      currentStreamText: 'streaming',
      currentToolCalls: [],
      streamingBlocks: [],
      workspaceFiles: [],
      conversations: [],
      conversationsHasMore: false,
      conversationsPage: 1,
      engineVersion: 'harness',
      _abortController: null,
      conversationSessions: {},
    })
  })

  it('enables homepage web search by default', () => {
    expect(useChatStore.getState().webSearchEnabled).toBe(true)
  })

    it('keeps the homepage store in harness mode after starting a new chat', () => {
    useChatStore.getState().newChat()

    expect(useChatStore.getState().engineVersion).toBe('harness')
  })

  afterEach(() => {
    useChatStore.getState().reset()
  })

  it('resets the selected design system to auto mode when starting a new chat', () => {
    useChatStore.setState({
      selectedDesignSystemId: 'warm-editorial',
      conversationId: 'conv-home-existing',
    })

    useChatStore.getState().newChat()

    expect(useChatStore.getState().selectedDesignSystemId).toBeNull()
    expect(useChatStore.getState().conversationId).toBeNull()
  })

    it('clears active conversation runtime and model settings when starting a new chat', () => {
    useChatStore.setState({
      conversationId: 'conv-plan-ready',
      runtimeState: {
        conversation_id: 'conv-plan-ready',
        phase: 'planning_ready',
        run_status: 'waiting_input',
      } as any,
      runStatus: 'waiting_input',
      artifactMode: 'slides',
      mode: 'plan',
      interactionProfile: 'canvas_live_interaction',
      activeSkillId: 'pptx',
      skillSelectionMode: 'manual',
      selectedDesignSystemId: 'application',
      skillDecisionReason: 'previous choice',
      skillDecisionConfidence: 0.9,
      webSearchEnabled: false,
      modelPreferences: {
        image_model: 'old-image',
        image_provider: 'builtin',
        video_model: 'old-video',
        video_provider: 'builtin',
        multimodal_model: 'old-chat',
        multimodal_provider: 'builtin',
        auto: false,
      },
      workspaceFiles: [{ file_id: 'plan.md', name: 'plan.md', path: 'plan.md' }] as any,
    })

    useChatStore.getState().newChat()

    expect(useChatStore.getState()).toEqual(expect.objectContaining({
      conversationId: null,
      runtimeState: null,
      runStatus: 'idle',
      artifactMode: 'web',
      mode: 'fast',
      interactionProfile: 'home_blocking_preflight',
      activeSkillId: null,
      skillSelectionMode: 'auto',
      selectedDesignSystemId: null,
      skillDecisionReason: null,
      skillDecisionConfidence: null,
      webSearchEnabled: true,
      modelPreferences: { auto: false },
      workspaceFiles: [],
    }))
  })

    it('switches immediately to the target conversation state without inheriting the previous settings', async () => {
    let resolveSnapshot: (value: any) => void = () => undefined
    getHarnessConversationMock.mockImplementationOnce(() => new Promise((resolve) => {
      resolveSnapshot = resolve
    }))
    useChatStore.setState({
      conversationId: 'conv-previous',
      messages: [{
        id: 'previous-message',
        role: 'assistant',
        content: 'previous content',
        createdAt: '2026-04-20T00:00:00.000Z',
      }],
      runtimeState: {
        conversation_id: 'conv-previous',
        phase: 'planning_ready',
        run_status: 'waiting_input',
      } as any,
      runStatus: 'waiting_input',
      artifactMode: 'slides',
      activeSkillId: 'pptx',
      skillSelectionMode: 'manual',
      selectedDesignSystemId: 'application',
      webSearchEnabled: false,
      modelPreferences: {
        multimodal_model: 'previous-chat',
        multimodal_provider: 'builtin',
        auto: false,
      },
      conversations: [{
        id: 'conv-target',
        title: 'Target conversation',
        skill_id: null,
        mode: 'fast',
        status: 'active',
        runtime_status: 'idle',
        engine_version: 'harness',
        run_id: null,
        started_at: '2026-04-20T00:00:00.000Z',
        finished_at: null,
        user_interaction: null,
        created_at: '2026-04-20T00:00:00.000Z',
        updated_at: '2026-04-20T00:00:00.000Z',
      }] as any,
    })

    const loadPromise = useChatStore.getState().loadConversation('conv-target')

    expect(useChatStore.getState()).toEqual(expect.objectContaining({
      conversationId: 'conv-target',
      messages: [],
      runtimeState: null,
      runStatus: 'idle',
      artifactMode: 'web',
      activeSkillId: null,
      skillSelectionMode: 'auto',
      selectedDesignSystemId: null,
      webSearchEnabled: true,
      modelPreferences: { auto: false },
    }))

    resolveSnapshot({
      data: buildHarnessConversationDetail({
        id: 'conv-target',
        runtime_status: 'idle',
      }),
    })
    await loadPromise
  })

    it('loads homepage conversations from the harness API even if the engine flag is stale', async () => {
    useChatStore.setState({
      engineVersion: 'v2',
      viewerUserId: 7,
    })

    await useChatStore.getState().loadConversations(123)

    expect(listHarnessConversationsMock).toHaveBeenCalledWith(1, 20)
    expect(listConversationsMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversations[0]?.id).toBe('conv-home-2')
    expect(useChatStore.getState().engineVersion).toBe('harness')
  })

    it('deduplicates concurrent homepage conversation list requests', async () => {
    await Promise.all([
      useChatStore.getState().loadConversations(123),
      useChatStore.getState().loadConversations(123),
    ])

    expect(listHarnessConversationsMock).toHaveBeenCalledTimes(1)
  })

    it('deduplicates concurrent homepage ui config requests', async () => {
    await Promise.all([
      useChatStore.getState().loadUiConfig(),
      useChatStore.getState().loadUiConfig(),
    ])

    expect(getUiConfigMock).toHaveBeenCalledTimes(1)
    expect(useChatStore.getState().uiConfig.hiddenToolCalls).toEqual(['debug_tool'])
  })

    it('creates a harness conversation for the first homepage message even if the engine flag is stale', async () => {
    const createHarnessConversationMock = vi.fn(async () => {
      useChatStore.setState({
        conversationId: 'conv-created',
        engineVersion: 'harness',
      })
    })

    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: null,
      projectId: 123,
      engineVersion: 'v2',
      createHarnessConversation: createHarnessConversationMock as any,
    })

    await useChatStore.getState().sendMessage('hello')

    expect(createHarnessConversationMock).toHaveBeenCalled()
  })

    it('creates a harness conversation before opening the fast-start harness stream', async () => {
    const createHarnessConversationMock = vi.fn(async () => {
      useChatStore.setState({
        conversationId: 'conv-created-before-resolve',
        engineVersion: 'harness',
      })
    })
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: null,
      artifactMode: 'web',
      activeSkillId: null,
      skillSelectionMode: 'auto',
      messages: [],
      createHarnessConversation: createHarnessConversationMock as any,
    })

    await useChatStore.getState().sendMessage('做一个设计公司的落地页')

    expect(createHarnessConversationMock).toHaveBeenCalled()
    expect(resolveHarnessSelectionMock).not.toHaveBeenCalled()
    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-created-before-resolve',
      expect.any(Object),
      expect.any(AbortSignal),
      0,
    )
  })

    it('sends homepage messages through the harness stream even if the engine flag is stale', async () => {
    const createHarnessConversationMock = vi.fn(async () => {
      useChatStore.setState({
        conversationId: 'conv-home-send',
        engineVersion: 'harness',
      })
    })

    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: null,
      engineVersion: 'v2',
      createHarnessConversation: createHarnessConversationMock as any,
    })

    await useChatStore.getState().sendMessage('hello')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-send',
      expect.objectContaining({ content: 'hello' }),
      expect.any(AbortSignal),
      0,
    )
    expect(streamSendMessageMock).not.toHaveBeenCalled()
  })

    it('marks structured homepage UI actions before opening the harness message stream', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-action',
      engineVersion: 'harness',
      modelPreferences: {},
    })

    await useChatStore.getState().sendMessage('Help me regenerate slide 2 in the PPT', undefined, {
      actionType: 'presentation_regenerate_slide',
    })

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-action',
      expect.objectContaining({
        content: 'Help me regenerate slide 2 in the PPT',
        input_kind: 'user_ui_action',
        action_type: 'presentation_regenerate_slide',
      }),
      expect.any(AbortSignal),
      0,
    )
  })

    it('passes the session sequence cursor and ignores replayed durable events during a live send', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield turnCompleted('failed', {
        sequence: 3,
        conversation_id: 'conv-home-cursor',
        run_id: 'run-home-cursor',
        message: '余额不足',
        summary: '余额不足',
      })
      yield presentationComplete(31, 'assistant-new-output', '充值后的新输出', {
        run_id: 'run-home-cursor',
      })
      yield {
        type: 'message_done',
        sequence: 32,
        data: {
          conversation_id: 'conv-home-cursor',
        },
      }
    })

    useChatStore.setState({
      conversationId: 'conv-home-cursor',
      engineVersion: 'harness',
      messages: [],
      conversationSessions: {
        'conv-home-cursor': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 30,
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().sendMessage('继续')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-cursor',
      expect.objectContaining({ content: '继续' }),
      expect.any(AbortSignal),
      30,
    )
    const session = useChatStore.getState().conversationSessions['conv-home-cursor']
    expect(session?.messages.some((message) => String(message.content).includes('余额不足'))).toBe(false)
    expect(session?.messages.some((message) => String(message.content).includes('充值后的新输出'))).toBe(true)
    expect(session?.lastSequence).toBe(32)
  })

    it('lets a terminal detail snapshot stop an active live send before later SSE events', async () => {
    let resolveSnapshot: ((value: any) => void) | null = null
    const snapshotPromise = new Promise((resolve) => {
      resolveSnapshot = resolve
    })
    getHarnessConversationMock.mockImplementationOnce(() => snapshotPromise)
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield presentationComplete(31, 'assistant-final', '', {
        run_id: 'run-home-live-snapshot',
        ui_kind: 'assistant_final_answer',
      })
      resolveSnapshot?.({
        data: buildHarnessConversationDetail({
          id: 'conv-home-live-snapshot',
          runtime_status: 'completed',
          status: 'completed',
          projection: { event_last_sequence: 24 },
        }, []),
      })
      await snapshotPromise
      yield presentationDelta(32, 'assistant-final', '黑格尔正文', {
        run_id: 'run-home-live-snapshot',
      })
      yield {
        type: 'message_done',
        sequence: 33,
        data: { conversation_id: 'conv-home-live-snapshot' },
      }
    })

    useChatStore.setState({
      conversationId: 'conv-home-live-snapshot',
      engineVersion: 'harness',
      messages: [],
      conversationSessions: {
        'conv-home-live-snapshot': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 24,
          runStatus: 'idle',
        },
      },
    })

    const sendPromise = useChatStore.getState().sendMessage('检索下黑格尔的生平')
    await useChatStore.getState().loadConversation('conv-home-live-snapshot')
    await sendPromise

    const session = useChatStore.getState().conversationSessions['conv-home-live-snapshot']
    expect(session?.messages.some((message) => String(message.content).includes('黑格尔正文'))).toBe(false)
    expect(session?.runStatus).toBe('completed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.abortController).toBeNull()
    expect(session?.lastSequence).toBe(31)
  })

    it('continues from the detail snapshot event cursor after a failed run is refreshed', async () => {
    getHarnessConversationMock
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail(
          {
            id: 'conv-home-failed-cursor',
            runtime_status: 'failed',
            status: 'active',
            projection: {
              event_last_sequence: 3,
            },
          },
          [
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
        ),
      })
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail(
          {
            id: 'conv-home-failed-cursor',
            runtime_status: 'completed',
            status: 'completed',
            projection: {
              event_last_sequence: 5,
            },
          },
          [
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
        ),
      })

    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield turnCompleted('failed', {
        sequence: 3,
        conversation_id: 'conv-home-failed-cursor',
        run_id: 'run-home-failed-cursor',
        message: '余额不足',
        summary: '余额不足',
      })
      yield presentationComplete(4, 'assistant-new-output', '充值后的新输出', {
        run_id: 'run-home-failed-cursor',
      })
      yield turnCompleted('failed', {
        sequence: 5,
        conversation_id: 'conv-home-failed-cursor',
        run_id: 'run-home-failed-cursor',
        summary: '余额不足',
        failure_signature: 'sig-home-failed-cursor',
      })
    })

    await useChatStore.getState().loadConversation('conv-home-failed-cursor')
    await useChatStore.getState().sendMessage('第二次')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-failed-cursor',
      expect.objectContaining({ content: '第二次' }),
      expect.any(AbortSignal),
      3,
    )
    const session = useChatStore.getState().conversationSessions['conv-home-failed-cursor']
    expect(session?.messages.filter((message) => String(message.content).includes('余额不足'))).toHaveLength(2)
    expect(session?.messages.some((message) => String(message.content).includes('充值后的新输出'))).toBe(true)
    expect(session?.lastSequence).toBe(5)
  })

    it('sends structured media references for homepage image attachments', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-image-ref',
      engineVersion: 'harness',
      activeSkillId: 'imagegen',
      skillSelectionMode: 'manual',
    })

    await useChatStore.getState().sendMessage('照着这张图生成一张新图', [
      {
        type: 'image',
        url: 'references/inputs/upload_001/source.png',
        name: 'reference.png',
      },
    ])

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-image-ref',
      expect.objectContaining({
        attachments: [
          {
            type: 'image',
            url: 'references/inputs/upload_001/source.png',
            name: 'reference.png',
          },
        ],
        references: [
          {
            id: 'upload:references/inputs/upload_001/source.png',
            kind: 'upload_attachment',
            media_type: 'image',
            display_name: 'reference.png',
            source: {
              type: 'harness_input',
              path: 'references/inputs/upload_001/source.png',
            },
          },
        ],
      }),
      expect.any(AbortSignal),
      0,
    )
  })

    it('strips pending preview-only fields from homepage attachment payloads', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield turnCompleted('completed', { conversation_id: 'conv-home-pending-preview' })
    })

    useChatStore.setState({
      conversationId: 'conv-home-pending-preview',
      engineVersion: 'harness',
      activeSkillId: 'imagegen',
      skillSelectionMode: 'manual',
    })

    await useChatStore.getState().sendMessage('照着这张图生成', [
      {
        type: 'image',
        url: 'references/inputs/upload_001/source.png',
        name: 'reference.png',
        preview_url: 'blob:pending-thumb',
        _previewObjectUrl: 'blob:pending-thumb',
        _clientAttachmentId: 'pending-home-1',
      } as any,
    ])

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-pending-preview',
      expect.objectContaining({
        attachments: [
          {
            type: 'image',
            url: 'references/inputs/upload_001/source.png',
            name: 'reference.png',
          },
        ],
      }),
      expect.any(AbortSignal),
      0,
    )
  })

    it('sends structured media references for homepage library and workspace image attachments', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-asset-ref',
      engineVersion: 'harness',
      activeSkillId: 'imagegen',
      skillSelectionMode: 'manual',
    })

    await useChatStore.getState().sendMessage('用这些图继续生成', [
      {
        type: 'image',
        url: 'https://cdn.example.com/assets/library-image.png',
        name: 'library-image.png',
      },
      {
        type: 'image',
        url: 'references/generated/generated_image_001/original.png',
        name: 'generated.png',
      },
    ])

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-asset-ref',
      expect.objectContaining({
        references: [
          {
            id: 'home-asset:https://cdn.example.com/assets/library-image.png',
            kind: 'home_asset',
            media_type: 'image',
            display_name: 'library-image.png',
            source: {
              type: 'home_asset',
              url: 'https://cdn.example.com/assets/library-image.png',
            },
          },
          {
            id: 'workspace-file:references/generated/generated_image_001/original.png',
            kind: 'workspace_file',
            media_type: 'image',
            display_name: 'generated.png',
            source: {
              type: 'workspace_file',
              path: 'references/generated/generated_image_001/original.png',
            },
          },
        ],
      }),
      expect.any(AbortSignal),
      0,
    )
  })

    it('sends auto-selection context to the harness stream without pre-resolving selections', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-auto',
      artifactMode: 'web',
      activeSkillId: null,
      skillSelectionMode: 'auto',
    })

    await useChatStore.getState().sendMessage('做一个设计公司的落地页')

    expect(resolveHarnessSelectionMock).not.toHaveBeenCalled()
    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-auto',
      expect.objectContaining({
        skill_id: null,
        skill_selection_mode: 'auto',
        design_system_id: null,
      }),
      expect.any(AbortSignal),
      0,
    )
    expect(useChatStore.getState().activeSkillId).toBeNull()
    expect(useChatStore.getState().selectedDesignSystemId).toBeNull()
  })

    it('does not auto-resolve a design system when one is already selected', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-manual-ds',
      artifactMode: 'web',
      activeSkillId: null,
      selectedDesignSystemId: 'apple',
      skillSelectionMode: 'manual',
      isStreaming: false,
      runStatus: 'idle',
      messages: [],
    })

    await useChatStore.getState().sendMessage('做一个品牌官网')

    expect(resolveHarnessSelectionMock).not.toHaveBeenCalled()
    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-manual-ds',
      expect.objectContaining({
        design_system_id: 'apple',
      }),
      expect.any(AbortSignal),
      0,
    )
  })

    it('marks the conversation as running as soon as the harness stream starts', async () => {
    let releaseStream!: () => void
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
    })

    useChatStore.setState({
      conversationId: 'conv-home-pending',
      messages: [],
      artifactMode: 'web',
      activeSkillId: null,
      skillSelectionMode: 'auto',
      isStreaming: false,
      runStatus: 'idle',
    })

    const sendPromise = useChatStore.getState().sendMessage('先帮我看一下这个页面')
    await Promise.resolve()

    expect(useChatStore.getState().isStreaming).toBe(true)
    expect(useChatStore.getState().runStatus).toBe('running')

    releaseStream()
    await sendPromise
  })

    it('keeps a newer homepage send running when an aborted send settles later', async () => {
    let releaseSecondStream!: () => void
    let callCount = 0
    streamHarnessSendMessageMock.mockImplementation((
      _conversationId: string,
      _data: any,
      signal: AbortSignal,
    ) => {
      callCount += 1
      if (callCount === 1) {
        return (async function* () {
          await new Promise<void>((resolve) => {
            signal.addEventListener('abort', () => resolve(), { once: true })
          })
          const abortError = new Error('Aborted')
          abortError.name = 'AbortError'
          throw abortError
        })()
      }

      return (async function* () {
        await new Promise<void>((resolve) => {
          releaseSecondStream = resolve
        })
      })()
    })
    cancelHarnessConversationRunMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-abort-race',
        runtime_status: 'cancelled',
        finished_at: '2026-04-20T00:11:00.000Z',
      }),
    })
    getHarnessConversationMock.mockResolvedValue({
      data: buildHarnessConversationDetail({
        id: 'conv-home-abort-race',
        runtime_status: 'idle',
        status: 'completed',
      }),
    })

    useChatStore.setState({
      conversationId: 'conv-home-abort-race',
      messages: [],
      artifactMode: 'web',
      activeSkillId: null,
      skillSelectionMode: 'auto',
      isStreaming: false,
      runStatus: 'idle',
      conversationSessions: {},
    })

    const firstSend = useChatStore.getState().sendMessage('你好')
    await Promise.resolve()
    useChatStore.getState().stopStreaming()
    const secondSend = useChatStore.getState().sendMessage('嘿嘿')
    await Promise.resolve()

    const activeSession = useChatStore.getState().conversationSessions['conv-home-abort-race']
    expect(streamHarnessSendMessageMock).toHaveBeenCalledTimes(2)
    expect(activeSession?.runStatus).toBe('running')
    expect(activeSession?.isStreaming).toBe(true)
    expect(activeSession?.messages.map((message) => message.content)).toEqual(['你好', '嘿嘿'])

    releaseSecondStream()
    await Promise.all([firstSend, secondSend])
  })

    it('does not wait for later artifact mode changes before sending the fast-start payload', async () => {
    let releaseStream!: () => void
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
    })

    useChatStore.setState({
      conversationId: 'conv-home-latest-mode',
      messages: [],
      artifactMode: 'web',
      activeSkillId: null,
      skillSelectionMode: 'auto',
      isStreaming: false,
      runStatus: 'idle',
    })

    const sendPromise = useChatStore.getState().sendMessage('帮我做一个表格')
    await Promise.resolve()

    useChatStore.getState().setArtifactMode('spreadsheet')
    releaseStream()

    await sendPromise

    expect(streamHarnessSendMessageMock).toHaveBeenCalledWith(
      'conv-home-latest-mode',
      expect.objectContaining({
        artifact_mode: 'web',
        skill_id: null,
      }),
      expect.any(AbortSignal),
      0,
    )
  })

    it('ignores v2-only tool_result events while sending a homepage message even if the engine flag is stale', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'tool_result',
        data: {
          tool: 'image_generation',
          call_id: 'call-home-1',
          status: 'completed',
          result: {
            status: 'completed',
            result_url: 'https://example.com/image.png',
          },
        },
      }
    })

    useChatStore.setState({
      conversationId: 'conv-home-existing',
      engineVersion: 'v2',
      messages: [],
    })

    await useChatStore.getState().sendMessage('hello')

    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0]?.role).toBe('user')
    expect(useChatStore.getState().messages[0]?.blocks).toBeUndefined()
  })

    it('ignores v2-only generation events while sending a homepage message even if the engine flag is stale', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'generation_started',
        data: {
          task_id: 'gen-home-1',
          media_type: 'image',
          status: 'running',
          prompt: 'draw a cat',
        },
      }
      yield {
        type: 'generation_completed',
        data: {
          task_id: 'gen-home-1',
          result_url: 'https://example.com/generated.png',
        },
      }
    })

    useChatStore.setState({
      conversationId: 'conv-home-existing',
      engineVersion: 'v2',
      messages: [],
    })

    await useChatStore.getState().sendMessage('hello')

    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0]?.role).toBe('user')
    expect(useChatStore.getState().messages[0]?.blocks).toBeUndefined()
    expect(useChatStore.getState().streamingBlocks).toEqual([])
  })

    it('hides internal exclude_from_history messages when loading harness conversation detail', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({}, [
        {
          id: 'internal-revision',
          role: 'user',
          content: '用户要求修改当前大纲：先检索公开数据。',
          metadata: {
            exclude_from_history: true,
          },
          created_at: '2026-04-21T00:00:00.000Z',
        },
        {
          id: 'assistant-visible',
          role: 'assistant',
          content: '这是用户可见的计划回复。',
          created_at: '2026-04-21T00:00:01.000Z',
        },
      ]),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    const messages = useChatStore.getState().messages
    expect(messages).toHaveLength(1)
    expect(messages[0]?.content).toBe('这是用户可见的计划回复。')
  })

    it('hides internal_model_prompt messages when loading harness conversation detail', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({}, [
        {
          id: 'internal-gate',
          role: 'user',
          content: '系统提醒：模型准备给最终回复。',
          metadata: {
            message_kind: 'internal_model_prompt',
          },
          created_at: '2026-04-21T00:00:00.000Z',
        },
        {
          id: 'assistant-visible',
          role: 'assistant',
          content: '这是用户可见的最终回复。',
          created_at: '2026-04-21T00:00:01.000Z',
        },
      ]),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    const messages = useChatStore.getState().messages
    expect(messages).toHaveLength(1)
    expect(messages[0]?.content).toBe('这是用户可见的最终回复。')
  })

    it('restores persisted model preferences when loading harness conversation detail', async () => {
    useChatStore.setState({
      modelPreferences: {
        image_model: 'current-image',
        image_provider: 'current-provider',
        video_model: 'current-video',
        video_provider: 'current-provider',
        multimodal_model: 'current-chat',
        multimodal_provider: 'current-provider',
        auto: false,
      },
    } as any)
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
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
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    expect(useChatStore.getState().modelPreferences).toEqual({
      image_model: 'history-image',
      image_provider: 'builtin',
      video_model: 'history-video',
      video_provider: 'builtin',
      multimodal_model: 'history-chat',
      multimodal_provider: 'builtin',
      auto: false,
    })
  })

    it('restores submitted interaction answers when loading harness conversation detail snapshots', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        runtime_status: 'completed',
        runtime_state: {
          user_interaction: null,
        },
      }, [
        {
          id: 'assistant-interaction-1',
          role: 'assistant',
          content: null,
          created_at: '2026-05-12T10:08:58.000Z',
          blocks: [
            {
              id: 'interaction-form:functions.ask_user:11',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              ui_kind: 'interaction_form',
              render_key: 'interaction:functions.ask_user:11',
              payload: {
                request_id: 'functions.ask_user:11',
                requestId: 'functions.ask_user:11',
                tool_call_id: 'functions.ask_user:11',
                toolCallId: 'functions.ask_user:11',
                question: 'Gate A: confirm strategy?',
                kind: 'ask_user',
                schema: {
                  title: 'Gate A',
                  fields: [
                    {
                      id: 'strategy_confirmation',
                      label: '确认状态',
                      type: 'radio',
                      options: [
                        { label: '确认，请进入下一步视觉方向设计', value: 'confirm' },
                        { label: '需要调整', value: 'adjust' },
                      ],
                    },
                    {
                      id: 'adjustment_notes',
                      label: '补充意见',
                      type: 'textarea',
                    },
                  ],
                },
                answers: null,
                status: 'pending',
              },
            },
          ],
        },
        {
          id: 'user-reply-1',
          role: 'user',
          content: '确认，请进入下一步视觉方向设计',
          created_at: '2026-05-12T10:09:44.000Z',
          metadata: {
            request_id: 'functions.ask_user:11',
            answer: '{"strategy_confirmation":{"type":"option","value":"confirm","label":"确认，请进入下一步视觉方向设计"},"adjustment_notes":""}',
            display_label: '确认，请进入下一步视觉方向设计',
            answers: {
              strategy_confirmation: {
                type: 'option',
                value: 'confirm',
                label: '确认，请进入下一步视觉方向设计',
              },
              adjustment_notes: '',
            },
            source: 'preflight_interaction_submission',
        },
      },
      ]),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    const interactionBlock = useChatStore.getState().messages
      .flatMap((message) => message.blocks || [])
      .find((block) => block.uiKind === 'interaction_form')

    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.submittedLabel).toBe('确认，请进入下一步视觉方向设计')
    expect(interactionBlock?.payload.submittedAnswer).toBe('{"strategy_confirmation":{"type":"option","value":"confirm","label":"确认，请进入下一步视觉方向设计"},"adjustment_notes":""}')
    expect(interactionBlock?.payload.answers).toEqual({
      strategy_confirmation: {
        type: 'option',
        value: 'confirm',
        label: '确认，请进入下一步视觉方向设计',
      },
      adjustment_notes: '',
    })
  })

    it('responds through the harness stream even if the engine flag is stale', async () => {
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {})
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-respond',
      }, [
        {
          id: 'assistant-interaction-respond',
          role: 'assistant',
          content: null,
          created_at: '2026-05-12T10:08:58.000Z',
          blocks: [
            {
              id: 'interaction-form:req-1',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              ui_kind: 'interaction_form',
              render_key: 'interaction:req-1',
              payload: {
                request_id: 'req-1',
                requestId: 'req-1',
                question: 'Continue?',
                kind: 'ask_user',
                status: 'submitted',
                answers: null,
                submitted_label: 'yes',
                submittedLabel: 'yes',
                submitted_answer: 'yes',
                submittedAnswer: 'yes',
              },
            },
          ],
        },
        {
          id: 'user-reply-respond',
          role: 'user',
          content: 'yes',
          created_at: '2026-05-12T10:09:44.000Z',
        },
      ]),
    })

    useChatStore.setState({
      conversationId: 'conv-home-respond',
      engineVersion: 'v2',
      userInteraction: {
        request_id: 'req-1',
        question: 'Continue?',
        kind: 'ask_user',
        schema: null,
      },
    })

    await useChatStore.getState().respondToAgent('req-1', 'yes')

    expect(streamHarnessRespondToAgentMock).toHaveBeenCalledWith(
      'conv-home-respond',
      { request_id: 'req-1', answer: 'yes', display_label: 'yes' },
      expect.any(AbortSignal),
      0,
    )
    expect(streamRespondToAgentMock).not.toHaveBeenCalled()

    const state = useChatStore.getState()
  expect(state.userInteraction).toBeNull()
    expect(state.messages.some((message) => message.role === 'user' && message.content === 'yes')).toBe(true)
    const submittedInteraction = state.messages.find((message) =>
      message.role === 'assistant'
      && message.blocks?.some((block) => block.uiKind === 'interaction_form'),
    )
    expect(submittedInteraction).toBeDefined()
    expect(submittedInteraction?.blocks?.[0]?.payload?.status).toBe('submitted')
    expect(submittedInteraction?.blocks?.[0]?.payload?.submittedLabel).toBe('yes')
  })

    it('syncs design system picker design system selection into the composer state', async () => {
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {
      yield {
        type: 'workspace_runtime_session_updated',
        data: {
          workspace_runtime_session: {
            selected_skill: 'html-ppt',
            selected_direction: null,
            selected_design_system: 'arc-browser',
          },
        },
      }
    })
    getHarnessConversationMock.mockResolvedValue({
      data: buildHarnessConversationDetail({
        id: 'conv-home-design-system',
        design_system_id: 'arc-browser',
      }, [
        {
          id: 'assistant-design-system-1',
          role: 'assistant',
          content: null,
          created_at: '2026-05-12T10:08:58.000Z',
          blocks: [
            {
              id: 'interaction-form:design-system:conv-home-design-system',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              ui_kind: 'interaction_form',
              render_key: 'interaction:design-system:conv-home-design-system',
              payload: {
                request_id: 'design-system:conv-home-design-system',
                requestId: 'design-system:conv-home-design-system',
                question: '选择设计体系',
                kind: 'design_system_picker',
                answers: {
                  design_system_id: 'arc-browser',
                },
                status: 'submitted',
                submitted_label: 'Arc Browser',
                submittedLabel: 'Arc Browser',
                submitted_answer: '{"design_system_id":"arc-browser"}',
                submittedAnswer: '{"design_system_id":"arc-browser"}',
              },
            },
          ],
        },
        {
          id: 'user-design-system-submission',
          role: 'user',
          content: 'Arc Browser',
          created_at: '2026-05-12T10:09:44.000Z',
          metadata: {
            request_id: 'design-system:conv-home-design-system',
            kind: 'design_system_picker',
            answer: '{"design_system_id":"arc-browser"}',
            display_label: 'Arc Browser',
            answers: {
              design_system_id: 'arc-browser',
            },
            source: 'preflight_interaction_submission',
          },
        },
      ]),
    })

    useChatStore.setState({
      conversationId: 'conv-home-design-system',
      engineVersion: 'harness',
      selectedDesignSystemId: null,
      messages: [
        {
          id: 'assistant-design-system-picker',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-12T10:08:58.000Z',
          blocks: [
            {
              id: 'interaction-form:design-system:conv-home-design-system',
              kind: 'interaction',
              order: 0,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              renderKey: 'interaction:design-system:conv-home-design-system',
              payload: {
                requestId: 'design-system:conv-home-design-system',
                request_id: 'design-system:conv-home-design-system',
                question: '选择设计体系',
                kind: 'design_system_picker',
                status: 'pending',
                answers: null,
              },
            },
          ],
        },
      ],
      conversations: [
        buildHarnessConversationDetail({
          id: 'conv-home-design-system',
          design_system_id: null,
        }) as any,
      ],
      userInteraction: {
        request_id: 'design-system:conv-home-design-system',
        question: '选择设计体系',
        kind: 'design_system_picker',
        schema: null,
      },
    })

    await useChatStore.getState().respondToAgent(
      'design-system:conv-home-design-system',
      '{"design_system_id":"arc-browser"}',
      'Arc Browser',
      undefined,
      { design_system_id: 'arc-browser' },
    )

    const state = useChatStore.getState()
    expect(state.selectedDesignSystemId).toBe('arc-browser')
    expect(state.conversations[0]?.design_system_id).toBe('arc-browser')
    expect(state.messages.filter((message) => message.role === 'user' && message.content === 'Arc Browser')).toHaveLength(1)
    const interactionBlock = state.messages
      .flatMap((message) => message.blocks || [])
      .find((block) => block.uiKind === 'interaction_form')
    expect(interactionBlock?.payload.status).toBe('submitted')
    expect(interactionBlock?.payload.submittedLabel).toBe('Arc Browser')
    expect(interactionBlock?.payload.answers).toEqual({
      design_system_id: 'arc-browser',
    })
  })

    it('optimistically syncs design system picker design system selection before runtime session events', async () => {
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {})
    getHarnessConversationMock.mockResolvedValue({
      data: buildHarnessConversationDetail({
        id: 'conv-home-design-system-optimistic',
        runtime_status: 'idle',
        design_system_id: null,
      }),
    })

    useChatStore.setState({
      conversationId: 'conv-home-design-system-optimistic',
      engineVersion: 'harness',
      selectedDesignSystemId: null,
      messages: [],
      conversations: [
        buildHarnessConversationDetail({
          id: 'conv-home-design-system-optimistic',
          design_system_id: null,
        }) as any,
      ],
      userInteraction: {
        request_id: 'design-system:conv-home-design-system-optimistic',
        question: '选择设计体系',
        kind: 'design_system_picker',
        schema: null,
      },
      conversationSessions: {
        'conv-home-design-system-optimistic': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: {
            request_id: 'design-system:conv-home-design-system-optimistic',
            question: '选择设计体系',
            kind: 'design_system_picker',
            schema: null,
          },
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().respondToAgent(
      'design-system:conv-home-design-system-optimistic',
      '{"design_system_id":"arc-browser"}',
      'Arc Browser',
      undefined,
      { design_system_id: 'arc-browser' },
    )

    expect(useChatStore.getState().selectedDesignSystemId).toBe('arc-browser')
    expect(useChatStore.getState().conversations[0]?.design_system_id).toBe('arc-browser')
  })

    it('keeps a single user reply and immediately enables cancellation after plan approval resumes a running conversation', async () => {
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {})
    cancelHarnessConversationRunMock.mockResolvedValueOnce({
      data: {
        ...buildHarnessConversationDetail({
          id: 'conv-home-plan-approval',
          runtime_status: 'cancelled',
          finished_at: '2026-04-21T00:05:00.000Z',
        }),
      },
    })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      await new Promise(() => {})
    })

    useChatStore.setState({
      conversationId: 'conv-home-plan-approval',
      engineVersion: 'harness',
      messages: [
        {
          id: 'plan-message-local',
          role: 'assistant',
          content: null,
          createdAt: '2026-04-21T00:00:00.000Z',
          blocks: [
            {
              id: 'plan-artifact',
              kind: 'content',
              order: 0,
              status: 'in_progress',
              visible: true,
              uiKind: 'plan_artifact',
              renderKey: 'plan-artifact',
              payload: {
                title: '任务计划',
                status: 'in_progress',
                currentStep: 'step-1',
                steps: [
                  { id: 'step-1', order: 1, title: '阅读文档', status: 'in_progress' },
                  { id: 'step-2', order: 2, title: '编写脚本', status: 'pending' },
                ],
              },
            },
            {
              id: 'interaction-form:req-plan-1',
              kind: 'interaction',
              order: 1,
              status: 'completed',
              visible: true,
              uiKind: 'interaction_form',
              payload: {
                requestId: 'req-plan-1',
                request_id: 'req-plan-1',
                question: '按这个执行继续吗？',
                options: [],
                status: 'pending',
                kind: 'ask_user',
              },
            },
          ],
        },
      ],
      isStreaming: false,
  userInteraction: {
        request_id: 'req-plan-1',
        question: '按这个执行继续吗？',
        kind: 'ask_user',
        schema: null,
      },
      conversationSessions: {
        'conv-home-plan-approval': {
          messages: [
            {
              id: 'plan-message-local',
              role: 'assistant',
              content: null,
              createdAt: '2026-04-21T00:00:00.000Z',
              blocks: [
                {
                  id: 'plan-artifact',
                  kind: 'content',
                  order: 0,
                  status: 'in_progress',
                  visible: true,
                  uiKind: 'plan_artifact',
                  renderKey: 'plan-artifact',
                  payload: {
                    title: '任务计划',
                    status: 'in_progress',
                    currentStep: 'step-1',
                    steps: [
                      { id: 'step-1', order: 1, title: '阅读文档', status: 'in_progress' },
                      { id: 'step-2', order: 2, title: '编写脚本', status: 'pending' },
                    ],
                  },
                },
                {
                  id: 'interaction-form:req-plan-1',
                  kind: 'interaction',
                  order: 1,
                  status: 'completed',
                  visible: true,
                  uiKind: 'interaction_form',
                  payload: {
                    requestId: 'req-plan-1',
                    request_id: 'req-plan-1',
                    question: '按这个执行继续吗？',
                    options: [],
                    status: 'pending',
                    kind: 'ask_user',
                  },
                },
              ],
            },
          ],
          activePlan: null,
          userInteraction: {
            request_id: 'req-plan-1',
            question: '按这个执行继续吗？',
            kind: 'ask_user',
            schema: null,
          },
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'waiting_input',
        },
      },
    })

    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-plan-approval',
        runtime_status: 'running',
        run_id: 'run-after-approval',
        status: 'active',
      }),
    })

    await useChatStore.getState().respondToAgent('req-plan-1', '按这个执行')

    const activeSession = useChatStore.getState().conversationSessions['conv-home-plan-approval']
    expect(streamHarnessConversationEventsMock).toHaveBeenCalledWith(
      'conv-home-plan-approval',
      expect.any(AbortSignal),
    )
    expect(activeSession?.messages.filter((message) => message.role === 'user')).toHaveLength(1)
    expect(activeSession?.messages[0]?.blocks?.some((block) => block.uiKind === 'plan_artifact')).toBe(true)
    expect(activeSession?.messages[1]).toMatchObject({
      role: 'user',
      content: '按这个执行',
    })
    expect(activeSession?.runStatus).toBe('running')
    expect(activeSession?.eventStreamController).not.toBeNull()

    useChatStore.getState().stopStreaming()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(cancelHarnessConversationRunMock).toHaveBeenCalledWith('conv-home-plan-approval')
  })

    it('loads homepage conversation detail from the harness API even if the engine flag is stale and the id is numeric', async () => {
    useChatStore.setState({
      engineVersion: 'v2',
      viewerUserId: 7,
    })

    await useChatStore.getState().loadConversation(77)

    expect(getHarnessConversationMock).toHaveBeenCalledWith('77', expect.any(AbortSignal))
    expect(getConversationMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversationId).toBe('conv-home-detail')
    expect(useChatStore.getState().engineVersion).toBe('harness')
  })

    it('restores render-only rich blocks from persisted message blocks without replay', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-render-plan',
        role: 'assistant',
        content: null,
        created_at: '2026-04-20T00:00:00.000Z',
        blocks: [
          {
            id: 'home-user-plan-card',
            kind: 'content',
            order: 0,
            status: 'planning_ready',
            visible: true,
            ui_kind: 'user_plan_card',
            payload: {
              artifact_type: 'ppt',
              title: '设计行业洞察',
              summary: '四页演示文稿',
              status: 'planning_ready',
              outline: [
                { id: 'slide-1', title: '封面', summary: '主题与定位', order: 1, status: 'pending' },
              ],
            },
            user_visible: true,
            debug_only: false,
          },
        ],
        metadata: {
          render_only: true,
        },
      },
    ] as any)

    expect(messages).toHaveLength(1)
    expect(messages[0]?.id).toMatch(/^render:home-user-plan(?::|$)/)
    expect(messages[0]?.content).toBeNull()
    expect(messages[0]?.blocks?.[0]?.uiKind).toBe('user_plan_card')
    expect(messages[0]?.blocks?.[0]?.payload?.title).toBe('设计行业洞察')
  })

    it('restores persisted Design Jury cards in message order instead of trailing global state', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-critique-card',
        role: 'assistant',
        content: null,
        created_at: '2026-06-03T08:01:08.000Z',
        blocks: [
          {
            id: 'critique:critique-1:round:1',
            kind: 'content',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'design_jury_card',
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
            user_visible: true,
            debug_only: false,
            render_key: 'critique-card:critique-1:1',
          },
        ],
        metadata: {
          render_only: true,
          render_key: 'critique-card:critique-1:1',
        },
      },
      {
        id: 'assistant-publish-call',
        role: 'assistant',
        content: '',
        created_at: '2026-06-03T08:01:19.000Z',
        tool_calls: [{ id: 'call-publish', name: 'publish_output', arguments: {} }],
        metadata: { finish_reason: 'tool_calls' },
      },
      {
        id: 'assistant-final-summary',
        role: 'assistant',
        content: '最终总结',
        created_at: '2026-06-03T08:01:29.000Z',
        blocks: [
          {
            id: 'final-answer',
            kind: 'text',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'assistant_final_answer',
            payload: { text: '最终总结' },
          },
        ],
      },
    ] as any)

    expect(messages).toHaveLength(2)
    expect(messages[0]?.blocks?.[0]?.uiKind).toBe('design_jury_card')
    expect(messages[0]?.blocks?.[0]?.payload?.critiqueRunId).toBe('critique-1')
    expect(messages[1]?.blocks?.[0]?.uiKind).toBe('assistant_final_answer')
  })

  it.each([
    ['image analysis', 'media_card', { tool_name: 'analyze_image', media_type: 'image_analysis' }],
    ['image generation', 'media_card', { tool_name: 'generate_image', media_type: 'image_generation' }],
    ['video generation', 'media_card', { tool_name: 'generate_video', media_type: 'video_generation' }],
    ['generation status', 'generation_card', { tool_name: 'generate_image' }],
    ['web search', 'web_search_card', { query: 'home agent render order' }],
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
    ] as any)

    expect(messages).toHaveLength(2)
    expect(messages[0]?.id).toBe(`run:render:${uiKind}`)
    expect(messages[0]?.blocks?.[0]?.uiKind).toBe(uiKind)
    expect(messages[1]?.id).toBe('assistant-final-summary')
    expect(messages[1]?.blocks?.[0]?.uiKind).toBe('assistant_final_answer')
  })

  it('drops duplicated plain content for persisted render-only progress cards', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-render-progress',
        role: 'assistant',
        content: '已完成',
        created_at: '2026-05-03T07:58:42.000Z',
        blocks: [
          {
            id: 'home-user-progress-card',
            kind: 'content',
            order: 1,
            status: 'completed',
            visible: true,
            ui_kind: 'user_progress_card',
            payload: {
              message: '已完成',
              completedMessage: '开始执行',
              status: 'completed',
            },
            user_visible: true,
            debug_only: false,
          },
        ],
        metadata: {
          render_only: true,
          render_key: 'home-user-progress',
        },
      },
    ] as any)

    expect(messages).toHaveLength(1)
    expect(messages[0]?.id).toBe('render:home-user-progress')
    expect(messages[0]?.content).toBeNull()
    expect(messages[0]?.blocks?.[0]?.payload?.message).toBe('已完成')
  })

    it('syncs the active harness skill from replay refresh when a resumed run reports docx', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {})
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          id: 'conv-home-docx',
          skill_id: 'docx',
          runtime_status: 'running',
          status: 'active',
          run_id: 'run-docx-1',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Preparing document output',
            created_at: '2026-04-20T00:00:05.000Z',
          },
        ],
      ),
    })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-docx',
      activeSkillId: null,
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-docx': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
  userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'idle',
        },
      },
    })

    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-docx',
        skill_id: 'docx',
        runtime_status: 'running',
        status: 'active',
        run_id: 'run-docx-1',
      }),
    })

    await useChatStore.getState().sendMessage('重试')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(useChatStore.getState().activeSkillId).toBe('docx')
    expect(streamHarnessConversationEventsMock).toHaveBeenCalledWith(
      'conv-home-docx',
      expect.any(AbortSignal),
    )
  })

    it('loads harness conversation history from the persisted snapshot when rebuilding the UI', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        runtime_status: 'idle',
      }, [
        {
          id: 'assistant-main',
          role: 'assistant',
          content: 'Restored from snapshot',
          created_at: '2026-04-20T00:00:30.000Z',
        },
      ]),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    expect(getHarnessConversationMock).toHaveBeenCalledWith('conv-home-detail', expect.any(AbortSignal))
    expect(useChatStore.getState().messages[0]?.content).toBe('Restored from snapshot')
    expect(useChatStore.getState().conversationSessions['conv-home-detail']?.lastSequence).toBe(0)
  })

    it('restores the selected design system when loading a persisted harness conversation', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-design-system',
        runtime_status: 'idle',
        design_system_id: 'warm-editorial',
      }),
    })

    useChatStore.setState({
      selectedDesignSystemId: null,
      conversations: [
        buildHarnessConversationDetail({
          id: 'conv-home-design-system',
          design_system_id: null,
        }) as any,
      ],
    })

    await useChatStore.getState().loadConversation('conv-home-design-system')

    expect(useChatStore.getState().selectedDesignSystemId).toBe('warm-editorial')
  })

    it('loads the explicit interaction profile from the harness detail snapshot', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-interaction-profile',
        runtime_profile: 'home',
        interaction_profile: 'home_blocking_preflight',
        runtime_status: 'idle',
      }),
    })

    await useChatStore.getState().loadConversation('conv-home-interaction-profile')

    expect(useChatStore.getState().interactionProfile).toBe('home_blocking_preflight')
    expect(
      useChatStore.getState().conversations.find((item) => item.id === 'conv-home-interaction-profile')?.interaction_profile,
    ).toBe('home_blocking_preflight')
  })

    it('rebuilds the initial user message from the persisted snapshot after refresh', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        runtime_status: 'idle',
      }, [
        {
          id: 'user-msg-1',
          role: 'user',
          content: 'Analyze this image',
          attachments: [
            { type: 'image', url: 'assets/inputs/upload.png', name: 'upload.png' },
          ],
          created_at: '2026-04-21T00:00:00.000Z',
        },
        {
          id: 'assistant-main',
          role: 'assistant',
          content: 'Image analysis complete.',
          created_at: '2026-04-21T00:00:01.000Z',
        },
      ]),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    expect(useChatStore.getState().messages).toHaveLength(2)
    expect(useChatStore.getState().messages[0]).toMatchObject({
      id: 'user-msg-1',
      role: 'user',
      content: 'Analyze this image',
    })
    expect(useChatStore.getState().messages[1]).toMatchObject({
      role: 'assistant',
      content: 'Image analysis complete.',
    })
  })

    it('rebuilds refreshed conversation state from persisted snapshots instead of replayed events', async () => {
    getHarnessConversationMock
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail({
          runtime_status: 'idle',
        }, [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Initial snapshot',
            created_at: '2026-04-21T00:00:00.000Z',
          },
        ]),
      })
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail({
          runtime_status: 'idle',
        }, [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Refreshed snapshot',
            created_at: '2026-04-21T00:00:02.000Z',
          },
        ]),
      })

    await useChatStore.getState().loadConversation('conv-home-detail')
    expect(useChatStore.getState().messages[0]?.content).toBe('Initial snapshot')

    await useChatStore.getState().loadConversation('conv-home-detail')

    expect(useChatStore.getState().messages[0]?.content).toBe('Refreshed snapshot')
    expect(useChatStore.getState().conversationSessions['conv-home-detail']?.lastSequence).toBe(0)
  })

    it('rebuilds homepage history from the persisted snapshot when stored user messages exist', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'idle',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Restored assistant response',
            created_at: '2026-04-20T00:00:30.000Z',
          },
        ],
      ),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    expect(useChatStore.getState().messages).toHaveLength(1)
    expect(useChatStore.getState().messages[0]?.role).toBe('assistant')
    expect(useChatStore.getState().messages[0]?.content).toBe('Restored assistant response')
  })


    it('rebuilds submitted plan approvals from persisted messages after refresh', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'idle',
          started_at: '2026-04-20T16:10:00.000Z',
          finished_at: '2026-04-20T16:11:30.000Z',
          updated_at: '2026-04-20T16:11:30.000Z',
        },
        [
          {
            id: 'persisted-user-approval',
            role: 'user',
            content: 'approve execution',
            created_at: '2026-04-20T00:00:00.500Z',
          },
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Execution started',
            created_at: '2026-04-20T00:00:01.000Z',
          },
        ],
      ),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')

    const messages = useChatStore.getState().messages
    expect(messages.some((message) => message.role === 'user' && message.content === 'approve execution')).toBe(true)
    expect(messages.some((message) => message.role === 'assistant' && message.content === 'Execution started')).toBe(true)
    const interactionMessage = messages.find((message) =>
      message.role === 'assistant'
      && message.blocks?.some((block) => block.uiKind === 'interaction_form'),
    )
    expect(interactionMessage).toBeUndefined()
  })

    it('loads more homepage conversations from the harness API even if the engine flag is stale', async () => {
    listHarnessConversationsMock.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 'conv-home-3',
            title: 'Older Harness Conversation',
            skill_id: null,
            mode: 'fast',
            status: 'completed',
            runtime_status: 'idle',
            engine_version: 'harness',
            run_id: null,
            started_at: '2026-04-19T00:00:00.000Z',
            finished_at: '2026-04-19T00:10:00.000Z',
    user_interaction: null,
            created_at: '2026-04-19T00:00:00.000Z',
            updated_at: '2026-04-19T00:10:00.000Z',
          },
        ],
        has_more: false,
      },
    })

    useChatStore.setState({
      conversations: [
        {
          id: 'conv-home-2',
          title: 'Harness Conversation',
          skill_id: null,
          phase: 'executing',
          mode: 'fast',
          status: 'active',
          runtime_status: 'idle',
          engine_version: 'harness',
          run_id: null,
          started_at: '2026-04-20T00:00:00.000Z',
          finished_at: null,
          created_at: '2026-04-20T00:00:00.000Z',
          updated_at: '2026-04-20T00:00:00.000Z',
        },
      ],
      conversationsPage: 1,
      conversationsHasMore: true,
      engineVersion: 'v2',
    })

    await useChatStore.getState().loadMoreConversations()

    expect(listHarnessConversationsMock).toHaveBeenCalledWith(2, 20)
    expect(useChatStore.getState().conversations).toHaveLength(2)
    expect(useChatStore.getState().conversations[1]?.id).toBe('conv-home-3')
  })

    it('dedupes legacy plan artifacts by render key when rebuilding homepage history', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-plan-awaiting',
        role: 'assistant',
        content: null,
        created_at: '2026-04-20T00:00:00.000Z',
        blocks: [
          {
            id: 'plan-artifact-awaiting',
            kind: 'content',
            order: 0,
            status: 'planning_ready',
            visible: true,
            ui_kind: 'plan_artifact',
            render_key: 'plan-artifact',
            payload: {
              file_path: 'plan.md',
              status: 'planning_ready',
            },
          },
        ],
      },
      {
        id: 'assistant-plan-completed',
        role: 'assistant',
        content: null,
        created_at: '2026-04-20T00:05:00.000Z',
        blocks: [
          {
            id: 'plan-artifact-completed',
            kind: 'content',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'plan_artifact',
            render_key: 'plan-artifact',
            payload: {
              file_path: 'plan.md',
              status: 'completed',
            },
          },
        ],
      },
    ] as any)

    const planMessages = messages.filter((message) =>
      (message.blocks || []).some((block) => block.uiKind === 'plan_artifact'),
    )

    expect(planMessages).toHaveLength(1)
    expect(planMessages[0]?.id).toBe('assistant-plan-completed')
    expect(planMessages[0]?.blocks?.[0]?.status).toBe('completed')
  })

    it('prefers the completed generation card when snapshot rebuild sees duplicate artifact refs', () => {
    const messages = __chatStoreTestUtils.buildHarnessUiMessages([
      {
        id: 'assistant-generation-completed',
        role: 'assistant',
        content: null,
        created_at: '2026-04-20T00:00:00.000Z',
        blocks: [
          {
            id: 'media-artifact-abc',
            kind: 'content',
            order: 0,
            status: 'completed',
            visible: true,
            ui_kind: 'media_card',
            render_key: 'media:artifact:artifact_ref:abc',
            payload: {
              artifact_ref: 'artifact_ref:abc',
              media_type: 'image_generation',
              status: 'completed',
              result_url: 'assets/references/generated_image_abc/original.png',
            },
          },
        ],
      },
      {
        id: 'assistant-generation-processing',
        role: 'assistant',
        content: null,
        created_at: '2026-04-20T00:05:00.000Z',
        blocks: [
          {
            id: 'media-call-old-processing',
            kind: 'content',
            order: 0,
            status: 'processing',
            visible: true,
            ui_kind: 'media_card',
            payload: {
              artifact_ref: 'artifact_ref:abc',
              media_type: 'image_generation',
              status: 'processing',
            },
          },
        ],
      },
    ] as any)

    const mediaMessages = messages.filter((message) =>
      (message.blocks || []).some((block) => block.uiKind === 'media_card'),
    )

    expect(mediaMessages).toHaveLength(1)
    expect(mediaMessages[0]?.id).toBe('assistant-generation-completed')
    expect(mediaMessages[0]?.blocks?.[0]?.status).toBe('completed')
    expect(mediaMessages[0]?.blocks?.[0]?.payload.resultUrl).toBe('assets/references/generated_image_abc/original.png')
  })

    it('matches full replay when ordered events are replayed first and then appended live', () => {
    const events = buildProjectionReplayEvents()
    const splitIndex = 6

    const replayedThenAppended = events
      .slice(splitIndex)
      .reduce(
        (state, event) => applyHomeHarnessEvent(state, event),
        replayHomeHarnessEvents(events.slice(0, splitIndex)),
      )

    const fullReplay = replayHomeHarnessEvents(events)
    const incrementalReplay = events.reduce(
      (state, event) => applyHomeHarnessEvent(state, event),
      createHomeHarnessProjectionState(),
    )

    expect(replayedThenAppended).toEqual(fullReplay)
    expect(incrementalReplay).toEqual(fullReplay)
  })

    it('surfaces a protocol error when message_done closes a resumed stream without turn_completed', async () => {
    getHarnessConversationMock
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail({
          runtime_status: 'running',
          status: 'active',
        }, [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Resumed snapshot response',
            created_at: '2026-04-20T00:00:01.000Z',
          },
        ]),
      })
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail({
          runtime_status: 'completed',
          status: 'completed',
          finished_at: '2026-04-20T00:00:02.000Z',
        }, [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Resumed snapshot response',
            created_at: '2026-04-20T00:00:01.000Z',
          },
        ]),
      })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      yield {
        type: 'message_done',
        data: {
          conversation_id: 'conv-home-detail',
        },
      }
    })

    useChatStore.setState({
      engineVersion: 'harness',
      conversationId: 'conv-home-detail',
      messages: [],
      isStreaming: false,
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getHarnessConversationMock).toHaveBeenCalledTimes(2)
    expect(useChatStore.getState().messages[0]?.content).toBe('Resumed snapshot response')
    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(session?.runStatus).toBe('failed')
    expect(session?.messages.some((message) => String(message.content).includes('missingTurnCompleted'))).toBe(true)
  })

    it('preserves freshly streamed assistant blocks while surfacing a missing turn_completed protocol error', async () => {
    getHarnessConversationMock
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail({
          runtime_status: 'running',
          status: 'active',
        }),
      })
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail({
          runtime_status: 'completed',
          status: 'completed',
          finished_at: '2026-04-20T00:00:02.000Z',
        }, []),
      })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      yield presentationComplete(1, 'assistant-final-stream', 'Fresh streamed final answer', {
        run_id: 'run-home-detail',
        ui_kind: 'assistant_final_answer',
        payload: { message_kind: 'final_answer' },
      })
      yield {
        type: 'message_done',
        data: {
          conversation_id: 'conv-home-detail',
        },
      }
    })

    useChatStore.setState({
      engineVersion: 'harness',
      conversationId: 'conv-home-detail',
      messages: [],
      isStreaming: false,
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getHarnessConversationMock).toHaveBeenCalledTimes(2)
    expect(useChatStore.getState().messages[0]?.content).toBe('Fresh streamed final answer')
    expect(useChatStore.getState().messages[0]?.blocks?.[0]?.uiKind).toBe('assistant_final_answer')
    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(session?.runStatus).toBe('failed')
    expect(session?.messages.some((message) => String(message.content).includes('missingTurnCompleted'))).toBe(true)
  })

    it('reconnects the harness SSE stream from the replayed last sequence', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'running',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'History cursor',
            created_at: '2026-04-20T00:00:18.000Z',
          },
        ],
      ),
    })

    streamHarnessConversationEventsMock.mockImplementation(async function* () {})

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(streamHarnessConversationEventsMock).toHaveBeenCalledWith(
      'conv-home-detail',
      expect.any(AbortSignal),
    )
  })

    it('keeps the latched auto-selected skill and interaction profile stable when a running conversation reconnects', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail({
        id: 'conv-home-reconnect-sticky',
        runtime_profile: 'home',
        interaction_profile: 'home_blocking_preflight',
        skill_id: 'html-ppt',
        resolved_skill_id: 'html-ppt',
        skill_selection_mode: 'auto',
        skill_resolution_source: 'ai_resolved',
        runtime_status: 'running',
        status: 'active',
      }),
    })

    streamHarnessConversationEventsMock.mockImplementation(async function* () {})

    useChatStore.setState({
      conversationId: 'conv-home-reconnect-sticky',
      interactionProfile: 'canvas_live_interaction',
      activeSkillId: null,
      skillSelectionMode: 'manual',
      conversations: [],
      conversationSessions: {
        'conv-home-reconnect-sticky': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().loadConversation('conv-home-reconnect-sticky')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(useChatStore.getState().interactionProfile).toBe('home_blocking_preflight')
    expect(useChatStore.getState().activeSkillId).toBe('html-ppt')
    expect(useChatStore.getState().skillSelectionMode).toBe('auto')
    expect(streamHarnessConversationEventsMock).toHaveBeenCalledWith(
      'conv-home-reconnect-sticky',
      expect.any(AbortSignal),
    )
  })

    it('keeps a running harness conversation alive when the SSE transport detaches and resubscribes after the shared delay', async () => {
    getHarnessConversationMock
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail(
          {
            runtime_status: 'running',
            status: 'active',
          },
          [
            {
              id: 'assistant-main',
              role: 'assistant',
              content: 'Still running',
              created_at: '2026-04-20T00:00:18.000Z',
            },
          ],
        ),
      })
      .mockResolvedValueOnce({
        data: buildHarnessConversationDetail(
          {
            runtime_status: 'running',
            status: 'active',
            updated_at: '2026-04-20T00:00:30.000Z',
          },
          [
            {
              id: 'assistant-main',
              role: 'assistant',
              content: 'Still running',
              created_at: '2026-04-20T00:00:18.000Z',
            },
          ],
        ),
      })

    let streamCalls = 0
    streamHarnessConversationEventsMock.mockImplementation((() => {
      return async function* (
        _conversationId: string,
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
      }
    })())

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 800))

    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(streamHarnessConversationEventsMock).toHaveBeenCalledTimes(2)
    expect(session?.runStatus).toBe('running')
    expect(session?.isStreaming).toBe(true)
  })

    it('does not resubscribe when restored quick brief, design-system, or ask-user cards are waiting for input', async () => {
    for (const kind of ['quick_brief', 'design_system_picker', 'ask_user']) {
      useChatStore.getState().reset()
      streamHarnessConversationEventsMock.mockReset()
      streamHarnessConversationEventsMock.mockImplementation(async function* () {})
      getHarnessConversationMock.mockReset()
      getHarnessConversationMock.mockResolvedValueOnce({
        data: buildHarnessConversationDetail(
          {
            id: `conv-home-${kind}`,
            runtime_status: 'waiting_input',
            run_state: 'waiting_input',
            status: 'active',
            user_interaction: {
              kind,
              request_id: `${kind}:req`,
              tool_call_id: `${kind}:req`,
              question: 'Confirm?',
              status: 'pending',
              schema: {
                title: 'Confirm',
                fields: [{ id: 'choice', label: 'Choice', type: 'radio', options: [] }],
              },
            },
            runtime_state: {
              runtime_status: 'waiting_input',
              run_state: 'waiting_input',
              user_interaction: null,
            },
            projection: {
              event_last_sequence: 8,
            },
          },
          [
            {
              id: 'assistant-interaction',
              role: 'assistant',
              content: 'Confirm?',
              created_at: '2026-04-20T00:00:02.000Z',
            },
          ],
        ),
      })

      await useChatStore.getState().loadConversation(`conv-home-${kind}`)
      await new Promise((resolve) => setTimeout(resolve, 0))

      const session = useChatStore.getState().conversationSessions[`conv-home-${kind}`]
      expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
      expect(session?.runStatus).toBe('waiting_input')
      expect(session?.isStreaming).toBe(false)
      expect(session?.lastSequence).toBe(8)
      expect(session?.userInteraction?.kind).toBe(kind)
    }
  })

    it('does not resubscribe when a planning-ready conversation is waiting for start execution', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
          run_state: 'waiting_input',
          status: 'active',
          runtime_state: {
            runtime_status: 'waiting_input',
            run_state: 'waiting_input',
            user_interaction: null,
          },
          user_plan: {
            id: 'plan-ready-1',
            title: 'PPT 大纲',
            status: 'planning_ready',
            items: [],
          },
        },
        [
          {
            id: 'assistant-plan-ready',
            role: 'assistant',
            content: 'PPT大纲已准备好',
            created_at: '2026-04-20T00:00:02.000Z',
          },
        ],
      ),
    })

    streamHarnessConversationEventsMock.mockImplementation(async function* () {})

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(session?.runStatus).toBe('waiting_input')
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

    it('stops the homepage stream when a generated outline is waiting for start execution', async () => {
    useChatStore.setState({
      conversationId: 'conv-home-plan-ready-stream',
      conversations: [
        {
          id: 'conv-home-plan-ready-stream',
          title: '生成一个设计公司的落地页',
          skill_id: 'web',
          mode: 'fast',
          status: 'active',
          runtime_status: 'running',
          engine_version: 'harness',
          run_id: 'run-plan-ready',
          started_at: '2026-04-20T00:00:00.000Z',
          finished_at: null,
          created_at: '2026-04-20T00:00:00.000Z',
          updated_at: '2026-04-20T00:00:00.000Z',
        } as any,
      ],
    })

    const outline = {
      title: '像素重组设计公司落地页',
      status: 'planning_ready',
      summary: '单页落地页将围绕品牌定位、服务介绍、合作流程、目标客户、专业优势与预约咨询六个区块展开。',
      version: 1,
      outline_id: 'outline-home-ready',
      plan_instance_id: 'plan-home-ready',
      artifact_type: 'html',
      items: [
        {
          id: 'slide-1',
          order: 1,
          title: 'N/A',
          status: 'completed',
          summary: 'HTML 交付无演示页。',
        },
      ],
      projection_state: {
        status: 'planning_ready',
        plan_instance_id: 'plan-home-ready',
        outline_version: 1,
        items: [
          {
            id: 'slide-1',
            order: 1,
            title: 'N/A',
            status: 'pending',
            summary: 'HTML 交付无演示页。',
          },
        ],
      },
      execution_state: {
        status: 'planning_ready',
        current_step: 'step-2',
        steps: [
          { id: 'step-1', order: 1, title: '明确页面目标与内容框架', status: 'completed' },
          { id: 'step-2', order: 2, title: '制定落地页结构方案', status: 'in_progress' },
        ],
      },
    }

    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'current_outline_created',
        lane: 'user',
        sequence: 10,
        run_id: 'run-plan-ready',
        data: {
          outline,
          projection: outline.projection_state,
          execution_state: outline.execution_state,
          change_source: 'initial_plan',
          created_at: '2026-04-20T00:00:05.000Z',
        },
      }
      yield {
        type: 'execution_progress_updated',
        lane: 'user',
        sequence: 11,
        run_id: 'run-plan-ready',
        data: {
          status: 'planning_ready',
          message: '制定落地页结构方案',
          completed_message: '明确页面目标与内容框架',
          created_at: '2026-04-20T00:00:06.000Z',
        },
      }
      yield {
        type: 'message_done',
        lane: 'user',
        sequence: 12,
        run_id: 'run-plan-ready',
        data: {
          conversation_id: 'conv-home-plan-ready-stream',
          status: 'waiting_input',
          created_at: '2026-04-20T00:00:07.000Z',
        },
      }
      yield turnCompleted('waiting_input', {
        sequence: 13,
        conversation_id: 'conv-home-plan-ready-stream',
        run_id: 'run-plan-ready',
      })
    })

    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          id: 'conv-home-plan-ready-stream',
          phase: 'planning_ready',
          runtime_status: 'waiting_input',
          run_state: 'waiting_input',
          status: 'active',
          runtime_state: {
            phase: 'planning_ready',
            runtime_status: 'waiting_input',
            run_state: 'waiting_input',
            user_interaction: null,
          },
          user_plan: outline,
          outline_runtime: {
            current_outline: outline,
            execution_state: outline.execution_state,
            projection_state: outline.projection_state,
          },
        },
        [
          {
            id: 'assistant-plan-ready-stream',
            role: 'assistant',
            content: outline.summary,
            created_at: '2026-04-20T00:00:06.000Z',
          },
        ],
      ),
    })

    await useChatStore.getState().sendMessage('生成一个设计公司的落地页')
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-home-plan-ready-stream']
    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    expect(session?.runStatus).toBe('waiting_input')
    expect(session?.isStreaming).toBe(false)
    expect(session?.eventStreamController).toBeNull()
    expect(useChatStore.getState().runStatus).toBe('waiting_input')
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

    it('applies a turn_completed(cancelled) SSE event immediately without waiting for a detail refresh', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'running',
          status: 'active',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Preparing response',
            created_at: '2026-04-20T00:00:02.000Z',
          },
        ],
      ),
    })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      yield turnCompleted('cancelled', {
        sequence: 3,
        conversation_id: 'conv-home-detail',
        run_id: 'run-home-detail',
      })
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(session?.runStatus).toBe('cancelled')
    expect(session?.isStreaming).toBe(false)
    expect(session?.messages[session.messages.length - 1]?.content).toContain('Preparing response')
  })

    it('applies a turn_completed(failed) SSE event immediately without waiting for a detail refresh', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'running',
          status: 'active',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Preparing response',
            created_at: '2026-04-20T00:00:02.000Z',
          },
        ],
      ),
    })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      yield turnCompleted('failed', {
        sequence: 3,
        conversation_id: 'conv-home-detail',
        run_id: 'run-home-detail',
        terminal_error: 'tool crashed',
        summary: 'tool crashed',
      })
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(session?.runStatus).toBe('failed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.messages.some((message) => message.content?.includes('Preparing response'))).toBe(true)
    expect(session?.messages[session.messages.length - 1]?.content).toContain('tool crashed')
  })

    it('marks a harness conversation cancelled and calls the backend cancel endpoint when stopping a run', async () => {
    const abortController = new AbortController()
    const eventStreamController = new AbortController()
    cancelHarnessConversationRunMock.mockResolvedValueOnce({
      data: {
        ...buildHarnessConversationDetail({
          runtime_status: 'cancelled',
          finished_at: '2026-04-20T00:11:00.000Z',
        }),
      },
    })

    useChatStore.setState({
      conversationId: 'conv-home-cancel',
      engineVersion: 'harness',
      isStreaming: true,
      conversationSessions: {
        'conv-home-cancel': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
  userInteraction: null,
          isStreaming: true,
          currentStreamText: 'drafting',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController,
          eventStreamController,
          lastSequence: 12,
          runStatus: 'running',
        },
      },
    })

    useChatStore.getState().stopStreaming()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(cancelHarnessConversationRunMock).toHaveBeenCalledWith('conv-home-cancel')
    expect(abortController.signal.aborted).toBe(true)
    expect(eventStreamController.signal.aborted).toBe(true)
    expect(useChatStore.getState().conversationSessions['conv-home-cancel']?.runStatus).toBe('cancelled')
    expect(useChatStore.getState().conversationSessions['conv-home-cancel']?.isStreaming).toBe(false)
  })

    it('keeps existing conversation content visible after cancelling a running harness conversation', async () => {
    const abortController = new AbortController()
    const eventStreamController = new AbortController()
    cancelHarnessConversationRunMock.mockResolvedValueOnce({
      data: {
        ...buildHarnessConversationDetail({
          id: 'conv-home-cancel-visible',
          runtime_status: 'cancelled',
          finished_at: '2026-04-20T00:11:00.000Z',
        }),
      },
    })

    useChatStore.setState({
      conversationId: 'conv-home-cancel-visible',
      engineVersion: 'harness',
      messages: [
        {
          id: 'assistant-existing-visible',
          role: 'assistant',
          content: 'Existing assistant output',
          createdAt: '2026-04-20T00:10:00.000Z',
        },
      ],
      isStreaming: true,
      conversationSessions: {
        'conv-home-cancel-visible': {
          messages: [
            {
              id: 'assistant-existing-visible',
              role: 'assistant',
              content: 'Existing assistant output',
              createdAt: '2026-04-20T00:10:00.000Z',
            },
          ],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
  userInteraction: null,
          isStreaming: true,
          currentStreamText: 'drafting',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController,
          eventStreamController,
          lastSequence: 12,
          runStatus: 'running',
        },
      },
    })

    useChatStore.getState().stopStreaming()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(useChatStore.getState().messages[0]?.content).toBe('Existing assistant output')
    expect(useChatStore.getState().conversationSessions['conv-home-cancel-visible']?.messages[0]?.content).toBe('Existing assistant output')
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

    it('keeps the homepage session cancelled when the cancel endpoint only acknowledges a healthy foreign owner request', async () => {
    const abortController = new AbortController()
    const eventStreamController = new AbortController()
    cancelHarnessConversationRunMock.mockResolvedValueOnce({
      data: {
        ...buildHarnessConversationDetail({
          id: 'conv-home-cancel-requested',
          runtime_status: 'running',
          run_state: 'executing',
          status: 'active',
          finished_at: null,
        }),
      },
    })

    useChatStore.setState({
      conversationId: 'conv-home-cancel-requested',
      engineVersion: 'harness',
      isStreaming: true,
      conversations: [
        {
          ...buildHarnessConversationDetail({
            id: 'conv-home-cancel-requested',
            runtime_status: 'running',
            run_state: 'executing',
            status: 'active',
          }),
        } as any,
      ],
      conversationSessions: {
        'conv-home-cancel-requested': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: true,
          currentStreamText: 'drafting',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController,
          eventStreamController,
          lastSequence: 12,
          runStatus: 'running',
        },
      },
    })

    useChatStore.getState().stopStreaming()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(useChatStore.getState().conversationSessions['conv-home-cancel-requested']?.runStatus).toBe('cancelled')
    expect(useChatStore.getState().conversationSessions['conv-home-cancel-requested']?.isStreaming).toBe(false)
    expect(useChatStore.getState().conversations[0]?.runtime_status).toBe('cancelled')
  })

    it('replays a cancelled harness conversation as cancelled without resubscribing to SSE', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'cancelled',
          finished_at: '2026-04-20T00:11:00.000Z',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Partial draft',
            created_at: '2026-04-20T00:00:06.000Z',
          },
        ],
      ),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversationSessions['conv-home-detail']?.runStatus).toBe('cancelled')
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

    it('replays a blocked harness conversation as blocked without resubscribing to SSE', async () => {
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'blocked',
          finished_at: '2026-04-20T00:11:00.000Z',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Blocked draft',
            created_at: '2026-04-20T00:00:06.000Z',
          },
        ],
      ),
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversationSessions['conv-home-detail']?.runStatus).toBe('blocked')
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

    it('lets a blocked server snapshot override a local live session', async () => {
    const staleAbortController = new AbortController()
    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          runtime_status: 'blocked',
          finished_at: '2026-04-20T00:11:00.000Z',
        },
        [
          {
            id: 'assistant-main',
            role: 'assistant',
            content: 'Blocked by server',
            created_at: '2026-04-20T00:00:06.000Z',
          },
        ],
      ),
    })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {})

    useChatStore.setState({
      engineVersion: 'harness',
      conversationId: 'conv-home-detail',
      conversationSessions: {
        'conv-home-detail': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: true,
          currentStreamText: 'still streaming',
          currentToolCalls: [],
          streamingBlocks: [{
            id: 'local-stream',
            kind: 'text',
            order: 0,
            status: 'running',
            visible: true,
            uiKind: 'assistant_text',
            payload: { text: 'local' },
          }],
          workspaceFiles: [],
          abortController: staleAbortController,
          eventStreamController: null,
          lastSequence: 165,
          runStatus: 'running',
        },
      },
    })

    await useChatStore.getState().loadConversation('conv-home-detail')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-home-detail']
    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    expect(session?.runStatus).toBe('blocked')
    expect(session?.isStreaming).toBe(false)
    expect(session?.streamingBlocks).toEqual([])
    expect(session?.currentStreamText).toBe('')
    expect(session?.abortController).toBeNull()
  })

    it('clears the send abort controller after projection finalizes a completed stream', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'message_done',
        data: {
          conversation_id: 'conv-home-send-finished',
        },
      }
      yield turnCompleted('completed', { conversation_id: 'conv-home-send-finished', run_id: 'run-home-send-finished' })
    })

    useChatStore.setState({
      conversationId: 'conv-home-send-finished',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-send-finished': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          runtimeState: null,
          userProgress: null,
  userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().sendMessage('hello')

    const session = useChatStore.getState().conversationSessions['conv-home-send-finished']
    expect(session?.abortController).toBeNull()
    expect(session?.isStreaming).toBe(false)
  })

    it('drains every server event through turn_completed without short-circuiting on a cleared abortController', async () => {
    const eventsDelivered: string[] = []

    streamHarnessSendMessageMock.mockImplementation(async function* () {
      const yieldEvent = async (event: any) => {
        eventsDelivered.push(event.type)
        return event
      }

      yield await yieldEvent({
        type: 'run_started',
        sequence: 22,
        run_id: 'run-2',
        data: {
          conversation_id: 'conv-home-second-send',
          run_state: 'executing',
          activity: 'answering',
        },
      })
      yield await yieldEvent(presentationDelta(24, 'assistant-second', '黑格尔', {
        run_id: 'run-2',
      }))
      yield await yieldEvent(presentationComplete(25, 'assistant-second', '黑格尔生平简述', {
        run_id: 'run-2',
      }))
      yield await yieldEvent({
        type: 'message_done',
        sequence: 26,
        run_id: 'run-2',
        data: { conversation_id: 'conv-home-second-send' },
      })
      yield await yieldEvent(turnCompleted('completed', {
        sequence: 27,
        conversation_id: 'conv-home-second-send',
        run_id: 'run-2',
      }))
    })

    getHarnessConversationMock.mockResolvedValue({
      data: buildHarnessConversationDetail({
        id: 'conv-home-second-send',
        runtime_status: 'completed',
        status: 'completed',
      }),
    })

    useChatStore.setState({
      conversationId: 'conv-home-second-send',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-second-send': {
          messages: [
            { id: 'u1', role: 'user', content: '第一次', createdAt: '2026-05-22T21:04:31.000Z' },
            { id: 'a1', role: 'assistant', content: '第一次回答', createdAt: '2026-05-22T21:04:33.000Z' },
          ],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 21,
          runStatus: 'completed',
        },
      },
    })

    await useChatStore.getState().sendMessage('第二次：搜索下黑格尔的生平')

    // The mock generator always finishes its body (yield does not throw on a
    // consumer break), so eventsDelivered counts what the mock generated, not
    // what the consumer saw. We assert the visible side-effects of each event
    // instead.
    expect(eventsDelivered).toEqual([
      'run_started',
      'presentation.block.delta',
      'presentation.block.complete',
      'message_done',
      'turn_completed',
    ])

    const session = useChatStore.getState().conversationSessions['conv-home-second-send']
    // The assistant message was projected before turn_completed.
    expect(session?.messages.some((m) => String(m.content).includes('黑格尔生平简述'))).toBe(true)
    // turn_completed sets runStatus=completed and the projection-to-session
    // adapter nulls abortController because isStreaming flipped to false.
    expect(session?.runStatus).toBe('completed')
    expect(session?.abortController).toBeNull()
    expect(session?.isStreaming).toBe(false)
    // Regression for hypothesis #1.
    //
    // The server emitted:
    //   run_started, presentation.block.delta,
    //   presentation.block.complete, message_done, turn_completed
    //
    // Pre-fix, a terminal event nulled session.abortController via
    // applyProjectionStateToSession's
    //   abortController: projection.isStreaming ? session.abortController : null
    // which caused the next iteration's
    //   if (!isActiveHarnessSend(get, conversationId, abortController)) break
    // to short-circuit, dropping the terminal event sequence.
    // never advanced past 27. With the projection no longer touching
    // abortController, the loop drains the full server stream.
    expect(session?.lastSequence).toBe(27)
  })

  it('also drains every server event on a first send from idle (regression mirror of the above)', async () => {
    // Counterpart to the previous test, starting from an idle session (no
    // prior run). Pre-fix this also dropped the terminal event; the
    // post-fix behavior must match — lastSequence reaches the highest
    // server sequence regardless of whether this is the first or Nth send.
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'run_started',
        sequence: 12,
        run_id: 'run-only',
        data: { conversation_id: 'conv-home-single-send', activity: 'answering' },
      }
      yield presentationDelta(14, 'assistant-only', '内', {
        run_id: 'run-only',
      })
      yield presentationComplete(15, 'assistant-only', '内容', {
        run_id: 'run-only',
      })
      yield {
        type: 'message_done',
        sequence: 16,
        run_id: 'run-only',
        data: { conversation_id: 'conv-home-single-send' },
      }
      yield turnCompleted('completed', {
        sequence: 17,
        conversation_id: 'conv-home-single-send',
        run_id: 'run-only',
      })
    })

    getHarnessConversationMock.mockResolvedValue({
      data: buildHarnessConversationDetail({
        id: 'conv-home-single-send',
        runtime_status: 'completed',
        status: 'completed',
      }),
    })

    useChatStore.setState({
      conversationId: 'conv-home-single-send',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-single-send': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().sendMessage('一条新消息')

    const session = useChatStore.getState().conversationSessions['conv-home-single-send']
    expect(session?.messages.some((m) => String(m.content).includes('内容'))).toBe(true)
    expect(session?.runStatus).toBe('completed')
    expect(session?.lastSequence).toBe(17)
  })

  it('applies turn_completed when a presentation patch shares the same sequence', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'run_started',
        sequence: 42,
        run_id: 'run-same-seq',
        data: { conversation_id: 'conv-home-same-seq', activity: 'executing' },
      }
      yield presentationComplete(43, 'assistant-same-seq', '最终回答', {
        run_id: 'run-same-seq',
      })
      yield presentationPatch(44, 'home-user-progress-card', {
        status: 'completed',
        payload: {
          status: 'completed',
          message: '已完成',
        },
      }, {
        run_id: 'run-same-seq',
        message_key: 'home-user-progress',
        status: 'completed',
      })
      yield turnCompleted('completed', {
        sequence: 44,
        conversation_id: 'conv-home-same-seq',
        run_id: 'run-same-seq',
      })
    })

    useChatStore.setState({
      conversationId: 'conv-home-same-seq',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-same-seq': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().sendMessage('开始')

    const session = useChatStore.getState().conversationSessions['conv-home-same-seq']
    expect(session?.messages.some((m) => String(m.content).includes('最终回答'))).toBe(true)
    expect(session?.runStatus).toBe('completed')
    expect(session?.isStreaming).toBe(false)
    expect(session?.lastSequence).toBe(44)
  })

  it('applies a replayed turn_completed when the cursor already reached a terminal text block with no source sequence', async () => {
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      yield turnCompleted('completed', {
        sequence: 94,
        conversation_id: 'conv-home-terminal-cursor',
        run_id: 'run-terminal-cursor',
      })
    })

    getHarnessConversationMock.mockResolvedValueOnce({
      data: buildHarnessConversationDetail(
        {
          id: 'conv-home-terminal-cursor',
          runtime_status: 'running',
          run_id: 'run-terminal-cursor',
          projection: {
            event_last_sequence: 94,
          },
        },
        [
          {
            id: 'assistant-terminal-cursor',
            role: 'assistant',
            content: '最终回答',
            created_at: '2026-06-07T18:47:02.000Z',
            blocks: [
              {
                id: 'assistant-terminal-text',
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                ui_kind: 'text',
                uiKind: 'text',
                content: '最终回答',
                payload: {
                  text: '最终回答',
                },
                revision: 0,
                source_sequence: 0,
              },
            ],
          },
        ],
      ),
    })

    useChatStore.setState({
      conversationId: 'conv-home-terminal-cursor',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {},
    })

    await useChatStore.getState().loadConversation('conv-home-terminal-cursor')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const session = useChatStore.getState().conversationSessions['conv-home-terminal-cursor']
    expect(session?.lastSequence).toBe(94)
    expect(session?.runStatus).toBe('completed')
    expect(session?.isStreaming).toBe(false)
  })

  it('applies realtime workspace file events that arrive after higher-sequence presentation ops', async () => {
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'run_started',
        sequence: 340,
        run_id: 'run-file-out-of-order',
        data: { conversation_id: 'conv-home-file-out-of-order', activity: 'executing' },
      }
      yield presentationComplete(343, 'assistant-file-out-of-order', '文件已准备好', {
        run_id: 'run-file-out-of-order',
      })
      yield {
        type: 'file_version_created',
        sequence: 341,
        run_id: 'run-file-out-of-order',
        lane: 'user',
        event_id: 19621,
        data: {
          file_id: 'f_8b40f57dbc',
          name: 'index.zip',
          path: 'published/f_8b40f57dbc/v0001/source.zip',
          type: 'web',
          size: 7958,
          current_version_id: 'v0001',
          artifact_kind: 'web_bundle',
          artifact_metadata: {
            artifact_kind: 'web_bundle',
            bundle_format: 'zip',
            entry: 'index.html',
          },
          versions: [
            {
              version_id: 'v0001',
              label: '版本 1',
              size: 7958,
              sha256: 'x',
              created_at: '2026-06-07T17:15:31.605301+00:00',
              created_by: 'agent',
              run_id: 'run-file-out-of-order',
              artifact_metadata: {
                artifact_kind: 'web_bundle',
                bundle_format: 'zip',
                entry: 'index.html',
              },
            },
          ],
        },
      }
      yield turnCompleted('completed', {
        sequence: 378,
        conversation_id: 'conv-home-file-out-of-order',
        run_id: 'run-file-out-of-order',
      })
    })

    useChatStore.setState({
      conversationId: 'conv-home-file-out-of-order',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-file-out-of-order': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          appliedPresentationOps: [],
          appliedRuntimeEvents: [],
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().sendMessage('开始')

    const session = useChatStore.getState().conversationSessions['conv-home-file-out-of-order']
    expect(session?.runStatus).toBe('completed')
    expect(session?.lastSequence).toBe(378)
    expect(session?.workspaceFiles).toEqual(expect.arrayContaining([
      expect.objectContaining({
        file_id: 'f_8b40f57dbc',
        name: 'index.zip',
        path: 'published/f_8b40f57dbc/v0001/source.zip',
        artifact_kind: 'web_bundle',
      }),
    ]))
  })

  it('refreshes workspace files after a completed home harness stream', async () => {
    const publishedFile = {
      file_id: 'f_published_bundle',
      name: 'index.zip',
      path: 'published/f_published_bundle/v0001/source.zip',
      type: 'web',
      size: 7958,
      current_version_id: 'v0001',
      current_version_path: 'published/f_published_bundle/v0001/source.zip',
      artifact_kind: 'web_bundle',
      artifact_metadata: {
        artifact_kind: 'web_bundle',
        bundle_format: 'zip',
        entry: 'index.html',
      },
      versions: [],
      source: 'generated',
      created_at: '2026-06-07T17:15:31.605301+00:00',
      updated_at: null,
    }
    listWorkspaceFilesMock.mockResolvedValue({ data: [publishedFile] })
    streamHarnessSendMessageMock.mockImplementation(async function* () {
      yield {
        type: 'run_started',
        sequence: 10,
        run_id: 'run-refresh-files',
        data: { conversation_id: 'conv-home-refresh-files', activity: 'executing' },
      }
      yield presentationComplete(
        20,
        'assistant-refresh-files',
        '文件已发布：`published/f_published_bundle/v0001/source.zip`',
        { run_id: 'run-refresh-files' },
      )
      yield turnCompleted('completed', {
        sequence: 30,
        conversation_id: 'conv-home-refresh-files',
        run_id: 'run-refresh-files',
      })
    })

    useChatStore.setState({
      conversationId: 'conv-home-refresh-files',
      engineVersion: 'harness',
      messages: [],
      isStreaming: false,
      conversationSessions: {
        'conv-home-refresh-files': {
          messages: [],
          activePlan: null,
          activeUserPlan: null,
          outlineRuntime: null,
          runtimeState: null,
          userProgress: null,
          userInteraction: null,
          isStreaming: false,
          currentStreamText: '',
          currentToolCalls: [],
          streamingBlocks: [],
          workspaceFiles: [],
          abortController: null,
          eventStreamController: null,
          lastSequence: 0,
          appliedPresentationOps: [],
          appliedRuntimeEvents: [],
          runStatus: 'idle',
        },
      },
    })

    await useChatStore.getState().sendMessage('开始')
    await new Promise((resolve) => setTimeout(resolve, 400))

    const session = useChatStore.getState().conversationSessions['conv-home-refresh-files']
    expect(listWorkspaceFilesMock).toHaveBeenCalledWith('conv-home-refresh-files')
    expect(session?.runStatus).toBe('completed')
    expect(session?.workspaceFiles).toEqual([publishedFile])
    expect(useChatStore.getState().workspaceFiles).toEqual([publishedFile])
  })
})

// Confirms the 409 active-run race (stop a run, then immediately trigger another
// streaming action) is recovered on every home streaming entry point — not just
// sendMessage — so the action is not silently dropped / left stuck on "thinking".
describe('homeHarnessStore stop-then-action recovery', () => {
  function settledDetail() {
    return buildHarnessConversationDetail({
      id: 'conv-home-stuck',
      runtime_status: 'idle',
      run_state: 'idle',
      status: 'active',
    })
  }

  function homeTurnCompleted(sequence: number) {
    return turnCompleted('completed', {
      conversation_id: 'conv-home-stuck',
      run_id: 'run-1',
      sequence,
    })
  }

  function conflictThenComplete(mock: ReturnType<typeof vi.fn>) {
    mock
      .mockImplementationOnce(async function* () {
        const err: any = new Error('Conversation already has an active run')
        err.status = 409
        throw err
      })
      .mockImplementationOnce(async function* () {
        yield homeTurnCompleted(6)
      })
  }

  // Seed an explicit session entry (not just top-level fields) so the scenario is
  // robust against state from earlier tests in the suite.
  function seedHomeSession(overrides: Partial<ReturnType<typeof createEmptyConversationSession>> = {}) {
    const session = { ...createEmptyConversationSession(), runStatus: 'cancelled' as const, ...overrides }
    useChatStore.setState({
      conversationId: 'conv-home-stuck',
      engineVersion: 'harness',
      runStatus: session.runStatus,
      isStreaming: session.isStreaming,
      userInteraction: session.userInteraction,
      outlineRuntime: session.outlineRuntime,
      activeUserPlan: session.activeUserPlan,
      conversationSessions: { 'conv-home-stuck': session },
    } as any)
  }

  it('respondToAgent recovers from a 409 and is not left stuck', async () => {
    getHarnessConversationMock.mockResolvedValue({ data: settledDetail() })
    conflictThenComplete(streamHarnessRespondToAgentMock)

    seedHomeSession({
      userInteraction: { request_id: 'req-1', question: 'Continue?', kind: 'ask_user', schema: null } as any,
    })

    try {
      await useChatStore.getState().respondToAgent('req-1', 'yes')
    } catch {
      // current (unfixed) code may reject; the fix swallows the recovered error
    }

    expect(streamHarnessRespondToAgentMock).toHaveBeenCalledTimes(2)
    expect(useChatStore.getState().conversationSessions['conv-home-stuck']?.isStreaming).toBe(false)
  })

  it('startExecution recovers from a 409 and is not left stuck', async () => {
    getHarnessConversationMock.mockResolvedValue({ data: settledDetail() })
    conflictThenComplete(streamHarnessStartExecutionMock)

    const outline = {
      title: 'Plan',
      sections: [{ id: 's1', title: 'Section 1' }],
      execution_state: { status: 'planning_ready' },
    }
    seedHomeSession({
      activeUserPlan: outline as any,
      outlineRuntime: { current_outline: outline, execution_state: { status: 'planning_ready' } } as any,
    })

    try {
      await useChatStore.getState().startExecution()
    } catch {
      // current (unfixed) code has no catch and rejects on 409
    }

    expect(streamHarnessStartExecutionMock).toHaveBeenCalledTimes(2)
    expect(useChatStore.getState().conversationSessions['conv-home-stuck']?.isStreaming).toBe(false)
  })

  it('revisePlan recovers from a 409 and is not left stuck', async () => {
    getHarnessConversationMock.mockResolvedValue({ data: settledDetail() })
    conflictThenComplete(streamHarnessRevisePlanMock)

    seedHomeSession()

    try {
      await useChatStore.getState().revisePlan('改一下第一节')
    } catch {
      // current (unfixed) code has no catch and rejects on 409
    }

    expect(streamHarnessRevisePlanMock).toHaveBeenCalledTimes(2)
    expect(useChatStore.getState().conversationSessions['conv-home-stuck']?.isStreaming).toBe(false)
  })
})
