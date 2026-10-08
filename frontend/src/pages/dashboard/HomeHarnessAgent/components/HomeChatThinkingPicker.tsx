import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Lightbulb } from 'lucide-react'

import { cn } from '@/lib/utils'

interface HomeChatThinkingPickerProps {
  isDark: boolean
  thinkingEnabled: boolean
  thinkingAvailable: boolean
  onThinkingChange: (enabled: boolean) => void
}

export function HomeChatThinkingPicker({ thinkingEnabled, thinkingAvailable, onThinkingChange }: HomeChatThinkingPickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const currentTitle = thinkingEnabled
    ? t('canvas.chat.modes.thinking', 'Thinking Mode')
    : t('canvas.chat.modes.quick', 'Quick Mode')
  const currentDescription = thinkingEnabled
    ? t('canvas.chat.modes.thinking_desc', 'Use deeper reasoning before answering')
    : t('canvas.chat.modes.quick_desc', 'Respond faster with lighter reasoning')
  const thinkingDisabled = !thinkingEnabled && !thinkingAvailable
  const thinkingUnavailableDescription = t(
    'canvas.chat.modes.thinking_unavailable',
    'Current model does not support thinking mode',
  )

  return (
    <div
      ref={containerRef}
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        aria-label={t('canvas.chat.modes.thinking', 'Thinking Mode')}
        aria-expanded={open}
        className={cn(
          'p-2 rounded-lg transition-colors focus:outline-none border',
          thinkingEnabled || open
            ? 'text-blue-500 bg-blue-500/10 border-blue-500/20'
            : thinkingDisabled
              ? 'text-zinc-400 border-transparent opacity-50 cursor-not-allowed'
            : 'border-transparent text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
        )}
        onClick={() => {
          if (thinkingDisabled) return
          setOpen(current => !current)
        }}
      >
        <Lightbulb className="w-4 h-4" />
      </button>

      {hovered && !open ? (
        <div
          className={cn(
            'absolute bottom-full right-0 mb-3 w-52 rounded-2xl px-3 py-2.5 shadow-2xl z-20',
            'border border-[var(--app-border)] bg-[var(--app-glass)] text-foreground backdrop-blur-2xl',
          )}
        >
          <div className="text-xs font-semibold">{currentTitle}</div>
          <div className="text-[11px] text-zinc-300 mt-1">
            {thinkingDisabled ? thinkingUnavailableDescription : currentDescription}
          </div>
        </div>
      ) : null}

      {open ? (
        <div
          className={cn(
            'absolute bottom-full right-0 mb-3 w-56 rounded-xl border p-1.5 shadow-2xl z-30',
            'border-[var(--app-border)] bg-[var(--app-glass)] backdrop-blur-2xl',
          )}
        >
          <button
            type="button"
            aria-label="Quick Mode Option"
            onClick={() => {
              onThinkingChange(false)
              setOpen(false)
            }}
            className={cn(
              'w-full text-left rounded-lg px-2.5 py-2 text-sm transition-colors',
              !thinkingEnabled
                ? 'bg-[var(--app-tint-primary)] text-[var(--app-primary)]'
                : 'text-foreground hover:bg-[var(--app-control-hover)]',
            )}
          >
            <div className="font-medium">{t('canvas.chat.modes.quick', 'Quick Mode')}</div>
            <div className="text-xs text-zinc-500 mt-1">
              {t('canvas.chat.modes.quick_desc', 'Respond faster with lighter reasoning')}
            </div>
          </button>

          <button
            type="button"
            aria-label="Thinking Mode Option"
            onClick={() => {
              if (thinkingDisabled) return
              onThinkingChange(true)
              setOpen(false)
            }}
            className={cn(
              'mt-1 w-full text-left rounded-lg px-2.5 py-2 text-sm transition-colors',
              thinkingDisabled
                ? 'opacity-50 cursor-not-allowed text-zinc-400'
                : thinkingEnabled
                ? 'bg-[var(--app-tint-primary)] text-[var(--app-primary)]'
                : 'text-foreground hover:bg-[var(--app-control-hover)]',
            )}
          >
            <div className="font-medium">{t('canvas.chat.modes.thinking', 'Thinking Mode')}</div>
            <div className="text-xs text-zinc-500 mt-1">
              {thinkingDisabled
                ? thinkingUnavailableDescription
                : t('canvas.chat.modes.thinking_desc', 'Use deeper reasoning before answering')}
            </div>
          </button>
        </div>
      ) : null}
    </div>
  )
}
