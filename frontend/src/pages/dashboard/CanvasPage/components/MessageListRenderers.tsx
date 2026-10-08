import { Loader2, CheckCircle2, XCircle, Wrench, Copy, Check, Film, Image as ImageIcon, ChevronDown, Sparkles } from 'lucide-react'
import * as React from 'react'
import type { TFunction } from 'i18next'
import { useIsDarkMode } from '@/hooks/useTheme'
import { useTranslation } from 'react-i18next'
import { useChatStore, type ChatMessage, type MessageBlock, type ToolCallInfo } from '@/store/canvasAgentStore'
import {
    createPresentationRendererRegistry,
    normalizePresentationUiKind,
    registerDefaultPresentationRenderers,
    type PresentationBlockRenderer,
} from '@/store/harnessMessageProjection/rendererRegistry'
import { normalizeHarnessWorkspacePath, type PendingInteraction } from '@/api/endpoints/agent'
import {
    EcommerceInteractionCard,
    type EcommerceReferenceImageRequestOptions,
    type EcommerceReferenceImageSource,
} from '@/components/agent/EcommerceInteractionCard'
import { isEcommerceInteractionKind } from '@/components/agent/ecommerceInteractionKinds'
import { dedupeEcommerceInteractionBlocks } from '@/components/agent/ecommerceInteractionDedupe'
import { type CanvasItem } from '@/api/endpoints/projects'
import { getLocalizedSubagentPurpose } from '@/utils/subagentDisplayLabels'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { GenerationArtifactReferenceChip } from '../../HomeHarnessAgent/components/GenerationArtifactReferenceChip'
import {
    createGenerationArtifactReferenceRemarkPlugin,
    decodeGenerationArtifactReferenceHref,
    GENERATION_ARTIFACT_REFERENCE_SCHEME,
    normalizeGenerationArtifactRef,
} from '../../HomeHarnessAgent/components/generationArtifactMarkdownReferences'
import {
    CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME,
    createCanvasWorkspaceFileReferenceRemarkPlugin,
    decodeCanvasWorkspaceFileReferenceHref,
    normalizeWorkspaceMediaReference,
} from '../canvasWorkspaceFileReferences'
import { CHAT_SKILL_META } from '../chatSkills'
import { getForwardSelectableEntries } from '../chatForwardSelection'
import { CanvasWebSearchCard } from '../WebSearchCard'
import { InteractionCard } from '../InteractionCard'
import { ChatAttachmentStrip } from './ChatAttachmentStrip'
import { CanvasMarkdownImage } from './CanvasMarkdownImage'
import { CanvasWorkspaceMediaReferenceChip } from './CanvasWorkspaceMediaReferenceChip'
import { GenerationTaskBox } from './GenerationTaskBox'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'
import { isAgentBlockTerminal, isAgentHeavyBlock } from '../../agentMedia/agentRenderWeight'
import { ensureFullUrl } from './messageMediaUrl'
import {
    CANVAS_MARK_TOKEN_PATTERN,
    CANVAS_MENTION_TOKEN_PATTERN,
    parseCanvasMarkToken,
    parseCanvasMentionToken,
} from '../canvasReferenceTokens'

export { ensureFullUrl } from './messageMediaUrl'

function normalizeMarkdownRenderUrl(url: string): string {
    const raw = String(url || '').trim()
    if (!raw) {
        return ''
    }

    if (
        raw.startsWith(GENERATION_ARTIFACT_REFERENCE_SCHEME)
        || raw.startsWith(CANVAS_WORKSPACE_FILE_REFERENCE_SCHEME)
        || normalizeGenerationArtifactRef(raw)
        || normalizeWorkspaceMediaReference(raw)
    ) {
        return raw
    }

    if (/^sandbox:\/+/i.test(raw)) {
        return normalizeHarnessWorkspacePath(raw)
    }

    return defaultUrlTransform(raw)
}

function normalizeCanvasToolName(name: unknown): string {
    return String(name || '').replace(/^lc_/, '')
}

function extractCanvasAnalyzeImageCallId(block: MessageBlock): string | null {
    const payloadCallId = String(block.payload.call_id || '').trim()
    if (payloadCallId) {
        return payloadCallId
    }

    if (typeof block.id === 'string' && block.id.startsWith('tool-')) {
        return block.id.slice('tool-'.length)
    }
    if (typeof block.id === 'string' && block.id.startsWith('media-')) {
        return block.id.slice('media-'.length)
    }
    if (typeof block.id === 'string' && block.id.startsWith('analyze-image-text-')) {
        return block.id.slice('analyze-image-text-'.length)
    }

    return null
}

function isCanvasAnalyzeImageTextBlock(block: MessageBlock): boolean {
    const toolName = normalizeCanvasToolName(block.payload.tool_name)
    return toolName === 'analyze_image' && (block.kind === 'text' || block.uiKind === 'text' || block.uiKind === 'assistant_text')
}

function isCanvasAnalyzeImageStreamPanel(block: MessageBlock): boolean {
    return block.uiKind === 'stream_panel' && normalizeCanvasToolName(block.payload.tool_name) === 'analyze_image'
}

function isCanvasImageAnalysisMediaCard(block: MessageBlock): boolean {
    return block.uiKind === 'media_card' && String(block.payload.media_type || '') === 'image_analysis'
}

function blocksShareCanvasAnalyzeImageIdentity(left: MessageBlock, right: MessageBlock): boolean {
    const leftCallId = extractCanvasAnalyzeImageCallId(left)
    const rightCallId = extractCanvasAnalyzeImageCallId(right)
    return !!leftCallId && leftCallId === rightCallId
}

function extractCanvasAnalyzeImageBlockText(block: MessageBlock | undefined): string {
    if (!block) {
        return ''
    }

    if (isCanvasAnalyzeImageTextBlock(block)) {
        return extractAnalyzeImageText(String(block.payload.text || ''))
    }

    if (isCanvasAnalyzeImageStreamPanel(block)) {
        return extractAnalyzeImageText(
            block.payload.stream_text
            || block.payload.text
            || block.payload.result
            || '',
        )
    }

    if (isCanvasImageAnalysisMediaCard(block)) {
        return extractAnalyzeImageText(
            block.payload.text
            || block.payload.analysis
            || block.payload.result
            || '',
        )
    }

    return ''
}

function mergeCanvasAnalyzeImageBlocks(blocks: MessageBlock[]): MessageBlock[] {
    const mediaCards = blocks.filter(isCanvasImageAnalysisMediaCard)
    if (mediaCards.length === 0) {
        return blocks
    }

    return blocks.flatMap((block) => {
        if (isCanvasImageAnalysisMediaCard(block)) {
            const childCompanions = (block.children || [])
                .filter((candidate) => blocksShareCanvasAnalyzeImageIdentity(block, candidate))
            const siblingCompanions = blocks
                .filter((candidate) => candidate !== block && blocksShareCanvasAnalyzeImageIdentity(block, candidate))
            const companions = [...childCompanions, ...siblingCompanions]
            const companionText = companions.find(isCanvasAnalyzeImageTextBlock)
            const companionPanel = companions.find(isCanvasAnalyzeImageStreamPanel)
            const mergedText = (
                extractCanvasAnalyzeImageBlockText(companionPanel)
                || extractCanvasAnalyzeImageBlockText(companionText)
                || extractCanvasAnalyzeImageBlockText(block)
            )
            const elapsedMs = Number(
                companionPanel?.payload.elapsed_ms
                ?? companionPanel?.payload.result?.elapsed_ms
                ?? block.payload.elapsed_ms
                ?? block.payload.result?.elapsed_ms
                ?? 0,
            )

            return [{
                ...block,
                payload: {
                    ...block.payload,
                    text: mergedText,
                    analysis: mergedText || block.payload.analysis,
                    elapsed_ms: Number.isFinite(elapsedMs) && elapsedMs > 0 ? elapsedMs : block.payload.elapsed_ms,
                },
            }]
        }

        if ((isCanvasAnalyzeImageTextBlock(block) || isCanvasAnalyzeImageStreamPanel(block))
            && mediaCards.some((mediaCard) => blocksShareCanvasAnalyzeImageIdentity(mediaCard, block))) {
            return []
        }

        return [block]
    })
}

export function buildRenderableBlocks(blocks: MessageBlock[]): {
    blocks: MessageBlock[]
    mirroredChildBlockIds: Set<string>
} {
    const nextBlocks: MessageBlock[] = []
    const mirroredChildBlockIds = new Set<string>()
    const sortedBlocks = dedupeEcommerceInteractionBlocks(mergeCanvasAnalyzeImageBlocks(
        [...blocks].sort((a, b) => a.order - b.order),
    ))

    sortedBlocks.forEach((block) => {
        nextBlocks.push(block)

        if (block.uiKind !== 'subagent_card') {
            return
        }

        const childBlocks = [...(block.children || [])]
            .filter((child) => child.visible !== false && child.uiKind === 'generation_task')
            .sort((a, b) => a.order - b.order)

        if (childBlocks.length === 0) {
            return
        }

        childBlocks.forEach((childBlock) => {
            mirroredChildBlockIds.add(childBlock.id)
            nextBlocks.push({
                ...childBlock,
                id: `mirror-${block.id}-${childBlock.id}`,
            })
        })
    })

    return {
        blocks: nextBlocks.map((block, index) => ({ ...block, order: index })),
        mirroredChildBlockIds,
    }
}

function hasVisibleChoicePromptBlock(blocks: MessageBlock[] | undefined): boolean {
    return Array.isArray(blocks)
        && blocks.some((block) => (
            block.visible !== false
            && (block.uiKind === 'choice_prompt' || block.uiKind === 'interaction_form')
        ))
}

