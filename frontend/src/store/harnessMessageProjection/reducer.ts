import type { OutlineRuntimeRead, PlanningDraftRead, UserPlanRead } from '@/api/endpoints/agent'
import { EMPTY_MESSAGE_BLOCKS } from '../canvasAgentTypes'
import type { PresentationOpEvent, ProjectionChatMessage, ProjectionMessageBlock, ProjectionSessionLike } from './types'
import {
  getPresentationSourceSequence,
  hasAppliedPresentationOp,
  markPresentationOpApplied,
} from './cursor'

export function applyPresentationOpToSession<T extends ProjectionSessionLike>(
  session: T,
  event: PresentationOpEvent,
): T {
  if (hasAppliedPresentationOp(session, event)) {
    return session
  }
  const op = normalizeOp(event)
  if (op.type === 'presentation.conversation.patch') {
    return markPresentationOpApplied(session, event)
  }
  let nextMessages = session.messages
  if (op.type === 'presentation.message.upsert') {
    nextMessages = upsertMessage(nextMessages, op)
  } else if (op.type === 'presentation.block.remove') {
    nextMessages = updateMessageBlocks(nextMessages, op.messageKey, (blocks) => removeBlock(blocks, op.blockKey), op)
  } else if (op.type === 'presentation.block.delta') {
    nextMessages = updateMessageBlocks(nextMessages, op.messageKey, (blocks) => applyBlockOperation(blocks, op, applyBlockDelta), op)
  } else if (op.type === 'presentation.block.patch') {
    nextMessages = updateMessageBlocks(nextMessages, op.messageKey, (blocks) => applyBlockOperation(blocks, op, applyBlockPatch), op)
  } else if (op.type === 'presentation.block.upsert' || op.type === 'presentation.block.complete') {
    nextMessages = updateMessageBlocks(nextMessages, op.messageKey, (blocks) => applyBlockOperation(blocks, op, (items, currentOp) => upsertBlock(items, currentOp.block)), op)
  }

  const nextSession = applyPresentationStateProjection({
    ...session,
    messages: nextMessages.map((message) => {
      const blockText = extractText(message.blocks || [])
      return {
        ...message,
        content: blockText ?? message.content,
      }
    }),
    streamingBlocks: EMPTY_MESSAGE_BLOCKS,
  }, op)
  return markPresentationOpApplied(nextSession, event)
}

function applyPresentationStateProjection<T extends ProjectionSessionLike>(
  session: T,
  op: ReturnType<typeof normalizeOp>,
): T {
  if (op.type !== 'presentation.block.upsert' && op.type !== 'presentation.block.complete' && op.type !== 'presentation.block.patch') {
    return session
  }
  if (op.block.uiKind === 'planning_draft_card') {
    const planningDraft = planningDraftFromPayload(op.block.payload)
    return planningDraft ? { ...session, planningDraft } : session
  }
  if (op.block.uiKind !== 'user_plan_card') {
    return session
  }
  const plan = userPlanFromPayload(op.block.payload)
  if (!plan || !shouldProjectCurrentPlan(session, plan)) {
    return session
  }
  const outlineRuntime: OutlineRuntimeRead = {
    ...(session.outlineRuntime || {}),
    current_outline: plan,
    execution_state: plan.execution_state ?? session.outlineRuntime?.execution_state ?? null,
    projection_state: plan.projection_state ?? session.outlineRuntime?.projection_state ?? null,
    execution_run: session.outlineRuntime?.execution_run ?? null,
    last_revision: session.outlineRuntime?.last_revision ?? null,
  }
  return {
    ...session,
    activeUserPlan: plan,
    outlineRuntime,
    runtimeState: {
      ...(session.runtimeState || {}),
      phase: plan.status === 'executing' ? 'executing' : (session.runtimeState?.phase || 'planning_ready'),
    },
  }
}

