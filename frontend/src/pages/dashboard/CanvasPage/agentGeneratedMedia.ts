import type { CanvasItem } from '@/api/endpoints/projects'

export interface AgentGeneratedMediaSessionItem {
  id: string
  name: string
  order: number
}

export interface AgentGeneratedMediaSession {
  conversationId: string | number | null
  messageId: string | null
  items: AgentGeneratedMediaSessionItem[]
  groupId: string | null
}

export interface AgentGeneratedMediaState {
  sessions: Record<string, AgentGeneratedMediaSession>
}

interface IncomingAgentGeneratedMedia {
  id?: string | null
  task_id?: string | number | null
  artifact_ref?: string | null
  agentMediaKey?: string | null
}

interface PlanAgentGeneratedMediaInsertionArgs {
  currentState: AgentGeneratedMediaState
  conversationId: string | number | null
  messageId: string | null
  groupKey?: string | null
  incomingId: string
  incomingName: string
  fallbackGroupId: string
}

interface AgentGeneratedMediaInsertionPlan {
  shouldInsert: boolean
  nextState: AgentGeneratedMediaState
  nextSession: AgentGeneratedMediaSession
  currentCount: number
  createdGroupId: string | null
  nextOrder: number
}

export interface AgentGroupLayoutOptions {
  columns: number
  gap: number
  padding: number
}

interface AgentGroupLayoutResult {
  group: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>
  members: CanvasItem[]
}

const LEGACY_CONVERSATION_PREFIX = 'legacy'
export const DEFAULT_AGENT_GROUP_LAYOUT: AgentGroupLayoutOptions = {
  columns: 10,
  gap: 20,
  padding: 80,
}

function normalizeMessageId(messageId: string | number | null | undefined): string | null {
  if (typeof messageId === 'number') {
    return String(messageId)
  }

  if (typeof messageId === 'string') {
    const trimmed = messageId.trim()
    return trimmed || null
  }

  return null
}

function normalizeConversationId(conversationId: string | number | null | undefined): string | null {
  if (typeof conversationId === 'number') {
    return String(conversationId)
  }

  if (typeof conversationId === 'string') {
    const trimmed = conversationId.trim()
    return trimmed || null
  }

  return null
}

function buildAgentGeneratedMediaSessionKey(conversationId: string | number | null, messageId: string | null) {
  const normalizedMessageId = normalizeMessageId(messageId)
  const conversationSegment = normalizeConversationId(conversationId) ?? LEGACY_CONVERSATION_PREFIX
  return `conversation:${conversationSegment}:message:${normalizedMessageId ?? 'null'}`
}

function buildAgentGeneratedMediaExplicitGroupKey(conversationId: string | number | null, groupKey: string) {
  const conversationSegment = normalizeConversationId(conversationId) ?? LEGACY_CONVERSATION_PREFIX
  return `conversation:${conversationSegment}:agent-group:${groupKey}`
}

function buildAgentGeneratedMediaGroupKey(groupId: string) {
  return `group:${groupId}`
}

function findFallbackConversationSession(
  sessions: Record<string, AgentGeneratedMediaSession>,
  conversationId: string | number | null,
) {
  const normalizedConversationId = normalizeConversationId(conversationId)
  if (normalizedConversationId == null) {
    return null
  }

  const conversationEntries = Object.entries(sessions).filter(([, session]) => (
    normalizeConversationId(session.conversationId) === normalizedConversationId
  ))
  if (conversationEntries.length === 0) {
    return null
  }

  const groupedEntry = [...conversationEntries].reverse().find(([, session]) => session.groupId)
  return groupedEntry ?? conversationEntries[conversationEntries.length - 1]
}

function getExistingOrder(item: CanvasItem): number | null {
  return typeof item.agent_group_order === 'number' && Number.isFinite(item.agent_group_order)
    ? item.agent_group_order
    : null
}

