import type { TFunction } from 'i18next'

import type { MessageBlock } from '@/store/homeHarnessStore'

import { isHomeReadonlyTool, normalizeHomeToolName } from './homeToolDisplay'
import { isHomeToolBlock, resolveToolBlockName, resolveToolBlockStatus, type ToolRowStatus } from './homeToolBlock'

export const TOOL_GROUP_UI_KIND = 'tool_group'

export function isGroupableReadonlyToolBlock(block: MessageBlock): boolean {
  return (
    block.visible !== false
    && isHomeToolBlock(block)
    && isHomeReadonlyTool(resolveToolBlockName(block))
  )
}

function groupStatus(children: MessageBlock[]): ToolRowStatus {
  const statuses = children.map(resolveToolBlockStatus)
  if (statuses.some((status) => status === 'running')) {
    return 'running'
  }
  if (statuses.some((status) => status === 'failed')) {
    return 'failed'
  }
  return 'completed'
}

function buildToolGroupBlock(children: MessageBlock[]): MessageBlock {
  const first = children[0]
  const last = children[children.length - 1]
  return {
    id: `tool-group:${first.id}:${last.id}`,
    kind: 'tool',
    uiKind: TOOL_GROUP_UI_KIND,
    order: first.order,
    status: groupStatus(children),
    visible: true,
    payload: {},
    children,
  }
}

/**
 * Collapse runs of >= 2 consecutive read/search-family tool blocks into a single
 * synthetic `tool_group` block. Any other block (text / final-answer / write /
 * edit / exec / unrelated cards) breaks the run, preserving the
 * "解说 → 工具组 → 解说" order. A lone readonly tool stays as its own row.
 */
export function groupHomeReadonlyToolBlocks(blocks: MessageBlock[]): MessageBlock[] {
  const out: MessageBlock[] = []
  let run: MessageBlock[] = []

  const flush = () => {
    if (run.length === 0) {
      return
    }
    if (run.length === 1) {
      out.push(run[0])
    } else {
      out.push(buildToolGroupBlock(run))
    }
    run = []
  }

  for (const block of blocks) {
    if (isGroupableReadonlyToolBlock(block)) {
      run.push(block)
    } else {
      flush()
      out.push(block)
    }
  }
  flush()
  return out
}

type ToolGroupCategory = 'read' | 'search' | 'fetch'

function toolCategory(toolName: string): ToolGroupCategory {
  const name = normalizeHomeToolName(toolName).toLowerCase()
  if (name === 'glob_files' || name === 'grep_files') {
    return 'search'
  }
  if (name === 'fetch_webpage') {
    return 'fetch'
  }
  return 'read'
}

/**
 * Codex-style one-line summary for the collapsed group header, e.g.
 * "读取 3 个文件、搜索 1 处". Uses present-continuous wording while running.
 */
export function summarizeToolGroup(children: MessageBlock[], t: TFunction): string {
  const counts: Record<ToolGroupCategory, number> = { read: 0, search: 0, fetch: 0 }
  for (const child of children) {
    counts[toolCategory(resolveToolBlockName(child))] += 1
  }
  const running = children.some((child) => resolveToolBlockStatus(child) === 'running')
  const parts: string[] = []
  if (counts.read > 0) {
    parts.push(
      running
        ? t('home.tool.group.reading', { count: counts.read, defaultValue: '读取 {{count}} 个文件' })
        : t('home.tool.group.read', { count: counts.read, defaultValue: '读取 {{count}} 个文件' }),
    )
  }
  if (counts.search > 0) {
    parts.push(
      running
        ? t('home.tool.group.searching', { count: counts.search, defaultValue: '搜索 {{count}} 处' })
        : t('home.tool.group.search', { count: counts.search, defaultValue: '搜索 {{count}} 处' }),
    )
  }
  if (counts.fetch > 0) {
    parts.push(t('home.tool.group.fetch', { count: counts.fetch, defaultValue: '抓取 {{count}} 个网页' }))
  }
  if (parts.length === 0) {
    return t('home.tool.group.generic', { count: children.length, defaultValue: '{{count}} 个工具调用' })
  }
  return parts.join(t('home.tool.group.separator', '、'))
}
