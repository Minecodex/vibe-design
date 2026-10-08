import type { ChatMessage, MessageBlock } from './homeHarnessStore'

const USER_VISIBLE_UI_KINDS = new Set([
  'assistant_final_answer',
  'assistant_text',
  'design_jury_card',
  'interaction_form',
  'friendly_issue',
  'friendly_status',
  'generation_card',
  'generation_task',
  'md_document',
  'media_card',
  'plan_artifact',
  'planning_draft_card',
  'user_artifact_card',
  'user_plan_card',
  'user_progress_card',
  'subagent_card',
  'text',
  'tool_call',
  'tool_result',
  'tool_group',
  'compact_tool',
  'web_search_card',
])

export function toCamelKey(key: string): string {
  return key.replace(/_([a-z])/g, (_match, letter: string) => letter.toUpperCase())
}

export function camelizeBlockPayload(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => camelizeBlockPayload(item))
  }
  if (!value || typeof value !== 'object') {
    return value
  }

  const source = value as Record<string, unknown>
  const next: Record<string, unknown> = {}
  for (const [key, entry] of Object.entries(source)) {
    next[toCamelKey(key)] = camelizeBlockPayload(entry)
  }
  return next
}

export function normalizeBlock(raw: Record<string, any>): MessageBlock {
  const payload = (camelizeBlockPayload(raw.payload || {}) as Record<string, unknown>) || {}
  return {
    id: String(raw.id),
    kind: raw.kind,
    order: Number(raw.order ?? 0),
    status: String(raw.status ?? 'completed'),
    visible: raw.visible !== false,
    userVisible: raw.userVisible ?? raw.user_visible ?? payload.userVisible ?? payload.user_visible,
    debugOnly: Boolean(raw.debugOnly ?? raw.debug_only ?? payload.debugOnly ?? payload.debug_only ?? false),
    uiKind: String(raw.uiKind ?? raw.ui_kind ?? raw.kind ?? 'text'),
    payload,
    renderKey: raw.renderKey ?? raw.render_key ?? payload.renderKey ?? payload.render_key,
    taskId: raw.taskId ?? raw.task_id ?? raw.payload?.taskId ?? raw.payload?.task_id,
    label: raw.label ?? raw.payload?.label ?? raw.payload?.result?.label,
    summary: raw.summary ?? raw.payload?.summary,
    expanded: typeof raw.expanded === 'boolean' ? raw.expanded : undefined,
    children: normalizeBlocks(raw.children),
    revision: normalizePositiveNumber(raw.revision ?? payload.revision),
    sourceSequence: normalizePositiveNumber(
      raw.sourceSequence
      ?? raw.source_sequence
      ?? payload.sourceSequence
      ?? payload.source_sequence,
    ),
  }
}