function compareAgentGroupItems(a: CanvasItem, b: CanvasItem) {
  const orderA = getExistingOrder(a)
  const orderB = getExistingOrder(b)
  if (orderA != null && orderB != null && orderA !== orderB) {
    return orderA - orderB
  }

  if (a.y !== b.y) {
    return a.y - b.y
  }

  if (a.x !== b.x) {
    return a.x - b.x
  }

  return a.id.localeCompare(b.id)
}

function isLegacyAgentGroup(groupId: string, items: CanvasItem[], groups: Map<string, CanvasItem>) {
  const group = groups.get(groupId)
  if (!group || group.group_layout_mode === 'manual') {
    return false
  }

  const members = items.filter((item) => item.groupId === groupId)
  if (members.length < 2) {
    return false
  }

  const messageIds = new Set(
    members
      .map((item) => normalizeMessageId(item.agent_message_id))
      .filter((value): value is string => Boolean(value)),
  )

  return members.every((item) => item.asset_origin === 'ai_generated') && messageIds.size === 1
}

function shouldIncludeInAgentSession(
  item: CanvasItem,
  groups: Map<string, CanvasItem>,
  legacyAgentGroups: Set<string>,
) {
  if (item.asset_origin !== 'ai_generated') {
    return false
  }

  if (!normalizeMessageId(item.agent_message_id)) {
    return false
  }

  if (!item.groupId) {
    return true
  }

  const group = groups.get(item.groupId)
  if (!group) {
    return true
  }

  if (group.group_layout_mode === 'agent_grid') {
    return true
  }

  return legacyAgentGroups.has(item.groupId)
}

function buildGroupedAgentSessionIndex(
  items: CanvasItem[],
  groups: Map<string, CanvasItem>,
  legacyAgentGroups: Set<string>,
) {
  const groupedSessionKeys = new Set<string>()
  const groupedConversationIds = new Set<string>()

  items.forEach((item) => {
    if (!item.groupId) {
      return
    }

    if (!shouldIncludeInAgentSession(item, groups, legacyAgentGroups)) {
      return
    }

    const messageId = normalizeMessageId(item.agent_message_id)
    if (!messageId) {
      return
    }

    const conversationId = normalizeConversationId(item.agent_conversation_id as string | number | null | undefined)

    groupedSessionKeys.add(buildAgentGeneratedMediaSessionKey(conversationId, messageId))
    if (conversationId != null) {
      groupedConversationIds.add(conversationId)
    }
  })

  return {
    groupedSessionKeys,
    groupedConversationIds,
  }
}

function getGroupLayoutFrame(group: CanvasItem | undefined, members: CanvasItem[], options: AgentGroupLayoutOptions) {
  if (group) {
    return {
      x: group.x,
      y: group.y,
      width: group.width || 0,
      height: group.height || 0,
    }
  }

  const [firstMember] = [...members].sort(compareAgentGroupItems)
  return {
    x: firstMember ? firstMember.x - options.padding : 0,
    y: firstMember ? firstMember.y - options.padding : 0,
    width: 0,
    height: 0,
  }
}

export function createInitialAgentGeneratedMediaState(): AgentGeneratedMediaState {
  return {
    sessions: {},
  }
}

export function createInitialAgentGeneratedMediaSession() {
  return createInitialAgentGeneratedMediaState()
}

export function normalizeDeletedAgentMediaKeys(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  const seen = new Set<string>()
  return value.reduce<string[]>((result, entry) => {
    const normalized = typeof entry === 'string'
      ? entry.trim()
      : typeof entry === 'number'
        ? String(entry)
        : ''

    if (!normalized || seen.has(normalized)) {
      return result
    }

    seen.add(normalized)
    result.push(normalized)
    return result
  }, [])
}

export function recordDeletedAgentMediaKey(currentKeys: string[], key: string | null | undefined): string[] {
  const normalizedKey = typeof key === 'string' ? key.trim() : ''
  if (!normalizedKey) {
    return currentKeys
  }

  const normalizedKeys = normalizeDeletedAgentMediaKeys(currentKeys)
  if (normalizedKeys.includes(normalizedKey)) {
    return normalizedKeys
  }

  return [...normalizedKeys, normalizedKey]
}

