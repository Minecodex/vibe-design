import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createEmptyConversationSession } from './canvasAgentSession'

const getHarnessConversationMock = vi.fn()
const cancelHarnessConversationRunMock = vi.fn()
const listWorkspaceFilesMock = vi.fn()
const streamHarnessSendMessageMock = vi.fn()
const streamHarnessRespondToAgentMock = vi.fn()
const streamHarnessConversationEventsMock = vi.fn()

vi.mock('@/api/endpoints/agent', async () => {
  return {
    agentApi: {
      getHarnessConversation: getHarnessConversationMock,
      cancelHarnessConversationRun: cancelHarnessConversationRunMock,
      listWorkspaceFiles: listWorkspaceFilesMock,
      listHarnessConversations: vi.fn(),
      listConversations: vi.fn(),
      getConversation: vi.fn(),
      deleteHarnessConversation: vi.fn(),
      createConversation: vi.fn(),
      createHarnessConversation: vi.fn(),
    },
    streamSendMessage: vi.fn(),
    streamApprovePlan: vi.fn(),
    streamRespondToAgent: vi.fn(),
    streamHarnessRespondToAgent: streamHarnessRespondToAgentMock,
    streamHarnessSendMessage: streamHarnessSendMessageMock,
    streamHarnessConversationEvents: streamHarnessConversationEventsMock,
  }
})

vi.mock('@/i18n', () => ({
  default: {
    language: 'zh-CN',
    t: (key: string) => key,
  },
}))

vi.mock('./homeHarnessProjection', () => ({
  finalizeHomeHarnessProjection: vi.fn(() => null),
}))

function conversationDetail(runtimeStatus: string, runState: string) {
  return {
    id: 'conv-canvas-stuck',
    title: '会话',
    skill_id: 'design_workflow',
    runtime_profile: 'canvas',
    project_id: 88,
    phase: 'executing',
    mode: 'fast',
    web_search_enabled: false,
    status: 'active',
    runtime_status: runtimeStatus,
    run_state: runState,
    engine_version: 'harness',
    run_id: 'run-1',
    started_at: '2026-06-16T00:00:00.000Z',
    finished_at: null,
    created_at: '2026-06-16T00:00:00.000Z',
    updated_at: '2026-06-16T00:00:00.000Z',
  }
}

function turnCompletedEvent(sequence: number) {
  return {
    type: 'turn_completed',
    sequence,
    lane: 'user',
    data: {
      status: 'completed',
      error: null,
      completed_at: '2026-06-16T00:00:01.000Z',
    },
  } as any
}

function seedActiveStreamingConversation(useChatStore: any) {
  const session = {
    ...createEmptyConversationSession(),
    runStatus: 'running',
    isStreaming: true,
    abortController: new AbortController(),
    eventStreamController: new AbortController(),
    lastSequence: 5,
    messages: [
      { id: 'u-1', role: 'user', content: '画一个 logo', createdAt: '2026-06-16T00:00:00.000Z' },
    ],
  }
  useChatStore.setState({
    conversationId: 'conv-canvas-stuck',
    projectId: 88,
    mode: 'fast',
    activeSkillId: 'design_workflow',
    modelPreferences: { auto: false },
    webSearchEnabled: false,
    messages: session.messages,
    isStreaming: true,
    conversations: [
      {
        id: 'conv-canvas-stuck',
        title: '会话',
        skill_id: 'design_workflow',
        phase: 'executing',
        mode: 'fast',
        web_search_enabled: false,
        status: 'active',
        runtime_status: 'running',
        run_state: 'running',
        engine_version: 'harness',
        run_id: 'run-1',
        started_at: '2026-06-16T00:00:00.000Z',
        finished_at: null,
        created_at: '2026-06-16T00:00:00.000Z',
        updated_at: '2026-06-16T00:00:00.000Z',
      },
    ],
    conversationSessions: {
      'conv-canvas-stuck': session,
    },
  } as any)
}

function seedDetachedConversation(
  useChatStore: any,
  options: { lastSequence: number; pendingInteraction?: Record<string, any> | null },
) {
  const session = {
    ...createEmptyConversationSession(),
    runStatus: options.pendingInteraction ? 'waiting_input' : 'idle',
    lastSequence: options.lastSequence,
    pendingInteraction: options.pendingInteraction || null,
  }
  useChatStore.setState({
    conversationId: 'conv-canvas-stuck',
    projectId: 88,
    mode: 'fast',
    activeSkillId: 'design_workflow',
    modelPreferences: { auto: false },
    webSearchEnabled: false,
    messages: [],
    pendingInteraction: session.pendingInteraction,
    isStreaming: false,
    conversations: [conversationDetail('idle', 'idle')],
    conversationSessions: {
      'conv-canvas-stuck': session,
    },
  } as any)
}

