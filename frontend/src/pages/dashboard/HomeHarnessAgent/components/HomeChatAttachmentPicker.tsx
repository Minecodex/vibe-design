import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Paperclip } from 'lucide-react'

import { cn } from '@/lib/utils'
import { getHomeHarnessAttachmentAccept } from './homeChatAttachmentKinds'

interface HomeChatAttachmentPickerProps {
  isDark: boolean
  disabled?: boolean
  onFilesSelected: (files: FileList | null) => void
  onOpenLibrary: () => void
  onOpenReferenceGallery: () => void
}

export function HomeChatAttachmentPicker({
  isDark: _isDark,
  disabled = false,
  onFilesSelected,
  onOpenLibrary,
  onOpenReferenceGallery,
}: HomeChatAttachmentPickerProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  return (
    <div ref={containerRef} className="relative">
      <input
        ref={fileInputRef}
        data-testid="home-chat-local-upload-input"
        type="file"
        accept={getHomeHarnessAttachmentAccept()}
        className="hidden"
        onChange={(event) => {
          onFilesSelected(event.target.files)
          event.currentTarget.value = ''
          setOpen(false)
        }}
      />

      <button
        type="button"
        aria-label={t('home.chat.attachment_sources', 'Attachment Sources')}
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(current => !current)}
        className={cn(
          'p-2 rounded-lg transition-colors focus:outline-none border',
          open
            ? 'text-blue-500 bg-blue-500/10 border-blue-500/20'
            : 'border-transparent text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
          disabled ? 'opacity-50 cursor-not-allowed' : '',
        )}
      >
        <Paperclip className="w-4 h-4" />
      </button>

      {open ? (
        <div
          className={cn(
            'absolute bottom-full right-0 z-30 mb-3 w-52 rounded-2xl border p-2 shadow-2xl',
            'border-[var(--app-border)] bg-[var(--app-glass)] backdrop-blur-2xl',
          )}
        >
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              'w-full text-left rounded-xl px-3 py-2.5 text-sm transition-colors',
              'text-foreground hover:bg-[var(--app-control-hover)]',
            )}
          >
            {t('home.chat.local_upload', 'Local Upload')}
          </button>
          <button
            type="button"
            aria-label={t('home.chat.asset_library', 'Asset Library')}
            onClick={() => {
              setOpen(false)
              onOpenLibrary()
            }}
            className={cn(
              'mt-1 w-full text-left rounded-xl px-3 py-2.5 text-sm transition-colors',
              'text-foreground hover:bg-[var(--app-control-hover)]',
            )}
          >
            {t('home.chat.asset_library', 'Asset Library')}
          </button>
          <button
            type="button"
            aria-label={t('home.chat.reference_gallery', 'Reference Gallery')}
            onClick={() => {
              setOpen(false)
              onOpenReferenceGallery()
            }}
            className={cn(
              'mt-1 w-full text-left rounded-xl px-3 py-2.5 text-sm transition-colors',
              'text-foreground hover:bg-[var(--app-control-hover)]',
            )}
          >
            {t('home.chat.reference_gallery', 'Reference Gallery')}
          </button>
        </div>
      ) : null}
    </div>
  )
}
