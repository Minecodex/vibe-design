import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { extractPromptFromImageDataUrl, PromptExtractionResponse } from './lib/api'
import { getPromptExtractorModelLabel } from './lib/modelLabel'
import { loadPromptJob, savePromptJob, StoredPromptJob } from './lib/storage'

type PromptResultMode = 'page' | 'popover'
type PromptLocale = 'zh-CN' | 'en-US'

interface ResultCopywriting {
  title: string
  subtitle: string
  promptLabel: string
  zh: string
  en: string
  copy: string
  copied: string
  retry: string
  loading: string
  missingJob: string
  failed: string
  idle: string
  close: string
}

export interface AnchorPoint {
  x: number
  y: number
}

interface ViewportSize {
  width: number
  height: number
}

interface FloatingSize {
  width: number
  height: number
}

interface PopoverPosition {
  left: number
  top: number
}

export interface PromptResultViewProps {
  initialJob?: StoredPromptJob
  jobId?: string
  mode?: PromptResultMode
  anchorPoint?: AnchorPoint
  onClose?: () => void
  requestPrompt?: (
    imageDataUrl: string,
    locale: PromptLocale,
  ) => Promise<PromptExtractionResponse>
}

const PAGE_MAX_WIDTH = 520
const POPOVER_WIDTH = 440
const POPOVER_MIN_HEIGHT = 260
const EDGE_PADDING = 16
const ANCHOR_GAP = 14

export function queryPromptJobId(): string {
  const params = new URLSearchParams(window.location.search)
  return params.get('jobId') || ''
}

function getCopy(): ResultCopywriting {
  const isZh = navigator.language.toLowerCase().startsWith('zh')

  return isZh
    ? {
        title: '提取提示词',
        subtitle: 'Prompt Extractor',
        promptLabel: '生成结果',
        zh: '中文',
        en: 'English',
        copy: '复制',
        copied: '已复制',
        retry: '重新提取',
        loading: '正在提取提示词...',
        missingJob: '未找到提取任务',
        failed: '提取失败',
        idle: '等待生成提示词',
        close: '关闭',
      }
    : {
        title: 'Prompt Extractor',
        subtitle: '提取提示词',
        promptLabel: 'Generated prompt',
        zh: '中文',
        en: 'English',
        copy: 'Copy',
        copied: 'Copied',
        retry: 'Re-run',
        loading: 'Extracting prompt...',
        missingJob: 'Extraction job was not found',
        failed: 'Extraction failed',
        idle: 'Waiting for prompt generation',
        close: 'Close',
      }
}

function getStatusStyles(hasError: boolean) {
  if (hasError) {
    return {
      color: '#8a2233',
      background: 'rgba(255, 233, 238, 0.92)',
      border: '1px solid rgba(196, 64, 93, 0.2)',
    }
  }

  return {
    color: '#526072',
    background: 'rgba(255, 255, 255, 0.7)',
    border: '1px solid rgba(148, 163, 184, 0.18)',
  }
}

