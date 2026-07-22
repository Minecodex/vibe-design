import { ChevronLeft, ChevronRight, History } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { WorkspaceFileRead } from '@/api/endpoints/agent'
import { cn } from '@/lib/utils'
import { getVersionIndex } from '@/store/homeHarnessFileVersions'

interface HomeChatFileVersionControlProps {
  file: WorkspaceFileRead
  selectedVersionId: string | null
  isDark: boolean
  disabled?: boolean
  onSelectVersion: (versionId: string) => void
}

export function HomeChatFileVersionControl({
  file,
  selectedVersionId,
  isDark: _isDark,
  disabled = false,
  onSelectVersion,
}: HomeChatFileVersionControlProps) {
  const { t } = useTranslation()
  const versions = file.versions || []
  if (versions.length <= 0) {
    return null
  }
  const selectedIndex = Math.max(0, getVersionIndex(file, selectedVersionId))
  const selected = versions[selectedIndex] || versions[versions.length - 1]
  const canPrev = selectedIndex > 0
  const canNext = selectedIndex < versions.length - 1
  const triggerClass = 'border-[var(--app-border)] bg-[var(--app-control)] text-foreground shadow-[var(--app-shadow-control)] hover:bg-[var(--app-control-hover)]'
  const menuClass = 'border-[var(--app-border)] bg-[var(--app-glass)] text-foreground shadow-[var(--app-shadow-panel)]'
  const iconButtonClass = 'text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground'

  return (
    <div
      data-testid="home-chat-file-version-control"
      className="group relative z-30"
    >
      <div
        data-testid="home-chat-file-version-menu"
        className="absolute right-0 top-full hidden w-72 pt-2 group-hover:block group-focus-within:block"
      >
        <div className={cn('max-h-72 overflow-y-auto rounded-2xl border p-1.5 shadow-xl backdrop-blur-xl', menuClass)}>
          {versions.map((version, index) => (
            <button
              key={version.version_id}
              type="button"
              disabled={disabled}
              onClick={() => onSelectVersion(version.version_id)}
              className={cn(
                'flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-60',
                selected.version_id === version.version_id
                  ? 'bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)]'
                  : 'hover:bg-[var(--app-control-hover)]',
              )}
            >
              <span className="min-w-0 truncate">
                {version.label || t('homeHarness.fileVersions.versionLabel', { number: index + 1 })}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatVersionTime(version.created_at)}
              </span>
            </button>
          ))}
        </div>
      </div>
      <div className={cn(
        'grid h-8 grid-cols-[24px_auto_24px] items-center rounded-lg border px-1 transition-colors backdrop-blur-xl',
        triggerClass,
      )}>
        <button
          type="button"
          disabled={disabled || !canPrev}
          aria-label={t('homeHarness.fileVersions.previous')}
          onClick={() => canPrev && onSelectVersion(versions[selectedIndex - 1].version_id)}
          className={cn(
            'flex h-6 w-6 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-35',
            iconButtonClass,
          )}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <div className="flex min-w-[82px] items-center justify-center gap-1.5 px-1.5 text-xs font-medium leading-tight">
          <History className="h-3.5 w-3.5" />
          <span>
            {t('homeHarness.fileVersions.versionCounter', {
              current: selectedIndex + 1,
              total: versions.length,
            })}
          </span>
        </div>
        <button
          type="button"
          disabled={disabled || !canNext}
          aria-label={t('homeHarness.fileVersions.next')}
          onClick={() => canNext && onSelectVersion(versions[selectedIndex + 1].version_id)}
          className={cn(
            'flex h-6 w-6 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-35',
            iconButtonClass,
          )}
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

function formatVersionTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleString(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