function normalizeOp(event: PresentationOpEvent) {
  const data = (event.data && typeof event.data === 'object' ? event.data : event.payload || {}) as Record<string, any>
  const sourceSequence = getPresentationSourceSequence(event) ?? 0
  const messageKey = String(data.message_key || data.messageKey || `message:${event.run_id || 'default'}`)
  const blockKey = String(data.block_key || data.blockKey || data.block?.block_key || data.block?.id || `block:${sourceSequence}`)
  const status = String(data.status || data.block?.status || 'running')
  return {
    type: event.type,
    messageKey,
    blockKey,
    parentBlockKey: data.parent_block_key || data.parentBlockKey || null,
    role: normalizeRole(data.role),
    status,
    content: typeof data.content === 'string' ? data.content : null,
    order: Number(data.order ?? data.block?.order ?? 0) || 0,
    payload: data.payload && typeof data.payload === 'object' ? data.payload as Record<string, any> : {},
    block: normalizeBlock(data.block && typeof data.block === 'object' ? data.block : data, blockKey, sourceSequence, status),
    sourceSequence,
    revision: Number(data.revision ?? data.block?.revision ?? sourceSequence) || sourceSequence,
    requiresExistingMessage: Boolean(data.requires_existing_message ?? data.requiresExistingMessage),
  }
}

function normalizeRole(role: unknown): ProjectionChatMessage['role'] {
  return role === 'user' || role === 'tool' ? role : 'assistant'
}

function normalizeBlock(source: Record<string, any>, blockKey: string, sourceSequence: number, status: string): ProjectionMessageBlock {
  const payload = source.payload && typeof source.payload === 'object' ? source.payload as Record<string, any> : {}
  const uiKind = String(source.uiKind || source.ui_kind || payload.uiKind || payload.ui_kind || 'text')
  const kind = normalizeBlockKind(source.kind, uiKind)
  const children = Array.isArray(source.children)
    ? source.children
      .filter((child): child is Record<string, any> => !!child && typeof child === 'object')
      .map((child) => normalizeBlock(child, String(child.block_key || child.blockKey || child.id || ''), sourceSequence, String(child.status || status)))
    : []
  return {
    id: String(source.id || blockKey),
    kind,
    order: Number(source.order ?? 0) || 0,
    status,
    visible: source.visible !== false,
    uiKind,
    payload,
    renderKey: source.renderKey || source.render_key,
    taskId: source.taskId || source.task_id || payload.taskId || payload.task_id,
    label: source.label || payload.label,
    summary: source.summary || payload.summary,
    expanded: typeof source.expanded === 'boolean' ? source.expanded : undefined,
    children,
    revision: normalizePositiveNumber(source.revision ?? payload.revision) ?? sourceSequence,
    sourceSequence: normalizePositiveNumber(
      source.sourceSequence
      ?? source.source_sequence
      ?? payload.sourceSequence
      ?? payload.source_sequence,
    ) ?? sourceSequence,
  }
}

function normalizeBlockKind(kind: unknown, uiKind: string): ProjectionMessageBlock['kind'] {
  if (kind === 'text' || kind === 'tool' || kind === 'interaction' || kind === 'content') {
    return kind
  }
  if (uiKind === 'text') {
    return 'text'
  }
  if (uiKind === 'tool_call' || uiKind === 'tool_result') {
    return 'tool'
  }
  if (uiKind === 'interaction_form') {
    return 'interaction'
  }
  return 'content'
}

// A snapshot reload (`buildHarnessUiMessages`) keys render-only cards as
// `render:${renderKey}`, while the live op keys them by the raw `message_key`
// (which equals that renderKey). Treat the two as the same message so a resumed
// stream updates the reloaded card in place instead of forking a duplicate.
function matchesProjectionMessageId(messageId: string, messageKey: string): boolean {
  return messageId === messageKey || messageId === `render:${messageKey}`
}