export function hasDeletedAgentMediaKey(currentKeys: string[], key: string | null | undefined): boolean {
  const normalizedKey = typeof key === 'string' ? key.trim() : ''
  if (!normalizedKey) {
    return false
  }

  return normalizeDeletedAgentMediaKeys(currentKeys).includes(normalizedKey)
}

export function findExistingAgentGeneratedMedia(
  items: CanvasItem[],
  incoming: IncomingAgentGeneratedMedia,
): CanvasItem | undefined {
  const normalizedIncomingId = typeof incoming.id === 'string' ? incoming.id.trim() : ''
  const normalizedIncomingKey = typeof incoming.agentMediaKey === 'string'
    ? incoming.agentMediaKey.trim()
    : ''
  const incomingTaskId = incoming.task_id == null ? '' : String(incoming.task_id).trim()
  const incomingArtifactRef = typeof incoming.artifact_ref === 'string' ? incoming.artifact_ref.trim() : ''

  return items.find((item) => {
    const existingKey = typeof item.agent_media_key === 'string' ? item.agent_media_key.trim() : ''
    const existingTaskId = item.task_id == null ? '' : String(item.task_id).trim()
    const existingArtifactRef = typeof item.artifact_ref === 'string' ? item.artifact_ref.trim() : ''

    if (normalizedIncomingId && item.id === normalizedIncomingId) {
      return true
    }

    if (normalizedIncomingKey && existingKey === normalizedIncomingKey) {
      return true
    }

    if (incomingTaskId && existingTaskId === incomingTaskId) {
      return true
    }

    if (incomingArtifactRef && existingArtifactRef === incomingArtifactRef) {
      return true
    }

    return false
  })
}

function buildAgentGeneratedMediaState(
  items: CanvasItem[],
  includeLegacyGroups: boolean,
): AgentGeneratedMediaState {
  const groups = new Map(
    items
      .filter((item) => item.type === 'group')
      .map((item) => [item.id, item] as const),
  )
  const legacyAgentGroups = includeLegacyGroups
    ? new Set(
        items
          .filter((item) => item.groupId)
          .map((item) => item.groupId as string)
          .filter((groupId) => isLegacyAgentGroup(groupId, items, groups)),
      )
    : new Set<string>()
  const groupedAgentSessions = buildGroupedAgentSessionIndex(items, groups, legacyAgentGroups)

  const groupedItems = new Map<string, CanvasItem[]>()

  items.forEach((item) => {
    if (!shouldIncludeInAgentSession(item, groups, legacyAgentGroups)) {
      return
    }

    const messageId = normalizeMessageId(item.agent_message_id)
    const conversationId = normalizeConversationId(item.agent_conversation_id as string | number | null | undefined)
    const explicitGroupKey = typeof item.agent_group_key === 'string' ? item.agent_group_key.trim() : ''
    const hasAgentGridGroup =
      item.groupId && (groups.get(item.groupId)?.group_layout_mode === 'agent_grid' || legacyAgentGroups.has(item.groupId))
    const key = explicitGroupKey
      ? buildAgentGeneratedMediaExplicitGroupKey(conversationId, explicitGroupKey)
      : hasAgentGridGroup
        ? buildAgentGeneratedMediaGroupKey(item.groupId as string)
        : buildAgentGeneratedMediaSessionKey(conversationId, messageId)

    if (!item.groupId) {
      const isDetachedFromGroupedConversation =
        (conversationId != null && groupedAgentSessions.groupedConversationIds.has(conversationId))
        || groupedAgentSessions.groupedSessionKeys.has(key)

      if (isDetachedFromGroupedConversation) {
        return
      }
    }

    const currentItems = groupedItems.get(key) || []
    currentItems.push(item)
    groupedItems.set(key, currentItems)
  })

  const sessions = Array.from(groupedItems.entries()).reduce<Record<string, AgentGeneratedMediaSession>>((result, [key, sessionItems]) => {
    const orderedItems = [...sessionItems].sort(compareAgentGroupItems)
    const [firstItem] = orderedItems
    const groupId = orderedItems.find((item) => item.groupId)?.groupId ?? null
    const group = groupId ? groups.get(groupId) : undefined
    const conversationId = normalizeConversationId(
      (group?.agent_conversation_id ?? firstItem?.agent_conversation_id) as string | number | null | undefined,
    )
    const messageId = normalizeMessageId(group?.agent_message_id) ?? normalizeMessageId(firstItem?.agent_message_id) ?? null

    result[key] = {
      conversationId,
      messageId,
      groupId,
      items: orderedItems.map((item, index) => ({
        id: item.id,
        name: item.name || 'agent',
        order: getExistingOrder(item) ?? index,
      })),
    }

    return result
  }, {})

  return { sessions }
}

