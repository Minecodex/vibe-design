import type { HarnessSkillRead } from '@/api/endpoints/agent'
import type { HomeHarnessProjectionState } from './homeHarnessProjection'
import type { MediaGenerationSettings } from '@/types/modelPreferences'

// ── Types ──────────────────────────────────────────────────────

export interface ChatMessage {
    id: number | string
    role: 'user' | 'assistant' | 'tool'
    content: string | null
    attachments?: Record<string, unknown>[]
    toolCalls?: ToolCallInfo[]
    blocks?: MessageBlock[]
    skillId?: string | null
    isHistoryLoaded?: boolean
    metadata?: Record<string, unknown> | null
    createdAt: string
}

export interface HarnessMessageLike {
    id?: string | number | null
    role: string
    content?: string | null
    blocks?: Record<string, unknown>[] | null
    attachments?: Record<string, unknown>[] | null
    metadata?: Record<string, unknown> | null
    created_at?: string | null
    tool_call_id?: string | null
    tool_name?: string | null
}

export interface MessageBlock {
    id: string
    kind: 'text' | 'tool' | 'interaction' | 'content'
    order: number
    status: string
    visible: boolean
    uiKind: string
    payload: Record<string, unknown>
    renderKey?: string
    messageId?: string
    taskId?: string
    label?: string
    summary?: string
    expanded?: boolean
    children?: MessageBlock[]
    revision?: number
    sourceSequence?: number
}

export interface ToolCallInfo {
    callId: string
    name: string
    args: Record<string, unknown>
    result?: Record<string, unknown>
    error?: string
    status: 'pending' | 'running' | 'completed' | 'failed'
    /** Incremental streaming text for tools that support streaming (e.g., image analysis) */
    streamingText?: string
}

export type ConversationRunStatus = HomeHarnessProjectionState['runStatus']

export interface ModelPreferences {
    image_model?: string
    image_provider?: string
    video_model?: string
    video_provider?: string
    multimodal_model?: string
    multimodal_provider?: string
    media_generation_settings?: MediaGenerationSettings
    auto?: boolean
}

export interface ChatUiConfig {
    hiddenToolCalls: string[]
    canvasDefaultSkillId?: string
    canvasExplicitSkillIds?: string[]
    canvasSkills?: HarnessSkillRead[]
}

export const EMPTY_MESSAGE_BLOCKS: MessageBlock[] = []

export const FALLBACK_CANVAS_DEFAULT_SKILL_ID = 'design_workflow'
export const CANVAS_MENSWEAR_ECOMMERCE_HERO_SKILL_ID = 'menswear-ecommerce-hero'
export const LEGACY_CANVAS_PRODUCT_HERO_SKILL_ID = 'product-hero'
export const FALLBACK_CANVAS_EXPLICIT_SKILL_IDS = ['brand_strategy_architect', 'logo', CANVAS_MENSWEAR_ECOMMERCE_HERO_SKILL_ID, 'vi-design-guide']

export function normalizeCanvasSkillIdAlias(skillId: unknown): string {
    const normalized = String(skillId || '').trim()
    return normalized === LEGACY_CANVAS_PRODUCT_HERO_SKILL_ID
        ? CANVAS_MENSWEAR_ECOMMERCE_HERO_SKILL_ID
        : normalized
}

export function resolveCanvasSkillPolicy(config?: Partial<ChatUiConfig> | null): { defaultSkillId: string; explicitSkillIds: Set<string> } {
    const defaultSkillId = String(config?.canvasDefaultSkillId || FALLBACK_CANVAS_DEFAULT_SKILL_ID).trim()
        || FALLBACK_CANVAS_DEFAULT_SKILL_ID
    const explicitSkillIds = new Set(
            (config?.canvasExplicitSkillIds?.length ? config.canvasExplicitSkillIds : FALLBACK_CANVAS_EXPLICIT_SKILL_IDS)
            .map(normalizeCanvasSkillIdAlias)
            .filter(Boolean),
    )
    explicitSkillIds.delete(defaultSkillId)
    return { defaultSkillId, explicitSkillIds }
}

export function normalizeCanvasSelectedSkillId(
    skillId: string | null | undefined,
    config?: Partial<ChatUiConfig> | null,
): string | null {
    const normalized = normalizeCanvasSkillIdAlias(skillId)
    const { defaultSkillId, explicitSkillIds } = resolveCanvasSkillPolicy(config)
    if (!normalized || normalized === defaultSkillId) {
        return null
    }
    return explicitSkillIds.has(normalized) ? normalized : null
}

export function normalizeCanvasResolvedSkillId(
    skillId: string | null | undefined,
    config?: Partial<ChatUiConfig> | null,
): string | null {
    const normalized = normalizeCanvasSkillIdAlias(skillId)
    if (!normalized) {
        return null
    }
    const { defaultSkillId, explicitSkillIds } = resolveCanvasSkillPolicy(config)
    if (normalized === defaultSkillId || explicitSkillIds.has(normalized)) {
        return normalized
    }
    return null
}

export function resolveCanvasRequestSkillId(
    skillId: string | null | undefined,
    config?: Partial<ChatUiConfig> | null,
): string | null {
    return normalizeCanvasSelectedSkillId(skillId, config)
}

export function shouldOmitCanvasReplayMessage(message: HarnessMessageLike): boolean {
    const metadata = (message.metadata || {}) as Record<string, unknown>
    const messageKind = String(metadata.message_kind || '').trim()
    const renderKind = String(metadata.render_kind || '').trim()
    const isPresentationSnapshot = renderKind === 'presentation_v2'
    if (
        metadata.exclude_from_history === true
        || (!isPresentationSnapshot && metadata.ui_visible === false && metadata.model_visible !== false)
        || (!isPresentationSnapshot && (
            messageKind === 'agent_context'
            || messageKind.startsWith('internal_')
        ))
    ) {
        return true
    }

    if (message.role !== 'assistant') {
        return false
    }

    const source = String(metadata.source || '').trim()
    const selectedSkillId = String(metadata.selected_skill_id || '').trim()

    return (
        source === 'auto_selection_announcement'
        && selectedSkillId === FALLBACK_CANVAS_DEFAULT_SKILL_ID
    )
}

export function resolvePersistedCanvasMessageSkillId(metadata: Record<string, unknown> | null | undefined): string | null {
    if (!metadata || typeof metadata !== 'object') {
        return null
    }

    const skillId = normalizeCanvasSkillIdAlias(
        metadata.skill_id
        ?? metadata.skillId
        ?? metadata.selected_skill_id
        ?? metadata.selectedSkillId
        ?? metadata.resolved_skill_id
        ?? metadata.resolvedSkillId
        ?? '',
    )

    return skillId || null
}