function upsertMessage(messages: ProjectionChatMessage[], op: ReturnType<typeof normalizeOp>): ProjectionChatMessage[] {
  const existingIndex = messages.findIndex((message) => matchesProjectionMessageId(String(message.id), op.messageKey))
  const blocks = Array.isArray(op.payload.blocks)
    ? op.payload.blocks
      .filter((block): block is Record<string, any> => !!block && typeof block === 'object')
      .map((block) => normalizeBlock(block, String(block.block_key || block.blockKey || block.id || ''), op.sourceSequence, String(block.status || op.status)))
    : undefined
  const attachments = normalizeAttachments(op.payload.attachments)
  const baseFileVersions = normalizeBaseFileVersions(op.payload.base_file_versions ?? op.payload.baseFileVersions)
  const nextMessage: ProjectionChatMessage = {
    id: op.messageKey,
    role: op.role,
    content: op.content,
    attachments,
    blocks: blocks ?? [],
    metadata: op.payload.metadata && typeof op.payload.metadata === 'object'
      ? { ...op.payload.metadata }
      : undefined,
    createdAt: new Date().toISOString(),
  }
  if (existingIndex < 0) {
    const optimisticIndex = findOptimisticUserMessageIndex(messages, op, attachments, baseFileVersions)
    if (optimisticIndex >= 0) {
      return messages.map((message, index) => index === optimisticIndex
        ? {
          ...message,
          id: op.messageKey,
          role: nextMessage.role,
          content: nextMessage.content ?? message.content,
          attachments: attachments ?? message.attachments,
          blocks: blocks ?? message.blocks ?? [],
          metadata: nextMessage.metadata ?? message.metadata,
          createdAt: message.createdAt || nextMessage.createdAt,
        }
        : message)
    }
    return [...messages, nextMessage]
  }
  return messages.map((message, index) => index === existingIndex
    ? {
      ...message,
      role: nextMessage.role,
      content: nextMessage.content ?? message.content,
      attachments: attachments ?? message.attachments,
      blocks: blocks ?? message.blocks,
      metadata: nextMessage.metadata ?? message.metadata,
    }
    : message)
}

function findOptimisticUserMessageIndex(
  messages: ProjectionChatMessage[],
  op: ReturnType<typeof normalizeOp>,
  attachments: ProjectionChatMessage['attachments'],
  baseFileVersions: unknown[],
): number {
  if (op.role !== 'user') {
    return -1
  }
  const content = String(op.content ?? op.payload.content ?? '').trim()
  const submissionRequestId = optimisticSubmissionRequestId(op.payload.metadata)
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role !== 'user' || !String(message.id).startsWith('temp-')) {
      continue
    }
    if (submissionRequestId) {
      const messageRequestId = optimisticSubmissionRequestId((message as Record<string, any>).metadata)
        || optimisticSubmissionRequestId((message as Record<string, any>).payload?.metadata)
      if (messageRequestId !== submissionRequestId) {
        continue
      }
    } else if (String(message.content ?? '').trim() !== content) {
      continue
    }
    if (!areEquivalentMessageAttachments(message.attachments ?? [], attachments ?? [])) {
      continue
    }
    const messageBaseFileVersions = Array.isArray((message as Record<string, any>).baseFileVersions)
      ? (message as Record<string, any>).baseFileVersions
      : []
    if (!areEquivalentJsonValues(messageBaseFileVersions, baseFileVersions)) {
      continue
    }
    return index
  }
  return -1
}

function optimisticSubmissionRequestId(metadata: unknown): string {
  if (!metadata || typeof metadata !== 'object') {
    return ''
  }
  const source = String((metadata as Record<string, unknown>).source || '').trim()
  if (source !== 'interaction_submitted' && source !== 'optimistic_interaction_submitted') {
    return ''
  }
  return String(
    (metadata as Record<string, unknown>).request_id
    || (metadata as Record<string, unknown>).requestId
    || '',
  ).trim()
}

function normalizeAttachments(value: unknown): ProjectionChatMessage['attachments'] {
  if (!Array.isArray(value)) {
    return undefined
  }
  const attachments = value.filter((item): item is Record<string, any> => !!item && typeof item === 'object')
  return attachments.length ? attachments.map((item) => ({ ...item })) : undefined
}