export function formatReplyTimestamp(value: string | null | undefined) {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const now = new Date()
    const timeSegment = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
    const isSameDay = date.getFullYear() === now.getFullYear()
        && date.getMonth() === now.getMonth()
        && date.getDate() === now.getDate()

    if (isSameDay) {
        return timeSegment
    }

    return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${timeSegment}`
}

export function ThinkingIndicator({ label, paused = false }: { label: string; paused?: boolean }) {
    return (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px 0', contain: 'layout paint' }}>
            <Loader2
                size={16}
                color="var(--app-foreground-subtle)"
                style={{
                    animation: 'spin 1s linear infinite',
                    animationPlayState: paused ? 'paused' : 'running',
                    willChange: paused ? 'auto' : 'transform',
                }}
            />
            <span style={{ fontSize: 13, color: 'var(--app-foreground-subtle)' }}>{label}</span>
        </div>
    )
}

function getPlanStatusLabel(status: string, t: TFunction) {
    switch (String(status || '').toLowerCase()) {
        case 'awaiting_approval':
            return t('canvas.chat.plan.status.awaiting_approval', 'Awaiting approval')
        case 'completed':
            return t('canvas.chat.plan.status.completed', 'Completed')
        case 'failed':
            return t('canvas.chat.plan.status.failed', 'Failed')
        default:
            return t('canvas.chat.plan.status.in_progress', 'In progress')
    }
}

function getPlanStepStatusLabel(
    stepStatus: string,
    isActive: boolean,
    planStatus: string,
    t: TFunction,
) {
    if (String(stepStatus || '').toLowerCase() === 'completed') {
        return t('canvas.chat.plan.status.completed', 'Completed')
    }
    if (String(planStatus || '').toLowerCase() === 'awaiting_approval' && isActive) {
        return t('canvas.chat.plan.status.awaiting_approval', 'Awaiting approval')
    }
    return isActive
        ? t('canvas.chat.plan.status.in_progress', 'In progress')
        : t('canvas.chat.plan.status.pending', 'Pending')
}

function MessageBubbleImpl({ message, isDark, onPreview, onDownload, onFocusItem, resolveMentionItem, activeSkillId, replyTimestamp, hiddenToolCalls = [], deletedAgentMediaKeys = [], canReplayCompletedMedia = true, isHistoryLoaded = false, forwardSelectionMode = false, selectedForwardMessageIds = new Set<string>(), onEnterForwardSelectionMode, onToggleForwardMessage, conversationId, hasUserReplyBelow = false, getHeavyBlockRenderMode, onExpandCompactBlock, onRequestEcommerceReferenceImages, onUploadEcommerceReferenceImage, maxEcommerceReferenceImages }: {
    message: ChatMessage;
    isDark: boolean;
    onPreview: (url: string) => void;
    onDownload: (url: string, e: React.MouseEvent) => void;
    onFocusItem?: (itemId: string) => void;
    resolveMentionItem?: (id: string) => CanvasItem | undefined;
    activeSkillId?: string;
    replyTimestamp?: string;
    hiddenToolCalls?: string[];
    deletedAgentMediaKeys?: string[];
    canReplayCompletedMedia?: boolean;
    isHistoryLoaded?: boolean;
    forwardSelectionMode?: boolean;
    selectedForwardMessageIds?: ReadonlySet<string>;
    onEnterForwardSelectionMode?: (messageId: string) => void;
    onToggleForwardMessage?: (messageId: string) => void;
    conversationId?: string | number | null;
    hasUserReplyBelow?: boolean;
    getHeavyBlockRenderMode?: (blockId: string) => 'compact' | 'full';
    onExpandCompactBlock?: (blockId: string) => void;
    onRequestEcommerceReferenceImages?: (
        source: EcommerceReferenceImageSource,
        onSelect: (urls: string[]) => void,
        options?: EcommerceReferenceImageRequestOptions,
    ) => void;
    onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>;
    maxEcommerceReferenceImages?: number;
}) {
    const { t } = useTranslation()
    const isUser = message.role === 'user'
    const forwardEntries = React.useMemo(() => getForwardSelectableEntries(message), [message])
    const contentForwardEntry = React.useMemo(
        () => forwardEntries.find((entry) => entry.source === 'message_content') || null,
        [forwardEntries],
    )
    const blockForwardEntryMap = React.useMemo(() => new Map(
        forwardEntries
            .filter((entry) => entry.source === 'block' && entry.blockId)
            .map((entry) => [entry.blockId as string, entry.id]),
    ), [forwardEntries])
    const renderState = React.useMemo(
        () => buildRenderableBlocks(message.blocks || []),
        [message.blocks],
    )
    const suppressAskUserToolCall = React.useMemo(
        () => hasVisibleChoicePromptBlock(renderState.blocks),
        [renderState.blocks],
    )
    const shouldRenderToolCall = React.useCallback((toolCall: ToolCallInfo) => {
        return !hiddenToolCalls.includes(toolCall.name)
    }, [hiddenToolCalls])
    const attachmentNode = message.attachments && message.attachments.length > 0
        ? (
            <ChatAttachmentStrip
                attachments={message.attachments as any}
                isDark={isDark}
                conversationId={conversationId}
                onPreview={onPreview}
            />
        )
        : null
    const renderForwardSelectionCheckbox = (entryId: string) => (
        <label
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0,
                width: 28,
                minWidth: 28,
                alignSelf: 'stretch',
            }}
        >
            <input
                type="checkbox"
                aria-label={t('canvas.chat.forward.select_reply', 'Select reply to forward')}
                checked={selectedForwardMessageIds.has(entryId)}
                onChange={() => onToggleForwardMessage?.(entryId)}
                style={{
                    width: 18,
                    height: 18,
                    margin: 0,
                    accentColor: 'var(--app-primary)',
                    cursor: 'pointer',
                }}
            />
        </label>
    )
    const renderForwardActionButton = (entryId: string) => (
        <button
            type="button"
            aria-label={t('canvas.chat.forward.send_to_home', 'Send reply to homepage agent')}
            onClick={() => onEnterForwardSelectionMode?.(entryId)}
            title={t('canvas.chat.forward.send_to_home', 'Send reply to homepage agent')}
            style={{
                width: 24,
                height: 24,
                padding: 0,
                borderRadius: 8,
                border: 'none',
                background: 'var(--app-primary)',
                boxShadow: 'var(--app-shadow-control)',
                color: 'var(--app-primary-foreground)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-1px) scale(1.03)'
                e.currentTarget.style.boxShadow = 'var(--app-shadow-control)'
            }}
            onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0) scale(1)'
                e.currentTarget.style.boxShadow = 'var(--app-shadow-control)'
            }}
        >
            <Sparkles size={12} strokeWidth={2.2} />
        </button>
    )
    const NUMBER_CIRCLES = ['\u2460', '\u2461', '\u2462', '\u2463', '\u2464', '\u2465', '\u2466', '\u2467', '\u2468', '\u2469']

    const renderContent = (content: string) => {
        const parts: React.ReactNode[] = []
        const COMBINED_REGEX = new RegExp(
            `${CANVAS_MENTION_TOKEN_PATTERN.source}|${CANVAS_MARK_TOKEN_PATTERN.source}`,
            'g',
        )
        let lastIndex = 0
        let match

        while ((match = COMBINED_REGEX.exec(content)) !== null) {
            // Push text before this match
            if (match.index > lastIndex) {
                parts.push(content.substring(lastIndex, match.index))
            }

            if (match[1]) {
                const parsedMention = parseCanvasMentionToken(match)
                if (!parsedMention) {
                    parts.push(match[0])
                    lastIndex = match.index + match[0].length
                    continue
                }
                const name = parsedMention.label
                const id = parsedMention.itemId
                const canvasItem = resolveMentionItem?.(id)
                const isVideo = canvasItem?.type === 'video' || canvasItem?.type === 'video_generator'

                parts.push(
                    <span
                        key={`m-${match.index}`}
                        onClick={() => onFocusItem?.(id)}
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                            padding: '2px 8px 2px 4px',
                            borderRadius: 8,
                            backgroundColor: isUser ? 'var(--app-on-primary-control)' : 'var(--app-tint-primary)',
                            color: isUser ? 'var(--app-primary-foreground)' : 'var(--app-primary)',
                            cursor: 'pointer',
                            fontWeight: 500,
                            border: isUser ? '1px solid var(--app-on-primary-border)' : '1px solid color-mix(in srgb, var(--app-primary) 20%, var(--app-border))',
                            transition: 'all 0.2s',
                            verticalAlign: 'middle',
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = isUser ? 'var(--app-on-primary-control-hover)' : 'var(--app-tint-primary-hover)'
                            e.currentTarget.style.boxShadow = 'var(--app-shadow-control)'
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor = isUser ? 'var(--app-on-primary-control)' : 'var(--app-tint-primary)'
                            e.currentTarget.style.boxShadow = 'none'
                        }}
                    >
                        {canvasItem?.url && !isVideo ? (
                            <AgentLazyMedia
                                src={canvasItem.url}
                                alt=""
                                aspectRatio={1}
                                style={{
                                    width: 18,
                                    height: 18,
                                    borderRadius: 4,
                                    flexShrink: 0,
                                }}
                                mediaStyle={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                        ) : (
                            <span style={{
                                width: 18,
                                height: 18,
                                borderRadius: 4,
                                backgroundColor: isUser ? 'var(--app-media-control)' : 'var(--app-control)',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexShrink: 0,
                            }}>
                                {isVideo
                                    ? <Film size={10} color={isUser ? 'var(--app-primary-foreground)' : (isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-muted)')} />
                                    : <ImageIcon size={10} color={isUser ? 'var(--app-primary-foreground)' : (isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-muted)')} />
                                }
                            </span>
                        )}
                        {name}
                    </span>
                )
            } else if (match[3]) {
                const parsedMark = parseCanvasMarkToken([match[0], match[3], match[4]] as unknown as RegExpMatchArray)
                if (!parsedMark) {
                    parts.push(match[0])
                    lastIndex = match.index + match[0].length
                    continue
                }
                const label = parsedMark.label
                const imageId = parsedMark.imageItemId
                const markNumber = Number((parsedMark.markId.match(/(\d+)$/) || [])[1] || 0)
                const canvasItem = resolveMentionItem?.(imageId)
                const numIcon = NUMBER_CIRCLES[markNumber - 1] || `(${markNumber})`

                parts.push(
                    <span
                        key={`k-${match.index}`}
                        onClick={() => onFocusItem?.(imageId)}
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                            padding: '2px 8px 2px 4px',
                            borderRadius: 8,
                            backgroundColor: isUser ? 'var(--app-on-primary-control)' : 'var(--app-tint-warning)',
                            color: isUser ? 'var(--app-primary-foreground)' : 'var(--app-warning)',
                            cursor: 'pointer',
                            fontWeight: 500,
                            border: isUser ? '1px solid var(--app-on-primary-border)' : '1px solid color-mix(in srgb, var(--app-warning) 20%, var(--app-border))',
                            transition: 'all 0.2s',
                            verticalAlign: 'middle',
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = isUser ? 'var(--app-on-primary-control-hover)' : 'var(--app-tint-warning)'
                            e.currentTarget.style.boxShadow = 'var(--app-shadow-control)'
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor = isUser ? 'var(--app-on-primary-control)' : 'var(--app-tint-warning)'
                            e.currentTarget.style.boxShadow = 'none'
                        }}
                    >
                        {canvasItem?.url ? (
                            <AgentLazyMedia
                                src={canvasItem.url}
                                alt=""
                                aspectRatio={1}
                                style={{
                                    width: 18,
                                    height: 18,
                                    borderRadius: 4,
                                    flexShrink: 0,
                                }}
                                mediaStyle={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                        ) : (
                            <span style={{
                                width: 18,
                                height: 18,
                                borderRadius: 4,
                                backgroundColor: isUser ? 'var(--app-media-control)' : 'var(--app-control)',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexShrink: 0,
                            }}>
                                <ImageIcon size={10} color={isUser ? 'var(--app-primary-foreground)' : (isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-muted)')} />
                            </span>
                        )}
                        <span style={{ fontWeight: 700, color: isUser ? 'var(--app-primary-foreground)' : 'var(--app-primary)' }}>{numIcon}</span>
                        {label}
                    </span>
                )
            }

            lastIndex = match.index + match[0].length
        }

        if (lastIndex < content.length) {
            parts.push(content.substring(lastIndex))
        }

        return parts
    }

    if (!isUser && message.blocks && message.blocks.length > 0) {
        return (
            <div style={{
                display: 'flex',
                alignItems: 'stretch',
                gap: 8,
            }}>
                <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
                    {replyTimestamp && (
                        <div
                            data-testid={`assistant-reply-timestamp-${message.id}`}
                            style={{ fontSize: 12, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)', paddingLeft: 2 }}
                        >
                            {replyTimestamp}
                        </div>
                    )}
                    {renderState.blocks
                        .sort((a, b) => a.order - b.order)
                        .map((block) => {
                            const forwardEntryId = blockForwardEntryMap.get(block.id)
                            const blockNode = (
                                <MessageBlockRenderer
                                    key={block.id}
                                    block={block}
                                    parentMessageContent={message.content}
                                    isDark={isDark}
                                    onPreview={onPreview}
                                    onDownload={onDownload}
                                    messageId={message.id}
                                    deletedAgentMediaKeys={deletedAgentMediaKeys}
                                    canReplayCompletedMedia={canReplayCompletedMedia}
                                    mirroredChildBlockIds={renderState.mirroredChildBlockIds}
                                    suppressAskUserToolCall={suppressAskUserToolCall}
                                    isHistoryLoaded={isHistoryLoaded}
                                    forwardActionButton={!forwardSelectionMode && forwardEntryId ? renderForwardActionButton(forwardEntryId) : null}
                                    conversationId={conversationId}
                                    hasUserReplyBelow={hasUserReplyBelow}
                                    heavyBlockRenderMode={getHeavyBlockRenderMode?.(String(block.id)) || 'full'}
                                    onExpandCompactBlock={onExpandCompactBlock}
                                    onRequestEcommerceReferenceImages={onRequestEcommerceReferenceImages}
                                    onUploadEcommerceReferenceImage={onUploadEcommerceReferenceImage}
                                    maxEcommerceReferenceImages={maxEcommerceReferenceImages}
                                />
                            )

                            if (!forwardEntryId || !forwardSelectionMode) {
                                return blockNode
                            }

                            return (
                                <div key={block.id} style={{ display: 'flex', alignItems: 'stretch', gap: 8, width: '100%' }}>
                                    {renderForwardSelectionCheckbox(forwardEntryId)}
                                    {blockNode}
                                </div>
                            )
                        })}
                </div>
            </div>
        )
    }

    return (
        <div style={{
            display: 'flex',
            alignItems: 'stretch',
            flexDirection: isUser ? 'row-reverse' : 'row',
            gap: isUser ? 0 : 8,
        }}>
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8, alignItems: isUser ? 'flex-end' : 'flex-start' }}>
            {!isUser && replyTimestamp && (
                <div
                    data-testid={`assistant-reply-timestamp-${message.id}`}
                    style={{ fontSize: 12, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)', paddingLeft: 2 }}
                >
                    {replyTimestamp}
                </div>
            )}
            {/* Skill badge */}
                {isUser && message.skillId && (() => {
                    const skill = CHAT_SKILL_META[message.skillId as keyof typeof CHAT_SKILL_META]
                    if (!skill) return null
                    return <SkillBadge skillId={message.skillId} />
                })()}
                {/* Skill intro text + pre-analysis tool calls (analyze_image) render BEFORE text */}
                {(message.toolCalls || []).some(tc => tc.name === 'analyze_image' && shouldRenderToolCall(tc)) && activeSkillId && (
                    <AnalysisIntroText skillId={activeSkillId} isDark={isDark} />
                )}
                {(message.toolCalls || []).filter(tc => tc.name === 'analyze_image' && shouldRenderToolCall(tc)).map((tc) => (
                    <ToolCallCard key={tc.callId} toolCall={tc} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                ))}

                {attachmentNode}

                {message.content?.trim() && (
                    <div style={{
                        display: 'flex',
                        alignItems: 'stretch',
                        justifyContent: isUser ? 'flex-end' : 'flex-start',
                        gap: 8,
                        width: '100%',
                        alignSelf: 'stretch',
                    }}>
                        {!isUser && forwardSelectionMode && contentForwardEntry ? renderForwardSelectionCheckbox(contentForwardEntry.id) : null}
                        <div className="group relative" style={{ maxWidth: '85%' }}>
                            <div style={{
                                padding: '10px 14px',
                                borderRadius: 16,
                                backgroundColor: isUser
                                    ? 'var(--app-primary)'
                                    : 'var(--app-surface-muted)',
                                color: isUser ? 'var(--app-primary-foreground)' : 'var(--app-foreground)',
                                fontSize: 14,
                                lineHeight: 1.6,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                userSelect: 'text',
                                WebkitUserSelect: 'text',
                            }}>
                                {isUser ? renderContent(message.content) : (
                                    <MarkdownContent content={message.content} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                                )}
                            </div>
                            <CopyButton
                                text={message.content}
                                isDark={isDark}
                                isUser={isUser}
                                extraActions={!isUser && !forwardSelectionMode && contentForwardEntry ? renderForwardActionButton(contentForwardEntry.id) : null}
                            />
                        </div>
                    </div>
                )}

                {/* Remaining tool calls & Generation boxes (excluding already-rendered analyze_image) */}
                {(message.toolCalls || []).filter(tc => tc.name !== 'analyze_image' && shouldRenderToolCall(tc)).map((tc) => {
                    const isGeneration = tc.name === 'generate_image' || tc.name === 'generate_video'
                    if (isGeneration) {
                        return (
                            <GenerationTaskBox
                                key={tc.callId}
                                toolCall={tc}
                                isDark={isDark}
                                messageId={message.id}
                                onPreview={onPreview}
                                onDownload={onDownload}
                                deletedAgentMediaKeys={deletedAgentMediaKeys}
                                canReplayCompletedMedia={canReplayCompletedMedia}
                                isHistoryLoaded={isHistoryLoaded}
                            />
                        )
                    }
                    return <ToolCallCard key={tc.callId} toolCall={tc} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                })}
            </div>
        </div>
    )
}

// Memoized so a streaming delta (≈32ms cadence) or a sibling message update only
// re-renders the message whose `message` reference actually changed. The store mints a
// new `message` ref only for the message that changed, and all cross-message derived
// state (hasUserReplyBelow / replyTimestamp / activeSkillId) is passed as explicit props,
// so the default shallow comparison is correct — do NOT add a custom areEqual.
export const MessageBubble = React.memo(MessageBubbleImpl)

type CanvasMessageBlockRendererProps = {
    block: MessageBlock
    parentMessageContent?: string | null
    isDark: boolean
    onPreview: (url: string) => void
    onDownload: (url: string, e: React.MouseEvent) => void
    messageId: string | number
    deletedAgentMediaKeys?: string[]
    canReplayCompletedMedia?: boolean
    mirroredChildBlockIds?: ReadonlySet<string>
    disableCanvasReplay?: boolean
    suppressAskUserToolCall?: boolean
    isHistoryLoaded?: boolean
    forwardActionButton?: React.ReactNode
    conversationId?: string | number | null
    hasUserReplyBelow?: boolean
    heavyBlockRenderMode?: 'compact' | 'full'
    onExpandCompactBlock?: (blockId: string) => void
    onRequestEcommerceReferenceImages?: (
        source: EcommerceReferenceImageSource,
        onSelect: (urls: string[]) => void,
        options?: EcommerceReferenceImageRequestOptions,
    ) => void
    onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>
    maxEcommerceReferenceImages?: number
}

const canvasPresentationRendererRegistry = createPresentationRendererRegistry()

function CanvasPresentationBlockRenderer(props: CanvasMessageBlockRendererProps) {
    return <MessageBlockRendererBody {...props} />
}

registerDefaultPresentationRenderers(
    canvasPresentationRendererRegistry,
    CanvasPresentationBlockRenderer as PresentationBlockRenderer,
)

export function MessageBlockRenderer(props: CanvasMessageBlockRendererProps) {
    const Renderer = canvasPresentationRendererRegistry.resolve(props.block.uiKind)
    if (Renderer) {
        return <Renderer {...props} />
    }
    return <MessageBlockRendererBody {...props} />
}

function MessageBlockRendererBody({
    block,
    parentMessageContent,
    isDark,
    onPreview,
    onDownload,
    messageId,
    deletedAgentMediaKeys = [],
    canReplayCompletedMedia = true,
    mirroredChildBlockIds,
    disableCanvasReplay = false,
    suppressAskUserToolCall = false,
    isHistoryLoaded = false,
    forwardActionButton,
    conversationId,
    hasUserReplyBelow = false,
    heavyBlockRenderMode = 'full',
    onExpandCompactBlock,
    onRequestEcommerceReferenceImages,
    onUploadEcommerceReferenceImage,
    maxEcommerceReferenceImages,
}: CanvasMessageBlockRendererProps) {
    const { t } = useTranslation()
    const presentationUiKind = normalizePresentationUiKind(block.uiKind)
    // Derive tool-call view models once per block identity so the memoized leaf cards
    // (GenerationTaskBox / ToolCallCard) keep a stable `toolCall` prop and can skip
    // re-rendering when the block is unchanged (e.g. during the streaming region's
    // ~32ms re-renders, only the block receiving a delta re-renders).
    const derivedToolCall = React.useMemo(() => toolCallFromBlock(block), [block])
    const derivedMediaCardToolCall = React.useMemo(() => toolCallFromMediaCardBlock(block), [block])
    if (block.visible === false || block.uiKind === 'hidden_tool') {
        return null
    }

    if (
        heavyBlockRenderMode === 'compact'
        && isAgentHeavyBlock(block)
        && isAgentBlockTerminal(block)
    ) {
        return <CompactAgentBlock block={block} isDark={isDark} t={t} onExpand={() => onExpandCompactBlock?.(String(block.id))} />
    }

    if (block.uiKind === 'assistant_text' || block.uiKind === 'assistant_final_answer' || presentationUiKind === 'text') {
        const text = String(block.payload.text || '')
        if (!text.trim()) return null
        const isStreaming = block.status === 'streaming' || block.status === 'running'
        return (
            <div className="group relative" style={{ maxWidth: '85%' }}>
                <div style={{
                    padding: '10px 14px',
                    borderRadius: 16,
                    backgroundColor: 'var(--app-surface-muted)',
                    color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                    fontSize: 14,
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                }}>
                    {isStreaming ? (
                        <PlainTextContent content={text} isDark={isDark} />
                    ) : (
                        <MarkdownContent content={text} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                    )}
                    {isStreaming && (
                        <span style={{
                            display: 'inline-block',
                            width: 6,
                            height: 16,
                            backgroundColor: 'var(--app-primary)',
                            marginLeft: 2,
                            animation: 'blink 1s infinite',
                            verticalAlign: 'text-bottom',
                        }} />
                    )}
                </div>
                <CopyButton text={text} isDark={isDark} isUser={false} extraActions={forwardActionButton} />
            </div>
        )
    }

    if (block.uiKind === 'plan_artifact' || presentationUiKind === 'plan_card') {
        const steps = Array.isArray(block.payload.steps) ? block.payload.steps : []
        const planStatus = String(block.payload.status || block.status || '')
        return (
            <div
                style={{
                    maxWidth: '85%',
                    padding: '14px 16px',
                    borderRadius: 18,
                    border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
                    background: 'var(--app-glass)',
                }}
            >
                <div style={{ fontSize: 14, fontWeight: 600, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                    {String(block.payload.title || t('canvas.chat.plan.title', 'Task Plan'))}
                </div>
                <div style={{
                    marginTop: 6,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '4px 10px',
                    borderRadius: 999,
                    fontSize: 11,
                    fontWeight: 600,
                    background: planStatus.toLowerCase() === 'awaiting_approval'
                        ? (isDark ? 'color-mix(in srgb, var(--app-warning) 18%, transparent)' : 'color-mix(in srgb, var(--app-warning) 18%, transparent)')
                        : (isDark ? 'var(--app-focus-ring)' : 'color-mix(in srgb, var(--app-primary) 12%, transparent)'),
                    color: planStatus.toLowerCase() === 'awaiting_approval'
                        ? (isDark ? 'var(--app-warning)' : 'var(--app-warning)')
                        : (isDark ? 'var(--app-primary)' : 'var(--app-primary)'),
                }}>
                    {getPlanStatusLabel(planStatus, t)}
                </div>
                {block.payload.summary ? (
                    <div style={{ marginTop: 6, fontSize: 13, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                        {String(block.payload.summary)}
                    </div>
                ) : null}
                {planStatus.toLowerCase() === 'awaiting_approval' ? (
                    <div style={{ marginTop: 8, fontSize: 12, color: isDark ? 'var(--app-warning)' : 'var(--app-warning)' }}>
                        {t(
                            'canvas.chat.plan.awaiting_approval_hint',
                            'Reply to approve the plan or tell the agent what to change before execution continues.',
                        )}
                    </div>
                ) : null}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
                    {steps.map((step: Record<string, any>) => {
                        const stepId = String(step.id || step.order || '')
                        const isActive = String(step.status || '').toLowerCase() === 'in_progress'
                        return (
                            <div
                                key={stepId}
                                style={{
                                    padding: '10px 12px',
                                    borderRadius: 12,
                                    background: isActive
                                        ? (isDark ? 'var(--app-focus-ring)' : 'color-mix(in srgb, var(--app-primary) 12%, transparent)')
                                        : 'var(--app-surface-muted)',
                                    border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)'}`,
                                }}
                            >
                                <div style={{ fontSize: 13, fontWeight: 600, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                                    {String(step.order || '')}. {String(step.title || '')}
                                </div>
                                {step.description ? (
                                    <div style={{ marginTop: 4, fontSize: 12, color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)' }}>
                                        {String(step.description)}
                                    </div>
                                ) : null}
                                <div style={{ marginTop: 4, fontSize: 11, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)' }}>
                                    {getPlanStepStatusLabel(String(step.status || ''), isActive, planStatus, t)}
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>
        )
    }

    if (block.uiKind === 'progress_update' || presentationUiKind === 'progress_card') {
        const progressText = String(block.payload.text || '')
        // Guard empty text like the other renderers (text / stream_panel / error_card) do —
        // a text-less progress block otherwise paints a bare empty bubble.
        if (!progressText.trim()) {
            return null
        }
        return (
            <div
                style={{
                    maxWidth: '85%',
                    padding: '10px 14px',
                    borderRadius: 16,
                    border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
                    background: 'var(--app-glass)',
                    color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-border-strong)',
                    fontSize: 13,
                }}
            >
                {progressText}
            </div>
        )
    }

    if (block.uiKind === 'media_card' || presentationUiKind === 'artifact_card') {
        const mediaType = String(block.payload.media_type || '')
        if (mediaType === 'image_analysis') {
            return (
                <AnalyzeImageMediaCard
                    block={block}
                    isDark={isDark}
                    onPreview={onPreview}
                    conversationId={conversationId}
                />
            )
        }

        return (
            <GenerationTaskBox
                toolCall={derivedMediaCardToolCall}
                isDark={isDark}
                messageId={messageId}
                onPreview={onPreview}
                onDownload={onDownload}
                deletedAgentMediaKeys={deletedAgentMediaKeys}
                canReplayCompletedMedia={canReplayCompletedMedia && !disableCanvasReplay}
                isHistoryLoaded={isHistoryLoaded}
            />
        )
    }

    if (block.kind === 'text') {
        const text = String(block.payload.text || '')
        if (!text.trim()) return null
        const isStreaming = block.status === 'streaming' || block.status === 'running'
        return (
            <div className="group relative" style={{ maxWidth: '85%' }}>
                <div style={{
                    padding: '10px 14px',
                    borderRadius: 16,
                    backgroundColor: 'var(--app-surface-muted)',
                    color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                    fontSize: 14,
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                }}>
                    {isStreaming ? (
                        <PlainTextContent content={text} isDark={isDark} />
                    ) : (
                        <MarkdownContent content={text} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                    )}
                    {isStreaming && (
                        <span style={{
                            display: 'inline-block',
                            width: 6,
                            height: 16,
                            backgroundColor: 'var(--app-primary)',
                            marginLeft: 2,
                            animation: 'blink 1s infinite',
                            verticalAlign: 'text-bottom',
                        }} />
                    )}
                </div>
                <CopyButton text={text} isDark={isDark} isUser={false} extraActions={forwardActionButton} />
            </div>
        )
    }

    if (presentationUiKind === 'subagent_card') {
        return (
            <SubagentCard
                block={block}
                isDark={isDark}
                onPreview={onPreview}
                onDownload={onDownload}
                messageId={messageId}
                deletedAgentMediaKeys={deletedAgentMediaKeys}
                canReplayCompletedMedia={canReplayCompletedMedia}
                mirroredChildBlockIds={mirroredChildBlockIds}
                isHistoryLoaded={isHistoryLoaded}
                conversationId={conversationId}
                hasUserReplyBelow={hasUserReplyBelow}
            />
        )
    }

    if (block.uiKind === 'generation_task') {
        return (
            <GenerationTaskBox
                toolCall={derivedToolCall}
                isDark={isDark}
                messageId={messageId}
                onPreview={onPreview}
                onDownload={onDownload}
                deletedAgentMediaKeys={deletedAgentMediaKeys}
                canReplayCompletedMedia={canReplayCompletedMedia && !disableCanvasReplay}
                isHistoryLoaded={isHistoryLoaded}
            />
        )
    }

    if (block.uiKind === 'choice_prompt' || presentationUiKind === 'interaction_form') {
        return (
            <InteractionBlock
                block={block}
                parentMessageContent={parentMessageContent}
                isDark={isDark}
                hasUserReplyBelow={hasUserReplyBelow}
                conversationId={conversationId}
                onPreview={onPreview}
                onRequestEcommerceReferenceImages={onRequestEcommerceReferenceImages}
                onUploadEcommerceReferenceImage={onUploadEcommerceReferenceImage}
                maxEcommerceReferenceImages={maxEcommerceReferenceImages}
            />
        )
    }

    if (presentationUiKind === 'error_card') {
        const message = String(block.payload.message || block.payload.error || block.payload.summary || '')
        if (!message.trim()) {
            return null
        }
        return (
            <div
                style={{
                    maxWidth: '85%',
                    padding: '10px 14px',
                    borderRadius: 16,
                    border: `1px solid ${isDark ? 'color-mix(in srgb, var(--app-danger) 26%, var(--app-border))' : 'color-mix(in srgb, var(--app-danger) 18%, var(--app-border))'}`,
                    background: isDark ? 'color-mix(in srgb, var(--app-danger) 18%, transparent)' : 'color-mix(in srgb, var(--app-danger) 12%, transparent)',
                    color: isDark ? 'var(--app-danger)' : 'var(--app-danger)',
                    fontSize: 13,
                }}
            >
                {message}
            </div>
        )
    }

    if (block.uiKind === 'stream_panel') {
        const toolName = String(block.payload.tool_name || '')
        if (toolName === 'analyze_image') {
            return <ToolCallCard toolCall={derivedToolCall} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
        }
        const text = extractCanvasStreamPanelText(block)
        if (!text.trim()) {
            return null
        }
        const isStreaming = block.status === 'running' || block.status === 'streaming'

        return (
            <div
                style={{
                    maxWidth: '85%',
                    padding: '12px 14px',
                    borderRadius: 16,
                    border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
                    background: 'var(--app-glass)',
                }}
            >
                {isStreaming ? (
                    <PlainTextContent content={text} isDark={isDark} />
                ) : (
                    <MarkdownContent content={text} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                )}
            </div>
        )
    }

    if (block.uiKind === 'web_search_card') {
        return (
            <CanvasWebSearchCard
                payload={block.payload}
                isDark={isDark}
                onPreview={onPreview}
                conversationId={useChatStore.getState().conversationId}
            />
        )
    }

    if (block.uiKind === 'compact_tool' || presentationUiKind === 'tool_call' || presentationUiKind === 'tool_result') {
        const toolCall = derivedToolCall
        if (suppressAskUserToolCall && toolCall.name === 'ask_user') {
            return null
        }
        return <ToolCallCard toolCall={toolCall} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
    }

    if (block.kind === 'tool') {
        const toolCall = derivedToolCall
        if (suppressAskUserToolCall && toolCall.name === 'ask_user') {
            return null
        }
        return <ToolCallCard toolCall={toolCall} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
    }

    return null
}

