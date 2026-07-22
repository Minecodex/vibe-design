import type { TFunction } from 'i18next'

import { getHomeToolDisplayName } from './homeChatMeta'

// Mirrors Claude Code's command-display truncation (MAX_COMMAND_DISPLAY_LINES=2,
// MAX_COMMAND_DISPLAY_CHARS=160) so long bash commands collapse to a tidy summary.
const COMMAND_MAX_LINES = 2
const COMMAND_MAX_CHARS = 160

export function normalizeHomeToolName(name: string | null | undefined): string {
  return String(name || '').trim().replace(/^lc_/, '')
}

// Read/search-family tools whose consecutive calls get collapsed into one
// "Explored"-style group row (see HomeToolGroupCard). Write/edit/exec are
// action tools and always render as their own row.
const READONLY_TOOLS = new Set([
  'read_file',
  'list_files',
  'glob_files',
  'grep_files',
  'fetch_webpage',
])

export function isHomeReadonlyTool(toolName: string | null | undefined): boolean {
  return READONLY_TOOLS.has(normalizeHomeToolName(toolName).toLowerCase())
}

/** Short action verb shown as the tool-row title, e.g. "读取 / Read". */
export function getHomeToolActionLabel(
  toolName: string | null | undefined,
  t: TFunction,
): string {
  const name = normalizeHomeToolName(toolName).toLowerCase()
  switch (name) {
    case 'read_file':
      return t('home.tool.action.read', '读取')
    case 'write_file':
      return t('home.tool.action.write', '写入')
    case 'edit_file':
      return t('home.tool.action.edit', '修改')
    case 'list_files':
      return t('home.tool.action.list', '列目录')
    case 'glob_files':
    case 'grep_files':
      return t('home.tool.action.search', '搜索')
    case 'exec_command':
    case 'bash':
      return t('home.tool.action.run', '执行命令')
    case 'fetch_webpage':
      return t('home.tool.action.fetch', '抓取网页')
    default:
      // Fall back to the existing bilingual display map (e.g. "联网搜索 / Web Search").
      return getHomeToolDisplayName(toolName)
  }
}

function asArgs(args: unknown): Record<string, any> {
  return args && typeof args === 'object' && !Array.isArray(args) ? (args as Record<string, any>) : {}
}

function relPath(value: unknown): string {
  return String(value || '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/^\.\//, '')
    .replace(/^\/+/, '')
}

function truncateCommand(command: string): string {
  const collapsed = command.trim()
  if (!collapsed) {
    return ''
  }
  const lines = collapsed.split('\n')
  let text = lines.slice(0, COMMAND_MAX_LINES).join('\n')
  let truncated = lines.length > COMMAND_MAX_LINES
  if (text.length > COMMAND_MAX_CHARS) {
    text = text.slice(0, COMMAND_MAX_CHARS)
    truncated = true
  }
  return truncated ? `${text.replace(/\s+$/, '')}…` : text
}

/**
 * One-line argument summary rendered in parentheses after the action verb,
 * mirroring Claude Code's per-tool `renderToolUseMessage`. Returns '' when there
 * is nothing useful to show (the row then shows just the action verb).
 * Language-agnostic on purpose: paths / patterns / commands are not translated.
 */
export function summarizeToolArgs(
  toolName: string | null | undefined,
  args: unknown,
): string {
  const a = asArgs(args)
  const name = normalizeHomeToolName(toolName).toLowerCase()
  const path = () => relPath(a.path ?? a.file_path)

  switch (name) {
    case 'read_file': {
      const p = path()
      if (!p) {
        return ''
      }
      const offset = Number(a.offset)
      const limit = Number(a.limit)
      if (Number.isFinite(offset) && offset > 0 && Number.isFinite(limit) && limit > 0) {
        return `${p} · ${offset}-${offset + limit - 1}`
      }
      return p
    }
    case 'write_file':
    case 'edit_file':
    case 'list_files':
      return path()
    case 'glob_files':
    case 'grep_files': {
      const pattern = String(a.pattern ?? '').trim()
      if (!pattern) {
        return ''
      }
      const p = relPath(a.path ?? a.file_path)
      return p ? `pattern: "${pattern}", path: "${p}"` : `pattern: "${pattern}"`
    }
    case 'exec_command':
    case 'bash':
      return truncateCommand(String(a.command ?? a.cmd ?? ''))
    case 'fetch_webpage':
      return String(a.url ?? '').trim()
    default:
      return ''
  }
}