function normalizeBaseFileVersions(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function areEquivalentJsonValues(left: unknown, right: unknown): boolean {
  return JSON.stringify(normalizeJsonComparable(left)) === JSON.stringify(normalizeJsonComparable(right))
}

function areEquivalentMessageAttachments(left: unknown, right: unknown): boolean {
  return JSON.stringify(normalizeMessageAttachmentComparable(left)) === JSON.stringify(normalizeMessageAttachmentComparable(right))
}

function normalizeMessageAttachmentComparable(value: unknown): unknown {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => {
      const reference = item.reference && typeof item.reference === 'object'
        ? item.reference as Record<string, unknown>
        : null
      const source = reference?.source && typeof reference.source === 'object'
        ? reference.source as Record<string, unknown>
        : null
      return normalizeJsonComparable({
        type: item.type,
        url: item.url,
        name: item.name,
        reference: reference
          ? {
            id: reference.id,
            kind: reference.kind,
            media_type: reference.media_type,
            display_name: reference.display_name,
            source,
          }
          : null,
      })
    })
}

function normalizeJsonComparable(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(normalizeJsonComparable)
  }
  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = normalizeJsonComparable((value as Record<string, unknown>)[key])
        return acc
      }, {})
  }
  return value
}

function updateMessageBlocks(
  messages: ProjectionChatMessage[],
  messageKey: string,
  updater: (blocks: ProjectionMessageBlock[]) => ProjectionMessageBlock[],
  op?: ReturnType<typeof normalizeOp>,
): ProjectionChatMessage[] {
  const index = findProjectionMessageIndex(messages, messageKey, op)
  const resolvedMessageKey = index >= 0 ? String(messages[index].id) : messageKey
  if (index < 0) {
    // A submission patch only marks an existing form submitted; it must never
    // materialize a stray message when the target was never projected.
    if (op?.requiresExistingMessage) {
      return messages
    }
    return [
      ...messages,
      {
        id: resolvedMessageKey,
        role: 'assistant',
        content: null,
        blocks: updater([]),
        createdAt: new Date().toISOString(),
      },
    ]
  }
  return messages.map((message, messageIndex) => messageIndex === index
    ? {
      ...message,
      blocks: updater(shouldReplaceCurrentPlanBlocks(op) ? [] : message.blocks || []),
    }
    : message)
}

function shouldReplaceCurrentPlanBlocks(op?: ReturnType<typeof normalizeOp>): boolean {
  return Boolean(op?.payload?.replace_current && op.block.uiKind === 'user_plan_card')
}

function findProjectionMessageIndex(
  messages: ProjectionChatMessage[],
  messageKey: string,
  op?: ReturnType<typeof normalizeOp>,
): number {
  const exactIndex = messages.findIndex((message) => matchesProjectionMessageId(String(message.id), messageKey))
  if (exactIndex >= 0 || !op?.payload?.replace_current) {
    return exactIndex
  }
  const planInstanceId = String(op.payload.plan_instance_id || op.payload.planInstanceId || '').trim()
  if (!planInstanceId) {
    return -1
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    const block = (message.blocks || []).find((candidate) => {
      const payload = candidate.payload || {}
      return candidate.uiKind === 'user_plan_card'
        && String(payload.plan_instance_id || payload.planInstanceId || '').trim() === planInstanceId
    })
    const payload = block?.payload || {}
    const snapshotStatus = String(payload.snapshot_status || payload.snapshotStatus || payload.status || '').toLowerCase()
    if (block && ['', 'active', 'executing', 'finalizing'].includes(snapshotStatus)) {
      return index
    }
  }
  return -1
}

function upsertBlock(blocks: ProjectionMessageBlock[], block: ProjectionMessageBlock): ProjectionMessageBlock[] {
  const index = blocks.findIndex((candidate) => candidate.id === block.id)
  if (index < 0) {
    return [...blocks, block].sort(compareBlocks)
  }
  return blocks.map((candidate, candidateIndex) => candidateIndex === index
    ? shouldAcceptBlockRevision(candidate, block)
      ? mergeIncomingBlock(candidate, block)
      : candidate
    : candidate).sort(compareBlocks)
}

