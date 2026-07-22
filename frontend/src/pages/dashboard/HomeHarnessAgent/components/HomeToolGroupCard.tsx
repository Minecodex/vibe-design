import { memo, useState } from 'react'
import type { TFunction } from 'i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { MessageBlock } from '@/store/homeHarnessStore'

import { HomeToolCallCard, ToolStatusDot } from './HomeToolCallCard'
import { resolveToolBlockStatus, type ToolRowStatus } from './homeToolBlock'
import { summarizeToolGroup } from './homeToolGrouping'

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

/**
 * Collapsed summary row for a run of consecutive read/search tool calls,
 * mirroring Codex's "Explored" grouping. Expands to the individual tool rows.
 */
export const HomeToolGroupCard = memo(HomeToolGroupCardImpl)

function HomeToolGroupCardImpl({
  block,
  isDark,
  t,
}: {
  block: MessageBlock
  isDark: boolean
  t: TFunction
}) {
  const [expanded, setExpanded] = useState(false)
  const children = (block.children || []).filter((child) => child.visible !== false)
  if (children.length === 0) {
    return null
  }

  const status = groupStatus(children)
  const summary = summarizeToolGroup(children, t)
  const ToggleIcon = expanded ? ChevronDown : ChevronRight

  return (
    <div
      className={cn(
        'app-card-muted max-w-[90%] rounded-xl',
      )}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        className={cn(
          'flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-[var(--app-control-hover)]',
        )}
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <ToolStatusDot status={status} />
          <span className={cn('truncate text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
            {summary}
          </span>
        </div>
        <ToggleIcon className={cn('h-3.5 w-3.5 shrink-0', isDark ? 'text-zinc-500' : 'text-zinc-400')} />
      </button>
      {expanded ? (
        <div className="app-divider space-y-1.5 border-t px-2 py-2">
          {children.map((child) => (
            <HomeToolCallCard key={child.id} block={child} isDark={isDark} t={t} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
