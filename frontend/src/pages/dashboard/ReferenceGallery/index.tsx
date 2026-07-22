import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Pencil, Plus, RotateCcw, Trash2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import {
  referenceGalleryApi,
  type ReferenceImageRead,
  type ReferenceTaxonomyKind,
  type ReferenceTaxonomyRead,
} from '@/api/endpoints/referenceGallery'
import type { AssetRead } from '@/api/endpoints/assets'
import { AssetPreviewModal } from '@/components/project/AssetPreviewModal'
import { Button } from '@/components/ui/button'
import { CachedImage } from '@/components/ui/CachedImage'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuthStore } from '@/store/authStore'

import {
  apiErrorMessage,
  EditReferenceImageDialog,
  imageLabels,
  TaxonomyManager,
  TaxonomySelect,
  UploadReferenceDialog,
} from './components'

const PAGE_SIZE = 40

type ReferenceGalleryTab = 'gallery' | 'category' | 'style' | 'classification'

function toPreviewAssets(images: ReferenceImageRead[]): AssetRead[] {
  return images.map((image) => ({
    id: image.id,
    project_id: 0,
    user_id: 0,
    asset_type: 'image',
    url: image.url,
    created_at: image.created_at,
    updated_at: image.updated_at,
    origin_kind: 'local_upload',
    source_asset_id: null,
    is_favorite: false,
    list_preview_url: image.list_preview_url ?? null,
    list_preview_status: image.list_preview_status ?? null,
  }))
}

