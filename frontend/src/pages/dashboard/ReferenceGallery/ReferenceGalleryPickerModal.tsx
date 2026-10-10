import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react'
import { Check, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import {
  referenceGalleryApi,
  type ReferenceImageRead,
  type ReferenceTaxonomyRead,
} from '@/api/endpoints/referenceGallery'
import { Button } from '@/components/ui/button'
import { CachedImage } from '@/components/ui/CachedImage'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { formatApiErrorDetail } from '@/utils/apiErrors'

import type { AssetLibrarySelectedAsset } from '../CanvasPage/AssetLibraryModal'

interface ReferenceGalleryPickerModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isDark: boolean
  selectionMode?: 'single' | 'multiple'
  maxSelection?: number
  onSelect: (assets: AssetLibrarySelectedAsset[]) => void
}

const PAGE_SIZE = 40
const PICKER_MODAL_Z_CLASS = '!z-[2147483647]'
const PICKER_SELECT_CONTENT_STYLE: CSSProperties = {
  pointerEvents: 'auto',
  zIndex: 2147483647,
}
const ALL_VALUE = '__all__'

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return formatApiErrorDetail(detail, fallback)
}

function mapReferenceImageToSelectedAsset(image: ReferenceImageRead): AssetLibrarySelectedAsset {
  return {
    id: image.id,
    url: image.url,
    type: 'image',
    origin_kind: 'local_upload',
    source_asset_id: null,
    name: image.name,
    list_preview_url: image.list_preview_url ?? null,
    source_kind: 'reference_gallery',
  }
}

