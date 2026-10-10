import { memo, useState } from 'react'
import type { TFunction } from 'i18next'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { MessageBlock } from '@/store/homeHarnessStore'
import { extractToolResultStreamText } from '@/store/canvasAgentToolCalls'

import { getHomeToolActionLabel, summarizeToolArgs } from './homeToolDisplay'
import {
  formatToolElapsed,
  resolveToolBlockName,
  resolveToolBlockStatus,
  type ToolRowStatus,
} from './homeToolBlock'

export function ToolStatusDot({ status }: { status: ToolRowStatus }) {
  if (status === 'running') {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-400" />
      </span>
    )
  }
  return (
    <span className="flex h-4 w-4 shrink-0 items-center justify-center">
      <span
        className={cn(
          'h-2 w-2 rounded-full',
          status === 'failed' ? 'bg-red-500' : 'bg-emerald-500',
        )}
      />
    </span>
  )
}

/**
 * Claude-Code-style inline tool row: `● 动作 (参数摘要) … 耗时`, with the tool
 * output collapsed by default and revealed on click.
 */
export const HomeToolCallCard = memo(HomeToolCallCardImpl)

function HomeToolCallCardImpl({
  block,
  isDark,
  t,
}: {
  block: MessageBlock
  isDark: boolean
  t: TFunction
}) {
  const [expanded, setExpanded] = useState(false)

  const toolName = resolveToolBlockName(block)
  const status = resolveToolBlockStatus(block)
  const action = getHomeToolActionLabel(toolName, t)
  const summary = summarizeToolArgs(toolName, block.payload?.args ?? block.payload?.input)
  const elapsed = formatToolElapsed(block)
  const output = extractToolResultStreamText((block.payload || {}) as Record<string, unknown>)
  const canExpand = Boolean(output && status !== 'running')

  const ToggleIcon = expanded ? ChevronDown : ChevronRight

  const header = (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <ToolStatusDot status={status} />
      <span className={cn('shrink-0 text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
        {action}
      </span>
      {summary ? (
        <span
          className={cn('min-w-0 truncate font-mono text-xs', isDark ? 'text-zinc-400' : 'text-zinc-500')}
          title={summary}
        >
          {summary}
        </span>
      ) : null}
    </div>
  )

  const trailing = (
    <div className="flex shrink-0 items-center gap-2">
      {elapsed ? (
        <span className={cn('text-xs tabular-nums', isDark ? 'text-zinc-500' : 'text-zinc-400')}>
          {elapsed}
        </span>
      ) : null}
      {canExpand ? (
        <ToggleIcon className={cn('h-3.5 w-3.5', isDark ? 'text-zinc-500' : 'text-zinc-400')} />
      ) : null}
    </div>
  )

  return (
    <div
      className={cn(
        'max-w-[90%] rounded-xl border',
        status === 'failed'
          ? (isDark ? 'border-red-500/25 bg-red-500/5' : 'border-red-200 bg-red-50/50')
          : 'app-card-muted',
      )}
    >
      {canExpand ? (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
          className={cn(
            'flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-[var(--app-control-hover)]',
          )}
        >
          {header}
          {trailing}
        </button>
      ) : (
        <div className="flex items-center justify-between gap-3 px-3 py-2">
          {header}
          {trailing}
        </div>
      )}
      {canExpand && expanded ? (
        <div className="app-divider border-t px-3 py-2">
          <pre
            className={cn(
              'max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5',
              isDark ? 'text-zinc-300' : 'text-zinc-700',
            )}
          >
            {output}
          </pre>
        </div>
      ) : null}
    </div>
  )
}