function normalizePositiveNumber(value: unknown): number | undefined {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

export function isUserVisibleHomepageBlock(block: MessageBlock): boolean {
  if (block.visible === false || block.debugOnly === true || block.userVisible === false) {
    return false
  }
  if (block.payload?.debugOnly === true || block.payload?.debug_only === true) {
    return false
  }
  if (block.payload?.userVisible === false || block.payload?.user_visible === false) {
    return false
  }
  return USER_VISIBLE_UI_KINDS.has(String(block.uiKind || ''))
}

export function filterHomepageBlocks(blocks: MessageBlock[]): MessageBlock[] {
  return blocks
    .filter(isUserVisibleHomepageBlock)
    .map((block) => ({
      ...block,
      children: filterHomepageBlocks(block.children || []),
    }))
}

export function normalizeBlocks(rawBlocks: unknown): MessageBlock[] {
  if (!Array.isArray(rawBlocks)) {
    return []
  }
  return filterHomepageBlocks(
    rawBlocks
      .filter((block): block is Record<string, unknown> => !!block && typeof block === 'object')
      .map(normalizeBlock)
      .sort((a, b) => a.order - b.order),
  )
}

export function appendBlockDelta(blocks: MessageBlock[], blockId: string, field: string, delta: string): MessageBlock[] {
  const normalizedField = toCamelKey(field)
  return blocks.map((block) => {
    if (block.id !== blockId) {
      return block
    }
    const previous = typeof block.payload[normalizedField] === 'string' ? block.payload[normalizedField] : ''
    return {
      ...block,
      payload: {
        ...block.payload,
        [normalizedField]: `${previous}${delta}`,
      },
    }
  })
}

export function appendBlockDeltaWithPlaceholder(
  blocks: MessageBlock[],
  blockId: string,
  field: string,
  delta: string,
): MessageBlock[] {
  const updated = appendBlockDelta(blocks, blockId, field, delta)
  if (updated.some((block) => block.id === blockId)) {
    return updated
  }

  const normalizedField = toCamelKey(field)
  const nextOrder = blocks.length > 0
    ? Math.max(...blocks.map((block) => Number(block.order ?? 0))) + 1
    : 0
  return [
    ...blocks,
    {
      id: blockId,
      kind: 'content',
      order: nextOrder,
      status: 'running',
      visible: true,
      uiKind: 'assistant_text',
      payload: {
        [normalizedField]: delta,
      },
    },
  ]
}

export function upsertBlockStart(blocks: MessageBlock[], raw: Record<string, unknown>): MessageBlock[] {
  const normalized = normalizeBlock(raw)
  if (!isUserVisibleHomepageBlock(normalized)) {
    return blocks
  }
  const existing = blocks.find((block) => block.id === normalized.id)
  if (!existing) {
    return [...blocks, normalized].sort((a, b) => a.order - b.order)
  }

  return blocks
    .map((block) => {
      if (block.id !== normalized.id) {
        return block
      }
      return {
        ...normalized,
        payload: {
          ...normalized.payload,
          ...block.payload,
        },
        children: normalized.children?.length ? normalized.children : block.children,
      }
    })
    .sort((a, b) => a.order - b.order)
}

export function mergeBlockPatch(blocks: MessageBlock[], blockId: string, patch: Record<string, unknown>): MessageBlock[] {
  const merge = (target: Record<string, unknown>, nextPatch: Record<string, unknown>): Record<string, unknown> => {
    const result = { ...target }
    for (const [key, value] of Object.entries(nextPatch)) {
      if (key === 'children' && Array.isArray(value)) {
        result[key] = normalizeBlocks(value)
        continue
      }
      if (
        value
        && typeof value === 'object'
        && !Array.isArray(value)
        && result[key]
        && typeof result[key] === 'object'
        && !Array.isArray(result[key])
      ) {
        result[key] = merge(result[key] as Record<string, unknown>, value as Record<string, unknown>)
      } else {
        result[key] = value
      }
    }
    return result
  }

  let didUpdate = false
  const nextBlocks = blocks.map((block) => {
    if (block.id !== blockId) {
      return block
    }
    didUpdate = true
    return merge(block as unknown as Record<string, unknown>, patch) as unknown as MessageBlock
  })

  return didUpdate ? filterHomepageBlocks(nextBlocks) : blocks
}

export function replaceBlockEnd(blocks: MessageBlock[], raw: Record<string, unknown>): MessageBlock[] {
  const normalized = normalizeBlock(raw)
  if (!isUserVisibleHomepageBlock(normalized)) {
    return blocks
  }

  return blocks
    .filter((block) => block.id !== normalized.id)
    .concat(normalized)
    .sort((a, b) => a.order - b.order)
}

export function replaceExistingBlockEnd(blocks: MessageBlock[], raw: Record<string, unknown>): MessageBlock[] {
  const normalized = normalizeBlock(raw)
  if (!isUserVisibleHomepageBlock(normalized)) {
    return blocks
  }

  if (!blocks.some((block) => block.id === normalized.id)) {
    return blocks
  }

  return blocks
    .filter((block) => block.id !== normalized.id)
    .concat(normalized)
    .sort((a, b) => a.order - b.order)
}

export function extractMessageText(blocks: MessageBlock[]): string | null {
  const text = blocks
    .filter((block) => (
      block.kind === 'text'
      || (block.kind === 'content' && (block.uiKind === 'assistant_text' || block.uiKind === 'assistant_final_answer'))
    ))
    .map((block) => String(block.payload.text || '').trim())
    .filter(Boolean)
    .join('\n')
  return text || null
}

export function extractBlockCallId(block: MessageBlock): string | null {
  const payloadCallId = block.payload.callId
    ?? block.payload.call_id
    ?? block.payload.result?.callId
    ?? block.payload.result?.call_id
  if (payloadCallId != null && String(payloadCallId)) {
    return String(payloadCallId)
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

function isAnalyzeImageStreamPanel(block: MessageBlock): boolean {
  if (block.uiKind !== 'stream_panel') {
    return false
  }
  const toolName = String(block.payload.toolName || block.payload.tool_name || '').replace(/^lc_/, '')
  return toolName === 'analyze_image'
}

function isImageAnalysisMediaCard(block: MessageBlock): boolean {
  return block.uiKind === 'media_card'
    && String(block.payload.mediaType || block.payload.media_type || '') === 'image_analysis'
}

export function dedupeStreamingBlocks(blocks: MessageBlock[]): MessageBlock[] {
  const imageAnalysisCallIds = new Set(
    blocks
      .filter(isImageAnalysisMediaCard)
      .map((block) => extractBlockCallId(block))
      .filter((callId): callId is string => !!callId),
  )

  if (imageAnalysisCallIds.size === 0) {
    return blocks
  }

  return blocks.filter((block) => {
    if (!isAnalyzeImageStreamPanel(block)) {
      return true
    }
    const callId = extractBlockCallId(block)
    return !callId || !imageAnalysisCallIds.has(callId)
  })
}

export function getBlockIdentityKeys(block: MessageBlock): string[] {
  const keys = new Set<string>()
  const renderKey = block.renderKey ?? block.payload.renderKey ?? block.payload.render_key
  const artifactRef = block.payload.artifactRef
    ?? block.payload.artifact_ref
    ?? block.payload.result?.artifactRef
    ?? block.payload.result?.artifact_ref
  const taskId = block.taskId
    ?? block.payload.taskId
    ?? block.payload.task_id
    ?? block.payload.result?.taskId
    ?? block.payload.result?.task_id
  const callId = extractBlockCallId(block)

  if (artifactRef != null && String(artifactRef)) {
    keys.add(`artifact:${String(artifactRef)}`)
  }
  if (taskId != null && String(taskId)) {
    keys.add(`task:${String(taskId)}`)
  }
  if (callId != null && String(callId)) {
    keys.add(`call:${String(callId)}`)
  }
  if (renderKey != null && String(renderKey)) {
    keys.add(`render:${String(renderKey)}`)
  }
  if (block.id) {
    keys.add(`block:${block.id}`)
  }

  return Array.from(keys)
}

export function hasEquivalentBlock(messages: ChatMessage[], incomingBlock: MessageBlock): boolean {
  const identityKeys = getBlockIdentityKeys(incomingBlock)
  if (identityKeys.length === 0) {
    return false
  }

  const stack: MessageBlock[] = messages.flatMap((message) => message.blocks || [])
  while (stack.length > 0) {
    const block = stack.pop()!
    if (getBlockIdentityKeys(block).some((key) => identityKeys.includes(key))) {
      return true
    }
    if (block.children?.length) {
      stack.push(...block.children)
    }
  }

  return false
}

function blocksShareIdentity(left: MessageBlock, right: MessageBlock): boolean {
  const leftKeys = getBlockIdentityKeys(left)
  if (leftKeys.length === 0) {
    return false
  }
  const rightKeys = getBlockIdentityKeys(right)
  return rightKeys.some((key) => leftKeys.includes(key))
}

function replaceEquivalentBlockInBlocks(
  blocks: MessageBlock[],
  incomingBlock: MessageBlock,
): { blocks: MessageBlock[]; updated: boolean } {
  let didUpdate = false

  const nextBlocks = blocks.map((block) => {
    if (block.id === incomingBlock.id || blocksShareIdentity(block, incomingBlock)) {
      didUpdate = true
      return incomingBlock
    }

    if (block.children?.length) {
      const childUpdate = replaceEquivalentBlockInBlocks(block.children, incomingBlock)
      if (childUpdate.updated) {
        didUpdate = true
        return {
          ...block,
          children: childUpdate.blocks,
        }
      }
    }

    return block
  })

  return {
    blocks: didUpdate ? nextBlocks.sort((a, b) => a.order - b.order) : blocks,
    updated: didUpdate,
  }
}

export function replaceEquivalentBlockInMessages(
  messages: ChatMessage[],
  incomingBlock: MessageBlock,
): { messages: ChatMessage[]; updated: boolean } {
  let didUpdate = false

  const nextMessages = messages.map((message) => {
    if (!message.blocks?.length) {
      return message
    }

    const blockUpdate = replaceEquivalentBlockInBlocks(message.blocks, incomingBlock)
    if (!blockUpdate.updated) {
      return message
    }

    didUpdate = true
    return {
      ...message,
      blocks: blockUpdate.blocks,
      content: extractMessageText(blockUpdate.blocks),
    }
  })

  return {
    messages: didUpdate ? nextMessages : messages,
    updated: didUpdate,
  }
}

export function removeEquivalentBlockFromBlocks(
  blocks: MessageBlock[],
  incomingBlock: MessageBlock,
): MessageBlock[] {
  return blocks.flatMap((block) => {
    if (block.id === incomingBlock.id || blocksShareIdentity(block, incomingBlock)) {
      return []
    }
    if (block.children?.length) {
      return [{
        ...block,
        children: removeEquivalentBlockFromBlocks(block.children, incomingBlock),
      }]
    }
    return [block]
  })
}

export function updateMessagesBlocks(
  messages: ChatMessage[],
  updater: (blocks: MessageBlock[]) => MessageBlock[],
): ChatMessage[] {
  let didUpdate = false

  const nextMessages = messages.map((message) => {
    if (!message.blocks?.length) {
      return message
    }

    const nextBlocks = updater(message.blocks)
    if (nextBlocks === message.blocks) {
      return message
    }

    didUpdate = true
    return {
      ...message,
      blocks: nextBlocks,
      content: extractMessageText(nextBlocks),
    }
  })

  return didUpdate ? nextMessages : messages
}

function nextChildBlockOrder(children: MessageBlock[]): number {
  return children.length > 0
    ? Math.max(...children.map((child) => Number(child.order ?? 0))) + 1
    : 0
}

function critiqueCardIdentity(child: MessageBlock, critiqueRunId: string): boolean {
  if (child.uiKind !== 'design_jury_card') {
    return false
  }
  const childCritiqueRunId = child.payload?.critiqueRunId ?? child.payload?.critique_run_id
  return !critiqueRunId || String(childCritiqueRunId || '') === critiqueRunId
}

function buildSubagentDesignJuryBlock(
  subagentTaskId: string,
  critiquePayload: Record<string, unknown>,
  existing?: MessageBlock,
): MessageBlock {
  const normalizedPayload = (camelizeBlockPayload(critiquePayload) as Record<string, unknown>) || {}
  const critiqueRunId = String(normalizedPayload.critiqueRunId || normalizedPayload.critique_run_id || 'active')
  const displayStatus = String(normalizedPayload.displayStatus || normalizedPayload.display_status || '').trim()
  const status = displayStatus === 'round_completed'
    ? 'completed'
    : String(normalizedPayload.status || existing?.status || 'running')
  return {
    id: existing?.id || `subagent-${subagentTaskId}-design-jury-${critiqueRunId}`,
    kind: 'content',
    order: existing?.order ?? 0,
    status,
    visible: true,
    uiKind: 'design_jury_card',
    renderKey: `subagent:${subagentTaskId}:design-jury:${critiqueRunId}`,
    payload: normalizedPayload,
    children: [],
  }
}

function terminalSubagentStatusForCritique(critiquePayload: Record<string, unknown>): string | null {
  const status = String(critiquePayload.status || critiquePayload.displayStatus || critiquePayload.display_status || '').trim().toLowerCase()
  if (status === 'shipped' || status === 'below_threshold' || status === 'completed') {
    return 'completed'
  }
  if (status === 'degraded') {
    return 'degraded'
  }
  if (status === 'failed') {
    return 'failed'
  }
  return null
}

function upsertSubagentDesignJuryCardInBlocks(
  blocks: MessageBlock[],
  subagentTaskId: string,
  critiquePayload: Record<string, unknown>,
): { blocks: MessageBlock[]; updated: boolean } {
  let didUpdate = false
  const normalizedTaskId = String(subagentTaskId || '').trim()
  const critiqueRunId = String(
    critiquePayload.critiqueRunId
    ?? critiquePayload.critique_run_id
    ?? '',
  )

  const nextBlocks = blocks.map((block) => {
    if (isMatchingSubagentBlock(block, normalizedTaskId)) {
      didUpdate = true
      const children = block.children || []
      const existing = children.find((child) => critiqueCardIdentity(child, critiqueRunId))
      const designJuryBlock = buildSubagentDesignJuryBlock(normalizedTaskId, critiquePayload, existing)
      designJuryBlock.order = existing?.order ?? nextChildBlockOrder(children)
      const nextChildren = children
        .filter((child) => !critiqueCardIdentity(child, critiqueRunId))
        .concat(designJuryBlock)
        .sort((a, b) => a.order - b.order)
      const terminalStatus = terminalSubagentStatusForCritique(critiquePayload)
      const nextPayload = terminalStatus
        ? {
          ...(block.payload || {}),
          status: terminalStatus,
          result: {
            ...((block.payload?.result && typeof block.payload.result === 'object') ? block.payload.result : {}),
            status: terminalStatus,
          },
        }
        : block.payload
      return {
        ...block,
        status: terminalStatus || block.status,
        expanded: true,
        payload: nextPayload,
        children: nextChildren,
      }
    }

    if (block.children?.length) {
      const childUpdate = upsertSubagentDesignJuryCardInBlocks(block.children, normalizedTaskId, critiquePayload)
      if (childUpdate.updated) {
        didUpdate = true
        return {
          ...block,
          children: childUpdate.blocks,
        }
      }
    }

    return block
  })

  return { blocks: didUpdate ? nextBlocks : blocks, updated: didUpdate }
}

export function upsertSubagentDesignJuryCard(
  blocks: MessageBlock[],
  subagentTaskId: string,
  critiquePayload: Record<string, unknown>,
): MessageBlock[] {
  const normalizedTaskId = String(subagentTaskId || '').trim()
  if (!normalizedTaskId) {
    return blocks
  }
  const update = upsertSubagentDesignJuryCardInBlocks(blocks, normalizedTaskId, critiquePayload)
  return update.updated ? update.blocks : blocks
}

function isMatchingSubagentBlock(block: MessageBlock, taskId: string): boolean {
  if (block.uiKind !== 'subagent_card') {
    return false
  }
  if (block.taskId === taskId) {
    return true
  }
  const payloadTaskId = block.payload.taskId ?? block.payload.result?.taskId
    ?? block.payload.task_id ?? block.payload.result?.task_id
  return String(payloadTaskId || '') === taskId
}

function subagentAnchorMessageId(blocks: MessageBlock[] | undefined): string {
  if (!Array.isArray(blocks)) {
    return ''
  }
  for (const block of blocks) {
    if (block.uiKind !== 'subagent_card') {
      continue
    }
    const anchor = block.payload?.anchorMessageId ?? block.payload?.anchor_message_id
    const normalized = String(anchor || '').trim()
    if (normalized) {
      return normalized
    }
  }
  return ''
}

function subagentSortValue(message: ChatMessage, fallbackIndex: number): number {
  const block = (message.blocks || []).find((item) => item.uiKind === 'subagent_card')
  const payload = block?.payload || {}
  const createdAt = String(payload.eventCreatedAt || payload.event_created_at || message.createdAt || '').trim()
  const timestamp = createdAt ? Date.parse(createdAt) : NaN
  if (Number.isFinite(timestamp)) {
    return timestamp
  }
  const sequence = Number(payload.sequence ?? payload.eventSequence ?? payload.event_sequence)
  return Number.isFinite(sequence) ? sequence : fallbackIndex
}

function insertAnchoredSubagentMessage(messages: ChatMessage[], assistantMessage: ChatMessage, anchorMessageId: string): ChatMessage[] {
  const anchorIndex = messages.findIndex((message) => String(message.id || '') === anchorMessageId)
  if (anchorIndex < 0) {
    return [...messages, assistantMessage]
  }

  const next = [...messages]
  let endIndex = anchorIndex + 1
  while (endIndex < next.length && subagentAnchorMessageId(next[endIndex]?.blocks) === anchorMessageId) {
    endIndex += 1
  }
  const anchoredGroup = [...next.slice(anchorIndex + 1, endIndex), assistantMessage]
    .map((message, index) => ({ message, sort: subagentSortValue(message, index) }))
    .sort((a, b) => a.sort - b.sort)
    .map((item) => item.message)
  return [
    ...next.slice(0, anchorIndex + 1),
    ...anchoredGroup,
    ...next.slice(endIndex),
  ]
}

export function reorderAnchoredSubagentMessages(messages: ChatMessage[]): ChatMessage[] {
  const anchored: ChatMessage[] = []
  const remaining: ChatMessage[] = []
  for (const message of messages) {
    const anchorMessageId = subagentAnchorMessageId(message.blocks)
    if (message.role === 'assistant' && anchorMessageId) {
      anchored.push(message)
    } else {
      remaining.push(message)
    }
  }
  return anchored.reduce((nextMessages, message) => {
    const anchorMessageId = subagentAnchorMessageId(message.blocks)
    if (!anchorMessageId || !nextMessages.some((item) => String(item.id || '') === anchorMessageId)) {
      return [...nextMessages, message]
    }
    return insertAnchoredSubagentMessage(nextMessages, message, anchorMessageId)
  }, remaining)
}