function mergeIncomingBlock(existing: ProjectionMessageBlock, incoming: ProjectionMessageBlock): ProjectionMessageBlock {
  const merged = { ...existing, ...incoming, children: incoming.children?.length ? incoming.children : existing.children }
  if (!isSameInteractionForm(existing, incoming)) {
    return merged
  }
  const existingStatus = String(existing.payload?.status || '').trim()
  const incomingStatus = String(incoming.payload?.status || '').trim()
  if (existingStatus !== 'submitted' || incomingStatus === 'submitted') {
    return merged
  }
  return {
    ...merged,
    payload: {
      ...merged.payload,
      status: 'submitted',
      answers: existing.payload.answers ?? merged.payload.answers ?? null,
      submitted_label: existing.payload.submitted_label ?? merged.payload.submitted_label,
      submittedLabel: existing.payload.submittedLabel ?? merged.payload.submittedLabel,
      submitted_answer: existing.payload.submitted_answer ?? merged.payload.submitted_answer,
      submittedAnswer: existing.payload.submittedAnswer ?? merged.payload.submittedAnswer,
    },
  }
}

function isSameInteractionForm(left: ProjectionMessageBlock, right: ProjectionMessageBlock): boolean {
  if (left.uiKind !== 'interaction_form' || right.uiKind !== 'interaction_form') {
    return false
  }
  const leftRequestId = String(left.payload?.request_id || left.payload?.requestId || '').trim()
  const rightRequestId = String(right.payload?.request_id || right.payload?.requestId || '').trim()
  return Boolean(leftRequestId && leftRequestId === rightRequestId)
}

function applyBlockOperation(
  blocks: ProjectionMessageBlock[],
  op: ReturnType<typeof normalizeOp>,
  apply: (blocks: ProjectionMessageBlock[], op: ReturnType<typeof normalizeOp>) => ProjectionMessageBlock[],
): ProjectionMessageBlock[] {
  if (!op.parentBlockKey) {
    return apply(blocks, op)
  }
  const scopedBlocks = removeBlockOutsideParent(blocks, op.blockKey, op.parentBlockKey)
  let didUpdate = false
  const nextBlocks = scopedBlocks.map((block) => {
    if (block.id !== op.parentBlockKey) {
      return block
    }
    didUpdate = true
    return {
      ...block,
      children: apply(block.children || [], { ...op, parentBlockKey: null }),
    }
  })
  if (didUpdate) {
    return nextBlocks
  }
  return upsertBlock(scopedBlocks, {
    id: op.parentBlockKey,
    kind: 'content',
    order: op.order,
    status: 'running',
    visible: true,
    uiKind: op.parentBlockKey.startsWith('subagent:') ? 'subagent_card' : 'content',
    payload: { status: 'running' },
    children: apply([], { ...op, parentBlockKey: null }),
  })
}

function removeBlockOutsideParent(
  blocks: ProjectionMessageBlock[],
  blockKey: string,
  parentBlockKey: string,
): ProjectionMessageBlock[] {
  if (!blockKey) {
    return blocks
  }
  return blocks
    .filter((block) => block.id === parentBlockKey || block.id !== blockKey)
    .map((block) => {
      if (block.id === parentBlockKey || !block.children?.length) {
        return block
      }
      return {
        ...block,
        children: removeBlock(block.children, blockKey),
      }
    })
}

function applyBlockDelta(blocks: ProjectionMessageBlock[], op: ReturnType<typeof normalizeOp>): ProjectionMessageBlock[] {
  const index = blocks.findIndex((block) => block.id === op.blockKey)
  const existing = index >= 0 ? blocks[index] : op.block
  if (isStaleBlockOp(existing, op)) {
    return blocks
  }
  const field = String(op.payload.field || 'content')
  const delta = String(op.payload.delta || '')
  const nextPayload = { ...existing.payload }
  if (field === 'content' || field === 'text') {
    nextPayload.text = `${nextPayload.text || (existing as any).content || ''}${delta}`
  } else {
    nextPayload[field] = `${nextPayload[field] || ''}${delta}`
  }
  const nextBlock = {
    ...existing,
    status: 'running',
    payload: nextPayload,
    revision: Math.max(Number(existing.revision || 0), op.revision),
    sourceSequence: Math.max(Number(existing.sourceSequence || 0), op.sourceSequence),
  }
  return upsertBlock(blocks, nextBlock)
}

