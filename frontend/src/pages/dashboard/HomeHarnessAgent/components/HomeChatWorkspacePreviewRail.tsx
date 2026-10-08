import type { ReactNode } from 'react'
import { ExternalLink, Loader2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { ExternalOpenSuite } from './homeChatExternalOpen'

interface HomeChatWorkspacePreviewRailProps {
  title: string
  metaSummary?: ReactNode
  isDark: boolean
  testId: string
  onClose: () => void
  onDownload: () => void
  onOpenExternal?: (suite: ExternalOpenSuite) => void
  externalOpenSuites?: ExternalOpenSuite[]
  isOpeningExternal?: boolean
  isOpenExternalDisabled?: boolean
  onSave?: () => void
  saveLabel?: string
  isSaveDisabled?: boolean
  isSaving?: boolean
  contentClassName?: string
  actionsBeforeDownload?: ReactNode
  footerOverlay?: ReactNode
  children: ReactNode
}

function OfficeSuiteIcon() {
  return (
    <span aria-hidden="true" className="grid h-4 w-4 grid-cols-2 gap-0.5">
      <span className="rounded-[2px] bg-orange-500" />
      <span className="rounded-[2px] bg-emerald-500" />
      <span className="rounded-[2px] bg-blue-500" />
      <span className="rounded-[2px] bg-amber-400" />
    </span>
  )
}

function WpsSuiteIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle cx="12" cy="12" r="10" fill="#fff" stroke="#e5e7eb" />
      <path
        d="M5.9 7.7 8.6 16l2.1-5.8L12.9 16l5.2-8.3h-2.5l-2.1 3.9-1.6-3.9H9.5l-1.3 3.9-1.1-3.9H5.9Z"
        fill="#ef1b1b"
      />
      <path
        d="M7.5 7.7h2.3l1.4 3.9 1.3-3.9h2.5"
        stroke="#ef1b1b"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function HomeChatWorkspacePreviewRail({ title, metaSummary, testId, onClose, onDownload, onOpenExternal, externalOpenSuites = ['office'], isOpeningExternal = false, isOpenExternalDisabled = false, onSave, saveLabel, isSaveDisabled = false, isSaving = false, contentClassName, actionsBeforeDownload, footerOverlay, children }: HomeChatWorkspacePreviewRailProps) {
  const { t } = useTranslation()
  const availableExternalOpenSuites = externalOpenSuites.filter((suite) => suite !== 'browser')

  return (
    <aside
      data-testid={testId}
      className={cn(
        'min-w-0 flex-1 rounded-[32px] relative border flex flex-col min-h-0 overflow-hidden',
        'border-[var(--app-border)] bg-[var(--app-glass)] shadow-[var(--app-shadow-panel)] backdrop-blur-2xl',
      )}
    >
      <div className={cn(
        'flex items-center justify-between gap-4 px-5 py-4 border-b',
        'border-[var(--app-border)]',
      )}>
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            aria-label="Close preview"
            onClick={onClose}
            className={cn(
              'rounded-lg p-2 transition-colors',
              'text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
            )}
          >
            <X className="w-4 h-4" />
          </button>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-foreground">
              {title}
            </div>
            {metaSummary ? (
              <div className="mt-1 min-w-0 text-xs text-muted-foreground">
                {metaSummary}
              </div>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actionsBeforeDownload}
          {onSave ? (
            <button
              type="button"
              aria-label={saveLabel || `Save ${title}`}
              onClick={onSave}
              disabled={isSaveDisabled || isSaving}
              className={cn(
                'rounded-lg px-3 py-1.5 text-xs font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-60',
                'bg-[var(--app-tint-primary)] text-[var(--app-primary)]',
              )}
            >
              {isSaving ? 'Saving...' : (saveLabel || 'Save')}
            </button>
          ) : null}
          <button
            type="button"
            onClick={onDownload}
            aria-label={t('common.download')}
            className={cn(
              'h-8 rounded-lg px-3 text-xs font-medium',
              'bg-[var(--app-control)] text-foreground hover:bg-[var(--app-control-hover)]',
            )}
          >
            {t('common.download')}
          </button>
          {onOpenExternal ? (
            availableExternalOpenSuites.length > 1 ? (
              <div className="group relative">
                <button
                  type="button"
                  aria-label={t('home.chat.open_external')}
                  title={t('home.chat.open_external')}
                  disabled={isOpenExternalDisabled || isOpeningExternal}
                  className={cn(
                    'h-8 w-8 rounded-lg inline-flex items-center justify-center transition-opacity disabled:cursor-not-allowed disabled:opacity-60',
                    'bg-[var(--app-control)] text-foreground hover:bg-[var(--app-control-hover)]',
                  )}
                >
                  {isOpeningExternal ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ExternalLink className="h-4 w-4" />
                  )}
                </button>
                <div className={cn(
                  'pointer-events-none absolute right-0 top-full z-20 flex items-center gap-2 rounded-xl border bg-clip-padding p-1.5 pt-3 opacity-0 shadow-lg transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100',
                  'border-[var(--app-border)] bg-[var(--app-glass)] backdrop-blur-2xl',
                )}>
                  {availableExternalOpenSuites.includes('office') ? (
                    <button
                      type="button"
                      aria-label={t('home.chat.open_external_office')}
                      title={t('home.chat.open_external_office')}
                      onClick={() => onOpenExternal('office')}
                      disabled={isOpenExternalDisabled || isOpeningExternal}
                      className={cn(
                        'h-8 w-8 rounded-lg inline-flex items-center justify-center disabled:cursor-not-allowed disabled:opacity-60',
                        'bg-[var(--app-tint-primary)] text-[var(--app-primary)] hover:bg-[var(--app-tint-primary-hover)]',
                      )}
                    >
                      <OfficeSuiteIcon />
                    </button>
                  ) : null}
                  {availableExternalOpenSuites.includes('wps') ? (
                    <button
                      type="button"
                      aria-label={t('home.chat.open_external_wps')}
                      title={t('home.chat.open_external_wps')}
                      onClick={() => onOpenExternal('wps')}
                      disabled={isOpenExternalDisabled || isOpeningExternal}
                      className={cn(
                        'h-8 w-8 rounded-lg inline-flex items-center justify-center disabled:cursor-not-allowed disabled:opacity-60',
                        'bg-[var(--app-tint-success)] text-[var(--app-success)] hover:bg-[var(--app-tint-success)]',
                      )}
                    >
                      <WpsSuiteIcon />
                    </button>
                  ) : null}
                </div>
              </div>
            ) : (
              <button
                type="button"
                aria-label={t('home.chat.open_external')}
                title={t('home.chat.open_external')}
                onClick={() => onOpenExternal(externalOpenSuites[0] || 'browser')}
                disabled={isOpenExternalDisabled || isOpeningExternal}
                className={cn(
                  'h-8 w-8 rounded-lg inline-flex items-center justify-center transition-opacity disabled:cursor-not-allowed disabled:opacity-60',
                  'bg-[var(--app-control)] text-foreground hover:bg-[var(--app-control-hover)]',
                )}
              >
                {isOpeningExternal ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ExternalLink className="h-4 w-4" />
                )}
              </button>
            )
          ) : null}
        </div>
      </div>
      <div className={cn('flex-1 min-h-0', contentClassName)}>
        {children}
      </div>
      {footerOverlay}
    </aside>
  )
}