export function ReferenceGalleryPage() {
  const { t } = useTranslation()
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'
  const [tab, setTab] = useState<ReferenceGalleryTab>('gallery')
  const [categories, setCategories] = useState<ReferenceTaxonomyRead[]>([])
  const [styles, setStyles] = useState<ReferenceTaxonomyRead[]>([])
  const [classifications, setClassifications] = useState<ReferenceTaxonomyRead[]>([])
  const [images, setImages] = useState<ReferenceImageRead[]>([])
  const [loading, setLoading] = useState(false)
  const [skip, setSkip] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [categoryFilter, setCategoryFilter] = useState<number | null>(null)
  const [styleFilter, setStyleFilter] = useState<number | null>(null)
  const [classificationFilter, setClassificationFilter] = useState<number | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [createTaxonomyKind, setCreateTaxonomyKind] = useState<ReferenceTaxonomyKind | null>(null)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [editingImage, setEditingImage] = useState<ReferenceImageRead | null>(null)
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [preview, setPreview] = useState<{ assets: AssetRead[]; index: number } | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)

  const hasFilters = !!categoryFilter || !!styleFilter || !!classificationFilter

  const loadTaxonomies = useCallback(async () => {
    const [categoryResponse, styleResponse, classificationResponse] = await Promise.all([
      referenceGalleryApi.listCategories(),
      referenceGalleryApi.listStyles(),
      referenceGalleryApi.listClassifications(),
    ])
    setCategories(categoryResponse.data || [])
    setStyles(styleResponse.data || [])
    setClassifications(classificationResponse.data || [])
  }, [])

  const loadImages = useCallback(async (nextSkip: number, replace = false) => {
    setLoading(true)
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
      setLoading(false)
    }
  }, [categoryFilter, classificationFilter, styleFilter, t])

  useEffect(() => {
    void loadTaxonomies().catch((error) => toast.error(apiErrorMessage(error, t('referenceGallery.taxonomy.loadFailed'))))
  }, [loadTaxonomies, t])

  useEffect(() => {
    if (tab !== 'gallery') return
    scrollRef.current?.scrollTo({ top: 0 })
    void loadImages(0, true)
  }, [loadImages, tab])

  useEffect(() => {
    const target = loadMoreRef.current
    const root = scrollRef.current
    if (tab !== 'gallery' || !target || !root || loading || !hasMore) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) void loadImages(skip, false)
    }, { root, rootMargin: '0px 0px 260px 0px' })
    observer.observe(target)
    return () => observer.disconnect()
  }, [hasMore, loadImages, loading, skip, tab])

  const refreshAll = async () => {
    await loadTaxonomies()
    await loadImages(0, true)
  }

  const handleUpload = async (categoryId: number, styleId: number | null, classificationId: number | null) => {
    if (pendingFiles.length === 0) return
    setSubmitting(true)
    try {
      await referenceGalleryApi.uploadImages(pendingFiles, categoryId, styleId, classificationId)
      toast.success(t('referenceGallery.upload.success', { count: pendingFiles.length }))
      setPendingFiles([])
      setUploadOpen(false)
      await refreshAll()
    } catch (error) {
      toast.error(apiErrorMessage(error, t('referenceGallery.upload.failed')))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteImage = async (imageId: number) => {
    try {
      await referenceGalleryApi.deleteImage(imageId)
      toast.success(t('referenceGallery.deleteSuccess'))
      await refreshAll()
    } catch (error) {
      toast.error(apiErrorMessage(error, t('referenceGallery.deleteFailed')))
    }
  }

  const handleUpdateImageTaxonomies = async (categoryId: number, styleId: number | null, classificationId: number | null) => {
    if (!editingImage) return
    setEditSubmitting(true)
    try {
      await referenceGalleryApi.updateImage(editingImage.id, {
        category_id: categoryId,
        style_id: styleId,
        classification_id: classificationId,
      })
      toast.success(t('referenceGallery.editImage.success'))
      setEditingImage(null)
      await refreshAll()
    } catch (error) {
      toast.error(apiErrorMessage(error, t('referenceGallery.editImage.failed')))
    } finally {
      setEditSubmitting(false)
    }
  }

  const previewAssets = useMemo(() => toPreviewAssets(images), [images])
  const currentTaxonomyKind: ReferenceTaxonomyKind | null = tab === 'gallery' ? null : tab

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-12 pb-10 pt-6 text-foreground transition-colors duration-500">
      <Tabs value={tab} onValueChange={(value) => setTab(value as ReferenceGalleryTab)} className="flex min-h-0 flex-1 flex-col">
        <div className="mb-5 flex shrink-0 flex-wrap items-center justify-between gap-3">
          <TabsList className="rounded-xl">
            <TabsTrigger value="gallery">{t('referenceGallery.tabs.gallery')}</TabsTrigger>
            <TabsTrigger value="category">{t('referenceGallery.tabs.categories')}</TabsTrigger>
            <TabsTrigger value="style">{t('referenceGallery.tabs.styles')}</TabsTrigger>
            <TabsTrigger value="classification">{t('referenceGallery.tabs.classifications')}</TabsTrigger>
          </TabsList>
          {tab === 'gallery' && isAdmin ? (
            <Button type="button" className="rounded-xl" onClick={() => setUploadOpen(true)}>
              <Upload className="h-4 w-4" /> {t('referenceGallery.upload.button')}
            </Button>
          ) : currentTaxonomyKind && isAdmin ? (
            <Button type="button" className="rounded-xl" onClick={() => setCreateTaxonomyKind(currentTaxonomyKind)}>
              <Plus className="h-4 w-4" /> {t('referenceGallery.add')}
            </Button>
          ) : null}
        </div>

        <TabsContent value="gallery" className="mt-0 flex min-h-0 flex-1 flex-col">
          <div className="mb-5 flex shrink-0 flex-wrap items-center gap-2">
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

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1">
            {loading && images.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t('common.loading')}
              </div>
            ) : images.length === 0 ? (
              <div className="flex h-64 items-center justify-center rounded-[var(--app-radius-md)] border border-[var(--app-border)] text-sm text-muted-foreground">
                {hasFilters ? t('referenceGallery.noMatched') : t('referenceGallery.empty')}
              </div>
            ) : (
              <div
                className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-7"
                data-testid="reference-gallery-image-grid"
              >
                {images.map((image, index) => (
                  <div
                    key={image.id}
                    className="group flex min-w-0 flex-col overflow-hidden rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-solid)] shadow-[var(--app-shadow-control)] transition-all duration-300 hover:-translate-y-0.5 hover:border-[var(--app-border-strong)] hover:shadow-[var(--app-shadow-panel)]"
                  >
                    <button
                      type="button"
                      className="relative block aspect-[4/3] w-full overflow-hidden bg-muted"
                      onClick={() => setPreview({ assets: previewAssets, index })}
                    >
                      <CachedImage src={image.list_preview_url || image.url} alt={image.name} className="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
                    </button>
                    <div className="flex min-h-[112px] flex-1 flex-col gap-2 p-3">
                      <div className="truncate text-sm font-semibold leading-5" title={image.name}>{image.name || t('referenceGallery.untitled')}</div>
                      <div className="flex min-h-5 flex-wrap gap-1">
                        {imageLabels(image).map((label) => (
                          <span key={label} className="max-w-full truncate rounded-md bg-[var(--app-control)] px-1.5 py-0.5 text-[11px] leading-4 text-muted-foreground">{label}</span>
                        ))}
                      </div>
                      {isAdmin ? (
                        <div className="mt-auto flex justify-end gap-1 border-t border-[var(--app-border)] pt-2">
                          <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setEditingImage(image)}>
                            <Pencil className="h-4 w-4" /> {t('referenceGallery.edit')}
                          </Button>
                          <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive" onClick={() => void handleDeleteImage(image.id)}>
                            <Trash2 className="h-4 w-4" /> {t('referenceGallery.delete')}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {images.length > 0 ? (
              <>
                <div ref={loadMoreRef} className="h-4 w-full" aria-hidden="true" />
                <div className="py-6 text-center text-sm text-muted-foreground">
                  {loading ? t('common.loading') : !hasMore ? t('referenceGallery.allLoaded') : ''}
                </div>
              </>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="category" className="mt-0 min-h-0 flex-1 overflow-y-auto">
          <TaxonomyManager
            kind="category"
            items={categories}
            isAdmin={isAdmin}
            createOpen={createTaxonomyKind === 'category'}
            onCreateOpenChange={(open) => setCreateTaxonomyKind(open ? 'category' : null)}
            onChanged={loadTaxonomies}
          />
        </TabsContent>

        <TabsContent value="style" className="mt-0 min-h-0 flex-1 overflow-y-auto">
          <TaxonomyManager
            kind="style"
            items={styles}
            isAdmin={isAdmin}
            createOpen={createTaxonomyKind === 'style'}
            onCreateOpenChange={(open) => setCreateTaxonomyKind(open ? 'style' : null)}
            onChanged={loadTaxonomies}
          />
        </TabsContent>

        <TabsContent value="classification" className="mt-0 min-h-0 flex-1 overflow-y-auto">
          <TaxonomyManager
            kind="classification"
            items={classifications}
            isAdmin={isAdmin}
            createOpen={createTaxonomyKind === 'classification'}
            onCreateOpenChange={(open) => setCreateTaxonomyKind(open ? 'classification' : null)}
            onChanged={loadTaxonomies}
          />
        </TabsContent>
      </Tabs>

      <UploadReferenceDialog
        open={uploadOpen}
        categories={categories}
        styles={styles}
        classifications={classifications}
        pendingFiles={pendingFiles}
        submitting={submitting}
        onOpenChange={setUploadOpen}
        onFilesChange={setPendingFiles}
        onSubmit={handleUpload}
      />
      <EditReferenceImageDialog
        open={!!editingImage}
        image={editingImage}
        categories={categories}
        styles={styles}
        classifications={classifications}
        submitting={editSubmitting}
        onOpenChange={(open) => {
          if (!open) setEditingImage(null)
        }}
        onSubmit={handleUpdateImageTaxonomies}
      />
      {preview ? (
        <AssetPreviewModal
          assets={preview.assets}
          initialIndex={preview.index}
          onClose={() => setPreview(null)}
        />
      ) : null}
    </div>
  )
}
