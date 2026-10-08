import type { MessageBlock } from '@/store/homeHarnessStore'
import { normalizeToolResultStatus } from '@/store/canvasAgentToolCalls'

export type ToolRowStatus = 'running' | 'completed' | 'failed'

const TOOL_BLOCK_UI_KINDS = new Set(['tool_call', 'tool_result', 'compact_tool'])

export function isHomeToolBlock(block: MessageBlock): boolean {
  return TOOL_BLOCK_UI_KINDS.has(String(block.uiKind || ''))
}

export function resolveToolBlockName(block: MessageBlock): string {
  return String(
    block.payload?.toolName
    || block.payload?.tool_name
    || block.payload?.tool
    || '',
  )
}

export function resolveToolBlockStatus(block: MessageBlock): ToolRowStatus {
  const payload = (block.payload || {}) as Record<string, unknown>
  if (payload.is_error || payload.isError) {
    return 'failed'
  }
  const normalized = normalizeToolResultStatus(payload, block.status)
  return normalized === 'failed' ? 'failed' : normalized === 'completed' ? 'completed' : 'running'
}

export function formatToolElapsed(block: MessageBlock): string | null {
  const raw = block.payload?.elapsedMs ?? block.payload?.elapsed_ms ?? block.payload?.result?.elapsed_ms
  const ms = Number(raw)
  if (!Number.isFinite(ms) || ms <= 0) {
    return null
  }
  return `${(ms / 1000).toFixed(1)}s`
}
