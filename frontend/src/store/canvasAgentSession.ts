import type {
    AgentUiConfigRead,
    PendingInteraction,
    PlanRead,
    WorkspaceFileRead,
} from '@/api/endpoints/agent'
import type { CanvasGenerationProjectionSession } from './canvasGenerationProjection'
import {
    createGenerationProjectionState,
    type GenerationProjectionState,
} from './generationProjection'
import {
    EMPTY_MESSAGE_BLOCKS,
    FALLBACK_CANVAS_DEFAULT_SKILL_ID,
    FALLBACK_CANVAS_EXPLICIT_SKILL_IDS,
    normalizeCanvasSkillIdAlias,
    type ChatMessage,
    type ConversationRunStatus,
    type MessageBlock,
    type ToolCallInfo,
} from './canvasAgentTypes'
import type { ChatState } from './canvasAgentStore'

export interface ConversationSessionState extends CanvasGenerationProjectionSession {
    messages: ChatMessage[]
    activePlan: PlanRead | null
    pendingInteraction: PendingInteraction | null
    runStatus: ConversationRunStatus
    isStreaming: boolean
    currentStreamText: string
    currentToolCalls: ToolCallInfo[]
    streamingBlocks: MessageBlock[]
    workspaceFiles: WorkspaceFileRead[]
    abortController: AbortController | null
    eventStreamController: AbortController | null
    lastSequence: number
    appliedPresentationOps?: string[]
    generationProjection: GenerationProjectionState
    // Cursor for the "load older messages" pagination (mirrors the home agent). When the
    // initial snapshot only returns a recent window, `hasMore`/`oldestSeq` drive scroll-up
    // loading via listHarnessConversationMessages.
    messagesPage?: {
        hasMore: boolean
        oldestSeq: number | null
        loading: boolean
    }
}

export const conversationListRequests = new Map<string, Promise<void>>()

const DEFAULT_CONVERSATION_TITLES = new Set([
    '',
    'New Chat',
    '新会话',
    'Untitled',
])

export function normalizeToolName(name: string | null | undefined): string {
    return String(name || '')
}

export function shouldReplaceConversationTitle(title: string | null | undefined): boolean {
    const normalizedTitle = String(title || '').trim()
    return DEFAULT_CONVERSATION_TITLES.has(normalizedTitle)
}

export function summarizeConversationTitle(content: string): string {
    return content.trim().replace(/\s+/g, ' ').slice(0, 80)
}

export function createEmptyConversationSession(): ConversationSessionState {
    return {
        messages: [],
        activePlan: null,
        pendingInteraction: null,
        runStatus: 'idle',
        isStreaming: false,
        currentStreamText: '',
        currentToolCalls: [],
        streamingBlocks: EMPTY_MESSAGE_BLOCKS,
        workspaceFiles: [],
        abortController: null,
        eventStreamController: null,
        lastSequence: 0,
        appliedPresentationOps: [],
        generationProjection: createGenerationProjectionState(),
        messagesPage: defaultMessagesPage(),
    }
}

export function defaultMessagesPage(): NonNullable<ConversationSessionState['messagesPage']> {
    return {
        hasMore: false,
        oldestSeq: null,
        loading: false,
    }
}

export function getMessagesPage(session: ConversationSessionState): NonNullable<ConversationSessionState['messagesPage']> {
    return session.messagesPage ?? defaultMessagesPage()
}

export function getConversationSessionKey(conversationId: number | string): string {
    return String(conversationId)
}

export function isSameConversationId(
    left: number | string | null | undefined,
    right: number | string | null | undefined,
): boolean {
    if (left == null || right == null) {
        return false
    }
    return getConversationSessionKey(left) === getConversationSessionKey(right)
}

export function getConversationSession(
    state: ChatState,
    conversationId: number | string,
): ConversationSessionState {
    const existing = state.conversationSessions[getConversationSessionKey(conversationId)]
    if (existing) {
        return existing
    }
    if (isSameConversationId(state.conversationId, conversationId)) {
        return {
            messages: state.messages,
            activePlan: state.activePlan,
            pendingInteraction: state.pendingInteraction,
            runStatus: 'idle',
            isStreaming: state.isStreaming,
            currentStreamText: state.currentStreamText,
            currentToolCalls: state.currentToolCalls,
            streamingBlocks: state.streamingBlocks,
            workspaceFiles: state.workspaceFiles,
            abortController: state._abortController,
            eventStreamController: null,
            lastSequence: 0,
            appliedPresentationOps: [],
            generationProjection: createGenerationProjectionState(),
        }
    }
    return createEmptyConversationSession()
}

