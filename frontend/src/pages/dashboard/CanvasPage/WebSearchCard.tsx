import { ChevronDown, ExternalLink, Globe, Image as ImageIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { useCanvasHarnessMediaSource } from './useCanvasHarnessMediaSource'

interface CanvasWebSearchCardProps {
  payload: Record<string, unknown>
  isDark: boolean
  onPreview: (url: string) => void
  conversationId?: string | number | null
}

interface SearchResult {
  title: string
  url?: string
  snippet?: string
  imageUrl?: string
  sourceUrl?: string
  thumbnailUrl?: string
  width?: number
  height?: number
}

interface SearchPayload {
  status: string
  searchType: 'text' | 'image'
  query: string
  message: string
  results: SearchResult[]
}

function getHostnameLabel(url?: string): string | undefined {
  if (!url) {
    return undefined
  }

  try {
    return new URL(url).hostname.replace(/^www\./, '')
  }
  catch {
    return undefined
  }
}

function asString(value: unknown): string | undefined {
  const normalized = String(value ?? '').trim()
  return normalized || undefined
}

function asNumber(value: unknown): number | undefined {
  const normalized = Number(value)
  return Number.isFinite(normalized) && normalized > 0 ? normalized : undefined
}

function normalizePayload(payload: Record<string, unknown>): SearchPayload {
  const resultPayload = payload.result && typeof payload.result === 'object'
    ? payload.result as Record<string, unknown>
    : payload
  const payloadArgs = payload.args && typeof payload.args === 'object'
    ? payload.args as Record<string, unknown>
    : undefined
  const rawResults = Array.isArray(resultPayload.uiResults)
    ? resultPayload.uiResults
    : Array.isArray(resultPayload.ui_results)
      ? resultPayload.ui_results
      : Array.isArray(resultPayload.results)
        ? resultPayload.results
        : Array.isArray(payload.uiResults)
          ? payload.uiResults
          : Array.isArray(payload.ui_results)
            ? payload.ui_results
            : (Array.isArray(payload.results) ? payload.results : [])
  const searchType = String(
    resultPayload.searchType
      ?? resultPayload.search_type
      ?? payload.searchType
      ?? payload.search_type
      ?? 'text',
  ).toLowerCase() === 'image' ? 'image' : 'text'

  return {
    status: String(payload.status ?? resultPayload.status ?? 'completed'),
    searchType,
    query: String(resultPayload.query ?? payload.query ?? payloadArgs?.query ?? ''),
    message: String(resultPayload.message ?? payload.message ?? ''),
    results: rawResults
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map((item) => ({
        title: String(item.title ?? ''),
        url: asString(item.url),
        snippet: asString(item.snippet),
        imageUrl: asString(
          item.localImageUrl
          ?? item.local_image_url
          ?? item.localImagePath
          ?? item.local_image_path
          ?? item.imageUrl
          ?? item.image_url,
        ),
        sourceUrl: asString(item.sourceUrl ?? item.source_url ?? item.url),
        thumbnailUrl: asString(item.thumbnailUrl ?? item.thumbnail_url),
        width: asNumber(item.width),
        height: asNumber(item.height),
      })),
  }
}

function buildImageSearchSubtitle(
  t: (key: string, fallback: string, options?: Record<string, unknown>) => string,
  query: string,
  count: number,
): string {
  if (!query) {
    return t('common.web_search_results_count', `${count} 条结果`, { count })
  }

  return t(
    'common.web_search_image_returned_count',
    `图片搜索 '${query}' 返回了 ${count} 条结果`,
    { query, count },
  )
}

function CanvasSearchImageTile({
  result,
  isDark,
  onPreview,
  conversationId,
}: {
  result: SearchResult
  isDark: boolean
  onPreview: (url: string) => void
  conversationId?: string | number | null
}) {
  const imageUrl = useCanvasHarnessMediaSource(
    conversationId,
    result.imageUrl || result.thumbnailUrl,
  )

  if (!imageUrl) {
    return null
  }

  return (
    <div
      className={cn(
        'app-card group overflow-hidden rounded-[20px] transition-colors hover:border-[var(--app-border-strong)]',
      )}
    >
      <button
        type="button"
        onClick={() => onPreview(imageUrl)}
        className="relative block w-full cursor-zoom-in overflow-hidden bg-transparent text-left"
      >
        <img
          src={imageUrl}
          alt={result.title || 'web search result'}
          className="block aspect-square w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
          loading="lazy"
        />
        <div
          className={cn(
            'pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t px-3 py-2 text-xs opacity-0 transition-opacity group-hover:opacity-100',
            isDark ? 'from-black/70 to-transparent text-white' : 'from-black/55 to-transparent text-white',
          )}
        >
          <span>点击预览</span>
          <ExternalLink className="h-3.5 w-3.5" />
        </div>
      </button>
      <div className="space-y-2 px-3 py-3">
        <div className={cn('line-clamp-2 text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
          {result.title || '图片结果'}
        </div>
        <div className="flex items-center gap-2 text-xs">
          {result.width && result.height ? (
            <span className={cn(isDark ? 'text-zinc-400' : 'text-zinc-500')}>
              {result.width} × {result.height}
            </span>
          ) : null}
          {getHostnameLabel(result.sourceUrl) ? (
            <span
              className={cn(
                'app-chip truncate rounded-full px-2 py-0.5',
              )}
            >
              {getHostnameLabel(result.sourceUrl)}
            </span>
          ) : null}
        </div>
        {result.sourceUrl ? (
          <a
            href={result.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className={cn(
              'inline-flex items-center gap-1 text-xs transition-colors',
              isDark ? 'text-zinc-300 hover:text-white' : 'text-zinc-600 hover:text-zinc-900',
            )}
          >
            查看来源
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>
    </div>
  )
}

function CanvasSearchResultItem({
  result,
  index,
  isDark,
}: {
  result: SearchResult
  index: number
  isDark: boolean
}) {
  const hostname = getHostnameLabel(result.url)

  return (
    <div
      className={cn(
        'app-card rounded-[20px] px-4 py-3 transition-colors hover:border-[var(--app-border-strong)]',
      )}
    >
      {hostname ? (
        <div className={cn('mb-2 text-xs', isDark ? 'text-zinc-500' : 'text-zinc-400')}>
          {hostname}
        </div>
      ) : null}
      <div className={cn('text-sm font-medium leading-6', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
        {result.title || result.url || `结果 ${index + 1}`}
      </div>
      {result.snippet ? (
        <div className={cn('mt-1.5 line-clamp-3 whitespace-pre-wrap text-sm leading-6', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
          {result.snippet}
        </div>
      ) : null}
      {result.url ? (
        <a
          href={result.url}
          target="_blank"
          rel="noreferrer"
          className={cn(
            'mt-3 inline-flex items-center gap-1 text-xs transition-colors',
            isDark ? 'text-zinc-300 hover:text-white' : 'text-zinc-600 hover:text-zinc-900',
          )}
        >
          打开链接
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </div>
  )
}

export function CanvasWebSearchCard({
  payload,
  isDark,
  onPreview,
  conversationId,
}: CanvasWebSearchCardProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const normalized = useMemo(() => normalizePayload(payload), [payload])
  const isImageSearch = normalized.searchType === 'image'
  const statusLabel = normalized.status === 'running' ? '搜索中' : `${normalized.results.length} 条结果`
  const subtitle = isImageSearch && normalized.status !== 'running'
    ? buildImageSearchSubtitle(t, normalized.query, normalized.results.length)
    : normalized.message || (normalized.query ? `查询：${normalized.query}` : '')
  const iconToneClass = 'bg-[var(--app-tint-primary)] text-[var(--app-primary)]'
  const metaToneClass = 'app-chip'

  return (
    <div
      className={cn(
        'app-card max-w-[90%] overflow-hidden rounded-[24px]',
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-start justify-between gap-3 px-4 py-4 text-left"
      >
        <div className="min-w-0 flex flex-1 gap-3">
          <div
            className={cn(
              'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl',
              iconToneClass,
            )}
          >
            {isImageSearch ? (
              <ImageIcon className="h-4 w-4" />
            ) : (
              <Globe className="h-4 w-4" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
                {isImageSearch ? '联网图片搜索' : '联网网页搜索'}
              </div>
              <div className={cn('rounded-full px-2 py-0.5 text-xs', metaToneClass)}>
                {statusLabel}
              </div>
            </div>
            {subtitle ? (
              <div className={cn('mt-1 line-clamp-2 text-sm leading-6', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
                {subtitle}
              </div>
            ) : null}
            {normalized.query ? (
              <div
                className={cn(
                  'mt-2 inline-flex max-w-full items-center rounded-full px-2.5 py-1 text-xs',
                  'app-chip',
                )}
              >
                <span className="truncate">{normalized.query}</span>
              </div>
            ) : null}
          </div>
        </div>
        <ChevronDown
          className={cn(
            'mt-1 h-4 w-4 shrink-0 transition-transform',
            expanded ? 'rotate-180' : 'rotate-0',
            isDark ? 'text-zinc-400' : 'text-zinc-500',
          )}
        />
      </button>

      {expanded ? (
        <div className="app-divider border-t px-4 py-4">
          {normalized.results.length === 0 ? (
            <div className={cn('text-sm', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
              暂无可展示的搜索结果。
            </div>
          ) : isImageSearch ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {normalized.results.map((result, index) => (
                <CanvasSearchImageTile
                  key={`${result.imageUrl || result.thumbnailUrl || result.sourceUrl || result.title}-${index}`}
                  result={result}
                  isDark={isDark}
                  onPreview={onPreview}
                  conversationId={conversationId}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {normalized.results.map((result, index) => (
                <CanvasSearchResultItem
                  key={`${result.url || result.title}-${index}`}
                  result={result}
                  index={index}
                  isDark={isDark}
                />
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