function CompactAgentBlock({ block, isDark, t, onExpand }: { block: MessageBlock; isDark: boolean; t: TFunction; onExpand?: () => void }) {
    const label = getCompactAgentBlockLabel(block, t)
    const status = String(block.payload.status || block.status || '').trim()
    const summary = String(block.payload.prompt || block.payload.text || block.payload.summary || block.payload.tool_name || '').trim()
    return (
        <button
            type="button"
            data-testid="agent-compact-block"
            onClick={onExpand}
            style={{
                maxWidth: '85%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
                padding: '10px 12px',
                borderRadius: 14,
                border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
                background: 'var(--app-glass)',
                color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                cursor: 'pointer',
                textAlign: 'left',
            }}
        >
            <span style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
                <span style={{ fontSize: 12, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {[status, summary].filter(Boolean).join(' · ') || t('agentMedia.compact.collapsed', '已折叠历史内容')}
                </span>
            </span>
            <span style={{ flexShrink: 0, fontSize: 12, color: 'var(--app-primary)', fontWeight: 600 }}>
                {t('agentMedia.compact.expand', '展开')}
            </span>
        </button>
    )
}

function getCompactAgentBlockLabel(block: MessageBlock, t: TFunction): string {
    const uiKind = String(block.uiKind || '')
    const mediaType = String(block.payload.media_type || block.payload.mediaType || '')
    if (uiKind.includes('generation') || mediaType) {
        return mediaType === 'video' || String(block.payload.tool_name || '').includes('video')
            ? t('agentMedia.compact.videoGeneration', '视频生成结果')
            : t('agentMedia.compact.imageGeneration', '图片生成结果')
    }
    if (uiKind.includes('tool') || block.kind === 'tool') {
        return t('agentMedia.compact.tool', '工具调用')
    }
    return t('agentMedia.compact.richBlock', '历史富媒体内容')
}

function extractCanvasStreamPanelText(block: MessageBlock): string {
    const streamText = String(block.payload.stream_text || '')
    const finalText = String(block.payload.text || '')
    const preferredText = streamText || finalText

    if (!preferredText.trim()) {
        return ''
    }

    if (String(block.payload.tool_name || '') !== 'analyze_image') {
        return preferredText
    }

    const trimmed = preferredText.trim()
    if (!trimmed.startsWith('{')) {
        return preferredText
    }

    try {
        const parsed = JSON.parse(trimmed)
        if (parsed && typeof parsed.analysis === 'string' && parsed.analysis.trim().length > 0) {
            return parsed.analysis
        }
    } catch {
        return preferredText
    }

    return preferredText
}

function normalizeToolBlockResult(rawResult: Record<string, any> | null | undefined): Record<string, any> {
    if (!rawResult || typeof rawResult !== 'object') {
        return {}
    }
    return rawResult
}

function toolCallFromBlock(block: MessageBlock): ToolCallInfo {
    const toolName = String(block.payload.tool_name || '')
    const normalizedResult = normalizeToolBlockResult(block.payload.result || {})
    const result = {
        ...normalizedResult,
        progress: block.payload.progress,
        status: block.payload.status,
        result_url: block.payload.result_url ?? normalizedResult.result_url,
        error_message: block.payload.error_message ?? normalizedResult.error_message,
        canvas_revision: block.payload.canvas_revision ?? normalizedResult.canvas_revision,
        canvas_item_deleted: block.payload.canvas_item_deleted ?? normalizedResult.canvas_item_deleted,
        canvas_item: block.payload.canvas_item || normalizedResult.canvas_item,
        id: block.payload.task_id ?? normalizedResult.id ?? normalizedResult.task_id,
        task_id: block.payload.task_id ?? normalizedResult.task_id ?? normalizedResult.id,
    }
    return {
        callId: String(block.payload.call_id || block.id),
        name: toolName,
        args: block.payload.args || {},
        result,
        error: block.payload.error_message || block.payload.result?.error,
        status: block.status === 'streaming'
            ? 'running'
            : block.status === 'failed'
                ? 'failed'
                : block.status === 'completed'
                    ? 'completed'
                    : 'running',
        streamingText: block.payload.stream_text,
    }
}

function inferToolNameFromMediaType(mediaType: string): string {
    if (mediaType === 'video_generation') {
        return 'generate_video'
    }
    if (mediaType === 'image_generation') {
        return 'generate_image'
    }
    if (mediaType === 'image_analysis') {
        return 'analyze_image'
    }
    return 'generate_image'
}

function toolCallFromMediaCardBlock(block: MessageBlock): ToolCallInfo {
    const mediaType = String(block.payload.media_type || '')
    const toolName = String(block.payload.tool_name || inferToolNameFromMediaType(mediaType))
    const status = String(block.payload.status || block.status || 'running')
    const prompt = String(block.payload.prompt || '').trim()
    const nestedResult = normalizeToolBlockResult(block.payload.result || {})
    const nestedParams = normalizeToolBlockResult(nestedResult.params || {})
    const params = {
        ...nestedParams,
        aspect_ratio: block.payload.aspect_ratio ?? nestedParams.aspect_ratio,
        resolution: block.payload.resolution ?? nestedParams.resolution,
        duration: block.payload.duration ?? nestedParams.duration,
        quality: block.payload.quality ?? nestedParams.quality,
    }
    const result = {
        ...nestedResult,
        task_id: block.payload.task_id ?? nestedResult.task_id,
        id: block.payload.task_id ?? nestedResult.id ?? nestedResult.task_id,
        status,
        progress: block.payload.progress ?? nestedResult.progress,
        result_url: block.payload.result_url ?? nestedResult.result_url,
        error_message: block.payload.error_message ?? nestedResult.error_message,
        canvas_revision: block.payload.canvas_revision ?? nestedResult.canvas_revision,
        canvas_item_deleted: block.payload.canvas_item_deleted ?? nestedResult.canvas_item_deleted,
        prompt: prompt || undefined,
        model_name: block.payload.model_name ?? nestedResult.model_name,
        model_label: block.payload.model_label ?? nestedResult.model_label,
        provider_code: block.payload.provider_code ?? nestedResult.provider_code,
        resolution: block.payload.resolution ?? nestedResult.resolution ?? nestedParams.resolution,
        duration: block.payload.duration ?? nestedResult.duration ?? nestedParams.duration,
        quality: block.payload.quality ?? nestedResult.quality ?? nestedParams.quality,
        artifact: block.payload.artifact || nestedResult.artifact || null,
        params,
        canvas_item: block.payload.canvas_item || nestedResult.canvas_item || undefined,
    }

    return {
        callId: String(block.payload.call_id || block.id),
        name: toolName,
        args: {
            aspect_ratio: params.aspect_ratio,
            resolution: params.resolution,
            duration: params.duration,
            quality: params.quality,
            prompt,
        },
        result,
        error: block.payload.error_message,
        status: status === 'failed'
            ? 'failed'
            : status === 'completed'
                ? 'completed'
                : 'running',
    }
}

function translateLabel(
    t: TFunction,
    key: string,
    defaultValue: string,
): string {
    const translated = t(key, { defaultValue })
    return typeof translated === 'string' ? translated : defaultValue
}

function getToolLabel(
    name: string,
    t: TFunction,
) {
    const toolLabels: Record<string, string> = {
        generate_image: translateLabel(t, 'canvas.chat.tool_labels.generate_image', '生成图片'),
        generate_video: translateLabel(t, 'canvas.chat.tool_labels.generate_video', '生成视频'),
        analyze_image: translateLabel(t, 'canvas.chat.tool_labels.analyze_image', '图片分析'),
        analyze_canvas: translateLabel(t, 'canvas.chat.tool_labels.analyze_canvas', '查看画布'),
        rearrange_items: translateLabel(t, 'canvas.chat.tool_labels.rearrange_items', '整理布局'),
        wait_for_task: translateLabel(t, 'canvas.chat.tool_labels.wait_for_task', '等待任务'),
        ask_user: translateLabel(t, 'canvas.chat.tool_labels.ask_user', '询问用户'),
        Agent: translateLabel(t, 'canvas.chat.tool_labels.Agent', '子代理'),
    }
    return toolLabels[name] || name
}

function isCustomInteractionOption(option: any): boolean {
    const label = String(option?.label || '').trim().toLowerCase()
    const value = String(option?.value || '').trim().toLowerCase()
    const description = String(option?.description || '').trim().toLowerCase()
    const combined = `${label} ${value} ${description}`

    if (!combined) {
        return false
    }

    return (
        combined.includes('其他')
        || combined.includes('其它')
        || combined.includes('自定义')
        || combined.includes('custom')
        || combined.includes('other')
    )
}

function normalizeInteractionFromBlock(block: MessageBlock): PendingInteraction | null {
    const requestId = String(block.payload.request_id || block.payload.requestId || '').trim()
    const question = String(block.payload.question || '').trim()
    const rawStatus = String(block.payload.status || block.status || '').trim().toLowerCase()
    const schema = block.payload.schema && typeof block.payload.schema === 'object'
        ? block.payload.schema as PendingInteraction['schema']
        : null
    const options = Array.isArray(block.payload.options) ? block.payload.options : []

    if (!requestId || (!question && !schema?.title)) {
        return null
    }

    return {
        ...block.payload,
        request_id: requestId,
        question,
        content: typeof block.payload.content === 'string' ? block.payload.content : null,
        kind: String(block.payload.kind || '').trim() || undefined,
        schema: schema ?? {
            title: question || 'Interaction',
            fields: [{
                id: 'response',
                label: question || 'Response',
                type: options.length > 0 ? 'radio' : 'text',
                options,
            }],
        },
        answers: block.payload.answers && typeof block.payload.answers === 'object'
            ? block.payload.answers as Record<string, any>
            : null,
        status: rawStatus === 'submitted'
            ? 'submitted'
            : rawStatus === 'processing'
                ? 'processing'
                : rawStatus === 'failed'
                    ? 'failed'
                    : 'pending',
    }
}

function InteractionBlock({
    block,
    parentMessageContent,
    hasUserReplyBelow = false,
    conversationId,
    onPreview,
    onRequestEcommerceReferenceImages,
    onUploadEcommerceReferenceImage,
    maxEcommerceReferenceImages,
}: {
    block: MessageBlock
    parentMessageContent?: string | null
    isDark: boolean
    hasUserReplyBelow?: boolean
    conversationId?: string | number | null
    onPreview: (url: string) => void
    onRequestEcommerceReferenceImages?: (
        source: EcommerceReferenceImageSource,
        onSelect: (urls: string[]) => void,
        options?: EcommerceReferenceImageRequestOptions,
    ) => void
    onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>
    maxEcommerceReferenceImages?: number
}) {
    const respondToAgent = useChatStore(s => s.respondToAgent)
    const interaction = React.useMemo(() => normalizeInteractionFromBlock(block), [block])

    if (!interaction) {
        return null
    }

    return (
        <div data-testid="interaction-block-shell" style={{ width: '85%', maxWidth: '85%' }}>
            {isEcommerceInteractionKind(interaction.kind) ? (
                <EcommerceInteractionCard
                    interaction={interaction}
                    disabled={interaction.status === 'submitted'}
                    conversationId={conversationId}
                    onPreviewImage={onPreview}
                    onRequestReferenceImages={onRequestEcommerceReferenceImages}
                    onUploadReferenceImage={onUploadEcommerceReferenceImage}
                    maxReferenceImages={maxEcommerceReferenceImages}
                    onRespond={(requestId, answer, displayLabel, answers) => {
                        void respondToAgent(requestId, answer, displayLabel, answers)
                    }}
                />
            ) : (
            <InteractionCard
                interaction={{
                    ...interaction,
                    schema: interaction.schema
                        ? {
                            ...interaction.schema,
                            fields: (interaction.schema.fields || []).map((field) => ({
                                ...field,
                                options: Array.isArray(field.options)
                                    ? field.options.filter((option) => !isCustomInteractionOption(option))
                                    : field.options,
                            })),
                        }
                        : interaction.schema,
                }}
                fallbackContent={parentMessageContent}
                disabled={interaction.status === 'submitted' || hasUserReplyBelow}
                onRespond={(requestId, answer, displayLabel, answers) => {
                    void respondToAgent(requestId, answer, displayLabel, answers)
                }}
            />
            )}
        </div>
    )
}

const SubagentCard = React.memo(SubagentCardImpl)

function SubagentCardImpl({
    block,
    isDark,
    onPreview,
    onDownload,
    messageId,
    deletedAgentMediaKeys = [],
    canReplayCompletedMedia = true,
    mirroredChildBlockIds,
    isHistoryLoaded = false,
    conversationId,
    hasUserReplyBelow = false,
}: {
    block: MessageBlock
    isDark: boolean
    onPreview: (url: string) => void
    onDownload: (url: string, e: React.MouseEvent) => void
    messageId: string | number
    deletedAgentMediaKeys?: string[]
    canReplayCompletedMedia?: boolean
    mirroredChildBlockIds?: ReadonlySet<string>
    isHistoryLoaded?: boolean
    conversationId?: string | number | null
    hasUserReplyBelow?: boolean
}) {
    const { t } = useTranslation()
    const [expanded, setExpanded] = React.useState(Boolean(block.expanded))

    React.useEffect(() => {
        setExpanded(Boolean(block.expanded))
    }, [block.expanded, block.id])

    const label = String(block.label || block.payload.label || block.payload.result?.label || '')
    const purpose = String(block.payload.purpose || block.payload.result?.purpose || label || '').trim()
    const purposeLabel = getLocalizedSubagentPurpose(
        t,
        purpose,
        block.payload.subagentType
        ?? block.payload.subagent_type
        ?? block.payload.result?.subagentType
        ?? block.payload.result?.subagent_type,
    )
    const status = String(block.payload.status || block.status || 'running').toLowerCase()
    const summary = String(
        block.summary
        || block.payload.summary
        || block.payload.result?.result
        || block.payload.result?.message
        || block.payload.result?.error
        || '',
    )
    const statusIcon = {
        pending: <Loader2 size={14} color="var(--app-foreground-subtle)" />,
        running: <Loader2 size={14} color="var(--app-primary)" style={{ animation: 'spin 1s linear infinite' }} />,
        completed: <CheckCircle2 size={14} color="var(--app-success)" />,
        failed: <XCircle size={14} color="var(--app-danger)" />,
    }
    const children = [...(block.children || [])].sort((a, b) => a.order - b.order)

    return (
        <div style={{
            borderRadius: 16,
            border: '1px solid var(--app-border)',
            backgroundColor: 'var(--app-glass)',
            maxWidth: '85%',
            width: '85%',
            overflow: 'hidden',
        }}>
            <button
                type="button"
                aria-label={label ? `展开下游机器人 ${label}` : '展开下游机器人'}
                onClick={() => setExpanded((current) => !current)}
                style={{
                    width: '100%',
                    padding: '12px 14px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                }}
            >
                <Wrench size={14} color="var(--app-primary)" style={{ marginTop: 3 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontWeight: 600 }}>{translateLabel(t, 'canvas.chat.subagent.title', '子代理')}</span>
                        {statusIcon[status as keyof typeof statusIcon] || statusIcon.completed}
                        <span style={{
                            padding: '2px 8px',
                            borderRadius: 999,
                            backgroundColor: status === 'completed'
                                ? (isDark ? 'color-mix(in srgb, var(--app-success) 15%, transparent)' : 'color-mix(in srgb, var(--app-success) 12%, transparent)')
                                : status === 'failed'
                                    ? (isDark ? 'color-mix(in srgb, var(--app-danger) 15%, transparent)' : 'color-mix(in srgb, var(--app-danger) 12%, transparent)')
                                    : (isDark ? 'color-mix(in srgb, var(--app-primary) 15%, transparent)' : 'color-mix(in srgb, var(--app-primary) 12%, transparent)'),
                            color: status === 'completed'
                                ? (isDark ? 'var(--app-success)' : 'var(--app-success)')
                                : status === 'failed'
                                    ? (isDark ? 'var(--app-danger)' : 'var(--app-danger)')
                                    : (isDark ? 'var(--app-primary)' : 'var(--app-primary)'),
                            fontSize: 11,
                            fontWeight: 600,
                        }}>
                            {status === 'completed'
                                ? translateLabel(t, 'canvas.chat.subagent.status.completed', '已完成')
                                : status === 'failed'
                                    ? translateLabel(t, 'canvas.chat.subagent.status.failed', '失败')
                                    : status === 'pending'
                                        ? translateLabel(t, 'canvas.chat.subagent.status.pending', '待处理')
                                        : translateLabel(t, 'canvas.chat.subagent.status.running', '进行中')}
                        </span>
                    </div>
                    {purpose && (
                        <div style={{ marginTop: 4, fontSize: 13, color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>
                            <span style={{ marginRight: 8, fontSize: 11, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)' }}>
                                {translateLabel(t, 'canvas.chat.subagent.purpose', '任务目的')}
                            </span>
                            {purposeLabel}
                        </div>
                    )}
                </div>
                <ChevronDown
                    size={16}
                    color="var(--app-foreground-subtle)"
                    style={{
                        marginTop: 2,
                        transition: 'transform 0.2s',
                        transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                    }}
                />
            </button>
            {expanded && (children.length > 0 || summary) && (
                <div style={{
                    padding: '0 14px 14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    borderTop: '1px solid var(--app-border)',
                }}>
                    {summary && (
                        <div style={{ fontSize: 12, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)', marginTop: 10 }}>
                            {summary}
                        </div>
                    )}
                    {children.map((childBlock) => (
                        <MessageBlockRenderer
                            key={`${block.id}-${childBlock.id}`}
                            block={childBlock}
                            isDark={isDark}
                            onPreview={onPreview}
                            onDownload={onDownload}
                            messageId={messageId}
                            deletedAgentMediaKeys={deletedAgentMediaKeys}
                            canReplayCompletedMedia={canReplayCompletedMedia}
                            mirroredChildBlockIds={mirroredChildBlockIds}
                            disableCanvasReplay={Boolean(mirroredChildBlockIds?.has(childBlock.id))}
                            isHistoryLoaded={isHistoryLoaded}
                            conversationId={conversationId}
                            hasUserReplyBelow={hasUserReplyBelow}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}

function getPreferredToolLabel(name: string, t: TFunction) {
    if (name === 'analyze_image') {
        return t('canvas.chat.tool_labels.analyze_image', '图片分析')
    }
    return getToolLabel(name, t)
}

function extractAnalyzeImageText(source: unknown): string {
    if (typeof source === 'string') {
        const text = source.trim()
        if (!text) {
            return ''
        }
        if (!text.startsWith('{')) {
            return text
        }
        try {
            const parsed = JSON.parse(text)
            if (parsed && typeof parsed.analysis === 'string' && parsed.analysis.trim().length > 0) {
                return parsed.analysis
            }
            if (parsed && typeof parsed.description === 'string' && parsed.description.trim().length > 0) {
                return parsed.description
            }
            if (parsed && typeof parsed.message === 'string' && parsed.message.trim().length > 0) {
                return parsed.message
            }
        } catch {
            return text
        }
        return text
    }

    if (!source || typeof source !== 'object') {
        return ''
    }

    const record = source as Record<string, any>
    const text = record.analysis || record.description || record.message || record.content
    if (typeof text === 'string' && text.trim().length > 0) {
        return text
    }

    try {
        return JSON.stringify(source)
    } catch {
        return ''
    }
}

const AnalyzeImageMediaCard = React.memo(AnalyzeImageMediaCardImpl)

function AnalyzeImageMediaCardImpl({
    block,
    isDark,
    onPreview,
    conversationId,
}: {
    block: MessageBlock
    parentMessageContent?: string | null
    isDark: boolean
    onPreview: (url: string) => void
    conversationId?: string | number | null
}) {
    const { t } = useTranslation()
    const status = String(block.payload.status || block.status || 'completed').toLowerCase()
    const isRunning = status === 'running' || status === 'pending' || status === 'streaming'
    const analysisText = extractAnalyzeImageText(
        block.payload.text
        || block.payload.analysis
        || block.payload.result
        || '',
    )
    const hasContent = isRunning || analysisText.length > 0
    const [expanded, setExpanded] = React.useState(false)
    const previousRunningRef = React.useRef(isRunning)

    React.useEffect(() => {
        if (isRunning && analysisText.length > 0) {
            setExpanded(true)
        } else if (!isRunning && previousRunningRef.current) {
            setExpanded(false)
        }
        previousRunningRef.current = isRunning
    }, [analysisText.length, isRunning])

    const statusIcon = {
        pending: <Loader2 size={14} color="var(--app-foreground-subtle)" />,
        running: <Loader2 size={14} color="var(--app-primary)" style={{ animation: 'spin 1s linear infinite' }} />,
        streaming: <Loader2 size={14} color="var(--app-primary)" style={{ animation: 'spin 1s linear infinite' }} />,
        completed: <CheckCircle2 size={14} color="var(--app-success)" />,
        failed: <XCircle size={14} color="var(--app-danger)" />,
    }

    return (
        <div style={{
            borderRadius: 16,
            border: `1px solid ${isDark ? 'var(--app-surface-muted)' : 'var(--app-border)'}`,
            background: 'var(--app-glass)',
            maxWidth: '85%',
            width: '85%',
            overflow: 'hidden',
        }}>
            <button
                type="button"
                aria-label={getPreferredToolLabel('analyze_image', t)}
                onClick={() => hasContent && setExpanded((current) => !current)}
                style={{
                    width: '100%',
                    padding: '12px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontSize: 13,
                    color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                    cursor: hasContent ? 'pointer' : 'default',
                    transition: 'background 0.15s',
                    border: 'none',
                    background: 'transparent',
                    textAlign: 'left',
                }}
                onMouseEnter={(e) => { if (hasContent) e.currentTarget.style.backgroundColor = 'var(--app-control-hover)' }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
            >
                <Wrench size={14} color="var(--app-primary)" />
                <span style={{ fontWeight: 500, flex: 1 }}>{getPreferredToolLabel('analyze_image', t)}</span>
                {statusIcon[status as keyof typeof statusIcon] || statusIcon.completed}
                {hasContent && (
                    <ChevronDown
                        size={16}
                        color="var(--app-foreground-subtle)"
                        style={{
                            transition: 'transform 0.2s',
                            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                        }}
                    />
                )}
            </button>
            {expanded && (
                <div
                    style={{
                        padding: '0 14px 12px',
                        fontSize: 13,
                        color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                        lineHeight: 1.6,
                        borderTop: '1px solid var(--app-border)',
                        paddingTop: 10,
                        maxHeight: 240,
                        overflowX: 'hidden',
                        overflowY: 'auto',
                    }}
                    data-testid="analyze-image-body"
                >
                    {analysisText ? (
                        <div className="group relative" style={{ width: '100%', maxWidth: '100%' }}>
                            <MarkdownContent content={analysisText} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                            <CopyButton text={analysisText} isDark={isDark} isUser={false} />
                        </div>
                    ) : isRunning ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--app-foreground-subtle)' }}>
                            <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                            <span>{t('canvas.chat.analyzing_image', '正在分析图片')}</span>
                        </div>
                    ) : null}
                </div>
            )}
        </div>
    )
}

const ToolCallCard = React.memo(ToolCallCardImpl)

function ToolCallCardImpl({
    toolCall,
    isDark,
    onPreview,
    conversationId,
}: {
    toolCall: ToolCallInfo
    isDark: boolean
    onPreview: (url: string) => void
    conversationId?: string | number | null
}) {
    const { t } = useTranslation()
    const isAnalyzeImage = toolCall.name === 'analyze_image'
    const isRunning = toolCall.status === 'running' || toolCall.status === 'pending'
    const [expanded, setExpanded] = React.useState(isAnalyzeImage ? isRunning : false)
    const previousRunningRef = React.useRef(isRunning)

    const statusIcon = {
        pending: <Loader2 size={14} color="var(--app-foreground-subtle)" />,
        running: <Loader2 size={14} color="var(--app-primary)" style={{ animation: 'spin 1s linear infinite' }} />,
        completed: <CheckCircle2 size={14} color="var(--app-success)" />,
        failed: <XCircle size={14} color="var(--app-danger)" />,
    }

    const analysisResult = isAnalyzeImage ? extractAnalyzeImageText(toolCall.result) : null
    const streamingText = isAnalyzeImage ? extractAnalyzeImageText(toolCall.streamingText) : (toolCall.streamingText || '')
    const isActivelyStreaming = isRunning && streamingText.length > 0
    const hasContent = isRunning || !!analysisResult || streamingText.length > 0

    React.useEffect(() => {
        if (!isAnalyzeImage) {
            return
        }

        if (isRunning) {
            setExpanded(true)
        } else if (previousRunningRef.current && !isRunning) {
            setExpanded(false)
        }

        previousRunningRef.current = isRunning
    }, [isAnalyzeImage, isRunning])

    const isExpanded = isAnalyzeImage && expanded

    if (isAnalyzeImage) {
        return (
            <div style={{
                borderRadius: 12,
                border: '1px solid var(--app-border)',
                backgroundColor: 'var(--app-glass)',
                maxWidth: '85%',
                width: '85%',
                overflow: 'hidden',
            }}>
                <button
                    type="button"
                    aria-label={getPreferredToolLabel(toolCall.name, t)}
                    onClick={() => hasContent && setExpanded(!expanded)}
                    style={{
                        width: '100%',
                        padding: '10px 14px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontSize: 13,
                        color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                        cursor: hasContent ? 'pointer' : 'default',
                        transition: 'background 0.15s',
                        border: 'none',
                        background: 'transparent',
                        textAlign: 'left',
                    }}
                    onMouseEnter={(e) => { if (hasContent) e.currentTarget.style.backgroundColor = 'var(--app-control-hover)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                >
                    <Wrench size={14} color="var(--app-primary)" />
                    <span style={{ fontWeight: 500, flex: 1 }}>{getPreferredToolLabel(toolCall.name, t)}</span>
                    {statusIcon[toolCall.status]}
                    {hasContent && (
                        <ChevronDown
                            size={16}
                            color="var(--app-foreground-subtle)"
                            style={{
                                transition: 'transform 0.2s',
                                transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                            }}
                        />
                    )}
                </button>
                {isExpanded && (
                    <div style={{
                        padding: '0 14px 12px',
                        fontSize: 13,
                        color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                        lineHeight: 1.6,
                        borderTop: '1px solid var(--app-border)',
                        paddingTop: 10,
                        maxHeight: 240,
                        overflowX: 'hidden',
                        overflowY: 'auto',
                        }} data-testid="analyze-image-body">
                        {isActivelyStreaming ? (
                            <div className="group relative" style={{ width: '100%', maxWidth: '100%' }}>
                    <MarkdownContent content={streamingText} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                                <span style={{
                                    display: 'inline-block',
                                    width: 6,
                                    height: 14,
                                    backgroundColor: 'var(--app-primary)',
                                    borderRadius: 1,
                                    marginLeft: 2,
                                    animation: 'blink 1s infinite',
                                    verticalAlign: 'text-bottom',
                                }} />
                                <CopyButton text={streamingText} isDark={isDark} isUser={false} />
                            </div>
                        ) : isRunning ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--app-foreground-subtle)' }}>
                                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                                 <span>{t('canvas.chat.analyzing_image', '正在分析图片')}</span>
                            </div>
                        ) : analysisResult ? (
                            <div className="group relative" style={{ width: '100%', maxWidth: '100%' }}>
                    <MarkdownContent content={analysisResult} isDark={isDark} onPreview={onPreview} conversationId={conversationId} />
                                <CopyButton text={analysisResult} isDark={isDark} isUser={false} />
                            </div>
                        ) : null}
                    </div>
                )}
            </div>
        )
    }

    return (
        <div style={{
            padding: '8px 12px',
            borderRadius: 12,
            border: '1px solid var(--app-border)',
            backgroundColor: 'var(--app-glass)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
            maxWidth: '85%',
        }}>
            <Wrench size={14} color="var(--app-foreground-subtle)" />
            <span>{getPreferredToolLabel(toolCall.name, t)}</span>
            {statusIcon[toolCall.status]}
            {toolCall.result?.message && (
                <span style={{ color: 'var(--app-foreground-subtle)', fontSize: 12, marginLeft: 4 }}>{toolCall.result.message}</span>
            )}
        </div>
    )
}

function AnalysisIntroText({ skillId, isDark }: { skillId: string; isDark: boolean }) {
    const { t } = useTranslation()
    const skill = CHAT_SKILL_META[skillId as keyof typeof CHAT_SKILL_META]
    if (!skill) return null
    const skillName = t(skill.nameKey)
    return (
        <div style={{
            fontSize: 14,
            lineHeight: 1.6,
            color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
            padding: '10px 14px',
            borderRadius: 16,
            backgroundColor: 'var(--app-control)',
            maxWidth: '85%',
        }}>
            {t('canvas.chat.analysis_intro', {
                skillName,
            })}
        </div>
    )
}

function SkillBadge({ skillId }: { skillId: string }) {
    const { t } = useTranslation()
    const isDark = useIsDarkMode()
    const skill = CHAT_SKILL_META[skillId as keyof typeof CHAT_SKILL_META]
    if (!skill) return null
    const Icon = skill.icon

    return (
        <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 8px 2px 6px',
            borderRadius: 8,
            backgroundColor: isDark ? `${skill.color}22` : `${skill.color}11`,
            border: `1px solid ${isDark ? `${skill.color}44` : `${skill.color}33`}`,
            marginBottom: 6,
        }}>
            <div style={{ color: skill.color, display: 'flex', alignItems: 'center' }}>
                <Icon size={14} />
            </div>
            <span style={{
                fontSize: 11,
                fontWeight: 600,
                color: skill.color,
            }}>{t(skill.nameKey)}</span>
        </div>
    )
}

function PlainTextContent({
    content,
    isDark,
}: {
    content: string
    isDark: boolean
}) {
    return (
        <div
            style={{
                fontSize: 14,
                lineHeight: 1.7,
                color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                userSelect: 'text',
                WebkitUserSelect: 'text',
            }}
        >
            {content}
        </div>
    )
}

// Memoized so finalized message content is not re-parsed by ReactMarkdown on every
// parent re-render (streaming deltas, forward-selection toggles, sibling block updates).
const MarkdownContent = React.memo(MarkdownContentImpl)

function MarkdownContentImpl({
    content,
    isDark,
    onPreview,
    conversationId,
    enableArtifactReferences = true,
}: {
    content: string
    isDark: boolean
    onPreview?: (url: string) => void
    conversationId?: string | number | null
    enableArtifactReferences?: boolean
}) {
    const { t } = useTranslation()
    const artifactReferenceRemarkPlugin = React.useMemo(
        () => enableArtifactReferences ? createGenerationArtifactReferenceRemarkPlugin() : null,
        [enableArtifactReferences],
    )
    const workspaceFileReferenceRemarkPlugin = React.useMemo(
        () => createCanvasWorkspaceFileReferenceRemarkPlugin(),
        [],
    )

    return (
        <div
            className="markdown-body"
            style={{
                fontSize: 14,
                lineHeight: 1.7,
                color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                whiteSpace: 'normal',
                wordBreak: 'break-word',
                userSelect: 'text',
                WebkitUserSelect: 'text',
            }}
        >
            <ReactMarkdown
                remarkPlugins={[
                    remarkGfm,
                    workspaceFileReferenceRemarkPlugin,
                    ...(artifactReferenceRemarkPlugin ? [artifactReferenceRemarkPlugin] : []),
                ]}
                urlTransform={normalizeMarkdownRenderUrl}
                components={{
                    h1: ({ children }) => <h1 style={{ fontSize: 20, fontWeight: 700, margin: '16px 0 8px', color: isDark ? 'var(--app-primary-foreground)' : 'var(--app-foreground)' }}>{children}</h1>,
                    h2: ({ children }) => <h2 style={{ fontSize: 17, fontWeight: 700, margin: '14px 0 6px', color: isDark ? 'var(--app-primary-foreground)' : 'var(--app-foreground)' }}>{children}</h2>,
                    h3: ({ children }) => <h3 style={{ fontSize: 15, fontWeight: 600, margin: '12px 0 4px', color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)' }}>{children}</h3>,
                    p: ({ children }) => <p style={{ margin: '6px 0' }}>{children}</p>,
                    ul: ({ children }) => <ul style={{ margin: '4px 0', paddingLeft: 20 }}>{children}</ul>,
                    ol: ({ children }) => <ol style={{ margin: '4px 0', paddingLeft: 20 }}>{children}</ol>,
                    li: ({ children }) => <li style={{ margin: '2px 0' }}>{children}</li>,
                    strong: ({ children }) => <strong style={{ fontWeight: 700, color: isDark ? 'var(--app-primary-foreground)' : 'var(--app-foreground)' }}>{children}</strong>,
                    em: ({ children }) => <em>{children}</em>,
                    blockquote: ({ children }) => (
                        <blockquote style={{
                            borderLeft: `3px solid ${isDark ? 'var(--app-foreground-muted)' : 'var(--app-border)'}`,
                            margin: '8px 0',
                            padding: '4px 12px',
                            color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-muted)',
                        }}>{children}</blockquote>
                    ),
                    code: ({ className, children, ...props }) => {
                        const isInline = !className
                        if (isInline) {
                            const referencedArtifact = enableArtifactReferences
                                ? normalizeGenerationArtifactRef(String(children || '').trim())
                                : null
                            if (referencedArtifact) {
                                return (
                                    <GenerationArtifactReferenceChip
                                        artifactRef={referencedArtifact}
                                        conversationId={conversationId}
                                        isDark={isDark}
                                        onPreviewImage={(url) => onPreview?.(url)}
                                    />
                                )
                            }
                            const referencedWorkspaceMedia = normalizeWorkspaceMediaReference(String(children || '').trim())
                            if (referencedWorkspaceMedia) {
                                return (
                                    <CanvasWorkspaceMediaReferenceChip
                                        filePath={referencedWorkspaceMedia}
                                        conversationId={conversationId}
                                        isDark={isDark}
                                        t={t}
                                        onPreview={onPreview}
                                    />
                                )
                            }

                            return (
                                <code style={{
                                    padding: '1px 6px',
                                    borderRadius: 4,
                                    backgroundColor: 'var(--app-control)',
                                    fontSize: 13,
                                    fontFamily: 'Menlo, Monaco, Consolas, monospace',
                                    color: isDark ? 'var(--app-warning)' : 'var(--app-danger)',
                                }} {...props}>{children}</code>
                            )
                        }
                        return (
                            <code style={{
                                display: 'block',
                                padding: 12,
                                borderRadius: 8,
                                backgroundColor: isDark ? 'var(--app-surface-muted)' : 'var(--app-surface-muted)',
                                border: '1px solid var(--app-border)',
                                fontSize: 13,
                                fontFamily: 'Menlo, Monaco, Consolas, monospace',
                                overflowX: 'auto',
                                margin: '8px 0',
                                lineHeight: 1.5,
                                whiteSpace: 'pre',
                            }} className={className} {...props}>{children}</code>
                        )
                    },
                    pre: ({ children }) => <>{children}</>,
                    table: ({ children }) => (
                        <div style={{ overflowX: 'auto', margin: '8px 0' }}>
                            <table style={{
                                borderCollapse: 'collapse',
                                width: '100%',
                                fontSize: 13,
                                border: '1px solid var(--app-border-strong)',
                            }}>{children}</table>
                        </div>
                    ),
                    th: ({ children }) => (
                        <th style={{
                            padding: '6px 10px',
                            border: `1px solid ${isDark ? 'var(--app-border-strong)' : 'var(--app-border)'}`,
                            backgroundColor: 'var(--app-surface-muted)',
                            textAlign: 'left',
                            fontWeight: 600,
                            color: isDark ? 'var(--app-foreground)' : 'var(--app-foreground)',
                        }}>{children}</th>
                    ),
                    td: ({ children }) => (
                        <td style={{
                            padding: '6px 10px',
                            border: '1px solid var(--app-border)',
                            color: isDark ? 'var(--app-foreground-muted)' : 'var(--app-foreground-muted)',
                        }}>{children}</td>
                    ),
                    a: ({ href, children }) => (
                        (() => {
                            const referencedArtifact = enableArtifactReferences ? decodeGenerationArtifactReferenceHref(href) : null
                            if (referencedArtifact) {
                                return (
                                    <GenerationArtifactReferenceChip
                                        artifactRef={referencedArtifact}
                                        conversationId={conversationId}
                                        isDark={isDark}
                                        onPreviewImage={(url) => onPreview?.(url)}
                                    />
                                )
                            }
                            const referencedWorkspaceMedia = decodeCanvasWorkspaceFileReferenceHref(href)
                            if (referencedWorkspaceMedia) {
                                return (
                                    <CanvasWorkspaceMediaReferenceChip
                                        filePath={referencedWorkspaceMedia}
                                        conversationId={conversationId}
                                        isDark={isDark}
                                        t={t}
                                        onPreview={onPreview}
                                    />
                                )
                            }

                            return (
                                <a
                                    href={ensureFullUrl(href)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{
                                        color: 'var(--app-primary)',
                                        textDecoration: 'none',
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.textDecoration = 'underline'}
                                    onMouseLeave={(e) => e.currentTarget.style.textDecoration = 'none'}
                                >{children}</a>
                            )
                        })()
                    ),
                    img: ({ src, alt }) => (
                        <CanvasMarkdownImage
                            src={src || ''}
                            alt={alt || ''}
                            conversationId={conversationId}
                            onPreview={onPreview}
                        />
                    ),
                    hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--app-border)', margin: '12px 0' }} />,
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    )
}

function CopyButton({
    text,
    isDark,
    isUser,
    extraActions,
}: {
    text: string
    isDark: boolean
    isUser: boolean
    extraActions?: React.ReactNode
}) {
    const { t } = useTranslation()
    const [copied, setCopied] = React.useState(false)

    const handleCopy = async (e: React.MouseEvent) => {
        e.stopPropagation()
        try {
            await navigator.clipboard.writeText(text)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch (err) {
            console.error('Failed to copy:', err)
        }
    }

    return (
        <div
            className="opacity-0 group-hover:opacity-100 transition-opacity"
            style={{
                position: 'absolute',
                top: 2,
                [isUser ? 'right' : 'left']: '100%',
                [isUser ? 'marginRight' : 'marginLeft']: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                transition: 'all 0.2s',
            }}
        >
            <button
                onClick={handleCopy}
                title={copied ? t('canvas.chat.copied') : t('canvas.chat.copy')}
                style={{
                    padding: 6,
                    borderRadius: 8,
                    border: 'none',
                    backgroundColor: 'transparent',
                    color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--app-control-hover)'
                    e.currentTarget.style.color = 'var(--app-foreground)'
                }}
                onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent'
                    e.currentTarget.style.color = 'var(--app-foreground-subtle)'
                }}
            >
                {copied ? <Check size={14} color="var(--app-success)" /> : <Copy size={14} />}
            </button>
            {extraActions}
        </div>
    )
}
