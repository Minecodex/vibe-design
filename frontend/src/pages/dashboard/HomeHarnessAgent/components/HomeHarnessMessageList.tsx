import { Fragment, memo, useCallback, useMemo, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
import type { TFunction } from 'i18next'
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Copy,
  History,
  Loader2,
} from 'lucide-react'
import { toast } from 'sonner'

import {
  type AttachmentData,
  type HarnessConversationRead,
  type OutlineRuntimeRead,
  type PendingInteraction,
  type UserPlanRead,
  type UserProgressRead,
} from '@/api/endpoints/agent'
import {
    EcommerceInteractionCard,
    type EcommerceReferenceImageRequestOptions,
    type EcommerceReferenceImageSource,
    isEcommerceInteractionKind,
} from '@/components/agent/EcommerceInteractionCard'
import {
  dedupeEcommerceInteractionBlocks,
  dedupeEcommerceInteractionMessages,
} from '@/components/agent/ecommerceInteractionDedupe'
import { cn } from '@/lib/utils'
import {
  createPresentationRendererRegistry,
  normalizePresentationUiKind,
  registerDefaultPresentationRenderers,
  type PresentationBlockRenderer,
} from '@/store/harnessMessageProjection/rendererRegistry'
import type { ChatMessage, MessageBlock } from '@/store/homeHarnessStore'
import { normalizeHomeHarnessCritiquePayload } from '@/store/homeHarnessCritiqueProjection'
import { getLocalizedSubagentPurpose } from '@/utils/subagentDisplayLabels'

import {
  blocksShareHomepageIdentity,
  filterDuplicateHomepageStreamingBlocks,
  removeRedundantHomepagePlanBlocks,
} from '../homepageBlockDedupe'
import { AttachmentCardStrip } from './AttachmentCardStrip'
import { GenerationCard } from './GenerationCard'
import { HomeHarnessInteractionForm } from './HomeHarnessInteractionForm'
import { HomeHarnessCritiquePanel } from './HomeHarnessCritiquePanel'
import { HomeChatMarkdown } from './HomeChatMarkdown'
import { HomeHarnessInlinePlanEditor } from './HomeHarnessInlinePlanEditor'
import { getHomeToolDisplayName } from './homeChatMeta'
import { HomeToolCallCard } from './HomeToolCallCard'
import { HomeToolGroupCard } from './HomeToolGroupCard'
import { groupHomeReadonlyToolBlocks } from './homeToolGrouping'
import { summarizeInteractionJsonContent } from './homeInteractionSummary'
import { HomeWebSearchCard } from './HomeWebSearchCard'
import type { SessionFileItem } from '../homeHarnessPageUtils'
import { getAgentMessageRenderWeight, isAgentBlockTerminal, isAgentHeavyBlock, shouldVirtualizeAgentItems } from '../../agentMedia/agentRenderWeight'
import type { AgentRenderWeightSnapshot } from '../../agentMedia/agentMediaTypes'

const HOMEPAGE_VISIBLE_UI_KINDS = new Set([
  'assistant_final_answer',
  'assistant_text',
  'artifact_card',
  'design_jury_card',
  'error_card',
  'interaction_form',
  'friendly_issue',
  'friendly_status',
  'generation_card',
  'generation_task',
  'md_document',
  'media_card',
  'plan_artifact',
  'plan_card',
  'planning_draft_card',
  'progress_card',
  'status_history_panel',
  'user_plan_card',
  'user_progress_card',
  'subagent_card',
  'text',
  'tool_call',
  'tool_result',
  'tool_group',
  'web_search_card',
])

function formatBaseVersionNumber(versionId?: string | null): string {
  const match = String(versionId || '').match(/^v0*(\d+)$/i)
  return match ? match[1] : String(versionId || 'current')
}

// Above this many groups the list is windowed with react-virtuoso (using the page's
// existing scroll container via customScrollParent, so the tested stick-to-bottom +
// load-older-anchor logic in useHomeChatMessageScroll keeps working). Below it we keep the
// plain map so short conversations and the jsdom render tests behave exactly as before.
const HOME_VIRTUALIZE_GROUP_THRESHOLD = 50

type HomeMessageListVirtuosoContext = { footer: React.ReactNode }
function HomeVirtuosoFooter({ context }: { context?: HomeMessageListVirtuosoContext }) {
  return <>{context?.footer ?? null}</>
}
const HOME_VIRTUOSO_COMPONENTS = { Footer: HomeVirtuosoFooter }

interface HomeHarnessMessageListProps {
  messages: ChatMessage[]
  streamingBlocks: MessageBlock[]
  isStreaming: boolean
  runStatus?: 'idle' | 'running' | 'waiting_input' | 'completed' | 'failed' | 'blocked' | 'cancelled'
  isDark: boolean
  t: TFunction
  language?: string
  conversationId?: number | string | null
  conversationLastActivityAt?: string | null
  conversationRuntime?: HarnessConversationRead | null
  conversationPhase?: string | null
  outlineRuntime?: OutlineRuntimeRead | null
  userProgress?: UserProgressRead | null
  userInteraction?: PendingInteraction | null
  respondToAgent: (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
  ) => Promise<void>
  onStartExecution?: () => Promise<void>
  onRevisePlan?: (instruction: string) => Promise<void>
  onPatchCurrentOutline?: (plan: UserPlanRead) => Promise<void>
  hiddenToolCalls: string[]
  onOpenWorkspaceRelativeFile: (filePath: string, fileName?: string) => void
  sessionFiles?: SessionFileItem[]
  onPreviewWorkspaceFile?: (file: SessionFileItem) => void
  onUseGeneratedAsReference?: (attachment: AttachmentData) => void
  onRequestEcommerceReferenceImages?: (
    source: EcommerceReferenceImageSource,
    onSelect: (urls: string[]) => void,
    options?: EcommerceReferenceImageRequestOptions,
  ) => void
  onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>
  maxEcommerceReferenceImages?: number
  scrollParent?: HTMLElement | null
}

interface HomepagePlanRenderState {
  planningReady: boolean
}

function normalizeHomepageToolName(name: string | null | undefined): string {
  return String(name || '').trim().replace(/^lc_/, '')
}

function isHomepageBlockVisible(block: MessageBlock): boolean {
  if (block.visible === false) {
    return false
  }
  if (block.debugOnly === true || block.userVisible === false) {
    return false
  }
  if (block.payload?.debugOnly === true || block.payload?.debug_only === true) {
    return false
  }
  if (block.payload?.userVisible === false || block.payload?.user_visible === false) {
    return false
  }
  const uiKind = String(block.uiKind || '')
  return HOMEPAGE_VISIBLE_UI_KINDS.has(uiKind)
    || HOMEPAGE_VISIBLE_UI_KINDS.has(normalizePresentationUiKind(uiKind))
}

function hasDedicatedHomePlanRenderer(uiKind: string | null | undefined): boolean {
  return uiKind === 'planning_draft_card' || uiKind === 'user_plan_card'
}

function hasDedicatedHomeArtifactRenderer(uiKind: string | null | undefined): boolean {
  return uiKind === 'media_card' || uiKind === 'generation_card'
}

function isInFlightGenerationBlock(block: MessageBlock): boolean {
  if (!isHomepageBlockVisible(block)) {
    return false
  }

  const status = String(block.payload?.status || block.status || '').toLowerCase()
  const uiKind = String(block.uiKind || '')
  const mediaType = String(block.payload?.mediaType || block.payload?.media_type || '')
  const isGenerationBlock = uiKind === 'generation_task'
    || uiKind === 'generation_card'
    || (uiKind === 'media_card' && mediaType !== 'image_analysis')
  const isTerminal = status === 'completed' || status === 'failed' || status === 'blocked' || status === 'cancelled'

  if (block.visible !== false && isGenerationBlock && !isTerminal) {
    return true
  }

  return (block.children || []).some(isInFlightGenerationBlock)
}

function hasVisibleInFlightGeneration(messages: ChatMessage[]): boolean {
  return messages.some((message) => (message.blocks || []).some(isInFlightGenerationBlock))
}

function extractRenderableMessageText(blocks: MessageBlock[]): string | null {
  for (const block of blocks) {
    if (!isHomepageBlockVisible(block)) {
      continue
    }
    if (block.uiKind === 'assistant_text' || block.uiKind === 'assistant_final_answer') {
      const text = String(block.payload?.text || '').trim()
      if (text) {
        return text
      }
    }
    if (block.uiKind === 'text') {
      const text = String(block.payload?.text || '').trim()
      if (text) {
        return text
      }
    }
  }
  return null
}

function shouldRenderHomepageAssistantBlocksInOrder(blocks: MessageBlock[]): boolean {
  return blocks.some((block) => {
    const uiKind = String(block.uiKind || '')
    return uiKind === 'assistant_text'
      || uiKind === 'assistant_final_answer'
      || uiKind === 'text'
      || uiKind === 'interaction_form'
      || isImageAnalysisMediaCardBlock(block)
  })
}

function AssistantFinalAnswerCard({
  block,
  isDark,
  t,
  conversationId,
  sessionFiles,
  onPreviewWorkspaceFile,
}: {
  block: MessageBlock
  isDark: boolean
  t: TFunction
  conversationId?: number | string | null
  sessionFiles?: SessionFileItem[]
  onPreviewWorkspaceFile?: (file: SessionFileItem) => void
}) {
  const text = String(block.payload?.text || '').trim()
  const statusHistory = normalizeStatusHistory(block.payload?.statusHistory || block.payload?.status_history)

  return (
    <div className="space-y-2">
      {text ? (
        <HomeChatMarkdown
          content={text}
          isDark={isDark}
          className="max-w-[90%]"
          conversationId={conversationId}
          workspaceFiles={sessionFiles}
          enableWorkspaceFileReferences={!!onPreviewWorkspaceFile}
          enableArtifactReferences
          onOpenWorkspaceFile={onPreviewWorkspaceFile}
        />
      ) : null}
      {statusHistory.length ? (
        <HomeStatusHistoryPanel
          statusHistory={statusHistory}
          isDark={isDark}
          t={t}
        />
      ) : null}
    </div>
  )
}

type HomeStatusHistoryItem = {
  id: string
  text: string
  status?: string
  toolCalls: Array<{ id?: string; name?: string; status?: string }>
}

function normalizeStatusHistory(raw: unknown): HomeStatusHistoryItem[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .filter((item): item is Record<string, any> => !!item && typeof item === 'object')
    .map((item, index) => ({
      id: String(item.id || `status-${index}`),
      text: String(item.text || item.message || item.summary || '').trim(),
      status: item.status ? String(item.status) : undefined,
      toolCalls: Array.isArray(item.toolCalls || item.tool_calls)
        ? (item.toolCalls || item.tool_calls)
          .filter((tool: unknown): tool is Record<string, any> => !!tool && typeof tool === 'object')
          .map((tool: Record<string, any>) => ({
            id: tool.id ? String(tool.id) : undefined,
            name: tool.name ? String(tool.name) : tool.tool ? String(tool.tool) : undefined,
            status: tool.status ? String(tool.status) : undefined,
          }))
        : [],
    }))
    .filter((item) => item.text || item.toolCalls.length)
}

