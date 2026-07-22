import { Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { WorkspaceFileRead } from '@/api/endpoints/agent'

import { FileCard } from './FileCard'
import {
  HOME_CHAT_FILE_TABS,
  type HomeChatFileTab,
} from './homeChatFileTabs'
import {
  getHomeFileTabFallback,
  type SessionFileItem,
} from '../homeHarnessPageUtils'

interface HomeSessionFilesDialogProps {
  open: boolean
  isDark: boolean
  activeFileTab: HomeChatFileTab
  fileTabCounts: Record<HomeChatFileTab, number>
  visibleSessionFiles: SessionFileItem[]
  sessionFiles: SessionFileItem[]
  conversationId: number | string | null
  onOpenChange: (open: boolean) => void
  onActiveFileTabChange: (tab: HomeChatFileTab) => void
  onDownloadFile: (file: WorkspaceFileRead) => void
  onPreviewWorkspaceFile: (file: WorkspaceFileRead) => void
}

export function HomeSessionFilesDialog({
  open,
  isDark,
  activeFileTab,
  fileTabCounts,
  visibleSessionFiles,
  sessionFiles,
  conversationId,
  onOpenChange,
  onActiveFileTabChange,
  onDownloadFile,
  onPreviewWorkspaceFile,
}: HomeSessionFilesDialogProps) {
  const { t } = useTranslation()

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        onOpenChange(nextOpen)
        if (nextOpen) {
          onActiveFileTabChange('all')
        }
      }}
    >
      <DialogContent className="glass-modal-unified overflow-hidden rounded-3xl border-none p-0 text-foreground shadow-2xl sm:max-w-[560px]">
        <DialogDescription className="sr-only">
          {t('canvas.chat.header.file_list_description', 'Browse the files generated in this conversation.')}
        </DialogDescription>
        <div className="p-6 pb-0 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <Folder className="w-5 h-5 text-amber-500" />
            </div>
            <DialogTitle className="text-lg font-bold">
              {t('canvas.chat.header.file_list', 'Files')}
            </DialogTitle>
          </div>
        </div>
        <div className="px-6 pt-4">
          <div className="flex gap-1 rounded-xl border border-[var(--app-border)] bg-[var(--app-control-track)] p-1">
            {HOME_CHAT_FILE_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => onActiveFileTabChange(tab)}
                className={cn(
                  'flex-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors',
                  activeFileTab === tab
                    ? 'bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]'
                    : 'text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
                )}
              >
                {t(`homeHarness.files.tabs.${tab}`, getHomeFileTabFallback(tab))}
                <span className="ml-1 text-[var(--app-foreground-subtle)]">{fileTabCounts[tab]}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[400px] overflow-y-auto px-6 py-4 custom-scrollbar flex flex-col gap-1">
          {visibleSessionFiles.length > 0 ? (
            visibleSessionFiles.map(file => (
              <FileCard
                conversationId={conversationId}
                key={file.path}
                file={file}
                previewUrl={file.previewUrl}
                isDark={isDark}
                onDownload={onDownloadFile}
                onClick={onPreviewWorkspaceFile}
              />
            ))
          ) : (
            <div className="text-center text-sm text-[var(--app-foreground-subtle)] py-12">
              {sessionFiles.length > 0
                ? t('homeHarness.files.emptyTab', 'No files in this category')
                : t('common.no_data', 'No data')}
            </div>
          )}
        </div>
        <div className="h-4" />
      </DialogContent>
    </Dialog>
  )
}
