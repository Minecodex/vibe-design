import { wireRecord } from '@/store/harnessWireFields'
import type { ChatMessage, MessageBlock } from '@/store/homeHarnessStore'

export function extractHomepageBlockCallId(block: MessageBlock): string | null {
  const explicitCallId = String(
    block.payload?.callId
    || block.payload?.call_id
    || wireRecord(block.payload?.result)?.callId
    || wireRecord(block.payload?.result)?.call_id
    || '',
  ).trim()
  if (explicitCallId) {
    return explicitCallId
  }

  const rawId = String(block.id || '')
  const knownPrefixes = [
    'tool-',
    'media-',
    'analyze-image-text-',
  ]

  for (const prefix of knownPrefixes) {
    if (rawId.startsWith(prefix) && rawId.length > prefix.length) {
      return rawId.slice(prefix.length)
    }
  }

  const callIdStart = rawId.lastIndexOf('functions.')
  if (callIdStart >= 0) {
    return rawId.slice(callIdStart)
  }

  return null
}

export function extractHomepageBlockTaskId(block: MessageBlock): string | null {
  const rawTaskId = block.payload?.taskId
    ?? block.payload?.task_id
    ?? wireRecord(block.payload?.result)?.taskId
    ?? wireRecord(block.payload?.result)?.task_id
    ?? block.taskId
  const taskId = String(rawTaskId || '').trim()
  return taskId || null
}

export function extractHomepageBlockArtifactRef(block: MessageBlock): string | null {
  const rawArtifactRef = block.payload?.artifactRef
    ?? block.payload?.artifact_ref
    ?? wireRecord(block.payload?.result)?.artifactRef
    ?? wireRecord(block.payload?.result)?.artifact_ref
  const artifactRef = String(rawArtifactRef || '').trim()
  return artifactRef || null
}

export function extractHomepageBlockIdentityKeys(block: MessageBlock): string[] {
  const keys = new Set<string>()
  const callId = extractHomepageBlockCallId(block)
  const taskId = extractHomepageBlockTaskId(block)
  const artifactRef = extractHomepageBlockArtifactRef(block)
  const renderKey = String(
    block.renderKey
    ?? block.payload?.renderKey
    ?? block.payload?.render_key
    ?? '',
  ).trim()

  if (artifactRef) {
    keys.add(`artifact:${artifactRef}`)
  }
  if (callId) {
    keys.add(`call:${callId}`)
  }
  if (taskId) {
    keys.add(`task:${taskId}`)
  }
  if (renderKey) {
    keys.add(`render:${renderKey}`)
  }
  if (block.id) {
    keys.add(`block:${block.id}`)
  }
  return Array.from(keys)
}

export function blocksShareHomepageIdentity(left: MessageBlock, right: MessageBlock): boolean {
  const leftKeys = extractHomepageBlockIdentityKeys(left)
  if (leftKeys.length === 0) {
    return false
  }
  const rightKeys = extractHomepageBlockIdentityKeys(right)
  return rightKeys.some((key) => leftKeys.includes(key))
}

function flattenMessageBlocks(messages: ChatMessage[]): MessageBlock[] {
  const flattened: MessageBlock[] = []
  const stack = messages.flatMap((message) => message.blocks || [])

  while (stack.length > 0) {
    const block = stack.pop()
    if (!block) {
      continue
    }
    flattened.push(block)
    if (Array.isArray(block.children) && block.children.length > 0) {
      stack.push(...block.children)
    }
  }

  return flattened
}

export function filterDuplicateHomepageStreamingBlocks(
  messages: ChatMessage[],
  streamingBlocks: MessageBlock[],
): MessageBlock[] {
  if (messages.length === 0 || streamingBlocks.length === 0) {
    return streamingBlocks
  }

  const existingBlocks = flattenMessageBlocks(messages)
  if (existingBlocks.length === 0) {
    return streamingBlocks
  }

  return streamingBlocks.filter((block) => {
    const identityKeys = extractHomepageBlockIdentityKeys(block)
    if (identityKeys.length === 0) {
      return true
    }

    return !existingBlocks.some((existing) =>
      extractHomepageBlockIdentityKeys(existing).some((key) => identityKeys.includes(key)),
    )
  })
}

function normalizeHomepageFilePath(value: unknown): string {
  return String(value || '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/^\.?\//, '')
    .toLowerCase()
}

function isHomepagePlanFilePath(value: unknown): boolean {
  const normalized = normalizeHomepageFilePath(value)
  return normalized === 'plan.md'
}

export function removeRedundantHomepagePlanBlocks(blocks: MessageBlock[]): MessageBlock[] {
  const hasPlanArtifact = blocks.some((block) => block.uiKind === 'plan_artifact')
  if (!hasPlanArtifact) {
    return blocks
  }

  return blocks.filter((block) => {
    if (block.uiKind !== 'md_document') {
      return true
    }
    const filePath = block.payload?.filePath ?? block.payload?.file_path
    return !isHomepagePlanFilePath(filePath)
  })
}
