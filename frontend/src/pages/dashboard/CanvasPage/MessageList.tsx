import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { Virtuoso } from 'react-virtuoso'

import { useIsDarkMode } from '@/hooks/useTheme'
import { useChatStore, type ChatMessage, type MessageBlock } from '@/store/canvasAgentStore'
import { hasRenderableChatMessage, hasRenderableMessageBlock } from '@/store/canvasMessageVisibility'
import { type CanvasItem } from '@/api/endpoints/projects'
import {
    agentApi,
    isHarnessWorkspaceRelativePath,
    normalizeHarnessWorkspacePath,
} from '@/api/endpoints/agent'
import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'

import {
    buildRenderableBlocks,
    ensureFullUrl,
    formatReplyTimestamp,
    MessageBlockRenderer,
    MessageBubble,
    ThinkingIndicator,
} from './components/MessageListRenderers'
import type {
    EcommerceReferenceImageRequestOptions,
    EcommerceReferenceImageSource,
} from '@/components/agent/EcommerceInteractionCard'
import { dedupeEcommerceInteractionMessages } from '@/components/agent/ecommerceInteractionDedupe'
import { getAgentRenderWeightSnapshot, shouldVirtualizeAgentItems } from '../agentMedia/agentRenderWeight'
import { handleScrollableWheel } from './scrollableWheel'

function hasVisibleUserReply(message: ChatMessage): boolean {
    if (message.role !== 'user') {
        return false
    }

    if (String(message.content || '').trim()) {
        return true
    }

    if (Array.isArray(message.attachments) && message.attachments.length > 0) {
        return true
    }

    return Array.isArray(message.blocks) && message.blocks.some((block) => {
        if (block.visible === false) {
            return false
        }
        if (String(block.payload?.text || '').trim()) {
            return true
        }
        return Object.keys(block.payload || {}).length > 0
    })
}

// Above this many messages the historical list is windowed (react-virtuoso) so a long
// conversation does not keep every bubble mounted. Below it we keep the plain map so short
// conversations (and the jsdom render tests, which have no layout engine) behave as before.
const VIRTUALIZE_MESSAGE_THRESHOLD = 50
// Virtuoso requires firstItemIndex to only ever decrease; we start high and subtract the
// number of older messages prepended on each "load earlier" page so the viewport stays put.
const VIRTUOSO_START_INDEX = 1_000_000

// Stable Footer for the virtualized list. The live streaming region / thinking indicator is
// passed through Virtuoso `context` (rather than a new component type each render) so the
// memoized MessageBubble rows are not remounted while the footer updates.
type CanvasMessageListContext = { footer: React.ReactNode }
function CanvasVirtuosoFooter({ context }: { context?: CanvasMessageListContext }) {
    return <>{context?.footer ?? null}</>
}
const CANVAS_VIRTUOSO_COMPONENTS = { Footer: CanvasVirtuosoFooter }
const EMPTY_RENDERABLE_BLOCKS: MessageBlock[] = []
const EMPTY_STREAMING_RENDER_STATE = {
    blocks: EMPTY_RENDERABLE_BLOCKS,
    mirroredChildBlockIds: new Set<string>(),
}

interface MessageListProps {
    messages: ChatMessage[]
    streamingBlocks: MessageBlock[]
    isStreaming: boolean
    conversationId?: string | number | null
    runStatus?: 'idle' | 'running' | 'waiting_input' | 'completed' | 'failed' | 'blocked' | 'cancelled'
    onFocusItem?: (itemId: string) => void
    canvasItems?: CanvasItem[]
    deletedAgentMediaKeys?: string[]
    canReplayCompletedMedia?: boolean
    forwardSelectionMode?: boolean
    selectedForwardMessageIds?: ReadonlySet<string>
    onEnterForwardSelectionMode?: (messageId: string) => void
    onToggleForwardMessage?: (messageId: string) => void
    pauseThinkingAnimation?: boolean
    onRequestEcommerceReferenceImages?: (
        source: EcommerceReferenceImageSource,
        onSelect: (urls: string[]) => void,
        options?: EcommerceReferenceImageRequestOptions,
    ) => void
    onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>
    maxEcommerceReferenceImages?: number
}