function HomeStatusHistoryPanel({
  statusHistory,
  isDark,
  t,
}: {
  statusHistory: HomeStatusHistoryItem[]
  isDark: boolean
  t: TFunction
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="app-card-muted max-w-[90%] rounded-2xl">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className={cn('inline-flex items-center gap-2 text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
          <History className="h-4 w-4" />
          {t('home.statusHistory.label', '状态历史')}
        </span>
        <ChevronDown className={cn('h-4 w-4 text-zinc-500 transition-transform', expanded ? 'rotate-180' : 'rotate-0')} />
      </button>
      {expanded ? (
        <div className="app-divider app-muted space-y-2 border-t px-4 py-3 text-sm">
          {statusHistory.map((item) => (
            <div key={item.id} className="space-y-1">
              {item.text ? <div>{item.text}</div> : null}
              {item.toolCalls.length ? (
                <div className={cn('flex flex-wrap gap-1 text-xs', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
                  {item.toolCalls.map((tool, index) => (
                    <span
                      key={tool.id || `${item.id}-tool-${index}`}
                      className="rounded-full bg-[var(--app-control)] px-2 py-0.5"
                    >
                      {tool.name || tool.id}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function isAnalyzeImageTextBlock(block: MessageBlock): boolean {
  return (
    String(block.uiKind || '') === 'text'
    && normalizeHomepageToolName(
      String(
        block.payload?.toolName
        || block.payload?.tool_name
        || block.payload?.name
        || block.payload?.tool
        || '',
      ),
    ) === 'analyze_image'
  )
}

function isAnalyzeImageStreamPanelBlock(block: MessageBlock): boolean {
  return (
    String(block.uiKind || '') === 'stream_panel'
    && normalizeHomepageToolName(String(block.payload?.toolName || block.payload?.tool_name || '')) === 'analyze_image'
  )
}

function getHomepageMediaType(block: MessageBlock): string {
  return String(
    block.payload?.mediaType
    || block.payload?.media_type
    || block.payload?.result?.mediaType
    || block.payload?.result?.media_type
    || '',
  )
}

function isHomepageMediaCardBlock(block: MessageBlock): boolean {
  return String(block.uiKind || '') === 'media_card' || String(block.uiKind || '') === 'generation_card'
}

function isImageAnalysisMediaCardBlock(block: MessageBlock): boolean {
  return isHomepageMediaCardBlock(block) && getHomepageMediaType(block) === 'image_analysis'
}

function isHomepageGenerationCompanionBlock(block: MessageBlock): boolean {
  const uiKind = String(block.uiKind || '')
  if (uiKind !== 'generation_task') {
    return false
  }

  const toolName = normalizeHomepageToolName(
    String(block.payload?.toolName || block.payload?.tool_name || ''),
  )
  return toolName === 'generate_image' || toolName === 'generate_video'
}

function extractAnalyzeImageBlockText(block: MessageBlock | undefined): string {
  if (!block) {
    return ''
  }
  if (isAnalyzeImageTextBlock(block)) {
    return extractAnalyzeImageDisplayText('', String(block.payload?.text || ''))
  }
  if (isAnalyzeImageStreamPanelBlock(block)) {
    return extractAnalyzeImageDisplayText(
      String(block.payload?.streamText || block.payload?.stream_text || ''),
      String(block.payload?.text || ''),
    )
  }
  if (isImageAnalysisMediaCardBlock(block)) {
    return extractAnalyzeImageDisplayText('', String(block.payload?.text || ''))
  }
  return ''
}

function mergeGenerationMediaCardPayload(
  mediaCard: MessageBlock,
  companion: MessageBlock | undefined,
): Record<string, any> {
  const companionPayload = companion?.payload || {}

  return {
    ...companionPayload,
    ...mediaCard.payload,
    toolName: mediaCard.payload?.toolName
      || mediaCard.payload?.tool_name
      || companionPayload.toolName
      || companionPayload.tool_name,
    status: mediaCard.payload?.status || companionPayload.status || mediaCard.status,
    taskId: mediaCard.payload?.taskId
      ?? mediaCard.payload?.task_id
      ?? companionPayload.taskId
      ?? companionPayload.task_id
      ?? companionPayload.result?.taskId
      ?? companionPayload.result?.task_id,
    resultUrl: mediaCard.payload?.resultUrl
      ?? mediaCard.payload?.result_url
      ?? companionPayload.resultUrl
      ?? companionPayload.result_url
      ?? companionPayload.result?.resultUrl
      ?? companionPayload.result?.result_url,
    prompt: mediaCard.payload?.prompt
      ?? companionPayload.prompt
      ?? companionPayload.result?.prompt,
    mediaType: mediaCard.payload?.mediaType
      ?? mediaCard.payload?.media_type
      ?? companionPayload.mediaType
      ?? companionPayload.media_type
      ?? companionPayload.result?.mediaType
      ?? companionPayload.result?.media_type,
    modelName: mediaCard.payload?.modelName
      ?? mediaCard.payload?.model_name
      ?? companionPayload.modelName
      ?? companionPayload.model_name
      ?? companionPayload.result?.modelName
      ?? companionPayload.result?.model_name,
    modelLabel: mediaCard.payload?.modelLabel
      ?? mediaCard.payload?.model_label
      ?? companionPayload.modelLabel
      ?? companionPayload.model_label
      ?? companionPayload.result?.modelLabel
      ?? companionPayload.result?.model_label,
    aspectRatio: mediaCard.payload?.aspectRatio
      ?? mediaCard.payload?.aspect_ratio
      ?? companionPayload.aspectRatio
      ?? companionPayload.aspect_ratio
      ?? companionPayload.result?.aspectRatio
      ?? companionPayload.result?.aspect_ratio,
    resolution: mediaCard.payload?.resolution
      ?? companionPayload.resolution
      ?? companionPayload.result?.resolution,
    duration: mediaCard.payload?.duration
      ?? companionPayload.duration
      ?? companionPayload.result?.duration,
    quality: mediaCard.payload?.quality
      ?? companionPayload.quality
      ?? companionPayload.result?.quality,
    progress: mediaCard.payload?.progress
      ?? companionPayload.progress
      ?? companionPayload.result?.progress,
    errorMessage: mediaCard.payload?.errorMessage
      ?? mediaCard.payload?.error_message
      ?? companionPayload.errorMessage
      ?? companionPayload.error_message
      ?? companionPayload.result?.errorMessage
      ?? companionPayload.result?.error_message,
    elapsedMs: mediaCard.payload?.elapsedMs
      ?? mediaCard.payload?.elapsed_ms
      ?? companionPayload.elapsedMs
      ?? companionPayload.elapsed_ms
      ?? companionPayload.result?.elapsedMs
      ?? companionPayload.result?.elapsed_ms,
  }
}

const homepageMergedBlocksCache = new WeakMap<MessageBlock[], MessageBlock[]>()

// Cache the (pure) merge/dedupe/group result by the blocks-array identity. Finalized
// messages keep a stable `blocks` reference, so during a streaming burst we skip rerunning
// this O(blocks) work for every already-completed message on every delta.
function mergeHomepageMessageBlocks(blocks: MessageBlock[]): MessageBlock[] {
  const cached = homepageMergedBlocksCache.get(blocks)
  if (cached) {
    return cached
  }
  const merged = mergeHomepageMessageBlocksUncached(blocks)
  homepageMergedBlocksCache.set(blocks, merged)
  return merged
}

function mergeHomepageMessageBlocksUncached(blocks: MessageBlock[]): MessageBlock[] {
  const filteredBlocks = removeRedundantHomepagePlanBlocks(blocks)
  const mediaCards = filteredBlocks.filter(isHomepageMediaCardBlock)
  if (mediaCards.length === 0) {
    return groupHomeReadonlyToolBlocks(dedupeEcommerceInteractionBlocks(filteredBlocks))
  }

  const mergedBlocks = filteredBlocks.flatMap((block) => {
    if (isHomepageMediaCardBlock(block)) {
      const companions = filteredBlocks.filter((candidate) => candidate !== block && blocksShareHomepageIdentity(block, candidate))

      if (isImageAnalysisMediaCardBlock(block)) {
        const companionText = companions.find(isAnalyzeImageTextBlock)
        const companionPanel = companions.find(isAnalyzeImageStreamPanelBlock)
        const mergedText = (
          extractAnalyzeImageBlockText(companionPanel)
          || extractAnalyzeImageBlockText(companionText)
          || extractAnalyzeImageBlockText(block)
        )
        const elapsedMs = Number(
          companionPanel?.payload?.elapsedMs
          ?? companionPanel?.payload?.elapsed_ms
          ?? companionPanel?.payload?.result?.elapsedMs
          ?? companionPanel?.payload?.result?.elapsed_ms
          ?? block.payload?.elapsedMs
          ?? block.payload?.elapsed_ms
          ?? 0,
        )

        return [{
          ...block,
          payload: {
            ...block.payload,
            text: mergedText,
            elapsedMs: Number.isFinite(elapsedMs) && elapsedMs > 0 ? elapsedMs : undefined,
          },
        }]
      }

      const generationCompanion = companions.find(isHomepageGenerationCompanionBlock)
      if (!generationCompanion) {
        return [block]
      }

      return [{
        ...block,
        payload: mergeGenerationMediaCardPayload(block, generationCompanion),
      }]
    }

    if (isAnalyzeImageTextBlock(block) || isAnalyzeImageStreamPanelBlock(block) || isHomepageGenerationCompanionBlock(block)) {
      const matchingMediaCard = mediaCards.find((mediaCard) => blocksShareHomepageIdentity(mediaCard, block))
      if (matchingMediaCard) {
        return []
      }
    }

    return [block]
  })

  return groupHomeReadonlyToolBlocks(dedupeEcommerceInteractionBlocks(mergedBlocks))
}

function buildRenderableHomeHarnessMessages(
  messages: ChatMessage[],
  streamingBlocks: MessageBlock[],
  isStreaming: boolean,
): ChatMessage[] {
  const dedupedMessages = dedupeEcommerceInteractionMessages(messages)
  if (!isStreaming || streamingBlocks.length === 0) {
    return dedupedMessages
  }

  const dedupedStreamingBlocks = filterDuplicateHomepageStreamingBlocks(
    dedupedMessages,
    mergeHomepageMessageBlocks(streamingBlocks),
  )

  if (dedupedStreamingBlocks.length === 0) {
    return dedupedMessages
  }

  return [
    ...dedupedMessages,
    {
      id: 'streaming-assistant',
      role: 'assistant',
      content: extractRenderableMessageText(dedupedStreamingBlocks),
      blocks: dedupedStreamingBlocks,
      createdAt: new Date().toISOString(),
    },
  ]
}

type HomeHarnessRenderableGroup = {
  id: string
  role: 'user' | 'assistant'
  messages: ChatMessage[]
}

function buildRenderableHomeHarnessGroups(messages: ChatMessage[]): HomeHarnessRenderableGroup[] {
  const groups: HomeHarnessRenderableGroup[] = []
  for (const message of messages) {
    if (message.role === 'tool') {
      continue
    }
    if (message.role !== 'assistant') {
      groups.push({
        id: String(message.id),
        role: 'user',
        messages: [message],
      })
      continue
    }

    const previous = groups.length > 0 ? groups[groups.length - 1] : undefined
    if (previous?.role === 'assistant') {
      previous.messages.push(message)
      previous.id = `${previous.id}:${String(message.id)}`
      continue
    }

    groups.push({
      id: String(message.id),
      role: 'assistant',
      messages: [message],
    })
  }
  return groups
}

function getInteractionRequestId(block: MessageBlock): string {
  if (block.uiKind !== 'interaction_form') {
    return ''
  }
  return String(block.payload?.requestId || block.payload?.request_id || '').trim()
}

function hasRenderableInteractionRequest(messages: ChatMessage[], requestId: string): boolean {
  if (!requestId) {
    return false
  }
  return messages.some((message) => (
    mergeHomepageMessageBlocks(message.blocks || []).some((block) => getInteractionRequestId(block) === requestId)
  ))
}

function getHomeSubagentStatusLabel(status: string | undefined, t: TFunction): string {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'cancelled' || normalized === 'canceled') {
    return t('home.subagent.status.cancelled', '已取消')
  }
  if (normalized === 'failed' || normalized === 'error') {
    return t('home.subagent.status.failed', '失败')
  }
  if (normalized === 'degraded') {
    return t('home.subagent.status.degraded', '已降级')
  }
  if (normalized === 'refused') {
    return t('home.subagent.status.refused', '已拒绝')
  }
  if (normalized === 'blocked') {
    return t('home.subagent.status.blocked', '已阻塞')
  }
  if (normalized === 'completed' || normalized === 'succeeded') {
    return t('home.subagent.status.completed', '已完成')
  }
  if (normalized === 'pending' || normalized === 'queued') {
    return t('home.subagent.status.pending', '待处理')
  }
  return t('home.subagent.status.running', '进行中')
}

function getHomeSubagentStatusTone(status: string | undefined): 'success' | 'warning' | 'danger' | 'neutral' | 'active' {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'completed' || normalized === 'succeeded') {
    return 'success'
  }
  if (normalized === 'blocked' || normalized === 'degraded') {
    return 'warning'
  }
  if (normalized === 'failed' || normalized === 'error' || normalized === 'refused') {
    return 'danger'
  }
  if (normalized === 'cancelled' || normalized === 'canceled' || normalized === 'pending' || normalized === 'queued') {
    return 'neutral'
  }
  return 'active'
}

function getSubagentType(block: MessageBlock): unknown {
  return block.payload?.subagentType
    ?? block.payload?.subagent_type
    ?? block.payload?.result?.subagentType
    ?? block.payload?.result?.subagent_type
    ?? block.payload?.taskSpec?.subagentType
    ?? block.payload?.taskSpec?.subagent_type
}

function isQualityReviewSubagent(block: MessageBlock): boolean {
  return String(getSubagentType(block) || '').trim().toLowerCase() === 'qualityreview'
}

function looksLikeQualityReviewJsonSummary(value: string): boolean {
  const trimmed = String(value || '').trim()
  if (!trimmed.startsWith('{')) {
    return false
  }
  // Robust to truncated/streamed review JSON: the structured review summary can be
  // cut off mid-object (so JSON.parse throws), which previously let the raw JSON leak
  // into the card. Detect it by its signature keys instead of requiring a full parse.
  if (/"(review_id|reviewId)"\s*:/.test(trimmed) && /"(artifact_entry|artifactEntry)"\s*:/.test(trimmed)) {
    return true
  }
  try {
    const parsed = JSON.parse(trimmed)
    return !!parsed
      && typeof parsed === 'object'
      && !Array.isArray(parsed)
      && (
        typeof parsed.review_id === 'string'
        || typeof parsed.reviewId === 'string'
      )
      && (
        typeof parsed.artifact_entry === 'string'
        || typeof parsed.artifactEntry === 'string'
      )
  } catch {
    return false
  }
}

function flattenSubagentChildBlocks(blocks: MessageBlock[]): MessageBlock[] {
  const flattened: MessageBlock[] = []
  for (const block of blocks) {
    const childBlocks = Array.isArray(block.children) ? block.children : []
    const isTransparentContainer = (
      block.uiKind === 'content'
      && childBlocks.length > 0
      && !block.payload?.text
      && !block.summary
    )
    if (isTransparentContainer) {
      flattened.push(...flattenSubagentChildBlocks(childBlocks))
      continue
    }
    flattened.push({
      ...block,
      children: childBlocks.length ? flattenSubagentChildBlocks(childBlocks) : childBlocks,
    })
  }
  return flattened
}

function HomeSubagentCard({
  block,
  isDark,
  t,
  language,
  isStreaming,
  conversationId,
  conversationLastActivityAt,
  onOpenWorkspaceRelativeFile,
  onRespondToInteraction,
  hiddenToolCalls,
  submittingInteractionLabels,
  planRenderState,
  onRequestEcommerceReferenceImages,
  onUploadEcommerceReferenceImage,
  maxEcommerceReferenceImages,
}: {
  block: MessageBlock
  isDark: boolean
  t: TFunction
  language?: string
  isStreaming: boolean
  conversationId?: number | string | null
  conversationLastActivityAt?: string | null
  onOpenWorkspaceRelativeFile?: (filePath: string, fileName?: string) => void
  onRespondToInteraction?: (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
  ) => Promise<void>
  hiddenToolCalls: string[]
  submittingInteractionLabels: Record<string, string>
  planRenderState?: HomepagePlanRenderState
  onRequestEcommerceReferenceImages?: (
    source: EcommerceReferenceImageSource,
    onSelect: (urls: string[]) => void,
    options?: EcommerceReferenceImageRequestOptions,
  ) => void
  onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>
  maxEcommerceReferenceImages?: number
}) {
  const [expanded, setExpanded] = useState(Boolean(block.expanded))
  const childBlocks = flattenSubagentChildBlocks(Array.isArray(block.children) ? block.children : [])
  const purpose = String(
    block.payload?.purpose
    || block.payload?.result?.purpose
    || block.label
    || block.payload?.label
    || '',
  ).trim()
  const purposeLabel = getLocalizedSubagentPurpose(t, purpose, getSubagentType(block))
  const status = String(block.payload?.status || block.status || 'running')
  const summary = String(block.summary || block.payload?.summary || '').trim()
  const objective = String(block.payload?.objective || block.payload?.taskSpec?.objective || '').trim()
  const targetFiles = Array.isArray(block.payload?.taskSpec?.inputs?.targetFiles)
    ? block.payload.taskSpec.inputs.targetFiles
    : Array.isArray(block.payload?.taskSpec?.inputs?.target_files)
      ? block.payload.taskSpec.inputs.target_files
      : []
  const missingInputs = Array.isArray(block.payload?.missingInputs) ? block.payload.missingInputs : []
  const mismatchedInputs = Array.isArray(block.payload?.mismatchedInputs) ? block.payload.mismatchedInputs : []
  const reasonCode = String(block.payload?.reasonCode || '').trim()
  const statusTone = getHomeSubagentStatusTone(status)
  const visibleChildren = childBlocks
    .filter((child) => child.visible !== false)
    .sort((a, b) => a.order - b.order)
  const hasDesignJuryChild = visibleChildren.some((child) => child.uiKind === 'design_jury_card')
  const isQualityReview = isQualityReviewSubagent(block)
  // A raw structured-review JSON summary must never render as a wall of text — suppress
  // it regardless of subagent type (defends against missing subagent_type / truncated
  // JSON). Also hide the QR summary when a dedicated design-jury card is present.
  const shouldRenderSummary = Boolean(summary)
    && !looksLikeQualityReviewJsonSummary(summary)
    && !(isQualityReview && hasDesignJuryChild)

  return (
    <div
      key={block.id}
      className={cn(
        'app-card max-w-[90%] rounded-2xl',
      )}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        className="w-full px-4 py-4 text-left"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
              {t('home.subagent.title', '子代理')}
            </div>
            {purpose ? (
              <div className={cn('mt-1 text-sm', isDark ? 'text-zinc-300' : 'text-zinc-700')}>
                <span className={cn('mr-2 text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {t('home.subagent.purpose', '任务目的')}
                </span>
                <span>{purposeLabel}</span>
              </div>
            ) : null}
            <div className="mt-2 flex items-center gap-2">
              <span
                className={cn(
                  'inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold',
                  statusTone === 'success'
                    ? (isDark ? 'bg-emerald-500/15 text-emerald-200' : 'bg-emerald-50 text-emerald-700')
                    : statusTone === 'warning'
                      ? (isDark ? 'bg-amber-500/15 text-amber-200' : 'bg-amber-100 text-amber-800')
                      : statusTone === 'danger'
                        ? (isDark ? 'bg-red-500/15 text-red-200' : 'bg-red-50 text-red-700')
                        : statusTone === 'neutral'
                          ? (isDark ? 'bg-zinc-500/15 text-zinc-200' : 'bg-zinc-100 text-zinc-700')
                          : (isDark ? 'bg-blue-500/15 text-blue-200' : 'bg-blue-50 text-blue-700'),
                )}
              >
                {getHomeSubagentStatusLabel(status, t)}
              </span>
              {visibleChildren.length > 0 ? (
                <span className={cn('text-xs', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {t('home.subagent.items_count', { defaultValue: '{{count}} 项内部内容', count: visibleChildren.length })}
                </span>
              ) : null}
            </div>
          </div>
          <ChevronDown
            className={cn('h-4 w-4 shrink-0 text-zinc-500 transition-transform', expanded ? 'rotate-180' : 'rotate-0')}
          />
        </div>
      </button>
      {expanded ? (
        <div className="app-divider border-t px-4 pb-4 pt-3 space-y-2">
          {shouldRenderSummary ? (
            <div className={cn('text-xs', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
              <HomeChatMarkdown
                content={summary}
                isDark={isDark}
                className="max-w-none"
                conversationId={conversationId}
              />
            </div>
          ) : null}
          {objective || targetFiles.length || missingInputs.length || mismatchedInputs.length || reasonCode ? (
            <div className="app-card-muted app-muted rounded-xl px-3 py-2 text-xs leading-5">
              {objective ? (
                <div>
                  <span className="font-medium">{t('home.subagent.objective', '目标')}</span>
                  <span className="ml-2">{objective}</span>
                </div>
              ) : null}
              {targetFiles.length ? (
                <div>
                  <span className="font-medium">{t('home.subagent.target_files', '输入文件')}</span>
                  <span className="ml-2">{targetFiles.map(String).join(', ')}</span>
                </div>
              ) : null}
              {missingInputs.length ? (
                <div>
                  <span className="font-medium">{t('home.subagent.missing_inputs', '缺少输入')}</span>
                  <span className="ml-2">{missingInputs.map(String).join(', ')}</span>
                </div>
              ) : null}
              {mismatchedInputs.length ? (
                <div>
                  <span className="font-medium">{t('home.subagent.mismatched_inputs', '不匹配输入')}</span>
                  <span className="ml-2">{mismatchedInputs.map(String).join(', ')}</span>
                </div>
              ) : null}
              {reasonCode ? (
                <div>
                  <span className="font-medium">{t('home.subagent.reason_code', '原因')}</span>
                  <span className="ml-2">{reasonCode}</span>
                </div>
              ) : null}
            </div>
          ) : null}
          {visibleChildren.map((child) => (
            <Fragment key={child.id}>
              {renderUserFacingHomeChatBlock(
                child,
                null,
                isDark,
                t,
                language,
                isStreaming,
                conversationId,
                conversationLastActivityAt,
                undefined,
                undefined,
                undefined,
                undefined,
                onOpenWorkspaceRelativeFile,
                undefined,
                onRespondToInteraction,
                undefined,
                undefined,
                undefined,
                hiddenToolCalls,
                [],
                undefined,
                false,
                submittingInteractionLabels,
                planRenderState,
                undefined,
                undefined,
                onRequestEcommerceReferenceImages,
                onUploadEcommerceReferenceImage,
                maxEcommerceReferenceImages,
              )}
            </Fragment>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function resolveHomepagePlanStatus(
  block: MessageBlock,
  planRenderState?: HomepagePlanRenderState,
): string {
  if (planRenderState?.planningReady) {
    return 'planning_ready'
  }
  return String(block.payload?.status || block.status || '')
}

function getPlanStatusLabel(status: string, t: TFunction) {
  switch (String(status || '').toLowerCase()) {
    case 'planning_ready':
      return t('home.planReview.status.planningReady', 'Ready to execute')
    case 'superseded':
      return t('home.planReview.status.superseded', 'Historical')
    case 'executing':
    case 'finalizing':
      return t('canvas.chat.plan.status.in_progress', 'In progress')
    case 'blocked':
      return t('canvas.chat.plan.status.blocked', 'Blocked')
    case 'completed':
      return t('canvas.chat.plan.status.completed', 'Completed')
    case 'failed':
      return t('canvas.chat.plan.status.failed', 'Failed')
    default:
      return t('canvas.chat.plan.status.in_progress', 'In progress')
  }
}

function isTerminalPlanStatus(status: string): boolean {
  const normalized = String(status || '').toLowerCase()
  return normalized === 'failed' || normalized === 'blocked' || normalized === 'cancelled' || normalized === 'canceled'
}

function normalizePlanOutlineItems(items: unknown): Array<Record<string, any>> {
  if (!Array.isArray(items)) {
    return []
  }
  return items
    .filter((item): item is Record<string, any> => !!item && typeof item === 'object')
    .map((item, index) => ({
      id: item.id ?? `item-${index + 1}`,
      title: String(item.title || ''),
      summary: item.summary ?? item.description ?? null,
      description: item.description ?? item.summary ?? null,
      order: typeof item.order === 'number' ? item.order : index + 1,
      file_path: item.file_path ?? item.filePath ?? null,
      file_name: item.file_name ?? item.fileName ?? null,
      artifact_ref: item.artifact_ref ?? item.artifactRef ?? null,
    }))
}

type PlanStepDisplayStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

function resolvePlanStepDisplayStatus(
  stepStatus: string,
  isActive: boolean,
  planStatus: string,
): PlanStepDisplayStatus {
  const normalizedStepStatus = String(stepStatus || '').toLowerCase()
  const normalizedPlanStatus = String(planStatus || '').toLowerCase()
  if (normalizedStepStatus === 'completed') {
    return 'completed'
  }
  if (
    normalizedStepStatus === 'failed'
    || normalizedStepStatus === 'error'
    || normalizedStepStatus === 'blocked'
    || normalizedStepStatus === 'cancelled'
    || normalizedStepStatus === 'canceled'
    || (isActive && isTerminalPlanStatus(normalizedPlanStatus))
  ) {
    return 'failed'
  }
  if (normalizedStepStatus === 'in_progress' || normalizedStepStatus === 'running' || isActive) {
    return 'in_progress'
  }
  return 'pending'
}

function getPlanStepStatusLabel(status: PlanStepDisplayStatus, t: TFunction) {
  switch (status) {
    case 'completed':
      return t('canvas.chat.plan.status.completed', '已完成')
    case 'failed':
      return t('canvas.chat.plan.status.failed', '失败')
    case 'in_progress':
      return t('canvas.chat.plan.status.in_progress', '进行中')
    default:
      return t('canvas.chat.plan.status.pending', '待处理')
  }
}

function formatPlanActivityTime(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatPlanElapsedDuration(value: unknown): string | null {
  const elapsedMs = Number(value)
  if (!Number.isFinite(elapsedMs) || elapsedMs <= 0) {
    return null
  }
  const totalSeconds = Math.max(Math.round(elapsedMs / 1000), 1)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) {
    return `${hours}小时${minutes}分${seconds}秒`
  }
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`
  }
  return `${seconds}秒`
}

function buildPlanStepFailureDetail(
  step: Record<string, any>,
  conversationRuntime?: HarnessConversationRead | null,
): string {
  const lastTool = normalizeHomepageToolName(conversationRuntime?.last_tool)
  const runtimeFailure = conversationRuntime?.runtime_state?.failure
  const reason = String(
    step.error_message
    || step.errorMessage
    || step.failure_reason
    || step.failureReason
    || runtimeFailure?.summary
    || conversationRuntime?.last_error_summary
    || '执行失败',
  ).trim()

  if (lastTool) {
    return `调用失败：${lastTool}：${reason}`
  }
  return `调用失败：${reason}`
}

function buildPlanStepMetaLabel(
  step: Record<string, any>,
  options: {
    displayStatus: PlanStepDisplayStatus
    conversationRuntime?: HarnessConversationRead | null
    fallbackLastActivityAt?: string | null
  },
): { text: string, title: string } | null {
  const { displayStatus, conversationRuntime, fallbackLastActivityAt } = options
  if (displayStatus === 'completed') {
    const elapsedLabel = formatPlanElapsedDuration(step.elapsed_ms ?? step.elapsedMs)
    return elapsedLabel ? { text: `耗时 ${elapsedLabel}`, title: `耗时 ${elapsedLabel}` } : null
  }
  if (displayStatus === 'failed') {
    const text = buildPlanStepFailureDetail(step, conversationRuntime)
    return { text, title: text }
  }
  if (displayStatus === 'in_progress') {
    const activityTime = formatPlanActivityTime(
      String(
        step.last_activity_at
        || step.lastActivityAt
        || fallbackLastActivityAt
        || '',
      ) || null,
    )
    return activityTime ? { text: activityTime, title: activityTime } : null
  }
  return null
}

function AnalyzeImageCard({
  toolName,
  text,
  status,
  elapsedLabel,
  isDark,
}: {
  toolName: string
  text: string
  status: string
  elapsedLabel: string | null
  isDark: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const ToggleIcon = expanded ? ChevronDown : ChevronRight

  return (
    <div
      className={cn(
        'app-card max-w-[90%] overflow-hidden rounded-2xl',
      )}
    >
      <button
        type="button"
        aria-label="Toggle analysis tool output"
        onClick={() => setExpanded((current) => !current)}
        className={cn(
          'w-full px-4 py-3 flex items-center justify-between gap-3 text-left transition-colors hover:bg-[var(--app-control-hover)]',
        )}
      >
        <div className="min-w-0 flex items-center gap-2">
          <ToggleIcon className={cn('w-4 h-4 shrink-0', isDark ? 'text-zinc-400' : 'text-zinc-500')} />
          <span
            className={cn(
              'text-xs font-medium uppercase tracking-[0.12em]',
              isDark ? 'text-zinc-400' : 'text-zinc-500',
            )}
          >
            {getHomeToolDisplayName(toolName)}
          </span>
        </div>
        {elapsedLabel ? (
          <span
            className={cn(
              'shrink-0 text-sm normal-case tracking-normal',
              isDark ? 'text-zinc-400' : 'text-zinc-500',
            )}
          >
            {elapsedLabel}
          </span>
        ) : null}
      </button>
      {expanded ? (
        <div className="px-4 pb-4">
          {text ? (
            <HomeChatMarkdown content={text} isDark={isDark} />
          ) : status === 'running' ? (
            <div className="text-sm text-zinc-500">Running...</div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function HomeCompactAgentBlock({
  block,
  isDark,
  t,
  onExpand,
}: {
  block: MessageBlock
  isDark: boolean
  t: TFunction
  onExpand?: () => void
}) {
  const label = getHomeCompactAgentBlockLabel(block, t)
  const status = String(block.payload?.status || block.status || '').trim()
  const summary = String(block.payload?.prompt || block.payload?.text || block.payload?.summary || block.payload?.tool_name || '').trim()
  return (
    <button
      type="button"
      data-testid="agent-compact-block"
      onClick={onExpand}
      className={cn(
        'app-card flex max-w-[90%] items-center justify-between gap-3 rounded-2xl px-3 py-2.5 text-left transition-colors hover:bg-[var(--app-control-hover)]',
      )}
    >
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">{label}</span>
        <span className={cn('block truncate text-xs', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
          {[status, summary].filter(Boolean).join(' · ') || t('agentMedia.compact.collapsed', 'Collapsed history content')}
        </span>
      </span>
      <span className="shrink-0 text-xs font-semibold text-blue-500">
        {t('agentMedia.compact.expand', 'Expand')}
      </span>
    </button>
  )
}

function getHomeCompactAgentBlockLabel(block: MessageBlock, t: TFunction): string {
  const uiKind = String(block.uiKind || '')
  const mediaType = String(block.payload?.media_type || block.payload?.mediaType || '')
  if (uiKind.includes('generation') || uiKind === 'media_card' || uiKind === 'generation_card' || mediaType) {
    return mediaType === 'video' || String(block.payload?.tool_name || block.payload?.toolName || '').includes('video')
      ? t('agentMedia.compact.videoGeneration', 'Video generation result')
      : t('agentMedia.compact.imageGeneration', 'Image generation result')
  }
  if (uiKind.includes('tool')) {
    return t('agentMedia.compact.tool', 'Tool call')
  }
  return t('agentMedia.compact.richBlock', 'Rich history content')
}

function extractAnalyzeImageDisplayText(streamText: string, finalText: string): string {
  const preferredText = streamText || finalText
  if (!preferredText) {
    return ''
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

type HomeMessageBlockRendererProps = {
  block: MessageBlock
  messageContent: string | null | undefined
  isDark: boolean
  t: TFunction
  language: string | undefined
  isStreaming: boolean
  conversationId?: number | string | null
  conversationLastActivityAt?: string | null
  conversationRuntime?: HarnessConversationRead | null
  conversationPhase?: string | null
  outlineRuntime?: OutlineRuntimeRead | null
  userProgress?: UserProgressRead | null
  onOpenWorkspaceRelativeFile?: (filePath: string, fileName?: string) => void
  onUseGeneratedAsReference?: (attachment: AttachmentData) => void
  onRespondToInteraction?: (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
) => Promise<void>
  onStartExecution?: () => Promise<void>
  onRevisePlan?: (instruction: string) => Promise<void>
  onPatchCurrentOutline?: (plan: UserPlanRead) => Promise<void>
  hiddenToolCalls?: string[]
  sessionFiles?: SessionFileItem[]
  onPreviewWorkspaceFile?: (file: SessionFileItem) => void
  enableWorkspaceFileReferencesForPersistedAssistantText?: boolean
  submittingInteractionLabels?: Record<string, string>
  planRenderState?: HomepagePlanRenderState
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

const homePresentationRendererRegistry = createPresentationRendererRegistry()

function HomePresentationBlockRenderer(props: HomeMessageBlockRendererProps) {
  return <RenderUserFacingHomeChatBlockBody {...props} />
}

registerDefaultPresentationRenderers(
  homePresentationRendererRegistry,
  HomePresentationBlockRenderer as PresentationBlockRenderer,
)

function renderUserFacingHomeChatBlock(
  block: MessageBlock,
  messageContent: string | null | undefined,
  isDark: boolean,
  t: TFunction,
  language: string | undefined,
  isStreaming: boolean,
  conversationId?: number | string | null,
  conversationLastActivityAt?: string | null,
  conversationRuntime?: HarnessConversationRead | null,
  conversationPhase?: string | null,
  outlineRuntime?: OutlineRuntimeRead | null,
  userProgress?: UserProgressRead | null,
  onOpenWorkspaceRelativeFile?: (filePath: string, fileName?: string) => void,
  onUseGeneratedAsReference?: (attachment: AttachmentData) => void,
  onRespondToInteraction?: (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
  ) => Promise<void>,
  onStartExecution?: () => Promise<void>,
  onRevisePlan?: (instruction: string) => Promise<void>,
  onPatchCurrentOutline?: (plan: UserPlanRead) => Promise<void>,
  hiddenToolCalls: string[] = [],
  sessionFiles: SessionFileItem[] = [],
  onPreviewWorkspaceFile?: (file: SessionFileItem) => void,
  enableWorkspaceFileReferencesForPersistedAssistantText = false,
  submittingInteractionLabels: Record<string, string> = {},
  planRenderState?: HomepagePlanRenderState,
  heavyBlockRenderMode: 'compact' | 'full' = 'full',
  onExpandCompactBlock?: (blockId: string) => void,
  onRequestEcommerceReferenceImages?: (
    source: EcommerceReferenceImageSource,
    onSelect: (urls: string[]) => void,
    options?: EcommerceReferenceImageRequestOptions,
  ) => void,
  onUploadEcommerceReferenceImage?: (file: File) => Promise<string | null | undefined>,
  maxEcommerceReferenceImages?: number,
) {
  const Renderer = homePresentationRendererRegistry.resolve(block.uiKind)
  const props: HomeMessageBlockRendererProps = {
    block,
    messageContent,
    isDark,
    t,
    language,
    isStreaming,
    conversationId,
    conversationLastActivityAt,
    conversationRuntime,
    conversationPhase,
    outlineRuntime,
    userProgress,
    onOpenWorkspaceRelativeFile,
    onUseGeneratedAsReference,
    onRespondToInteraction,
    onStartExecution,
    onRevisePlan,
    onPatchCurrentOutline,
    hiddenToolCalls,
    sessionFiles,
    onPreviewWorkspaceFile,
    enableWorkspaceFileReferencesForPersistedAssistantText,
    submittingInteractionLabels,
    planRenderState,
    heavyBlockRenderMode,
    onExpandCompactBlock,
    onRequestEcommerceReferenceImages,
    onUploadEcommerceReferenceImage,
    maxEcommerceReferenceImages,
  }
  if (Renderer) {
    return <Renderer key={block.id} {...props} />
  }
  return <RenderUserFacingHomeChatBlockBody {...props} />
}

// Memoized so a streaming delta only re-renders the block that actually changed. The
// parent passes stable handlers (all useCallback'd in HomeHarnessAgent) and per-message
// block identities are stable for finalized messages, so the default shallow comparison
// lets completed blocks skip re-rendering during the high-frequency streaming updates.
const RenderUserFacingHomeChatBlockBody = memo(RenderUserFacingHomeChatBlockBodyImpl)

function RenderUserFacingHomeChatBlockBodyImpl({
  block,
  messageContent,
  isDark,
  t,
  language,
  isStreaming,
  conversationId,
  conversationLastActivityAt,
  conversationRuntime,
  conversationPhase,
  outlineRuntime,
  userProgress,
  onOpenWorkspaceRelativeFile,
  onUseGeneratedAsReference,
  onRespondToInteraction,
  onStartExecution,
  onRevisePlan,
  onPatchCurrentOutline,
  hiddenToolCalls = [],
  sessionFiles = [],
  onPreviewWorkspaceFile,
  enableWorkspaceFileReferencesForPersistedAssistantText = false,
  submittingInteractionLabels = {},
  planRenderState,
  heavyBlockRenderMode = 'full',
  onExpandCompactBlock,
  onRequestEcommerceReferenceImages,
  onUploadEcommerceReferenceImage,
  maxEcommerceReferenceImages,
}: HomeMessageBlockRendererProps) {
  if (!isHomepageBlockVisible(block)) {
    return null
  }
  const presentationUiKind = normalizePresentationUiKind(block.uiKind)

  if (heavyBlockRenderMode === 'compact' && isAgentHeavyBlock(block) && isAgentBlockTerminal(block)) {
    return <HomeCompactAgentBlock block={block} isDark={isDark} t={t} onExpand={() => onExpandCompactBlock?.(String(block.id))} />
  }

  const toolName = normalizeHomepageToolName(
    String(
      block.payload?.toolName
      || block.payload?.tool_name
      || block.payload?.name
      || block.payload?.tool
      || '',
    ),
  )

  if (toolName && hiddenToolCalls.includes(toolName)) {
    return null
  }

  if (block.uiKind === 'text' && toolName === 'analyze_image') {
      return (
        <AnalyzeImageCard
          key={block.id}
          toolName={toolName}
          text={extractAnalyzeImageDisplayText('', String(block.payload?.text || ''))}
          status={String(block.payload?.status || block.status || 'running')}
          elapsedLabel={null}
          isDark={isDark}
        />
      )
  }

  if (block.uiKind === 'stream_panel') {
    const streamPanelToolName = String(block.payload?.toolName || '')
    const streamText = String(block.payload?.streamText || block.payload?.stream_text || '')
    const finalText = String(block.payload?.text || '')
    const elapsedMs = Number(
      block.payload?.elapsedMs
      ?? block.payload?.elapsed_ms
      ?? block.payload?.result?.elapsedMs
      ?? block.payload?.result?.elapsed_ms
      ?? 0,
    )
    const elapsedLabel = elapsedMs > 0 ? `${(elapsedMs / 1000).toFixed(1)}s` : null

    if (streamPanelToolName.replace(/^lc_/, '') === 'analyze_image') {
      return (
        <AnalyzeImageCard
          key={block.id}
          toolName={streamPanelToolName}
          text={extractAnalyzeImageDisplayText(streamText, finalText)}
          status={String(block.payload?.status || block.status || 'running')}
          elapsedLabel={elapsedLabel}
          isDark={isDark}
        />
      )
    }

    return null
  }

  if (block.uiKind === 'tool_group') {
    return <HomeToolGroupCard key={block.id} block={block} isDark={isDark} t={t} />
  }

  if (block.uiKind === 'compact_tool' || presentationUiKind === 'tool_call' || presentationUiKind === 'tool_result') {
    return <HomeToolCallCard key={block.id} block={block} isDark={isDark} t={t} />
  }

  if (block.uiKind === 'web_search_card') {
    return (
      <HomeWebSearchCard
        payload={block.payload || {}}
        isDark={isDark}
        conversationId={conversationId}
      />
    )
  }

  if (block.uiKind === 'generation_task' || (presentationUiKind === 'artifact_card' && !hasDedicatedHomeArtifactRenderer(block.uiKind))) {
    const result = (block.payload?.result || {}) as Record<string, any>
    const args = (block.payload?.args || {}) as Record<string, any>
    return (
      <GenerationCard
        key={block.id}
        conversationId={conversationId}
        taskId={block.payload?.taskId ?? block.payload?.task_id ?? result.taskId ?? result.task_id ?? ''}
        status={String(block.payload?.status || result.status || block.status || 'running')}
        resultUrl={block.payload?.resultUrl || block.payload?.result_url || result.resultUrl || result.result_url}
        artifact={block.payload?.artifact || result.artifact}
        prompt={String(block.payload?.prompt || result.prompt || '') || undefined}
        mediaType={String(block.payload?.mediaType || block.payload?.media_type || result.mediaType || result.media_type || '') || undefined}
        modelName={String(block.payload?.modelName || block.payload?.model_name || result.modelName || result.model_name || '') || undefined}
        modelLabel={String(block.payload?.modelLabel || block.payload?.model_label || result.modelLabel || result.model_label || '') || undefined}
        aspectRatio={String(block.payload?.aspectRatio || block.payload?.aspect_ratio || args.aspectRatio || args.aspect_ratio || result.aspectRatio || result.aspect_ratio || '') || undefined}
        resolution={String(block.payload?.resolution || args.resolution || result.resolution || '') || undefined}
        duration={block.payload?.duration ?? args.duration ?? result.duration}
        quality={String(block.payload?.quality || args.quality || result.quality || '') || undefined}
        progress={Number(block.payload?.progress ?? result.progress ?? 0) || undefined}
        toolName={String(block.payload?.toolName || block.payload?.tool_name || '') || undefined}
        errorMessage={String(block.payload?.errorMessage || block.payload?.error_message || result.errorMessage || result.error_message || '') || undefined}
        onUseAsReference={onUseGeneratedAsReference}
        isDark={isDark}
      />
    )
  }

  if (presentationUiKind === 'interaction_form') {
    const requestId = String(block.payload?.requestId || block.payload?.request_id || '').trim()
    const rawInteractionStatus = String(block.payload?.status || block.status || '').trim().toLowerCase()
    const ecommerceInteractionStatus = rawInteractionStatus === 'submitted'
      ? 'submitted'
      : rawInteractionStatus === 'processing'
        ? 'processing'
        : rawInteractionStatus === 'failed'
          ? 'failed'
          : 'pending'
    const formInteractionStatus = rawInteractionStatus === 'submitted' ? 'submitted' : 'pending'
    const kind = String(block.payload?.kind || '') || undefined
    if (isEcommerceInteractionKind(kind)) {
      const interaction = {
        ...block.payload,
        request_id: requestId,
        requestId,
        kind,
        status: ecommerceInteractionStatus,
      } as PendingInteraction
      return (
        <div key={block.id}>
          <EcommerceInteractionCard
            interaction={interaction}
            disabled={ecommerceInteractionStatus === 'submitted'}
            isSubmitting={!!submittingInteractionLabels[requestId]}
            conversationId={conversationId}
            onRequestReferenceImages={onRequestEcommerceReferenceImages}
            onUploadReferenceImage={onUploadEcommerceReferenceImage}
            maxReferenceImages={maxEcommerceReferenceImages}
            onRespond={(nextRequestId, answer, displayLabel, answers) => {
              void onRespondToInteraction?.(nextRequestId, answer, displayLabel, undefined, answers)
            }}
          />
        </div>
      )
    }
    const content = (
      <HomeHarnessInteractionForm
        requestId={requestId}
        kind={kind}
        question={String(block.payload?.question || '') || undefined}
        content={typeof block.payload?.content === 'string' ? block.payload.content : null}
        fallbackContent={messageContent}
        language={language}
        phase={conversationPhase}
        schema={block.payload?.schema || null}
        answers={block.payload?.answers || null}
        status={formInteractionStatus}
        submittedLabel={String(block.payload?.submittedLabel || block.payload?.submitted_label || '')}
        isDark={isDark}
        isSubmitting={!!submittingInteractionLabels[requestId]}
        t={t}
        onSubmit={onRespondToInteraction}
      />
    )
    return content ? <div key={block.id}>{content}</div> : null
  }

  if (presentationUiKind === 'subagent_card') {
    return (
      <HomeSubagentCard
        key={block.id}
        block={block}
        isDark={isDark}
        t={t}
        language={language}
        isStreaming={isStreaming}
        conversationId={conversationId}
        conversationLastActivityAt={conversationLastActivityAt}
        onOpenWorkspaceRelativeFile={onOpenWorkspaceRelativeFile}
        onRespondToInteraction={onRespondToInteraction}
        hiddenToolCalls={hiddenToolCalls}
        submittingInteractionLabels={submittingInteractionLabels}
        planRenderState={planRenderState}
        onRequestEcommerceReferenceImages={onRequestEcommerceReferenceImages}
        onUploadEcommerceReferenceImage={onUploadEcommerceReferenceImage}
        maxEcommerceReferenceImages={maxEcommerceReferenceImages}
      />
    )
  }

  if (block.uiKind === 'design_jury_card') {
    return (
      <HomeHarnessCritiquePanel
        key={block.id}
        critique={normalizeHomeHarnessCritiquePayload(block.payload || {})}
        isDark={isDark}
        t={t}
      />
    )
  }

  if (block.uiKind === 'assistant_final_answer') {
    return (
      <AssistantFinalAnswerCard
        key={block.id}
        block={block}
        isDark={isDark}
        t={t}
        conversationId={conversationId}
        sessionFiles={sessionFiles}
        onPreviewWorkspaceFile={onPreviewWorkspaceFile}
      />
    )
  }

  if (block.uiKind === 'status_history_panel') {
    const statusHistory = normalizeStatusHistory(block.payload?.statusHistory || block.payload?.status_history)
    return statusHistory.length ? (
      <HomeStatusHistoryPanel
        key={block.id}
        statusHistory={statusHistory}
        isDark={isDark}
        t={t}
      />
    ) : null
  }

  if (block.uiKind === 'assistant_text' || presentationUiKind === 'text') {
    const text = String(block.payload?.text || '')
    if (!text.trim()) {
      return null
    }
    return (
      <HomeChatMarkdown
        key={block.id}
        content={text}
        isDark={isDark}
        className="max-w-[90%]"
        conversationId={conversationId}
        workspaceFiles={sessionFiles}
        enableWorkspaceFileReferences={enableWorkspaceFileReferencesForPersistedAssistantText && !!onPreviewWorkspaceFile}
        enableArtifactReferences={enableWorkspaceFileReferencesForPersistedAssistantText}
        onOpenWorkspaceFile={onPreviewWorkspaceFile}
      />
    )
  }

  if (block.uiKind === 'plan_artifact' || (presentationUiKind === 'plan_card' && !hasDedicatedHomePlanRenderer(block.uiKind))) {
    const filePath = String(block.payload?.filePath || block.payload?.file_path || '')
    const steps = Array.isArray(block.payload?.steps) ? block.payload.steps : []
    const planStatus = resolveHomepagePlanStatus(block, planRenderState)
    return (
      <div
        key={block.id}
        className={cn(
          'app-card max-w-[90%] rounded-2xl px-4 py-4 space-y-3',
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
              {String(block.payload?.title || t('canvas.chat.plan.title', 'Task Plan'))}
            </div>
            <div
              className={cn(
                'mt-2 inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold',
                planStatus.toLowerCase() === 'planning_ready'
                  ? (isDark ? 'bg-amber-500/15 text-amber-200' : 'bg-amber-100 text-amber-800')
                  : planStatus.toLowerCase() === 'superseded'
                    ? (isDark ? 'bg-zinc-500/15 text-zinc-200' : 'bg-zinc-100 text-zinc-700')
                  : planStatus.toLowerCase() === 'blocked'
                    ? (isDark ? 'bg-amber-500/15 text-amber-200' : 'bg-amber-100 text-amber-800')
                    : planStatus.toLowerCase() === 'failed'
                      ? (isDark ? 'bg-red-500/15 text-red-200' : 'bg-red-50 text-red-700')
                      : planStatus.toLowerCase() === 'cancelled' || planStatus.toLowerCase() === 'canceled'
                        ? (isDark ? 'bg-zinc-500/15 text-zinc-200' : 'bg-zinc-100 text-zinc-700')
                    : planStatus.toLowerCase() === 'completed'
                      ? (isDark ? 'bg-emerald-500/15 text-emerald-200' : 'bg-emerald-50 text-emerald-700')
                      : (isDark ? 'bg-blue-500/15 text-blue-200' : 'bg-blue-50 text-blue-700'),
              )}
            >
              {getPlanStatusLabel(planStatus, t)}
            </div>
            {block.payload?.summary ? (
              <div className={cn('mt-1 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                {String(block.payload.summary)}
              </div>
            ) : null}
            {planStatus.toLowerCase() === 'planning_ready' ? (
              <div className={cn('mt-2 text-xs', isDark ? 'text-amber-200/90' : 'text-amber-800')}>
                {t(
                  'home.planReview.readyHint',
                  'Review or adjust the outline, then start execution when ready.',
                )}
              </div>
            ) : null}
          </div>
          {filePath ? (
            <button
              type="button"
              onClick={() => onOpenWorkspaceRelativeFile?.(
                filePath,
                String(block.payload?.fileName || block.payload?.file_name || filePath.split('/').pop() || 'plan.md'),
              )}
              className={cn(
                'app-chip shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium',
              )}
            >
              {t('canvas.chat.plan.open_plan', 'Open plan')}
            </button>
          ) : null}
        </div>
        <div className="space-y-1">
          {steps.map((step: Record<string, any>) => {
            const stepId = String(step.id || step.order || '')
            const stepStatus = String(step.status || '')
            const isActive = stepStatus.toLowerCase() === 'in_progress'
            const displayStepStatus = resolvePlanStepDisplayStatus(stepStatus, isActive, planStatus)
            const isCompleted = displayStepStatus === 'completed'
            const isFailed = displayStepStatus === 'failed'
            const isInProgress = displayStepStatus === 'in_progress'
            const isPlanningReady = planStatus.toLowerCase() === 'planning_ready' && isActive
            const stepMetaLabel = buildPlanStepMetaLabel(step, {
              displayStatus: displayStepStatus,
              conversationRuntime,
              fallbackLastActivityAt: conversationLastActivityAt,
            })
            return (
              <div
                key={stepId}
                className={cn(
                  'rounded-2xl px-4 py-3',
                  isCompleted
                      ? 'bg-[var(--app-surface-muted)]'
                    : isFailed
                      ? (isDark ? 'bg-red-500/10' : 'bg-red-50')
                    : isPlanningReady
                      ? (isDark ? 'bg-amber-500/10' : 'bg-amber-50')
                      : isInProgress
                        ? (isDark ? 'bg-blue-500/15' : 'bg-blue-50')
                        : 'bg-transparent',
                )}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={cn(
                      'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border text-[11px] leading-none',
                      isCompleted
                        ? (isDark ? 'border-emerald-400/60 bg-emerald-500/20 text-emerald-200' : 'border-emerald-500 bg-emerald-500 text-white')
                        : isFailed
                          ? (isDark ? 'border-red-300/50 bg-red-500/10 text-red-200' : 'border-red-400 bg-white text-red-700')
                        : isPlanningReady
                          ? (isDark ? 'border-amber-300/50 bg-amber-500/10 text-amber-200' : 'border-amber-400 bg-white text-amber-700')
                          : isInProgress
                            ? (isDark ? 'border-blue-300/50 bg-blue-500/10 text-blue-200' : 'border-blue-400 bg-white text-blue-700')
                            : 'border-[var(--app-border)] bg-transparent text-transparent',
                    )}
                  >
                    {isCompleted ? '✓' : isFailed ? '!' : '•'}
                  </div>
                  <div className="min-w-0">
                    <div className={cn('text-sm font-medium leading-6', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
                      {String(step.order || '')}. {String(step.title || '')}
                    </div>
                    {step.description ? (
                      <div className={cn('mt-1 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                        {String(step.description)}
                      </div>
                    ) : null}
                    <div
                      className={cn(
                        'mt-1 flex min-w-0 items-center gap-x-2 text-[11px] font-medium',
                        isCompleted
                          ? (isDark ? 'text-emerald-300/90' : 'text-emerald-700')
                          : isFailed
                            ? (isDark ? 'text-red-200/90' : 'text-red-700')
                          : isPlanningReady
                            ? (isDark ? 'text-amber-200/90' : 'text-amber-700')
                            : isInProgress
                              ? (isDark ? 'text-blue-200/90' : 'text-blue-700')
                              : (isDark ? 'text-zinc-500' : 'text-zinc-500'),
                      )}
                    >
                      <span className="shrink-0">{getPlanStepStatusLabel(displayStepStatus, t)}</span>
                      {stepMetaLabel ? (
                        <span
                          className={cn('min-w-0 truncate', isDark ? 'text-zinc-500' : 'text-zinc-500')}
                          title={stepMetaLabel.title}
                        >
                          {stepMetaLabel.text}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (block.uiKind === 'planning_draft_card') {
    const draftOutline = normalizePlanOutlineItems(block.payload?.draftOutline ?? block.payload?.draft_outline)
    const assumptions = Array.isArray(block.payload?.assumptions) ? block.payload.assumptions : []
    const openQuestions = Array.isArray(block.payload?.openQuestions ?? block.payload?.open_questions)
      ? (block.payload?.openQuestions ?? block.payload?.open_questions)
      : []
    const confirmedInputs = (
      block.payload?.confirmedInputs && typeof block.payload.confirmedInputs === 'object'
        ? block.payload.confirmedInputs
        : block.payload?.confirmed_inputs && typeof block.payload.confirmed_inputs === 'object'
          ? block.payload.confirmed_inputs
          : {}
    ) as Record<string, any>
    const confirmedEntries = Object.entries(confirmedInputs).filter(([, value]) => (
      value !== null && value !== undefined && String(value).trim() !== ''
    ))

    return (
      <div
        key={block.id}
        className={cn(
          'app-card max-w-[90%] rounded-2xl px-4 py-4 space-y-4',
        )}
      >
        <div className="min-w-0">
          <div className={cn('flex items-center gap-2 text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
            <span>{t('home.planningDraft.title', 'Planning draft')}</span>
            <span
              className={cn(
                'rounded-full border px-2 py-0.5 text-[11px] font-medium',
                isDark ? 'border-amber-300/20 bg-amber-300/10 text-amber-100' : 'border-amber-200 bg-amber-50 text-amber-700',
              )}
            >
              {t('home.planningDraft.status', 'Needs refinement')}
            </span>
          </div>
          {block.payload?.summary ? (
            <div className={cn('mt-2 text-sm leading-6', isDark ? 'text-zinc-300' : 'text-zinc-700')}>
              {String(block.payload.summary)}
            </div>
          ) : null}
        </div>

        {draftOutline.length > 0 ? (
          <div className="space-y-2">
            <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
              {t('home.planningDraft.outline', 'Draft outline')}
            </div>
            <div className="space-y-2">
              {draftOutline.map((item, index) => (
                <div
                  key={String(item.id || index)}
                  className="app-card-muted rounded-2xl px-4 py-3"
                >
                  <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
                    {String(item.title || t('home.planningDraft.untitledItem', 'Untitled item'))}
                  </div>
                  {item.summary || item.description ? (
                    <div className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                      {String(item.summary || item.description)}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {confirmedEntries.length > 0 ? (
          <div className="space-y-2">
            <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
              {t('home.planningDraft.confirmedInputs', 'Confirmed inputs')}
            </div>
            <div className="flex flex-wrap gap-2">
              {confirmedEntries.map(([key, value]) => (
                <span
                  key={key}
                  className="app-chip rounded-full px-2.5 py-1 text-xs"
                >
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {assumptions.length > 0 || openQuestions.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2">
            {assumptions.length > 0 ? (
              <div className="space-y-2">
                <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {t('home.planningDraft.assumptions', 'Assumptions')}
                </div>
                <ul className={cn('space-y-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                  {assumptions.map((item: unknown, index: number) => (
                    <li key={index}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {openQuestions.length > 0 ? (
              <div className="space-y-2">
                <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {t('home.planningDraft.openQuestions', 'Open questions')}
                </div>
                <ul className={cn('space-y-1 text-sm leading-6', isDark ? 'text-amber-200/90' : 'text-amber-700')}>
                  {openQuestions.map((item: unknown, index: number) => (
                    <li key={index}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    )
  }

  if (block.uiKind === 'user_plan_card') {
    const outline = Array.isArray(block.payload?.outline)
      ? block.payload.outline as Array<Record<string, any>>
      : []
    const projectionState = (block.payload?.projectionState && typeof block.payload.projectionState === 'object')
      ? block.payload.projectionState as Record<string, any>
      : (block.payload?.projection_state && typeof block.payload.projection_state === 'object')
        ? block.payload.projection_state as Record<string, any>
        : null
    const executionState = (block.payload?.executionState && typeof block.payload.executionState === 'object')
      ? block.payload.executionState as Record<string, any>
      : (block.payload?.execution_state && typeof block.payload.execution_state === 'object')
        ? block.payload.execution_state as Record<string, any>
        : null
    const blockItems = normalizePlanOutlineItems(block.payload?.items)
    const outlineItems = blockItems.length > 0
      ? blockItems
      : normalizePlanOutlineItems(outline)
    const constraints = Array.isArray(block.payload?.constraints) ? block.payload.constraints : []
    const styleNotes = Array.isArray(block.payload?.styleNotes)
      ? block.payload.styleNotes
      : Array.isArray(block.payload?.style_notes)
        ? block.payload.style_notes
        : []
    const currentOutline = outlineRuntime?.current_outline || null
    const cardPlanInstanceId = String(block.payload?.planInstanceId || block.payload?.plan_instance_id || '')
    const cardOutlineVersion = Number(block.payload?.outlineVersion ?? block.payload?.outline_version ?? 0) || 0
    const currentPlanInstanceId = String(currentOutline?.plan_instance_id || '')
    const currentOutlineVersion = Number(currentOutline?.version ?? 0) || 0
    const snapshotStatus = String(block.payload?.snapshotStatus || block.payload?.snapshot_status || '').toLowerCase()
    const effectiveSnapshotStatus = snapshotStatus || 'active'
    const isCurrentCard = Boolean(
      currentOutline
      && (
        (
          cardPlanInstanceId
          && cardPlanInstanceId === currentPlanInstanceId
          && cardOutlineVersion > 0
          && cardOutlineVersion === currentOutlineVersion
        )
        || (!cardPlanInstanceId && !cardOutlineVersion)
      ),
    )
    const shouldShowLiveProgress = isCurrentCard || !currentOutline
    const currentProgressMessage = shouldShowLiveProgress
      ? String(userProgress?.message || block.payload?.progressMessage || block.payload?.progress_message || '').trim()
      : ''
    const currentCompletedMessage = shouldShowLiveProgress
      ? String(userProgress?.completed_message || block.payload?.completedMessage || block.payload?.completed_message || '').trim()
      : ''
    const currentOutlineItems = normalizePlanOutlineItems(currentOutline?.items)
    const currentPlanView = currentOutline
      ? {
          ...currentOutline,
          items: currentOutlineItems.length > 0 ? currentOutlineItems : outlineItems,
          projection_state: outlineRuntime?.projection_state || projectionState || currentOutline.projection_state || null,
          execution_state: outlineRuntime?.execution_state || executionState || currentOutline.execution_state || null,
          progress_message: currentProgressMessage || currentOutline.progress_message || null,
          readonly: Boolean(
            !isCurrentCard
            || effectiveSnapshotStatus !== 'active'
            || currentOutline.readonly
            || block.payload?.readonly
            || projectionState?.readonly
            || conversationPhase === 'executing',
          ),
        }
      : null
    const historicalPlanView = {
      artifact_type: String(block.payload?.artifactType || block.payload?.artifact_type || 'other'),
      title: String(block.payload?.title || ''),
      summary: String(block.payload?.summary || ''),
      status: String(block.payload?.status || 'planning_ready'),
      plan_instance_id: cardPlanInstanceId || null,
      snapshot_status: effectiveSnapshotStatus,
      outline_id: block.payload?.outlineId || block.payload?.outline_id || null,
      version: cardOutlineVersion || null,
      progress_message: block.payload?.progressMessage || block.payload?.progress_message || null,
      items: outlineItems,
      constraints,
      style_notes: styleNotes,
      outline: normalizePlanOutlineItems(outline),
      projection_state: projectionState,
      execution_state: executionState,
      readonly: Boolean(block.payload?.readonly || projectionState?.readonly || conversationPhase === 'executing' || currentOutline),
    }
    const editablePlan = (isCurrentCard && currentPlanView) ? currentPlanView : historicalPlanView
    const shouldRenderLivePlanCard = isCurrentCard || !currentOutline
    const isPlanningReady = (
      conversationPhase === 'planning_ready'
      && Boolean(outlineRuntime?.current_outline)
      && isCurrentCard
      && effectiveSnapshotStatus === 'active'
    )
    return (
      <div
        key={block.id}
        className={cn(
          'app-card max-w-[90%] rounded-2xl px-4 py-4 space-y-3',
        )}
      >
        <div className="space-y-3">
          <div className="min-w-0">
            <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
              {String(block.payload?.title || '')}
            </div>
            {block.payload?.summary ? (
              <div className={cn('mt-1 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                {String(block.payload.summary)}
              </div>
            ) : null}
            {shouldShowLiveProgress && currentProgressMessage ? (
              <div
                className={cn(
                  'app-card-muted mt-3 rounded-2xl px-4 py-3',
                )}
              >
                <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {t('home.user_progress.title', 'Current progress')}
                </div>
                <div className={cn('mt-2 text-sm', isDark ? 'text-zinc-200' : 'text-zinc-800')}>
                  {currentProgressMessage}
                </div>
                {currentCompletedMessage ? (
                  <div className={cn('mt-1 text-xs', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                    {currentCompletedMessage}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        {outlineItems.length > 0 ? (
          shouldRenderLivePlanCard && ((isPlanningReady && onRevisePlan && onPatchCurrentOutline) || editablePlan.readonly) ? (
            <HomeHarnessInlinePlanEditor
              plan={editablePlan as UserPlanRead}
              isDark={isDark}
              t={t}
              isSubmitting={isPlanningReady ? false : isStreaming}
              onStartExecution={onStartExecution}
              onRevisePlan={onRevisePlan || (async () => {})}
              onPatchCurrentOutline={onPatchCurrentOutline || (async () => {})}
            />
          ) : (
            <div className="space-y-2">
              {outlineItems.map((item: Record<string, any>, index: number) => (
                <div
                  key={String(item.id || index)}
                  className="app-card-muted rounded-2xl px-4 py-3"
                >
                  <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
                    {String(item.title || '')}
                  </div>
                  {item.summary || item.description ? (
                    <div className={cn('mt-1 text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                      {String(item.summary || item.description || '')}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )
        ) : null}
        {constraints.length > 0 ? (
          <div className="space-y-1">
            <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
              {t('home.planReview.constraints', 'Constraints')}
            </div>
            <div className="flex flex-wrap gap-2">
              {constraints.map((constraint: string, index: number) => (
                <span
                  key={`${constraint}-${index}`}
                  className="app-chip rounded-full px-2.5 py-1 text-[11px]"
                >
                  {constraint}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        {styleNotes.length > 0 ? (
          <div className="space-y-1">
            <div className={cn('text-xs font-medium uppercase tracking-wide', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
              {t('home.planReview.styleNotes', 'Style notes')}
            </div>
            <div className={cn('text-xs leading-5', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
              {styleNotes.join(' · ')}
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  if (block.uiKind === 'user_progress_card' || presentationUiKind === 'progress_card') {
    return null
  }

  if (presentationUiKind === 'error_card') {
    const message = String(block.payload?.message || block.payload?.error || block.payload?.summary || '')
    return message.trim() ? (
      <div
        key={block.id}
        className={cn(
          'max-w-[90%] rounded-2xl border px-4 py-3 text-sm',
          isDark ? 'border-red-300/20 bg-red-500/10 text-red-100' : 'border-red-200 bg-red-50 text-red-800',
        )}
      >
        {message}
      </div>
    ) : null
  }

  if (block.uiKind === 'md_document') {
    const filePath = String(block.payload?.filePath || block.payload?.file_path || '')
    const docStatus = String(block.payload?.status || block.status || 'running')
    const previewSections = Array.isArray(block.payload?.previewSections)
      ? block.payload.previewSections
      : Array.isArray(block.payload?.preview_sections)
        ? block.payload.preview_sections
        : []
    const updatedAt = String(block.payload?.updatedAt || block.payload?.updated_at || '')
    const updatedLabel = updatedAt
      ? new Date(updatedAt).toLocaleString('zh-CN', { hour12: false })
      : ''

    return (
      <div
        key={block.id}
        className={cn(
          'app-card max-w-[90%] rounded-2xl px-4 py-4 space-y-3',
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className={cn('text-sm font-semibold', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
              {String(block.payload?.title || block.payload?.fileName || block.payload?.file_name || 'Markdown Document')}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <div
                className={cn(
                  'inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold',
                  docStatus.toLowerCase() === 'completed'
                    ? (isDark ? 'bg-emerald-500/15 text-emerald-200' : 'bg-emerald-50 text-emerald-700')
                    : (isDark ? 'bg-blue-500/15 text-blue-200' : 'bg-blue-50 text-blue-700'),
                )}
              >
                {docStatus.toLowerCase() === 'completed' ? '已完成' : docStatus.toLowerCase() === 'refining' ? '润色中' : '撰写中'}
              </div>
              {updatedLabel ? (
                <div className={cn('text-[11px]', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                  {updatedLabel}
                </div>
              ) : null}
            </div>
            {block.payload?.summary ? (
              <div className={cn('mt-2 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                {String(block.payload.summary)}
              </div>
            ) : null}
          </div>
          {filePath ? (
            <button
              type="button"
              onClick={() => onOpenWorkspaceRelativeFile?.(
                filePath,
                String(block.payload?.fileName || block.payload?.file_name || filePath.split('/').pop() || 'document.md'),
              )}
              className={cn(
                'app-chip shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium',
              )}
            >
              打开全文
            </button>
          ) : null}
        </div>
        <div className="space-y-2">
          {previewSections.map((section: Record<string, any>, index: number) => (
            <div
              key={`${block.id}-preview-${index}`}
              className="app-card-muted rounded-xl px-3 py-3"
            >
              {section.heading ? (
                <div className="text-sm font-medium">
                  {String(section.heading)}
                </div>
              ) : null}
              {section.snippet ? (
                <div className={cn('mt-1 text-sm leading-6', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                  {String(section.snippet)}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (block.uiKind === 'media_card' || block.uiKind === 'generation_card' || presentationUiKind === 'artifact_card') {
    const mediaType = String(block.payload?.mediaType || block.payload?.media_type || '')
    if (mediaType === 'image_analysis') {
      const elapsedMs = Number(
        block.payload?.elapsedMs
        ?? block.payload?.elapsed_ms
        ?? block.payload?.result?.elapsedMs
        ?? block.payload?.result?.elapsed_ms
        ?? 0,
      )
      return (
        <AnalyzeImageCard
          key={block.id}
          toolName="analyze_image"
          text={extractAnalyzeImageDisplayText('', String(block.payload?.text || ''))}
          status={String(block.payload?.status || block.status || 'completed')}
          elapsedLabel={elapsedMs > 0 ? `${(elapsedMs / 1000).toFixed(1)}s` : null}
          isDark={isDark}
        />
      )
    }

    return (
      <GenerationCard
        key={block.id}
        conversationId={conversationId}
        taskId={block.payload?.taskId ?? block.payload?.task_id ?? ''}
        status={String(block.payload?.status || block.status || 'completed')}
        mediaType={mediaType === 'video_generation' ? 'video' : (mediaType || undefined)}
        toolName={String(block.payload?.toolName || block.payload?.tool_name || (mediaType === 'video_generation' ? 'generate_video' : 'generate_image'))}
        resultUrl={block.payload?.resultUrl || block.payload?.result_url}
        artifact={block.payload?.artifact}
        prompt={String(block.payload?.prompt || '') || undefined}
        modelName={String(block.payload?.modelName || block.payload?.model_name || '') || undefined}
        modelLabel={block.payload?.modelLabel || block.payload?.model_label}
        aspectRatio={String(block.payload?.aspectRatio || block.payload?.aspect_ratio || '') || undefined}
        resolution={String(block.payload?.resolution || '') || undefined}
        duration={block.payload?.duration}
        quality={String(block.payload?.quality || '') || undefined}
        onUseAsReference={onUseGeneratedAsReference}
        isDark={isDark}
      />
    )
  }

  return null
}

export const HomeHarnessMessageList = memo(function HomeHarnessMessageList({
  messages,
  streamingBlocks,
  isStreaming,
  runStatus,
  isDark,
  t,
  language,
  conversationId,
  conversationLastActivityAt,
  conversationRuntime,
  conversationPhase,
  outlineRuntime,
  userProgress,
  userInteraction,
  respondToAgent,
  onStartExecution,
  onRevisePlan,
  onPatchCurrentOutline,
  hiddenToolCalls,
  onOpenWorkspaceRelativeFile,
  sessionFiles = [],
  onPreviewWorkspaceFile,
  onUseGeneratedAsReference,
  onRequestEcommerceReferenceImages,
  onUploadEcommerceReferenceImage,
  maxEcommerceReferenceImages,
  scrollParent,
}: HomeHarnessMessageListProps) {
  const [submittingInteractionLabels, setSubmittingInteractionLabels] = useState<Record<string, string>>({})
  const [visibleRange, setVisibleRange] = useState<{ startIndex: number; endIndex: number } | null>(null)
  const [expandedCompactBlockIds, setExpandedCompactBlockIds] = useState<Set<string>>(() => new Set())
  const isAgentBusy = isStreaming || runStatus === 'running'
  const enablePersistedAssistantFileReferences = !isStreaming && runStatus !== 'running'
  const renderableMessages = useMemo(
    () => buildRenderableHomeHarnessMessages(messages, streamingBlocks, isStreaming),
    [messages, streamingBlocks, isStreaming],
  )
  const renderableGroups = useMemo(
    () => buildRenderableHomeHarnessGroups(renderableMessages),
    [renderableMessages],
  )
  const standaloneInteractionRequestId = String(userInteraction?.request_id || '').trim()
  const shouldRenderStandaloneInteraction = Boolean(
    userInteraction
    && standaloneInteractionRequestId
    && !hasRenderableInteractionRequest(renderableMessages, standaloneInteractionRequestId),
  )
  const shouldShowThinkingPlaceholder = isAgentBusy
    && streamingBlocks.length === 0
    && !hasVisibleInFlightGeneration(renderableMessages)
  const planRenderState: HomepagePlanRenderState | undefined = useMemo(
    () => (conversationPhase === 'planning_ready' ? { planningReady: true } : undefined),
    [conversationPhase],
  )
  const copyToClipboard = useCallback((text: string) => {
    navigator.clipboard.writeText(text)
    toast.success(t('common.copied', 'Copied'))
  }, [t])

  const handleRespondToInteraction = useCallback(async (
    requestId: string,
    answer: string,
    displayLabel?: string,
    approved?: boolean,
    answers?: Record<string, any> | null,
  ) => {
    const nextLabel = String(displayLabel || answer || '').trim() || answer
    setSubmittingInteractionLabels((current) => ({
      ...current,
      [requestId]: nextLabel,
    }))
    try {
      await respondToAgent(requestId, answer, displayLabel, approved, answers)
    } finally {
      setSubmittingInteractionLabels((current) => {
        const next = { ...current }
        delete next[requestId]
        return next
      })
    }
  }, [respondToAgent])

  const renderWeightSnapshot = useMemo<AgentRenderWeightSnapshot>(() => {
    const weights = renderableGroups.map((group) => group.messages.reduce(
      (sum, message) => sum + getAgentMessageRenderWeight(message),
      0,
    ))
    return {
      itemCount: renderableGroups.length,
      totalWeight: weights.reduce((sum, weight) => sum + weight, 0),
      heavyItemCount: weights.filter((weight) => weight >= 8).length,
    }
  }, [renderableGroups])
  const shouldVirtualizeGroups = shouldVirtualizeAgentItems(renderWeightSnapshot, {
    itemThreshold: 30,
    weightThreshold: 50,
  }) || renderableGroups.length > HOME_VIRTUALIZE_GROUP_THRESHOLD
  const getHeavyBlockRenderMode = useCallback((groupIndex: number, blockId: string): 'compact' | 'full' => {
    if (!shouldVirtualizeGroups || !visibleRange || expandedCompactBlockIds.has(blockId)) {
      return 'full'
    }
    const distance = groupIndex < visibleRange.startIndex
      ? visibleRange.startIndex - groupIndex
      : groupIndex > visibleRange.endIndex
        ? groupIndex - visibleRange.endIndex
        : 0
    return distance > 2 ? 'compact' : 'full'
  }, [expandedCompactBlockIds, shouldVirtualizeGroups, visibleRange])
  const handleExpandCompactBlock = useCallback((blockId: string) => {
    setExpandedCompactBlockIds((current) => {
      const next = new Set(current)
      next.add(blockId)
      return next
    })
  }, [])

  const renderGroup = (group: HomeHarnessRenderableGroup, groupIndex: number) => {
    return (
          <div key={group.id}>
            {group.role === 'user' && group.messages.map((msg) => (
              <div key={msg.id} className="flex justify-end w-full group mb-2">
                <div className="flex max-w-[min(80%,760px)] min-w-0 items-center gap-2">
                  <button
                    onClick={() => copyToClipboard(msg.content || '')}
                    className="app-muted p-1.5 rounded-md opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--app-control-hover)]"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                  <div className="flex min-w-0 max-w-full flex-col items-end gap-2">
                    {msg.attachments && msg.attachments.length > 0 ? (
                      <AttachmentCardStrip
                        attachments={msg.attachments as AttachmentData[]}
                        isDark={isDark}
                        className="justify-end"
                        conversationId={conversationId}
                        onOpenWorkspaceRelativeFile={onOpenWorkspaceRelativeFile}
                      />
                    ) : null}
                    {msg.baseFileVersions?.map((version) => (
                      <div
                        key={`${version.file_id}:${version.version_id || 'current'}`}
                        className="app-chip-primary inline-flex max-w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs leading-none shadow-sm"
                      >
                        <History className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">
                          {t('homeHarness.fileVersions.composerBaseVersion', {
                            name: version.name || version.file_id,
                            version: formatBaseVersionNumber(version.version_id),
                          })}
                        </span>
                      </div>
                    ))}
                    <div
                      className={cn(
                        'min-w-0 max-w-full overflow-hidden rounded-[20px] px-4 py-2.5 text-[15px] whitespace-pre-wrap break-words [overflow-wrap:anywhere] shadow-sm',
                        'bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)]',
                      )}
                    >
                      {summarizeInteractionJsonContent(msg.content || '', language) || msg.content}
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {group.role === 'assistant' && (
              <div className="flex flex-col gap-3" data-testid="home-harness-assistant-message">
                <div className="flex items-center gap-2.5">
                  <div className="w-6 h-6 rounded-lg bg-blue-500 flex items-center justify-center p-1 shadow-md">
                    <Bot className="w-full h-full text-white" />
                  </div>
                  <span className={cn('text-sm font-semibold', isDark ? 'text-zinc-200' : 'text-zinc-800')}>
                    {t('home.agent', 'Agent')}
                  </span>
                </div>
                <div className="pl-8 space-y-2">
                  {group.messages.map((msg) => {
                    const dedupedBlocks = mergeHomepageMessageBlocks(msg.blocks || [])
                    const renderBlocksInOrder = shouldRenderHomepageAssistantBlocksInOrder(dedupedBlocks)
                    const assistantBlocks = renderBlocksInOrder
                      ? dedupedBlocks
                      : (
                          msg.content
                            ? dedupedBlocks.filter((block) => block.uiKind !== 'assistant_text' && block.uiKind !== 'assistant_final_answer')
                            : dedupedBlocks
                        )
                    return (
                      <div key={msg.id} className="space-y-2">
                        {!renderBlocksInOrder && msg.content ? (
                          <HomeChatMarkdown
                            content={msg.content}
                            isDark={isDark}
                            className="max-w-[90%]"
                            conversationId={conversationId}
                            workspaceFiles={sessionFiles}
                            enableWorkspaceFileReferences={!isStreaming && !!onPreviewWorkspaceFile}
                            enableArtifactReferences={!isStreaming}
                            onOpenWorkspaceFile={onPreviewWorkspaceFile}
                          />
                        ) : null}
                        {assistantBlocks.map((block) => (
                          <Fragment key={block.id}>
                            {renderUserFacingHomeChatBlock(
                              block,
                              msg.content,
                              isDark,
                              t,
                              language,
                              isStreaming,
                              conversationId,
                              conversationLastActivityAt,
                              conversationRuntime,
                              conversationPhase,
                              outlineRuntime,
                              userProgress,
                              onOpenWorkspaceRelativeFile,
                              onUseGeneratedAsReference,
                              handleRespondToInteraction,
                              onStartExecution,
                              onRevisePlan,
                              onPatchCurrentOutline,
                              hiddenToolCalls,
                              sessionFiles,
                              onPreviewWorkspaceFile,
                              enablePersistedAssistantFileReferences,
                              submittingInteractionLabels,
                              planRenderState,
                              getHeavyBlockRenderMode(groupIndex, String(block.id)),
                              handleExpandCompactBlock,
                              onRequestEcommerceReferenceImages,
                              onUploadEcommerceReferenceImage,
                              maxEcommerceReferenceImages,
                            )}
                          </Fragment>
                        ))}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
    )
  }

  const footerContent = (
    <>
      {shouldRenderStandaloneInteraction && userInteraction ? (
        <div className="flex flex-col gap-3" data-testid="home-harness-standalone-interaction">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-blue-500 flex items-center justify-center p-1 shadow-md">
              <Bot className="w-full h-full text-white" />
            </div>
            <span className={cn('text-sm font-semibold', isDark ? 'text-zinc-200' : 'text-zinc-800')}>
              {t('home.agent', 'Agent')}
            </span>
          </div>
          <div className="pl-8 space-y-2">
            {isEcommerceInteractionKind(userInteraction.kind) ? (
              <EcommerceInteractionCard
                interaction={userInteraction}
                disabled={userInteraction.status === 'submitted'}
                isSubmitting={!!submittingInteractionLabels[standaloneInteractionRequestId]}
                conversationId={conversationId}
                onRequestReferenceImages={onRequestEcommerceReferenceImages}
                onUploadReferenceImage={onUploadEcommerceReferenceImage}
                maxReferenceImages={maxEcommerceReferenceImages}
                onRespond={(requestId, answer, displayLabel, answers) => {
                  void handleRespondToInteraction(requestId, answer, displayLabel, undefined, answers)
                }}
              />
            ) : (
              <HomeHarnessInteractionForm
                requestId={standaloneInteractionRequestId}
                kind={userInteraction.kind}
                question={userInteraction.question}
                content={userInteraction.content ?? null}
                language={language}
                phase={conversationPhase}
                schema={userInteraction.schema ?? null}
                answers={userInteraction.answers ?? null}
                status={userInteraction.status === 'submitted' ? 'submitted' : 'pending'}
                isDark={isDark}
                isSubmitting={!!submittingInteractionLabels[standaloneInteractionRequestId]}
                t={t}
                onSubmit={handleRespondToInteraction}
              />
            )}
          </div>
        </div>
      ) : null}

      {shouldShowThinkingPlaceholder && (
        <div className="flex flex-col gap-3" data-testid="home-harness-thinking">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-blue-500 flex items-center justify-center p-1 shadow-md">
              <Bot className="w-full h-full text-white" />
            </div>
            <span className={cn('text-sm font-semibold', isDark ? 'text-zinc-200' : 'text-zinc-800')}>
              {t('home.agent', 'Agent')}
            </span>
          </div>
          <div className="pl-8 space-y-2">
            <div className="flex items-center gap-3 text-zinc-500 animate-pulse">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">{t('canvas.chat.thinking', 'Thinking...')}</span>
            </div>
          </div>
        </div>
      )}
    </>
  )

  // Windowed path for long conversations. Uses the page's existing scroll container
  // (customScrollParent) so useHomeChatMessageScroll keeps owning stick-to-bottom and the
  // load-older scroll anchor; Virtuoso only limits how many groups are mounted at once.
  if (shouldVirtualizeGroups && scrollParent) {
    return (
      <Virtuoso
        key={conversationId ?? 'none'}
        customScrollParent={scrollParent}
        data={renderableGroups}
        computeItemKey={(_index, group) => group.id}
        initialTopMostItemIndex={{
          index: Math.max(0, renderableGroups.length - 1),
          align: 'end',
        }}
        rangeChanged={(range) => setVisibleRange(range)}
        itemContent={(index) => (
          <div className="pb-6">{renderGroup(renderableGroups[index], index)}</div>
        )}
        components={HOME_VIRTUOSO_COMPONENTS}
        context={{ footer: footerContent }}
      />
    )
  }

  return (
    <div className="flex flex-col gap-6 w-full pb-4">
      {renderableGroups.map((group, index) => renderGroup(group, index))}
      {footerContent}
    </div>
  )
})