function applyBlockPatch(blocks: ProjectionMessageBlock[], op: ReturnType<typeof normalizeOp>): ProjectionMessageBlock[] {
  const existing = blocks.find((block) => block.id === op.blockKey) || op.block
  if (isStaleBlockOp(existing, op)) {
    return blocks
  }
  const nextBlock = {
    ...existing,
    ...op.payload,
    payload: {
      ...existing.payload,
      ...(op.payload.payload && typeof op.payload.payload === 'object' ? op.payload.payload : op.payload),
    },
  }
  return upsertBlock(blocks, normalizeBlock(nextBlock, op.blockKey, op.sourceSequence, String(nextBlock.status || op.status)))
}

function removeBlock(blocks: ProjectionMessageBlock[], blockKey: string): ProjectionMessageBlock[] {
  return blocks
    .filter((block) => block.id !== blockKey)
    .map((block) => ({
      ...block,
      children: block.children ? removeBlock(block.children, blockKey) : undefined,
    }))
}

function compareBlocks(left: ProjectionMessageBlock, right: ProjectionMessageBlock): number {
  return left.order - right.order
}

function planningDraftFromPayload(payload: Record<string, any>): PlanningDraftRead | null {
  const draftOutline = normalizeOutlineItems(payload.draft_outline ?? payload.draftOutline)
  const summary = String(payload.summary ?? '').trim()
  if (!summary && draftOutline.length === 0) {
    return null
  }
  return {
    summary: summary || null,
    confirmed_inputs: normalizePlainObject(payload.confirmed_inputs ?? payload.confirmedInputs) || {},
    assumptions: normalizeStringArray(payload.assumptions),
    draft_outline: draftOutline,
    open_questions: normalizeStringArray(payload.open_questions ?? payload.openQuestions),
    updated_at: payload.updated_at ?? payload.updatedAt ?? null,
  }
}

function userPlanFromPayload(payload: Record<string, any>): UserPlanRead | null {
  const outlineState = normalizePlainObject(payload.outline_state ?? payload.outlineState)
  const projectionState = normalizePlainObject(payload.projection_state ?? payload.projectionState)
  const executionState = normalizePlainObject(payload.execution_state ?? payload.executionState)
  const planInstanceId = String(
    payload.plan_instance_id
    ?? payload.planInstanceId
    ?? outlineState?.plan_instance_id
    ?? projectionState?.plan_instance_id
    ?? '',
  ).trim()
  const outlineVersion = normalizePositiveNumber(
    payload.outline_version
    ?? payload.outlineVersion
    ?? outlineState?.version
    ?? projectionState?.outline_version,
  ) ?? null
  const items = normalizeOutlineItems(payload.items ?? outlineState?.items ?? projectionState?.items ?? payload.outline)
  const outline = normalizeOutlineItems(payload.outline ?? outlineState?.outline ?? outlineState?.items ?? items)
  const title = String(payload.title ?? outlineState?.title ?? projectionState?.title ?? '').trim()
  if (!planInstanceId && !title && items.length === 0 && outline.length === 0) {
    return null
  }
  const status = String(payload.status ?? outlineState?.status ?? projectionState?.status ?? 'planning_ready').trim() || 'planning_ready'
  const snapshotStatus = String(
    payload.snapshot_status
    ?? payload.snapshotStatus
    ?? outlineState?.snapshot_status
    ?? projectionState?.snapshot_status
    ?? 'active',
  ).trim() || 'active'
  return {
    artifact_type: String(
      payload.artifact_type
      ?? payload.artifactType
      ?? outlineState?.artifact_type
      ?? projectionState?.artifact_type
      ?? 'other',
    ),
    title,
    summary: String(payload.summary ?? outlineState?.summary ?? projectionState?.summary ?? '').trim(),
    status,
    plan_instance_id: planInstanceId || null,
    snapshot_status: snapshotStatus,
    progress_message: payload.progress_message ?? payload.progressMessage ?? outlineState?.progress_message ?? null,
    items,
    outline: outline.length ? outline : items,
    constraints: normalizeStringArray(payload.constraints ?? outlineState?.constraints),
    style_notes: normalizeStringArray(payload.style_notes ?? payload.styleNotes ?? outlineState?.style_notes),
    file_path: payload.file_path ?? payload.filePath ?? outlineState?.file_path ?? null,
    file_name: payload.file_name ?? payload.fileName ?? outlineState?.file_name ?? null,
    outline_id: payload.outline_id ?? payload.outlineId ?? outlineState?.outline_id ?? projectionState?.outline_id ?? null,
    version: outlineVersion,
    readonly: Boolean(payload.readonly || outlineState?.readonly || projectionState?.readonly),
    outline_state: outlineState,
    projection_state: projectionState as UserPlanRead['projection_state'],
    execution_state: executionState as UserPlanRead['execution_state'],
  }
}