export function hydrateAgentGeneratedMediaState(items: CanvasItem[]): AgentGeneratedMediaState {
  return buildAgentGeneratedMediaState(items, false)
}

export function layoutAgentGridMembers(
  members: CanvasItem[],
  groupFrame: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>,
  options: AgentGroupLayoutOptions = DEFAULT_AGENT_GROUP_LAYOUT,
): AgentGroupLayoutResult {
  const sortedMembers = [...members].sort(compareAgentGroupItems)
  const originX = groupFrame.x + options.padding
  const originY = groupFrame.y + options.padding

  let currentX = originX
  let currentY = originY
  let rowMaxHeight = 0

  const laidOutMembers = sortedMembers.map((member, index) => {
    if (index > 0 && index % options.columns === 0) {
      currentX = originX
      currentY += rowMaxHeight + options.gap
      rowMaxHeight = 0
    }

    const width = member.width || 1024
    const height = member.height || 1024
    const nextMember = {
      ...member,
      x: currentX,
      y: currentY,
    }

    currentX += width + options.gap
    rowMaxHeight = Math.max(rowMaxHeight, height)

    return nextMember
  })

  if (laidOutMembers.length === 0) {
    return {
      group: groupFrame,
      members: [],
    }
  }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  laidOutMembers.forEach((member) => {
    const width = member.width || 1024
    const height = member.height || 1024
    minX = Math.min(minX, member.x)
    minY = Math.min(minY, member.y)
    maxX = Math.max(maxX, member.x + width)
    maxY = Math.max(maxY, member.y + height)
  })

  return {
    group: {
      x: minX - options.padding,
      y: minY - options.padding,
      width: maxX - minX + options.padding * 2,
      height: maxY - minY + options.padding * 2,
    },
    members: laidOutMembers,
  }
}

export function normalizeAgentGeneratedMediaItems(items: CanvasItem[]): CanvasItem[] {
  const state = buildAgentGeneratedMediaState(items, true)
  const groups = new Map(
    items
      .filter((item) => item.type === 'group')
      .map((item) => [item.id, { ...item }] as const),
  )
  const nextItems = new Map(items.map((item) => [item.id, { ...item }]))

  Object.values(state.sessions).forEach((session) => {
    session.items.forEach((sessionItem) => {
      const item = nextItems.get(sessionItem.id)
      if (!item) {
        return
      }

      item.agent_group_order = sessionItem.order
      item.agent_message_id = session.messageId
      item.agent_conversation_id = session.conversationId
      if (session.groupId) {
        item.groupId = session.groupId
      }
      nextItems.set(item.id, item)
    })

    if (!session.groupId || session.items.length < 2) {
      return
    }

    const group = groups.get(session.groupId) || nextItems.get(session.groupId)
    if (!group) {
      return
    }

    const members = session.items
      .map((sessionItem) => nextItems.get(sessionItem.id))
      .filter((item): item is CanvasItem => Boolean(item))

    const layout = layoutAgentGridMembers(
      members,
      getGroupLayoutFrame(group, members, DEFAULT_AGENT_GROUP_LAYOUT),
      DEFAULT_AGENT_GROUP_LAYOUT,
    )

    nextItems.set(group.id, {
      ...group,
      ...layout.group,
      group_layout_mode: 'agent_grid',
      agent_message_id: session.messageId,
      agent_conversation_id: session.conversationId,
    })

    layout.members.forEach((member) => {
      nextItems.set(member.id, {
        ...member,
        groupId: session.groupId || undefined,
        agent_group_order: session.items.find((sessionItem) => sessionItem.id === member.id)?.order ?? member.agent_group_order,
        agent_message_id: session.messageId,
        agent_conversation_id: session.conversationId,
      })
    })
  })

  return items
    .map((item) => nextItems.get(item.id) || item)
    .sort((a, b) => items.findIndex((entry) => entry.id === a.id) - items.findIndex((entry) => entry.id === b.id))
}