function TaxonomySelect({
  items,
  value,
  allLabel,
  placeholder,
  onChange,
}: {
  items: ReferenceTaxonomyRead[]
  value: number | null
  allLabel: string
  placeholder: string
  onChange: (value: number | null) => void
}) {
  return (
    <Select
      value={value ? String(value) : ALL_VALUE}
      onValueChange={(next) => onChange(next === ALL_VALUE ? null : Number(next))}
    >
      <SelectTrigger className="h-9 w-[180px] rounded-xl">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent style={PICKER_SELECT_CONTENT_STYLE}>
        <SelectItem value={ALL_VALUE}>{allLabel}</SelectItem>
        {items.map((item) => (
          <SelectItem key={item.id} value={String(item.id)}>
            {item.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function imageLabels(image: ReferenceImageRead): string[] {
  return [
    image.category_name,
    image.style_name || '',
    image.classification_name || '',
  ].filter(Boolean)
}

export function ReferenceGalleryPickerModal({ open, onOpenChange, selectionMode = 'multiple', maxSelection = 0, onSelect }: ReferenceGalleryPickerModalProps) {
  const { t } = useTranslation()
  const [categories, setCategories] = useState<ReferenceTaxonomyRead[]>([])
  const [styles, setStyles] = useState<ReferenceTaxonomyRead[]>([])
  const [classifications, setClassifications] = useState<ReferenceTaxonomyRead[]>([])
  const [images, setImages] = useState<ReferenceImageRead[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [categoryFilter, setCategoryFilter] = useState<number | null>(null)
  const [styleFilter, setStyleFilter] = useState<number | null>(null)
  const [classificationFilter, setClassificationFilter] = useState<number | null>(null)
  const [skip, setSkip] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)

  const hasFilters = !!categoryFilter || !!styleFilter || !!classificationFilter
  const isConfirmDisabled = selectedIds.size === 0

  const loadImages = useCallback(async (nextSkip: number, replace = false) => {
    if (replace) {
      setLoading(true)
    } else {
      setLoadingMore(true)
    }
    try {
      const response = await referenceGalleryApi.listImages({
        category_id: categoryFilter || undefined,
        style_id: styleFilter || undefined,
        classification_id: classificationFilter || undefined,
        skip: nextSkip,
        limit: PAGE_SIZE,
      })
      const nextImages = response.data || []
      setImages((current) => {
        if (replace) return nextImages
        const seen = new Set(current.map((image) => image.id))
        return [...current, ...nextImages.filter((image) => !seen.has(image.id))]
      })
      setHasMore(nextImages.length >= PAGE_SIZE)
      setSkip(nextSkip + nextImages.length)
    } catch (error) {
      toast.error(apiErrorMessage(error, t('referenceGallery.loadFailed')))
    } finally {
      if (replace) {
        setLoading(false)
      } else {
        setLoadingMore(false)
      }
    }
  }, [categoryFilter, classificationFilter, styleFilter, t])

  useEffect(() => {
    if (!open) {
      setImages([])
      setSelectedIds(new Set())
      setSkip(0)
      setHasMore(false)
      return
    }
    Promise.all([
      referenceGalleryApi.listCategories(),
      referenceGalleryApi.listStyles(),
      referenceGalleryApi.listClassifications(),
    ])
      .then(([categoryResponse, styleResponse, classificationResponse]) => {
        setCategories(categoryResponse.data || [])
        setStyles(styleResponse.data || [])
        setClassifications(classificationResponse.data || [])
      })
      .catch((error) => toast.error(apiErrorMessage(error, t('referenceGallery.taxonomy.loadFailed'))))
  }, [open, t])

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => {
      scrollContainerRef.current?.scrollTo?.({ top: 0 })
      setSelectedIds(new Set())
      void loadImages(0, true)
    }, 180)
    return () => window.clearTimeout(timer)
  }, [loadImages, open])

  useEffect(() => {
    const target = loadMoreRef.current
    const scrollRoot = scrollContainerRef.current
    if (!open || !target || !scrollRoot || loading || loadingMore || !hasMore) {
      return
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) void loadImages(skip, false)
    }, {
      root: scrollRoot,
      rootMargin: '0px 0px 260px 0px',
    })
    observer.observe(target)
    return () => observer.disconnect()
  }, [hasMore, loadImages, loading, loadingMore, open, skip])

  const toggleSelect = (image: ReferenceImageRead) => {
    setSelectedIds((current) => {
      if (selectionMode === 'single') {
        return current.has(image.id) ? new Set() : new Set([image.id])
      }
      const next = new Set(current)
      if (next.has(image.id)) {
        next.delete(image.id)
        return next
      }
      if (maxSelection > 0 && next.size >= maxSelection) {
        return next
      }
      next.add(image.id)
      return next
    })
  }

  const handleConfirm = () => {
    const selectedAssets = images
      .filter((image) => selectedIds.has(image.id))
      .map(mapReferenceImageToSelectedAsset)
    onSelect(selectedAssets)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        noDarken
        overlayClassName={PICKER_MODAL_Z_CLASS}
        className={cn(
          'sm:max-w-[1400px] w-[90vw] h-[85vh] flex flex-col p-8 glass-modal-unified !rounded-2xl',
          PICKER_MODAL_Z_CLASS,
          'text-foreground',
        )}
      >
        <div className="mb-2 flex items-center justify-between">
          <div className="text-xl font-medium">{t('referenceGallery.picker.title')}</div>
          <DialogTitle className="sr-only">{t('referenceGallery.picker.title')}</DialogTitle>
          <DialogDescription className="sr-only">
            {t('referenceGallery.picker.description')}
          </DialogDescription>
        </div>

        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <TaxonomySelect
              items={categories}
              value={categoryFilter}
              allLabel={t('referenceGallery.allCategories')}
              placeholder={t('referenceGallery.selectCategory')}
              onChange={setCategoryFilter}
            />
            <TaxonomySelect
              items={styles}
              value={styleFilter}
              allLabel={t('referenceGallery.allStyles')}
              placeholder={t('referenceGallery.selectStyle')}
              onChange={setStyleFilter}
            />
            <TaxonomySelect
              items={classifications}
              value={classificationFilter}
              allLabel={t('referenceGallery.allClassifications')}
              placeholder={t('referenceGallery.selectClassification')}
              onChange={setClassificationFilter}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="rounded-xl"
              disabled={!hasFilters}
              onClick={() => {
                setCategoryFilter(null)
                setStyleFilter(null)
                setClassificationFilter(null)
              }}
            >
              <RotateCcw className="h-4 w-4" /> {t('referenceGallery.reset')}
            </Button>
          </div>
          {maxSelection > 0 ? (
            <div className="text-sm text-muted-foreground">
              {t('referenceGallery.picker.limit', { count: maxSelection })}
            </div>
          ) : null}
        </div>

        <div ref={scrollContainerRef} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1">
          {loading && images.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {t('common.loading')}
            </div>
          ) : images.length === 0 ? (
            <div className="flex h-48 items-center justify-center rounded-[var(--app-radius-md)] border border-[var(--app-border)] text-sm text-muted-foreground">
              {hasFilters ? t('referenceGallery.noMatched') : t('referenceGallery.empty')}
            </div>
          ) : (
            <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
              {images.map((image) => {
                const selected = selectedIds.has(image.id)
                return (
                  <button
                    key={image.id}
                    type="button"
                    onClick={() => toggleSelect(image)}
                    className={cn(
                      'group relative aspect-square w-full overflow-hidden rounded-xl border-2 text-left transition-all',
                      selected
                        ? 'border-[var(--app-primary)] shadow-[0_0_0_3px_var(--app-focus-ring)]'
                        : 'border-[var(--app-border)] bg-[var(--app-surface-muted)] hover:border-[var(--app-border-strong)]',
                    )}
                  >
                    <CachedImage
                      src={image.list_preview_url || image.url}
                      alt={image.name}
                      className="absolute inset-0 h-full w-full object-cover"
                    />
                    <div className={cn(
                      'absolute right-2 top-2 z-10 flex h-5 w-5 items-center justify-center rounded border border-[var(--app-media-border)] transition-colors',
                      selected ? 'bg-[var(--app-primary)]' : 'bg-[var(--app-media-control)] group-hover:bg-[var(--app-media-control-hover)]',
                    )}>
                      {selected ? <Check size={14} color="var(--app-primary-foreground)" /> : null}
                    </div>
                    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-[var(--app-media-overlay)] to-transparent p-3 opacity-0 transition-opacity group-hover:opacity-100">
                      <div className="flex flex-wrap gap-1">
                        {imageLabels(image).map((label) => (
                          <span key={label} className="rounded-md bg-[var(--app-media-control)] px-1.5 py-0.5 text-[11px] text-white backdrop-blur-sm">
                            {label}
                          </span>
                        ))}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}

          {!loading && images.length > 0 ? (
            <>
              <div ref={loadMoreRef} className="h-4 w-full" aria-hidden="true" />
              <div className="py-6 text-center text-sm text-muted-foreground">
                {loadingMore ? t('common.loading') : !hasMore ? t('referenceGallery.allLoaded') : ''}
              </div>
            </>
          ) : null}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-[var(--app-border)] pt-4">
          <div className="text-sm text-muted-foreground">
            {t('referenceGallery.picker.selected', { count: selectedIds.size })}
          </div>
          <Button onClick={handleConfirm} disabled={isConfirmDisabled}>
            {t('common.confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