function shouldProjectCurrentPlan(session: ProjectionSessionLike, incoming: UserPlanRead): boolean {
  const snapshotStatus = String(incoming.snapshot_status || incoming.status || '').toLowerCase()
  if (!['', 'active', 'executing', 'finalizing'].includes(snapshotStatus)) {
    return false
  }
  const existing = session.outlineRuntime?.current_outline ?? session.activeUserPlan ?? null
  if (!existing) {
    return true
  }
  const incomingPlanInstanceId = String(incoming.plan_instance_id || '').trim()
  const existingPlanInstanceId = String(existing.plan_instance_id || '').trim()
  if (incomingPlanInstanceId && existingPlanInstanceId && incomingPlanInstanceId === existingPlanInstanceId) {
    const incomingVersion = Number(incoming.version ?? 0) || 0
    const existingVersion = Number(existing.version ?? 0) || 0
    return incomingVersion >= existingVersion
  }
  return true
}

function normalizePlainObject(value: unknown): Record<string, any> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? { ...(value as Record<string, any>) }
    : null
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : []
}

function normalizeOutlineItems(value: unknown): any[] {
  return Array.isArray(value)
    ? value
      .filter((item): item is Record<string, any> => !!item && typeof item === 'object')
      .map((item) => ({ ...item }))
    : []
}

function extractText(blocks: ProjectionMessageBlock[]): string | null {
  const parts: string[] = []
  const visit = (items: ProjectionMessageBlock[]) => {
    items.forEach((block) => {
      if (isMessageContentTextBlock(block)) {
        const text = block.payload.text
        if (typeof text === 'string') {
          parts.push(text)
        }
      }
      if (block.uiKind === 'content' && !hasToolIdentity(block) && block.children?.length) {
        visit(block.children)
      }
    })
  }
  visit(blocks)
  return parts.join('') || null
}

function isMessageContentTextBlock(block: ProjectionMessageBlock): boolean {
  return ['text', 'assistant_text', 'assistant_final_answer'].includes(String(block.uiKind || ''))
    && !hasToolIdentity(block)
}

function hasToolIdentity(block: ProjectionMessageBlock): boolean {
  return [
    block.payload?.tool,
    block.payload?.tool_name,
    block.payload?.toolName,
    block.payload?.call_id,
    block.payload?.callId,
    (block as Record<string, any>).tool,
    (block as Record<string, any>).tool_name,
    (block as Record<string, any>).toolName,
  ].some((value) => String(value || '').trim())
}

function normalizePositiveNumber(value: unknown): number | undefined {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

function shouldAcceptBlockRevision(existing: ProjectionMessageBlock, incoming: ProjectionMessageBlock): boolean {
  const existingRevision = normalizePositiveNumber(existing.revision) ?? normalizePositiveNumber(existing.sourceSequence) ?? 0
  const incomingRevision = normalizePositiveNumber(incoming.revision) ?? normalizePositiveNumber(incoming.sourceSequence) ?? 0
  if (incomingRevision <= 0 || existingRevision <= 0) {
    return true
  }
  return incomingRevision >= existingRevision
}

function isStaleBlockOp(existing: ProjectionMessageBlock, op: ReturnType<typeof normalizeOp>): boolean {
  const existingRevision = normalizePositiveNumber(existing.revision) ?? normalizePositiveNumber(existing.sourceSequence) ?? 0
  if (existingRevision <= 0 || op.revision <= 0) {
    return false
  }
  return op.revision < existingRevision
}