export function planAgentGeneratedMediaInsertion({
  currentState,
  conversationId,
  messageId,
  groupKey,
  incomingId,
  incomingName,
  fallbackGroupId,
}: PlanAgentGeneratedMediaInsertionArgs): AgentGeneratedMediaInsertionPlan {
  const normalizedMessageId = normalizeMessageId(messageId)
  const nextState: AgentGeneratedMediaState = {
    sessions: { ...currentState.sessions },
  }

  const normalizedGroupKey = typeof groupKey === 'string' ? groupKey.trim() : ''
  const nextKey = normalizedGroupKey
    ? buildAgentGeneratedMediaExplicitGroupKey(conversationId, normalizedGroupKey)
    : buildAgentGeneratedMediaSessionKey(conversationId, normalizedMessageId)
  let existingKey = nextKey
  let currentSession = nextState.sessions[nextKey]

  if (!currentSession && !normalizedGroupKey && normalizedMessageId) {
    const legacyEntry = Object.entries(nextState.sessions).find(([, session]) =>
      session.conversationId == null && session.messageId === normalizedMessageId,
    )
    if (legacyEntry) {
      existingKey = legacyEntry[0]
      currentSession = legacyEntry[1]
    }
  }

  if (!currentSession && !normalizedGroupKey) {
    const conversationEntry = findFallbackConversationSession(nextState.sessions, conversationId)
    if (conversationEntry) {
      existingKey = conversationEntry[0]
      currentSession = conversationEntry[1]
    }
  }

  const baseSession = currentSession
    ? {
        ...currentSession,
        conversationId,
        messageId: normalizedMessageId,
        items: [...currentSession.items],
      }
    : {
        conversationId,
        messageId: normalizedMessageId,
        items: [],
        groupId: null,
      }

  if (baseSession.items.some((item) => item.id === incomingId)) {
    return {
      shouldInsert: false,
      nextState,
      nextSession: baseSession,
      currentCount: baseSession.items.length,
      createdGroupId: null,
      nextOrder: baseSession.items.length === 0 ? 0 : Math.max(...baseSession.items.map((item) => item.order)),
    }
  }

  const nextOrder = baseSession.items.length === 0
    ? 0
    : Math.max(...baseSession.items.map((item) => item.order)) + 1
  const nextItems = [...baseSession.items, { id: incomingId, name: incomingName, order: nextOrder }]
  const currentCount = nextItems.length
  const shouldCreateGroup = !baseSession.groupId && (normalizedGroupKey ? currentCount >= 2 : currentCount === 2)
  const createdGroupId = shouldCreateGroup ? fallbackGroupId : null

  const nextSession = {
    conversationId,
    messageId: normalizedMessageId,
    items: nextItems,
    groupId: baseSession.groupId ?? createdGroupId,
  }

  const targetKey = normalizedGroupKey
    ? nextKey
    : nextSession.groupId
      ? buildAgentGeneratedMediaGroupKey(nextSession.groupId)
      : nextKey

  if (existingKey !== targetKey) {
    delete nextState.sessions[existingKey]
  }
  nextState.sessions[targetKey] = nextSession

  return {
    shouldInsert: true,
    nextState,
    nextSession,
    currentCount,
    createdGroupId,
    nextOrder,
  }
}