export function buildActiveConversationFields(
    session: ConversationSessionState,
): Pick<ChatState, 'messages' | 'activePlan' | 'pendingInteraction' | 'isStreaming' | 'currentStreamText' | 'currentToolCalls' | 'streamingBlocks' | 'workspaceFiles' | '_abortController'> {
    return {
        messages: session.messages,
        activePlan: session.activePlan,
        pendingInteraction: session.pendingInteraction,
        isStreaming: session.isStreaming,
        currentStreamText: session.currentStreamText,
        currentToolCalls: session.currentToolCalls,
        streamingBlocks: session.streamingBlocks,
        workspaceFiles: session.workspaceFiles,
        _abortController: session.abortController,
    }
}

function areConversationSessionsShallowEqual(
    left: ConversationSessionState,
    right: ConversationSessionState,
): boolean {
    if (left === right) {
        return true
    }

    const leftKeys = Object.keys(left) as Array<keyof ConversationSessionState>
    const rightKeys = Object.keys(right) as Array<keyof ConversationSessionState>
    if (leftKeys.length !== rightKeys.length) {
        return false
    }

    return leftKeys.every((key) => Object.is(left[key], right[key]))
}

function activeConversationFieldsMatch(
    state: ChatState,
    session: ConversationSessionState,
): boolean {
    return state.messages === session.messages
        && state.activePlan === session.activePlan
        && state.pendingInteraction === session.pendingInteraction
        && state.isStreaming === session.isStreaming
        && state.currentStreamText === session.currentStreamText
        && state.currentToolCalls === session.currentToolCalls
        && state.streamingBlocks === session.streamingBlocks
        && state.workspaceFiles === session.workspaceFiles
        && state._abortController === session.abortController
}

export function mergeChatStatePatches(
    state: ChatState,
    ...patches: Partial<ChatState>[]
): Partial<ChatState> {
    let didChange = false
    const merged: Partial<ChatState> = {}

    patches.forEach((patch) => {
        if (patch === state) {
            return
        }
        Object.entries(patch).forEach(([key, value]) => {
            const stateKey = key as keyof ChatState
            if (Object.is(state[stateKey], value)) {
                return
            }
            didChange = true
            ;(merged as Record<string, unknown>)[key] = value
        })
    })

    return didChange ? merged : state
}

export function applyConversationSessionUpdate(
    state: ChatState,
    conversationId: number | string,
    updater: (session: ConversationSessionState) => ConversationSessionState,
): Partial<ChatState> {
    const sessionKey = getConversationSessionKey(conversationId)
    const currentSession = getConversationSession(state, conversationId)
    const nextSession = updater(currentSession)
    const isActiveConversation = isSameConversationId(state.conversationId, conversationId)
    const hasStoredSession = state.conversationSessions[sessionKey] != null

    if (
        hasStoredSession
        && areConversationSessionsShallowEqual(currentSession, nextSession)
        && (!isActiveConversation || activeConversationFieldsMatch(state, nextSession))
    ) {
        return state
    }

    const conversationSessions = {
        ...state.conversationSessions,
        [sessionKey]: nextSession,
    }
    return {
        conversationSessions,
        ...(isActiveConversation
            ? buildActiveConversationFields(nextSession)
            : {}),
    }
}

export function normalizeHiddenToolCalls(config: AgentUiConfigRead): string[] {
    return Array.from(
        new Set(
            (config.hidden_tool_calls || [])
                .map(normalizeToolName)
                .filter(Boolean),
        ),
    )
}

export function normalizeCanvasDefaultSkillId(config: AgentUiConfigRead): string {
    return String(config.canvas_default_skill_id || FALLBACK_CANVAS_DEFAULT_SKILL_ID).trim()
        || FALLBACK_CANVAS_DEFAULT_SKILL_ID
}

export function normalizeCanvasExplicitSkillIds(config: AgentUiConfigRead): string[] {
    const defaultSkillId = normalizeCanvasDefaultSkillId(config)
    return Array.from(
        new Set(
            (config.canvas_explicit_skill_ids || FALLBACK_CANVAS_EXPLICIT_SKILL_IDS)
                .map(normalizeCanvasSkillIdAlias)
                .filter(skillId => skillId && skillId !== defaultSkillId),
        ),
    )
}
