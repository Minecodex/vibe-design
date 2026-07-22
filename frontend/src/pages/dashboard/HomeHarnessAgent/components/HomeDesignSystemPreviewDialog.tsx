import { useMemo } from 'react'

import {
  agentApi,
  type HarnessDesignSystemRead,
} from '@/api/endpoints/agent'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'

import {
  getDesignSystemDisplayTitle,
} from './homeDesignSystemPreviewUtils'

interface HomeDesignSystemPreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  designSystem: HarnessDesignSystemRead | null
  isDark: boolean
}

export function HomeDesignSystemPreviewDialog({
  open,
  onOpenChange,
  designSystem,
  isDark,
}: HomeDesignSystemPreviewDialogProps) {
  const { t } = useTranslation()
  const previewUrl = useMemo(() => {
    if (!open || !designSystem) {
      return ''
    }
    return agentApi.getHarnessDesignSystemPreviewHtmlUrl(designSystem.id)
  }, [designSystem, open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(
        'app-floating-panel flex h-[90vh] w-[min(1800px,98vw)] !max-w-[min(1800px,98vw)] flex-col gap-0 overflow-hidden p-0 sm:!max-w-[min(1800px,98vw)]',
      )}>
        <div className={cn(
          'app-divider grid items-center gap-4 border-b px-6 py-5 md:grid-cols-[1fr_auto_1fr]',
        )}>
          <div className="min-w-0">
            <DialogTitle className="truncate text-lg font-semibold">
              {designSystem ? getDesignSystemDisplayTitle(designSystem) : t('home.designSystem.label', 'Design System')}
            </DialogTitle>
            <DialogDescription className={cn('mt-1 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
              {designSystem?.description || t('home.designSystem.previewDescription', 'Preview this design system before using it.')}
            </DialogDescription>
          </div>
          <div aria-hidden="true" />
        </div>
        <iframe
          data-testid="home-design-system-preview-frame"
          title={`${designSystem ? getDesignSystemDisplayTitle(designSystem) : t('home.designSystem.label', 'Design System')} ${t('home.designSystem.showcaseTab', '示例')}`}
          src={previewUrl}
          sandbox=""
          className="min-h-0 flex-1 border-0 bg-white"
        />
      </DialogContent>
    </Dialog>
  )
}
