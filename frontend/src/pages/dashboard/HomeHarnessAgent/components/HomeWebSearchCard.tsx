import { ChevronDown, ExternalLink, Globe, Image as ImageIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'
import { cn } from '@/lib/utils'

import { useHarnessMediaSource } from './useHarnessMediaSource'

interface HomeWebSearchCardProps {
  payload: Record<string, any>
  isDark: boolean
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

function asString(value: unknown): string | undefined {
  const normalized = String(value ?? '').trim()
  return normalized || undefined
}

function asNumber(value: unknown): number | undefined {
  const normalized = Number(value)
  return Number.isFinite(normalized) && normalized > 0 ? normalized : undefined
}

function normalizePayload(payload: Record<string, any>): SearchPayload {
  const resultPayload = payload.result && typeof payload.result === 'object'
    ? payload.result as Record<string, any>
    : payload
  const rawResults = Array.isArray(resultPayload.results)
    ? resultPayload.results
    : Array.isArray(resultPayload.uiResults)
      ? resultPayload.uiResults
      : Array.isArray(resultPayload.ui_results)
        ? resultPayload.ui_results
        : (Array.isArray(payload.results)
            ? payload.results
            : Array.isArray(payload.uiResults)
              ? payload.uiResults
              : (Array.isArray(payload.ui_results) ? payload.ui_results : []))
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
    query: String(resultPayload.query ?? payload.query ?? ''),
    message: String(resultPayload.message ?? payload.message ?? ''),
    results: rawResults
      .filter((item): item is Record<string, any> => !!item && typeof item === 'object')
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

function HomeSearchImageTile({
  conversationId,
  result,
  isDark,
  onPreview,
  sourceLabel,
}: {
  conversationId?: string | number | null
  result: SearchResult
  isDark: boolean
  onPreview: (imageUrl: string, alt: string) => void
  sourceLabel: string
}) {
  const resolvedPrimaryUrl = useHarnessMediaSource(conversationId, result.imageUrl, { preferPreviewUrl: true })
  const resolvedThumbnailUrl = useHarnessMediaSource(conversationId, result.thumbnailUrl, { preferPreviewUrl: true })
  const displayUrl = resolvedPrimaryUrl || resolvedThumbnailUrl || result.imageUrl || result.thumbnailUrl

  if (!displayUrl) {
    return null
  }

  return (
    <div
      className={cn(
        'app-card overflow-hidden rounded-2xl',
      )}
    >
      <button
        type="button"
        onClick={() => onPreview(displayUrl, result.title || 'web search result')}
        className="block w-full cursor-zoom-in"
      >
        <img
          src={displayUrl}
          alt={result.title || 'web search result'}
          className="block aspect-square w-full object-cover"
          loading="lazy"
        />
      </button>
      <div className="space-y-2 px-3 py-3">
        <div className={cn('line-clamp-2 text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
          {result.title || '图片结果'}
        </div>
        {result.width && result.height ? (
          <div className={cn('text-xs', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
            {result.width} × {result.height}
          </div>
        ) : null}
        {result.sourceUrl ? (
          <a
            href={result.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className={cn(
              'inline-flex items-center gap-1 text-xs',
              isDark ? 'text-zinc-300 hover:text-white' : 'text-zinc-600 hover:text-zinc-900',
            )}
          >
            {sourceLabel}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>
    </div>
  )
}

export function HomeWebSearchCard({ payload, isDark, conversationId }: HomeWebSearchCardProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null)
  const normalized = useMemo(() => normalizePayload(payload), [payload])
  const isImageSearch = normalized.searchType === 'image'
  const sourceLabel = t('common.data_source', '数据来源')
  const statusLabel = normalized.status === 'running' ? '搜索中' : `${normalized.results.length} 条结果`
  const subtitle = isImageSearch && normalized.status !== 'running'
    ? buildImageSearchSubtitle(t, normalized.query, normalized.results.length)
    : normalized.message || (normalized.query ? `查询：${normalized.query}` : '')

  return (
    <div
      className={cn(
        'app-card max-w-[90%] overflow-hidden rounded-2xl',
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {isImageSearch ? (
              <ImageIcon className={cn('h-4 w-4', isDark ? 'text-zinc-300' : 'text-zinc-600')} />
            ) : (
              <Globe className={cn('h-4 w-4', isDark ? 'text-zinc-300' : 'text-zinc-600')} />
            )}
            <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
              {isImageSearch ? '联网图片搜索' : '联网网页搜索'}
            </div>
            <div className={cn('text-xs', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
              {statusLabel}
            </div>
          </div>
          {subtitle ? (
            <div className={cn('mt-1 line-clamp-2 text-sm', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
              {subtitle}
            </div>
          ) : null}
        </div>
        <ChevronDown
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0 transition-transform',
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
                <HomeSearchImageTile
                  key={`${result.imageUrl || result.thumbnailUrl || result.sourceUrl || result.title}-${index}`}
                  conversationId={conversationId}
                  result={result}
                  isDark={isDark}
                  onPreview={(src, alt) => setPreviewImage({ src, alt })}
                  sourceLabel={sourceLabel}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {normalized.results.map((result, index) => (
                <div
                  key={`${result.url || result.title}-${index}`}
                  className={cn(
                    'app-card-muted rounded-2xl px-3 py-3',
                  )}
                >
                  <div className={cn('text-sm font-medium', isDark ? 'text-zinc-100' : 'text-zinc-900')}>
                    {result.title || result.url || `结果 ${index + 1}`}
                  </div>
                  {result.snippet ? (
                    <div className={cn('mt-1 whitespace-pre-wrap text-sm', isDark ? 'text-zinc-300' : 'text-zinc-600')}>
                      {result.snippet}
                    </div>
                  ) : null}
                  {result.url ? (
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <a
                        href={result.url}
                        target="_blank"
                        rel="noreferrer"
                        className={cn(
                          'inline-flex items-center gap-1 text-xs',
                          isDark ? 'text-zinc-300 hover:text-white' : 'text-zinc-600 hover:text-zinc-900',
                        )}
                      >
                        {sourceLabel}
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      <ImagePreviewDialog
        open={!!previewImage}
        onOpenChange={(open) => !open && setPreviewImage(null)}
        src={previewImage?.src || null}
        alt={previewImage?.alt || 'Web search image preview'}
        title={previewImage?.alt || 'Web search image preview'}
        imageClassName="rounded-2xl"
        downloadUrl={previewImage?.src || null}
      />
    </div>
  )
}