describe('canvasAgentStore stop-then-send', () => {
  beforeEach(() => {
    getHarnessConversationMock.mockReset()
    cancelHarnessConversationRunMock.mockReset()
    listWorkspaceFilesMock.mockReset()
    streamHarnessSendMessageMock.mockReset()
    streamHarnessRespondToAgentMock.mockReset()
    streamHarnessConversationEventsMock.mockReset()
    listWorkspaceFilesMock.mockResolvedValue({ data: [] })
    streamHarnessConversationEventsMock.mockImplementation(async function* () {})
    cancelHarnessConversationRunMock.mockResolvedValue({
      data: conversationDetail('cancelling', 'cancelling'),
    })
  })

  afterEach(async () => {
    const { useChatStore } = await import('./canvasAgentStore')
    useChatStore.getState().reset()
  })

  // The original bug: clicking "stop" then immediately re-submitting raced the
  // backend run teardown, hit a 409 active-run guard, and left the UI pinned on
  // "thinking…" until a page refresh. The fix detects the 409, waits for the prior
  // run to settle (run_state leaves 'cancelling'), and retries the send once.
  it('retries after the cancelling run settles so the resend succeeds without getting stuck', async () => {
    // Backend is still tearing the cancelled run down on the first poll, then settles.
    getHarnessConversationMock
      .mockResolvedValueOnce({ data: conversationDetail('cancelled', 'cancelling') })
      .mockResolvedValue({ data: conversationDetail('cancelled', 'cancelled') })
    // First send is rejected by the active-run guard (409); the retry succeeds.
    streamHarnessSendMessageMock
      .mockImplementationOnce(async function* () {

        const err: any = new Error('Conversation already has an active run')
        err.status = 409
        yield* [] // This fixture intentionally emits no events.
        throw err
      })
      .mockImplementationOnce(async function* () {
        yield turnCompletedEvent(6)
      })

    const { useChatStore } = await import('./canvasAgentStore')
    seedActiveStreamingConversation(useChatStore)

    // 1) User stops the in-flight run.
    useChatStore.getState().stopStreaming()
    expect(useChatStore.getState().isStreaming).toBe(false)

    // 2) User immediately submits a new prompt; first attempt 409s, retry succeeds.
    await useChatStore.getState().sendMessage('再画一个')

    // We polled for settlement after the 409 and retried the send.
    expect(getHarnessConversationMock.mock.calls.length).toBeGreaterThanOrEqual(1)
    expect(streamHarnessSendMessageMock).toHaveBeenCalledTimes(2)

    const state = useChatStore.getState()
    expect(state.messages.some((m) => m.role === 'user' && m.content === '再画一个')).toBe(true)
    // The spinner settles instead of being stuck on "thinking".
    expect(state.isStreaming).toBe(false)
  })

  // Safety net: even if the send still fails after settling, the UI must not stay
  // stuck on "thinking" — isStreaming has to fall back to false so the user can retry.
  it('does not stay stuck on thinking if the resend still fails', async () => {
    getHarnessConversationMock.mockResolvedValue({ data: conversationDetail('idle', 'idle') })
    streamHarnessSendMessageMock.mockImplementation(async function* () {

      yield* [] // This fixture intentionally emits no events.
      throw new Error('Conversation already has an active run')
    })

    const { useChatStore } = await import('./canvasAgentStore')
    seedActiveStreamingConversation(useChatStore)

    useChatStore.getState().stopStreaming()
    await useChatStore.getState().sendMessage('再画一个')

    const state = useChatStore.getState()
    expect(state.messages.some((m) => m.role === 'user' && m.content === '再画一个')).toBe(true)
    expect(state.isStreaming).toBe(false)
  })

  // The same 409 race applies to answering an interaction card right after stop.
  it('respondToAgent recovers from a 409 and does not stay stuck on thinking', async () => {
    getHarnessConversationMock.mockResolvedValue({
      data: conversationDetail('cancelled', 'cancelled'),
    })
    streamHarnessRespondToAgentMock
      .mockImplementationOnce(async function* () {

        const err: any = new Error('Conversation already has an active run')
        err.status = 409
        yield* [] // This fixture intentionally emits no events.
        throw err
      })
      .mockImplementationOnce(async function* () {
        yield turnCompletedEvent(6)
      })

    const { useChatStore } = await import('./canvasAgentStore')
    seedActiveStreamingConversation(useChatStore)
    useChatStore.setState({
      pendingInteraction: { request_id: 'req-1', question: '继续？', kind: 'ask_user', schema: null },
    })

    useChatStore.getState().stopStreaming()
    await useChatStore.getState().respondToAgent('req-1', 'confirm', '确认')

    expect(streamHarnessRespondToAgentMock).toHaveBeenCalledTimes(2)
    expect(useChatStore.getState().isStreaming).toBe(false)
  })

  it('resumes a detached send through GET stream from the durable sequence without reposting', async () => {
    getHarnessConversationMock.mockResolvedValue({
      data: conversationDetail('running', 'running'),
    })
    streamHarnessSendMessageMock.mockImplementation(async function* () {})
    let releaseStream!: () => void
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
      yield turnCompletedEvent(6)
    })

    const { useChatStore } = await import('./canvasAgentStore')
    seedDetachedConversation(useChatStore, { lastSequence: 5 })

    await useChatStore.getState().sendMessage('继续生成')

    await vi.waitFor(() => {
      expect(streamHarnessConversationEventsMock).toHaveBeenCalledWith(
        'conv-canvas-stuck',
        5,
        expect.any(AbortSignal),
      )
    })
    expect(streamHarnessSendMessageMock).toHaveBeenCalledTimes(1)
    expect(getHarnessConversationMock).toHaveBeenCalledTimes(1)
    const resumedSession = useChatStore.getState().conversationSessions['conv-canvas-stuck']
    expect(resumedSession?.abortController).toBeNull()
    expect(resumedSession?.eventStreamController).toBeInstanceOf(AbortController)
    expect(resumedSession?.isStreaming).toBe(true)

    releaseStream()
    await vi.waitFor(() => {
      const completedSession = useChatStore.getState().conversationSessions['conv-canvas-stuck']
      expect(completedSession?.runStatus).toBe('completed')
      expect(completedSession?.eventStreamController).toBeNull()
    })
  })

  it('resumes a detached interaction response through GET stream without reposting', async () => {
    const pendingInteraction = {
      request_id: 'req-resume',
      question: '继续？',
      kind: 'ask_user',
      schema: null,
    }
    getHarnessConversationMock.mockResolvedValue({
      data: conversationDetail('running', 'running'),
    })
    streamHarnessRespondToAgentMock.mockImplementation(async function* () {})
    let releaseStream!: () => void
    streamHarnessConversationEventsMock.mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
      yield turnCompletedEvent(12)
    })

    const { useChatStore } = await import('./canvasAgentStore')
    seedDetachedConversation(useChatStore, {
      lastSequence: 11,
      pendingInteraction,
    })

    await useChatStore.getState().respondToAgent('req-resume', 'confirm', '确认')

    await vi.waitFor(() => {
      expect(streamHarnessConversationEventsMock).toHaveBeenCalledWith(
        'conv-canvas-stuck',
        11,
        expect.any(AbortSignal),
      )
    })
    expect(streamHarnessRespondToAgentMock).toHaveBeenCalledTimes(1)
    expect(getHarnessConversationMock).toHaveBeenCalledTimes(1)
    const resumedSession = useChatStore.getState().conversationSessions['conv-canvas-stuck']
    expect(resumedSession?.abortController).toBeNull()
    expect(resumedSession?.eventStreamController).toBeInstanceOf(AbortController)
    expect(resumedSession?.isStreaming).toBe(true)

    releaseStream()
    await vi.waitFor(() => {
      const completedSession = useChatStore.getState().conversationSessions['conv-canvas-stuck']
      expect(completedSession?.runStatus).toBe('completed')
      expect(completedSession?.eventStreamController).toBeNull()
    })
  })

  it('reuses an existing GET stream controller instead of creating a duplicate subscription', async () => {
    getHarnessConversationMock.mockResolvedValue({
      data: conversationDetail('running', 'running'),
    })
    streamHarnessSendMessageMock.mockImplementation(async function* () {})

    const { useChatStore } = await import('./canvasAgentStore')
    seedDetachedConversation(useChatStore, { lastSequence: 5 })
    const existingController = new AbortController()
    useChatStore.setState((state) => ({
      conversationSessions: {
        ...state.conversationSessions,
        'conv-canvas-stuck': {
          ...state.conversationSessions['conv-canvas-stuck'],
          eventStreamController: existingController,
        },
      },
    }))

    await useChatStore.getState().sendMessage('继续生成')

    expect(streamHarnessSendMessageMock).toHaveBeenCalledTimes(1)
    expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    expect(useChatStore.getState().conversationSessions['conv-canvas-stuck']?.eventStreamController).toBe(existingController)
  })

  it.each(['running', 'waiting_input'])(
    'keeps a stopped command cancelled when its %s snapshot resolves after the stop',
    async (snapshotStatus) => {
      let resolveSnapshot!: (value: { data: ReturnType<typeof conversationDetail> }) => void
      getHarnessConversationMock.mockImplementationOnce(() => new Promise((resolve) => {
        resolveSnapshot = resolve
      }))
      streamHarnessSendMessageMock.mockImplementation(async function* () {})

      const { useChatStore } = await import('./canvasAgentStore')
      seedDetachedConversation(useChatStore, { lastSequence: 5 })

      const sendPromise = useChatStore.getState().sendMessage('继续生成')
      await vi.waitFor(() => {
        expect(getHarnessConversationMock).toHaveBeenCalledTimes(1)
      })

      useChatStore.getState().stopStreaming()
      resolveSnapshot({ data: conversationDetail(snapshotStatus, snapshotStatus) })
      await sendPromise

      const state = useChatStore.getState()
      const session = state.conversationSessions['conv-canvas-stuck']
      expect(session?.runStatus).toBe('cancelled')
      expect(session?.isStreaming).toBe(false)
      expect(session?.abortController).toBeNull()
      expect(session?.eventStreamController).toBeNull()
      expect(state.conversations[0]?.runtime_status).toBe('cancelled')
      expect(streamHarnessConversationEventsMock).not.toHaveBeenCalled()
    },
  )
})
