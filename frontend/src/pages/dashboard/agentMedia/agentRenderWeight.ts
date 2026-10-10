import type { AgentRenderWeightSnapshot } from './agentMediaTypes'

interface WeightMessageLike {
  content?: unknown
  attachments?: Array<unknown>
  blocks?: Array<WeightBlockLike>
}

interface WeightBlockLike {
  kind?: unknown
  uiKind?: unknown
  status?: unknown
  payload?: Record<string, unknown>
  children?: Array<WeightBlockLike>
}

const MARKDOWN_IMAGE_PATTERN = /!\[[^\]]*]\([^)]+\)/g
const REFERENCE_IMAGE_PATTERN = /(generation-artifact:|canvas-workspace-file:|references\/(?:generated|inputs|sources)\/)/g

export function getAgentMessageRenderWeight(message: WeightMessageLike): number {
  let weight = 1
  const content = String(message.content || '')
  weight += countPattern(content, MARKDOWN_IMAGE_PATTERN) * 4
  weight += countPattern(content, REFERENCE_IMAGE_PATTERN) * 2
  weight += (message.attachments?.length || 0) * 3
  for (const block of message.blocks || []) {
    weight += getAgentBlockRenderWeight(block)
  }
  return weight
}

export function getAgentBlockRenderWeight(block: WeightBlockLike): number {
  const uiKind = String(block.uiKind || '')
  const kind = String(block.kind || '')
  const payload = block.payload || {}
  let weight = 1

  if (uiKind.includes('generation') || uiKind === 'media_card' || uiKind === 'artifact_card') {
    weight += 8
  }
  if (uiKind.includes('tool') || kind.includes('tool')) {
    weight += 4
  }
  if (uiKind.includes('web_search')) {
    weight += 5
  }
  if (String(payload.media_type || payload.mediaType || '').trim()) {
    weight += 5
  }
  const text = String(payload.text || payload.content || payload.stream_text || payload.summary || '')
  weight += countPattern(text, MARKDOWN_IMAGE_PATTERN) * 4
  weight += countPattern(text, REFERENCE_IMAGE_PATTERN) * 2
  for (const child of block.children || []) {
    weight += getAgentBlockRenderWeight(child)
  }
  return weight
}

export function isAgentHeavyBlock(block: WeightBlockLike): boolean {
  return getAgentBlockRenderWeight(block) >= 8
}

export function isAgentBlockTerminal(block: WeightBlockLike): boolean {
  const status = String(block.payload?.status || block.status || '').toLowerCase()
  return status === 'completed' || status === 'failed' || status === 'blocked' || status === 'cancelled'
}

export function getAgentRenderWeightSnapshot(items: WeightMessageLike[]): AgentRenderWeightSnapshot {
  const weights = items.map(getAgentMessageRenderWeight)
  return {
    itemCount: items.length,
    totalWeight: weights.reduce((sum, weight) => sum + weight, 0),
    heavyItemCount: weights.filter((weight) => weight >= 8).length,
  }
}

export function shouldVirtualizeAgentItems(
  snapshot: AgentRenderWeightSnapshot,
  options: { itemThreshold: number; weightThreshold: number },
): boolean {
  return snapshot.itemCount > options.itemThreshold || snapshot.totalWeight >= options.weightThreshold
}

function countPattern(value: string, pattern: RegExp): number {
  pattern.lastIndex = 0
  return Array.from(value.matchAll(pattern)).length
}