function getWindowHeight(cardHeight: number) {
  const chromeFrameHeight = 88
  const shellPaddingAllowance = 48
  return Math.max(500, Math.min(680, Math.ceil(cardHeight + chromeFrameHeight + shellPaddingAllowance)))
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function getStoredPromptForLocale(job: StoredPromptJob | null | undefined, locale: PromptLocale): string {
  if (!job) {
    return ''
  }
  return job.prompts?.[locale] || (job.locale === locale ? job.prompt || '' : '')
}

function resolveResponseAmountCents(result: PromptExtractionResponse): number | undefined {
  return result.amountCents ?? result.amount
}

export function resolvePopoverPosition(
  anchorPoint: AnchorPoint,
  viewportSize: ViewportSize,
  floatingSize: FloatingSize,
): PopoverPosition {
  const maxLeft = Math.max(EDGE_PADDING, viewportSize.width - floatingSize.width - EDGE_PADDING)
  const maxTop = Math.max(EDGE_PADDING, viewportSize.height - floatingSize.height - EDGE_PADDING)

  const fitsRight = anchorPoint.x + ANCHOR_GAP + floatingSize.width <= viewportSize.width - EDGE_PADDING
  const fitsBelow = anchorPoint.y + ANCHOR_GAP + floatingSize.height <= viewportSize.height - EDGE_PADDING

  const preferredLeft = fitsRight
    ? anchorPoint.x + ANCHOR_GAP
    : anchorPoint.x - floatingSize.width - ANCHOR_GAP
  const preferredTop = fitsBelow
    ? anchorPoint.y + ANCHOR_GAP
    : anchorPoint.y - floatingSize.height - ANCHOR_GAP

  return {
    left: clamp(preferredLeft, EDGE_PADDING, maxLeft),
    top: clamp(preferredTop, EDGE_PADDING, maxTop),
  }
}

function getViewportSize(): ViewportSize {
  return {
    width: window.innerWidth || document.documentElement.clientWidth || 1280,
    height: window.innerHeight || document.documentElement.clientHeight || 720,
  }
}

function getFallbackAnchorPoint(): AnchorPoint {
  const viewport = getViewportSize()
  return {
    x: Math.round(viewport.width / 2) - 120,
    y: Math.round(viewport.height / 2) - 120,
  }
}

export function PromptResultView({
  initialJob,
  jobId = '',
  mode = 'page',
  anchorPoint,
  onClose,
  requestPrompt = extractPromptFromImageDataUrl,
}: PromptResultViewProps) {
  const copy = getCopy()
  const cardRef = useRef<HTMLDivElement | null>(null)
  const [job, setJob] = useState<StoredPromptJob | null>(initialJob ?? null)
  const [locale, setLocale] = useState<PromptLocale>(initialJob?.locale || 'zh-CN')
  const [prompt, setPrompt] = useState(getStoredPromptForLocale(initialJob, initialJob?.locale || 'zh-CN'))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [popoverPosition, setPopoverPosition] = useState<PopoverPosition | null>(null)

  useEffect(() => {
    if (mode !== 'page') {
      return
    }

    const previousBody = {
      margin: document.body.style.margin,
      minHeight: document.body.style.minHeight,
      background: document.body.style.background,
      fontFamily: document.body.style.fontFamily,
      overflow: document.body.style.overflow,
    }
    const previousRoot = {
      margin: document.documentElement.style.margin,
      minHeight: document.documentElement.style.minHeight,
      background: document.documentElement.style.background,
      overflow: document.documentElement.style.overflow,
    }

    document.documentElement.style.margin = '0'
    document.documentElement.style.minHeight = '100%'
    document.documentElement.style.background = '#edf2f8'
    document.documentElement.style.overflow = 'hidden'
    document.body.style.margin = '0'
    document.body.style.minHeight = '100vh'
    document.body.style.background = '#edf2f8'
    document.body.style.overflow = 'hidden'
    document.body.style.fontFamily = '"Plus Jakarta Sans", "Segoe UI", sans-serif'

    return () => {
      document.body.style.margin = previousBody.margin
      document.body.style.minHeight = previousBody.minHeight
      document.body.style.background = previousBody.background
      document.body.style.fontFamily = previousBody.fontFamily
      document.body.style.overflow = previousBody.overflow
      document.documentElement.style.margin = previousRoot.margin
      document.documentElement.style.minHeight = previousRoot.minHeight
      document.documentElement.style.background = previousRoot.background
      document.documentElement.style.overflow = previousRoot.overflow
    }
  }, [mode])

  useEffect(() => {
    if (initialJob || !jobId) {
      return
    }

    void loadPromptJob(jobId).then((storedJob) => {
      if (!storedJob) {
        setError(copy.missingJob)
        return
      }
      setJob(storedJob)
      setLocale(storedJob.locale)
      setPrompt(getStoredPromptForLocale(storedJob, storedJob.locale))
    })
  }, [copy.missingJob, initialJob, jobId])

  useEffect(() => {
    if (!job) {
      return
    }

    const storedPrompt = getStoredPromptForLocale(job, job.locale)
    if (storedPrompt) {
      setPrompt(storedPrompt)
      return
    }

    void handleRequest(job.locale)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id])

  useEffect(() => {
    setCopied(false)
  }, [prompt])

  useEffect(() => {
    if (mode !== 'page') {
      return
    }

    const card = cardRef.current
    if (!card || typeof window.resizeTo !== 'function') {
      return
    }

    const nextHeight = getWindowHeight(card.scrollHeight)
    window.resizeTo(560, nextHeight)
  }, [copied, error, loading, mode, prompt])

  useLayoutEffect(() => {
    if (mode !== 'popover') {
      return
    }

    const card = cardRef.current
    const measuredRect = card?.getBoundingClientRect()
    const measuredSize = {
      width: measuredRect?.width || POPOVER_WIDTH,
      height: Math.max(measuredRect?.height || 0, POPOVER_MIN_HEIGHT),
    }
    const nextPosition = resolvePopoverPosition(
      anchorPoint || getFallbackAnchorPoint(),
      getViewportSize(),
      measuredSize,
    )
    setPopoverPosition(nextPosition)
  }, [anchorPoint, copied, error, loading, mode, prompt])

  useEffect(() => {
    if (mode !== 'popover' || !onClose) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) {
        return
      }

      if (!cardRef.current?.contains(target)) {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    document.addEventListener('mousedown', handlePointerDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('mousedown', handlePointerDown)
    }
  }, [mode, onClose])

  function handleLocaleChange(nextLocale: PromptLocale) {
    const storedPrompt = getStoredPromptForLocale(job, nextLocale)
    setLocale(nextLocale)
    if (storedPrompt) {
      setPrompt(storedPrompt)
      return
    }

    if (job && !loading) {
      void handleRequest(nextLocale)
    }
  }

  async function handleRequest(nextLocale: PromptLocale) {
    if (!job) {
      return
    }

    setLocale(nextLocale)
    setLoading(true)
    setError('')
    try {
      const result = await requestPrompt(job.imageDataUrl, nextLocale)
      const prompts = {
        ...job.prompts,
        ...result.prompts,
      }
      if (!prompts[result.language]) {
        prompts[result.language] = result.prompt
      }
      const nextPrompt = prompts[nextLocale] || prompts[result.language] || result.prompt
      const nextLanguage = prompts[nextLocale] ? nextLocale : result.language
      const amountCents = resolveResponseAmountCents(result)
      const nextJob = {
        ...job,
        locale: nextLanguage,
        prompt: nextPrompt,
        prompts,
        amountCents: amountCents ?? job.amountCents,
        model: result.model,
      }
      setJob(nextJob)
      setPrompt(nextPrompt)
      setLocale(nextLanguage)
      await savePromptJob(nextJob)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : copy.failed)
    } finally {
      setLoading(false)
    }
  }

  async function handleCopy() {
    if (!prompt) {
      return
    }

    await navigator.clipboard.writeText(prompt)
    setCopied(true)
  }

  const statusStyle = getStatusStyles(Boolean(error))
  const cardWidth = mode === 'popover' ? POPOVER_WIDTH : PAGE_MAX_WIDTH
  const shellStyles = mode === 'popover'
    ? {
        position: 'fixed' as const,
        inset: 0,
        zIndex: 2147483647,
        pointerEvents: 'none' as const,
      }
    : {
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        padding: '18px 16px 28px',
        boxSizing: 'border-box' as const,
        background: [
          'radial-gradient(circle at top left, rgba(255,255,255,0.92), rgba(255,255,255,0) 32%)',
          'radial-gradient(circle at 86% 14%, rgba(194, 219, 255, 0.58), rgba(194, 219, 255, 0) 26%)',
          'linear-gradient(180deg, #edf2f8 0%, #f7f9fc 100%)',
        ].join(', '),
      }

  const cardStyles = mode === 'popover'
    ? {
        position: 'fixed' as const,
        left: popoverPosition?.left ?? EDGE_PADDING,
        top: popoverPosition?.top ?? EDGE_PADDING,
        width: `min(${cardWidth}px, calc(100vw - ${EDGE_PADDING * 2}px))`,
        maxHeight: 'min(560px, calc(100vh - 24px))',
        overflow: 'auto' as const,
        pointerEvents: 'auto' as const,
      }
    : {
        width: '100%',
        maxWidth: cardWidth,
      }

  return (
    <main
      data-testid={mode === 'popover' ? 'result-popover-shell' : undefined}
      style={shellStyles}
    >
      <div
        ref={cardRef}
        data-testid="result-card"
        style={{
          borderRadius: 30,
          padding: mode === 'popover' ? '16px 16px 14px' : '18px 18px 16px',
          boxSizing: 'border-box',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.94), rgba(248,250,252,0.9))',
          border: '1px solid rgba(255,255,255,0.72)',
          boxShadow: '0 28px 60px rgba(15, 23, 42, 0.18)',
          backdropFilter: 'blur(20px)',
          ...cardStyles,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 14,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'linear-gradient(135deg, #111827, #2b3446)',
                color: '#fff',
                fontSize: 19,
                fontWeight: 800,
                boxShadow: '0 12px 20px rgba(15, 23, 42, 0.18)',
                flexShrink: 0,
              }}
            >
              提
            </div>

            <div
              style={{
                padding: '7px 10px',
                borderRadius: 999,
                background: 'rgba(15, 23, 42, 0.06)',
                color: '#465569',
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '0.03em',
              }}
            >
              {getPromptExtractorModelLabel(job?.model)}
            </div>
          </div>

          {mode === 'popover' && onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label={copy.close}
              style={{
                width: 36,
                height: 36,
                borderRadius: 12,
                border: '1px solid rgba(148, 163, 184, 0.18)',
                background: 'rgba(255,255,255,0.7)',
                color: '#475569',
                fontSize: 18,
                lineHeight: 1,
                fontWeight: 700,
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              ×
            </button>
          ) : null}
        </div>

        <div style={{ marginBottom: 16 }}>
          <h1 style={{ margin: 0, fontSize: mode === 'popover' ? 24 : 28, lineHeight: 1.1, color: '#0f172a', fontWeight: 800 }}>
            {copy.title}
          </h1>
          <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: 14, lineHeight: 1.6 }}>
            {copy.subtitle}
          </p>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
            marginBottom: 14,
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: 4,
              borderRadius: 999,
              background: 'rgba(15, 23, 42, 0.06)',
              border: '1px solid rgba(148, 163, 184, 0.12)',
            }}
          >
            {[
              { label: copy.zh, value: 'zh-CN' as const },
              { label: copy.en, value: 'en-US' as const },
            ].map((item) => {
              const isActive = locale === item.value
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => handleLocaleChange(item.value)}
                  disabled={loading}
                  style={{
                    height: 34,
                    padding: '0 14px',
                    borderRadius: 999,
                    border: 'none',
                    background: isActive ? 'linear-gradient(135deg, #111827, #293245)' : 'transparent',
                    color: isActive ? '#fff' : '#475569',
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: loading ? 'wait' : 'pointer',
                    boxShadow: isActive ? '0 10px 20px rgba(15, 23, 42, 0.18)' : 'none',
                  }}
                >
                  {item.label}
                </button>
              )
            })}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => void handleRequest(locale)}
              disabled={loading || !job}
              style={{
                height: 36,
                padding: '0 14px',
                borderRadius: 12,
                border: '1px solid rgba(148, 163, 184, 0.2)',
                background: 'rgba(255,255,255,0.7)',
                color: '#0f172a',
                fontSize: 13,
                fontWeight: 700,
                cursor: loading ? 'wait' : 'pointer',
              }}
            >
              {copy.retry}
            </button>
            <button
              type="button"
              onClick={() => void handleCopy()}
              disabled={!prompt}
              style={{
                height: 36,
                padding: '0 14px',
                borderRadius: 12,
                border: 'none',
                background: 'linear-gradient(135deg, #111827, #293245)',
                color: '#fff',
                fontSize: 13,
                fontWeight: 800,
                cursor: prompt ? 'pointer' : 'not-allowed',
                boxShadow: '0 12px 22px rgba(15, 23, 42, 0.18)',
              }}
            >
              {copied ? copy.copied : copy.copy}
            </button>
          </div>
        </div>

        {(loading || error) ? (
          <div
            style={{
              marginBottom: 14,
              padding: '12px 14px',
              borderRadius: 16,
              fontSize: 13,
              lineHeight: 1.5,
              ...statusStyle,
            }}
          >
            {error || copy.loading}
          </div>
        ) : null}

        <section
          style={{
            padding: 16,
            borderRadius: 22,
            background: 'linear-gradient(180deg, rgba(255,255,255,0.82), rgba(243,246,250,0.82))',
            border: '1px solid rgba(255,255,255,0.72)',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.55)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              marginBottom: 12,
            }}
          >
            <span style={{ color: '#0f172a', fontSize: 13, fontWeight: 800 }}>{copy.promptLabel}</span>
            <span style={{ color: '#64748b', fontSize: 12, fontWeight: 600 }}>{locale}</span>
          </div>

          <div
            aria-label="prompt-output"
            style={{
              color: '#172033',
              fontSize: 15,
              lineHeight: 1.72,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              minHeight: prompt ? undefined : 72,
            }}
          >
            {prompt || (loading ? copy.loading : copy.idle)}
          </div>
        </section>

      </div>
    </main>
  )
}

