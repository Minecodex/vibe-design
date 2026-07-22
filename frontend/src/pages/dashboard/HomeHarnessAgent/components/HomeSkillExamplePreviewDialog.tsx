import { useEffect, useMemo, useState } from 'react'
import { Check, Copy, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { agentApi, type HarnessSkillRead } from '@/api/endpoints/agent'
import { getApiBaseUrl } from '@/config/runtimeConfig'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'

import { disableOpenDesignPreviewNavigation } from './homeDesignSystemPreviewUtils'

function injectBaseHref(html: string, baseHref: string): string {
  if (!html) {
    return html
  }
  const baseTag = `<base href="${baseHref}">`
  if (/<base\b/i.test(html)) {
    return html
  }
  if (/<head\b[^>]*>/i.test(html)) {
    return html.replace(/<head\b([^>]*)>/i, `<head$1>${baseTag}`)
  }
  return `${baseTag}${html}`
}

interface HomeSkillExamplePreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  skill: Pick<HarnessSkillRead, 'id'> | null
  skillTitle: string
  examplePrompt: string
  isDark: boolean
}

export function HomeSkillExamplePreviewDialog({
  open,
  onOpenChange,
  skill,
  skillTitle,
  examplePrompt,
  isDark,
}: HomeSkillExamplePreviewDialogProps) {
  const { t } = useTranslation()
  const [previewHtml, setPreviewHtml] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasCopiedPrompt, setHasCopiedPrompt] = useState(false)

  useEffect(() => {
    if (!hasCopiedPrompt) {
      return
    }
    const timer = window.setTimeout(() => setHasCopiedPrompt(false), 1200)
    return () => window.clearTimeout(timer)
  }, [hasCopiedPrompt])

  useEffect(() => {
    if (!open || !skill?.id) {
      setPreviewHtml('')
      setError(null)
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)
    setError(null)
    setPreviewHtml('')

    void agentApi.getHarnessSkillExampleHtml(skill.id)
      .then((response) => {
        if (!cancelled) {
          setPreviewHtml(response.data || '')
        }
      })
      .catch((loadError) => {
        console.error('Failed to load skill example preview', loadError)
        if (!cancelled) {
          setError(t('home.primarySkill.previewLoadFailed', 'Failed to load skill example preview.'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [open, skill?.id, t])

  const previewSrcDoc = useMemo(() => {
    if (!previewHtml) {
      return ''
    }
    const baseHref = `${getApiBaseUrl()}/agent/harness/skills/${encodeURIComponent(skill?.id || '')}/files/`
    return disableOpenDesignPreviewNavigation(injectBaseHref(previewHtml, baseHref))
  }, [previewHtml, skill?.id])

  const promptText = examplePrompt.trim()
  const promptLabel = t('home.primarySkill.examplePromptLabel', '输入内容')

  const handleCopyPrompt = async () => {
    if (!promptText) {
      return
    }
    try {
      await navigator.clipboard.writeText(promptText)
      setHasCopiedPrompt(true)
      toast.success(t('common.copied', 'Copied'))
    } catch (copyError) {
      console.error('Failed to copy skill example prompt', copyError)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(
        'app-floating-panel flex h-[90vh] w-[min(1800px,98vw)] !max-w-[min(1800px,98vw)] flex-col gap-0 overflow-hidden p-0 sm:!max-w-[min(1800px,98vw)]',
      )}>
        <div className={cn(
          'app-divider border-b px-6 py-5',
        )}>
          <DialogTitle className="truncate text-lg font-semibold">
            {skillTitle}
          </DialogTitle>
          <div className={cn(
            'app-card-muted mt-3 flex items-start gap-4 rounded-2xl px-4 py-3',
          )}>
            <div className="min-w-0 flex-1">
              <div className={cn(
                'text-[11px] font-semibold uppercase tracking-[0.24em]',
                isDark ? 'text-zinc-500' : 'text-zinc-500',
              )}>
                {promptLabel}
              </div>
              <div className={cn(
                'mt-2 whitespace-pre-wrap break-words text-sm leading-6',
                isDark ? 'text-zinc-200' : 'text-zinc-800',
              )}>
                {promptText || t('home.primarySkill.examplePromptFallback', 'No example prompt provided.')}
              </div>
            </div>
            <button
              type="button"
              onClick={handleCopyPrompt}
              disabled={!promptText}
              aria-label={t('home.primarySkill.copyExamplePrompt', 'Copy example prompt')}
              className={cn(
                'app-chip inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              {hasCopiedPrompt ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              <span>
                {hasCopiedPrompt
                  ? t('home.primarySkill.copiedExamplePrompt', '已复制')
                  : t('home.primarySkill.copyExamplePromptButton', '复制')}
              </span>
            </button>
          </div>
        </div>
        {isLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            <span className={cn('text-sm', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
              {t('home.primarySkill.loadingPreview', 'Loading skill example...')}
            </span>
          </div>
        ) : error ? (
          <div className="flex flex-1 items-center justify-center px-8 text-center">
            <p className={cn('text-sm', isDark ? 'text-red-300' : 'text-red-600')}>{error}</p>
          </div>
        ) : (
          <div className="min-h-0 flex-1">
            <iframe
              data-testid="home-skill-example-preview-frame"
              title={skillTitle}
              srcDoc={previewSrcDoc}
              sandbox=""
              className="min-h-0 h-full w-full border-0 bg-white"
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