function getBlockScrollAnchorKey(block: MessageBlock): string {
    const payload = block.payload || {}
    const textLength = String(
        payload.text
        ?? payload.content
        ?? payload.stream_text
        ?? payload.message
        ?? payload.summary
        ?? payload.analysis
        ?? '',
    ).length
    const childrenKey = block.children?.length
        ? block.children.map(getBlockScrollAnchorKey).join(',')
        : ''
    return [
        block.id,
        block.status,
        block.revision ?? '',
        block.sourceSequence ?? '',
        textLength,
        childrenKey,
    ].join(':')
}

function getMessageScrollAnchorKey(message: ChatMessage | undefined): string {
    if (!message) {
        return ''
    }

    const blockKey = message.blocks?.length
        ? message.blocks.map(getBlockScrollAnchorKey).join('|')
        : ''
    return [
        message.id,
        String(message.content || '').length,
        message.attachments?.length ?? 0,
        message.blocks?.length ?? 0,
        blockKey,
    ].join(':')
}

export function MessageList({
    messages,
    streamingBlocks,
    isStreaming,
    conversationId: conversationIdProp,
    runStatus,
    onFocusItem,
    canvasItems = [],
    deletedAgentMediaKeys = [],
    canReplayCompletedMedia = true,
    forwardSelectionMode = false,
    selectedForwardMessageIds = new Set<string>(),
    onEnterForwardSelectionMode,
    onToggleForwardMessage,
    pauseThinkingAnimation = false,
    onRequestEcommerceReferenceImages,
    onUploadEcommerceReferenceImage,
    maxEcommerceReferenceImages,
}: MessageListProps) {
    const { t } = useTranslation()
    const isDark = useIsDarkMode()
    const storeConversationId = useChatStore(s => s.conversationId)
    const conversationId = conversationIdProp ?? storeConversationId
    const hiddenToolCalls = useChatStore(s => s.uiConfig.hiddenToolCalls)
    const loadOlderMessages = useChatStore(s => s.loadOlderMessages)
    const olderMessagesHasMore = useChatStore(s => {
        const id = s.conversationId
        if (id == null) return false
        return s.conversationSessions?.[String(id)]?.messagesPage?.hasMore ?? false
    })
    const visibleMessages = React.useMemo(
        () => dedupeEcommerceInteractionMessages(messages).filter(hasRenderableChatMessage),
        [messages],
    )
    // react-virtuoso prepend bookkeeping: keep the viewport anchored when older pages are
    // prepended by lowering firstItemIndex by exactly the number of messages added at the front.
    const [firstItemIndex, setFirstItemIndex] = React.useState(VIRTUOSO_START_INDEX)
    const prevFirstMessageIdRef = React.useRef<string | null>(null)
    React.useLayoutEffect(() => {
        // New conversation: reset the anchor (the Virtuoso instance is also keyed by id).
        setFirstItemIndex(VIRTUOSO_START_INDEX)
        prevFirstMessageIdRef.current = null
    }, [conversationId])
    React.useLayoutEffect(() => {
        const firstId = visibleMessages[0] ? String(visibleMessages[0].id) : null
        const prevFirstId = prevFirstMessageIdRef.current
        if (prevFirstId != null && firstId !== prevFirstId) {
            // The previous first message moved down by N — N older messages were prepended.
            const prependedCount = visibleMessages.findIndex((m) => String(m.id) === prevFirstId)
            if (prependedCount > 0) {
                setFirstItemIndex((value) => value - prependedCount)
            }
        }
        prevFirstMessageIdRef.current = firstId
    }, [visibleMessages])
    // Expose canvas items through a stable resolver so memoized MessageBubble props
    // are not invalidated every time the canvas array gets a new reference (e.g. on
    // each generated media insertion). Bubbles only need it to resolve @mention /
    // mark thumbnails, which does not require frame-accurate updates.
    const canvasItemsRef = React.useRef(canvasItems)
    canvasItemsRef.current = canvasItems
    const resolveMentionItem = React.useCallback(
        (id: string): CanvasItem | undefined => canvasItemsRef.current.find((item) => item.id === id),
        [],
    )
    const scrollRef = React.useRef<HTMLDivElement>(null)
    const isAtBottom = React.useRef(true)
    const lastMessageCount = React.useRef(visibleMessages.length)
    const [previewState, setPreviewState] = React.useState<{ src: string; ownedUrl?: string } | null>(null)
    const previewUrl = previewState?.src || null
    const closePreview = React.useCallback(() => {
        setPreviewState((current) => {
            if (current?.ownedUrl) {
                URL.revokeObjectURL(current.ownedUrl)
            }
            return null
        })
    }, [])
    React.useEffect(() => () => {
        if (previewState?.ownedUrl) {
            URL.revokeObjectURL(previewState.ownedUrl)
        }
    }, [previewState?.ownedUrl])
    const handlePreview = React.useCallback((url: string) => {
        const openResolvedPreview = (src: string, ownedUrl?: string) => {
            setPreviewState((current) => {
                if (current?.ownedUrl && current.ownedUrl !== ownedUrl) {
                    URL.revokeObjectURL(current.ownedUrl)
                }
                return { src, ownedUrl }
            })
        }

        if (!conversationId || !isHarnessWorkspaceRelativePath(url)) {
            openResolvedPreview(ensureFullUrl(url))
            return
        }

        const workspacePath = normalizeHarnessWorkspacePath(url)
        void agentApi.fetchWorkspaceFileBlob(String(conversationId), workspacePath)
            .then((blob) => {
                const objectUrl = URL.createObjectURL(blob)
                openResolvedPreview(objectUrl, objectUrl)
            })
            .catch(() => {
                openResolvedPreview(ensureFullUrl(url))
            })
    }, [conversationId])
    const [visibleRange, setVisibleRange] = React.useState<{ startIndex: number; endIndex: number } | null>(null)
    const [expandedCompactBlockIds, setExpandedCompactBlockIds] = React.useState<Set<string>>(() => new Set())
    const [virtuosoRecoveryEpoch, setVirtuosoRecoveryEpoch] = React.useState(0)
    const pageWasHiddenRef = React.useRef(false)
    const lastVirtuosoRecoveryAtRef = React.useRef(0)
    const streamingRenderState = React.useMemo(
        () => (streamingBlocks.length === 0
            ? EMPTY_STREAMING_RENDER_STATE
            : buildRenderableBlocks(streamingBlocks)),
        [streamingBlocks],
    )
    const visibleStreamingBlocks = React.useMemo(
        () => (streamingRenderState.blocks.length === 0
            ? EMPTY_RENDERABLE_BLOCKS
            : streamingRenderState.blocks.filter(hasRenderableMessageBlock)),
        [streamingRenderState.blocks],
    )
    const visibleMessageTailKey = React.useMemo(
        () => getMessageScrollAnchorKey(visibleMessages[visibleMessages.length - 1]),
        [visibleMessages],
    )
    const visibleStreamingBlocksKey = React.useMemo(
        () => visibleStreamingBlocks.map(getBlockScrollAnchorKey).join('|'),
        [visibleStreamingBlocks],
    )
    const isAgentBusy = isStreaming || runStatus === 'running'
    React.useEffect(() => {
        setExpandedCompactBlockIds(new Set())
        setVisibleRange(null)
    }, [conversationId])
    const hasUserReplyBelowByIndex = React.useMemo(() => {
        const suffixFlags = new Array<boolean>(visibleMessages.length).fill(false)
        let hasUserReplyBelow = false

        for (let index = visibleMessages.length - 1; index >= 0; index -= 1) {
            suffixFlags[index] = hasUserReplyBelow
            if (hasVisibleUserReply(visibleMessages[index])) {
                hasUserReplyBelow = true
            }
        }

        return suffixFlags
    }, [visibleMessages])
    const hasActivelyStreamingBlock = streamingBlocks.length > 0 && streamingBlocks.some((block) => {
        if (block.kind === 'text') {
            return block.status === 'streaming' && String(block.payload.text || '').trim().length > 0
        }
        if (block.uiKind === 'stream_panel') {
            return block.status === 'running' && String(block.payload.stream_text || '').trim().length > 0
        }
        return false
    })
    const showThinkingHint = isAgentBusy && streamingBlocks.length > 0 && !hasActivelyStreamingBlock

    const handleScroll = () => {
        if (!scrollRef.current) return
        const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
        const atBottom = scrollHeight - scrollTop - clientHeight < 50
        isAtBottom.current = atBottom
    }

    React.useEffect(() => {
        if (!scrollRef.current) return

        const shouldForceScroll = visibleMessages.length > lastMessageCount.current
        lastMessageCount.current = visibleMessages.length

        const frameId = window.requestAnimationFrame(() => {
            const container = scrollRef.current
            if (!container || (!isAtBottom.current && !shouldForceScroll)) {
                return
            }

            if (typeof container.scrollTo === 'function') {
                container.scrollTo({
                    top: container.scrollHeight,
                    behavior: shouldForceScroll ? 'smooth' : 'auto'
                })
            } else {
                container.scrollTop = container.scrollHeight
            }
        })

        return () => window.cancelAnimationFrame(frameId)
    }, [visibleMessages.length, visibleMessageTailKey, visibleStreamingBlocksKey])

    const handleDownload = React.useCallback(async (url: string, e?: React.MouseEvent) => {
        if (e) {
            e.stopPropagation()
            e.preventDefault()
        }
        try {
            const response = await fetch(url)
            const blob = await response.blob()
            const blobUrl = window.URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = blobUrl
            const filename = url.split('/').pop()?.split('?')[0] || 'generated-image.png'
            link.download = filename
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            window.URL.revokeObjectURL(blobUrl)
        } catch (error) {
            console.error('Download failed:', error)
            window.open(url, '_blank')
        }
    }, [])

    const renderWeightSnapshot = React.useMemo(
        () => getAgentRenderWeightSnapshot(visibleMessages),
        [visibleMessages],
    )
    const shouldVirtualizeMessages = shouldVirtualizeAgentItems(renderWeightSnapshot, {
        itemThreshold: 30,
        weightThreshold: 40,
    }) || visibleMessages.length > VIRTUALIZE_MESSAGE_THRESHOLD
    const recoverVirtualizedListAfterVisibilityResume = React.useCallback((bypassThrottle = false) => {
        if (!shouldVirtualizeMessages || visibleMessages.length === 0) {
            return
        }
        const now = Date.now()
        if (!bypassThrottle && now - lastVirtuosoRecoveryAtRef.current < 250) {
            return
        }
        lastVirtuosoRecoveryAtRef.current = now
        setVisibleRange(null)
        setVirtuosoRecoveryEpoch((value) => value + 1)
    }, [shouldVirtualizeMessages, visibleMessages.length])
    React.useEffect(() => {
        const handleVisibilityResume = (fallbackResumeSignal = false) => {
            if (document.visibilityState === 'hidden') {
                pageWasHiddenRef.current = true
                return
            }

            const resumedFromRecordedHide = pageWasHiddenRef.current
            pageWasHiddenRef.current = false
            if (resumedFromRecordedHide || fallbackResumeSignal) {
                recoverVirtualizedListAfterVisibilityResume(resumedFromRecordedHide)
            }
        }
        const handleVisibilityChange = () => {
            if (document.visibilityState === 'hidden') {
                pageWasHiddenRef.current = true
                return
            }
            handleVisibilityResume()
        }
        const handleFocusOrPageShow = () => handleVisibilityResume(true)

        if (document.visibilityState === 'hidden') {
            pageWasHiddenRef.current = true
        }

        document.addEventListener('visibilitychange', handleVisibilityChange)
        window.addEventListener('focus', handleFocusOrPageShow)
        window.addEventListener('pageshow', handleFocusOrPageShow)
        return () => {
            document.removeEventListener('visibilitychange', handleVisibilityChange)
            window.removeEventListener('focus', handleFocusOrPageShow)
            window.removeEventListener('pageshow', handleFocusOrPageShow)
        }
    }, [recoverVirtualizedListAfterVisibilityResume])

    // Shared per-index bubble renderer so the plain and virtualized paths stay identical.
    const getHeavyBlockRenderMode = React.useCallback((messageIndex: number, blockId: string): 'compact' | 'full' => {
        if (!shouldVirtualizeMessages || !visibleRange || expandedCompactBlockIds.has(blockId)) {
            return 'full'
        }
        const distance = messageIndex < visibleRange.startIndex
            ? visibleRange.startIndex - messageIndex
            : messageIndex > visibleRange.endIndex
                ? messageIndex - visibleRange.endIndex
                : 0
        return distance > 2 ? 'compact' : 'full'
    }, [expandedCompactBlockIds, shouldVirtualizeMessages, visibleRange])

    const handleExpandCompactBlock = React.useCallback((blockId: string) => {
        setExpandedCompactBlockIds((current) => {
            const next = new Set(current)
            next.add(blockId)
            return next
        })
    }, [])

    const renderBubble = (idx: number) => {
        const msg = visibleMessages[idx]
        if (!msg) return null
        let activeSkillId: string | undefined
        const showReplyTimestamp = msg.role === 'assistant' && visibleMessages[idx - 1]?.role === 'user'
        if (msg.role === 'assistant') {
            for (let i = idx - 1; i >= 0; i--) {
                if (visibleMessages[i].role === 'user' && visibleMessages[i].skillId) {
                    activeSkillId = visibleMessages[i].skillId || undefined
                    break
                }
            }
        }
        return (
            <MessageBubble
                key={msg.id}
                message={msg}
                isDark={isDark}
                onPreview={handlePreview}
                onDownload={handleDownload}
                onFocusItem={onFocusItem}
                resolveMentionItem={resolveMentionItem}
                activeSkillId={activeSkillId}
                replyTimestamp={showReplyTimestamp ? formatReplyTimestamp(msg.createdAt) : undefined}
                hiddenToolCalls={hiddenToolCalls}
                deletedAgentMediaKeys={deletedAgentMediaKeys}
                canReplayCompletedMedia={canReplayCompletedMedia}
                isHistoryLoaded={Boolean(msg.isHistoryLoaded)}
                forwardSelectionMode={forwardSelectionMode}
                selectedForwardMessageIds={selectedForwardMessageIds}
                onEnterForwardSelectionMode={onEnterForwardSelectionMode}
                onToggleForwardMessage={onToggleForwardMessage}
                conversationId={conversationId}
                hasUserReplyBelow={hasUserReplyBelowByIndex[idx]}
                getHeavyBlockRenderMode={(blockId: string) => getHeavyBlockRenderMode(idx, blockId)}
                onExpandCompactBlock={handleExpandCompactBlock}
                onRequestEcommerceReferenceImages={onRequestEcommerceReferenceImages}
                onUploadEcommerceReferenceImage={onUploadEcommerceReferenceImage}
                maxEcommerceReferenceImages={maxEcommerceReferenceImages}
            />
        )
    }
    // Streaming region + thinking indicators. Rendered as the Virtuoso Footer (virtualized
    // path) or inline after the messages (plain path), so it always sits at the conversation end.
    const streamingRegion = (
        <>
            {isAgentBusy && visibleStreamingBlocks.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {visibleStreamingBlocks
                            .sort((a, b) => a.order - b.order)
                            .map((block) => (
                                <MessageBlockRenderer
                                    key={block.id}
                                    block={block}
                                    isDark={isDark}
                                    onPreview={handlePreview}
                                    onDownload={handleDownload}
                                    messageId="streaming"
                                    deletedAgentMediaKeys={deletedAgentMediaKeys}
                                    canReplayCompletedMedia={canReplayCompletedMedia}
                                    mirroredChildBlockIds={streamingRenderState.mirroredChildBlockIds}
                                    conversationId={conversationId}
                                    onRequestEcommerceReferenceImages={onRequestEcommerceReferenceImages}
                                    onUploadEcommerceReferenceImage={onUploadEcommerceReferenceImage}
                                    maxEcommerceReferenceImages={maxEcommerceReferenceImages}
                                />
                            ))}
                    </div>
                </div>
            )}

            {isAgentBusy && streamingBlocks.length === 0 && (
                <ThinkingIndicator label={t('canvas.chat.thinking')} paused={pauseThinkingAnimation} />
            )}

            {showThinkingHint && (
                <ThinkingIndicator label={t('canvas.chat.thinking')} paused={pauseThinkingAnimation} />
            )}
        </>
    )

    return (
        <>
            {shouldVirtualizeMessages ? (
                <div
                    className="nowheel"
                    data-chat-message-scroll-root="true"
                    data-testid="chat-message-virtual-scroll"
                    data-recovery-epoch={virtuosoRecoveryEpoch}
                    data-canvas-text-selectable="true"
                    onWheel={handleScrollableWheel}
                    style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', userSelect: 'text', WebkitUserSelect: 'text' }}
                >
                    <Virtuoso
                        key={`${conversationId ?? 'none'}:${virtuosoRecoveryEpoch}`}
                        data={visibleMessages}
                        firstItemIndex={firstItemIndex}
                        initialTopMostItemIndex={Math.max(0, visibleMessages.length - 1)}
                        followOutput={(atBottom) => (atBottom ? 'auto' : false)}
                        atBottomThreshold={80}
                        startReached={() => { if (olderMessagesHasMore) void loadOlderMessages() }}
                        rangeChanged={(range) => setVisibleRange({
                            startIndex: Math.max(0, range.startIndex - firstItemIndex),
                            endIndex: Math.max(0, range.endIndex - firstItemIndex),
                        })}
                        components={CANVAS_VIRTUOSO_COMPONENTS}
                        context={{ footer: <div style={{ padding: '0 20px 20px' }}>{streamingRegion}</div> }}
                        itemContent={(index) => (
                            <div style={{ padding: '0 20px 16px' }}>
                                {renderBubble(index - firstItemIndex)}
                            </div>
                        )}
                        style={{ flex: 1, minHeight: 0 }}
                    />
                </div>
            ) : (
                <div
                    className="nowheel"
                    data-chat-message-scroll-root="true"
                    data-testid="chat-message-scroll"
                    data-canvas-text-selectable="true"
                    ref={scrollRef}
                    onScroll={handleScroll}
                    onWheel={handleScrollableWheel}
                    style={{
                        flex: 1,
                        minHeight: 0,
                        overflowY: 'auto',
                        padding: '0 20px 20px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 16,
                        userSelect: 'text',
                        WebkitUserSelect: 'text',
                    }}
                >
                    {olderMessagesHasMore && (
                        <div style={{ display: 'flex', justifyContent: 'center', padding: '4px 0 8px' }}>
                            <button
                                type="button"
                                onClick={() => void loadOlderMessages()}
                                style={{ border: 'none', background: 'transparent', color: 'var(--app-primary)', fontSize: 13, cursor: 'pointer' }}
                            >
                                {t('canvas.chat.load_older_messages', '加载更早消息')}
                            </button>
                        </div>
                    )}
                    {visibleMessages.map((_, idx) => renderBubble(idx))}
                    {streamingRegion}
                </div>
            )}

            <ImagePreviewDialog
                open={!!previewUrl}
                onOpenChange={(open) => !open && closePreview()}
                src={previewUrl}
                alt={t('canvas.chat.enlarge_view')}
                title={t('canvas.chat.enlarge_view')}
                imageClassName="rounded-lg"
                downloadUrl={previewUrl}
                onDownload={(e) => previewUrl ? handleDownload(previewUrl, e) : undefined}
            />
        </>
    )
}
