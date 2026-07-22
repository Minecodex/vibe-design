import * as React from 'react'
import { Check, Image as ImageIcon, Images, Loader2, PackageCheck, Plus, Trash2, Upload, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import {
  agentApi,
  isHarnessWorkspaceRelativePath,
  normalizeHarnessWorkspacePath,
  resolveHarnessWorkspaceUrl,
  type PendingInteraction,
} from '@/api/endpoints/agent'
import { referenceGalleryApi, type ReferenceTaxonomyRead } from '@/api/endpoints/referenceGallery'
import { Button } from '@/components/ui/button'
import { CachedImage } from '@/components/ui/CachedImage'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { getImageUrl } from '@/utils/imageUrl'

const ECOMMERCE_GENERATION_OPTIONS_KIND = 'ecommerce_generation_options'

export const ECOMMERCE_INTERACTION_KINDS = new Set([
  ECOMMERCE_GENERATION_OPTIONS_KIND,
])

export type EcommerceReferenceImageSource = 'asset_library' | 'reference_gallery'
export type EcommerceReferenceImageRequestOptions = { maxSelection?: number }

type ReferenceSectionKey = 'background' | 'model' | 'otherMain'

type EcommerceInteractionCardProps = {
  interaction: PendingInteraction
  disabled?: boolean
  isSubmitting?: boolean
  conversationId?: string | number | null
  onPreviewImage?: (url: string) => void
  onRequestReferenceImages?: (
    source: EcommerceReferenceImageSource,
    onSelect: (urls: string[]) => void,
    options?: EcommerceReferenceImageRequestOptions,
  ) => void
  onUploadReferenceImage?: (file: File) => Promise<string | null | undefined>
  maxReferenceImages?: number
  onRespond: (
    requestId: string,
    answer: string,
    displayLabel?: string,
    answers?: Record<string, any>,
  ) => void | Promise<void>
}

function getValue(source: Record<string, any>, ...keys: string[]): any {
  for (const key of keys) {
    const value = source[key]
    if (value !== undefined && value !== null) {
      return value
    }
  }
  return undefined
}

function numberValue(source: Record<string, any>, fallback: number, ...keys: string[]): number {
  const raw = getValue(source, ...keys)
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : fallback
}

function stringListValue(source: Record<string, any>, ...keys: string[]): string[] {
  const raw = getValue(source, ...keys)
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map((item) => String(item ?? '').trim()).filter(Boolean)
}

function isSubmitted(interaction: PendingInteraction): boolean {
  return String(interaction.status || '').trim() === 'submitted'
}

function submittedAnswersValue(source: Record<string, any>): Record<string, any> {
  const answers = source.answers
  return answers && typeof answers === 'object' && !Array.isArray(answers)
    ? answers as Record<string, any>
    : {}
}

function booleanValue(source: Record<string, any>, fallback: boolean, ...keys: string[]): boolean {
  const raw = getValue(source, ...keys)
  if (typeof raw === 'boolean') {
    return raw
  }
  if (typeof raw === 'number') {
    return raw !== 0
  }
  const text = String(raw ?? '').trim().toLowerCase()
  if (['true', '1', 'yes', 'on'].includes(text)) {
    return true
  }
  if (['false', '0', 'no', 'off'].includes(text)) {
    return false
  }
  return fallback
}

function handleNestedScrollBoundaryWheel(event: React.WheelEvent<HTMLElement>) {
  if (event.ctrlKey) {
    return
  }
  const target = event.currentTarget
  const deltaY = event.deltaY
  if (!deltaY) {
    return
  }
  const maxScrollTop = target.scrollHeight - target.clientHeight
  if (maxScrollTop <= 0) {
    return
  }
  const isAtTop = target.scrollTop <= 0
  const isAtBottom = target.scrollTop >= maxScrollTop - 1
  const shouldHandOff = (deltaY < 0 && isAtTop) || (deltaY > 0 && isAtBottom)
  if (!shouldHandOff) {
    return
  }
  const scrollRoot = target.closest('[data-chat-message-scroll-root="true"]') as HTMLElement | null
  if (!scrollRoot) {
    return
  }
  event.preventDefault()
  event.stopPropagation()
  scrollRoot.scrollTop += deltaY
}

function uniqueImageUrls(urls: string[]): string[] {
  return Array.from(new Set(urls.map((url) => String(url || '').trim()).filter(Boolean)))
}

function isDirectDisplayUrl(url: string): boolean {
  return (
    url.startsWith('http://')
    || url.startsWith('https://')
    || url.startsWith('data:')
    || url.startsWith('blob:')
  )
}

function isArtifactRef(url: string): boolean {
  return /^artifact_ref:[A-Za-z0-9_-]+$/.test(url.trim())
}

function normalizeUploadPreviewUrl(url: string): string | undefined {
  const raw = url.trim()
  if (!raw) {
    return undefined
  }
  if (isDirectDisplayUrl(raw)) {
    return raw
  }
  if (raw.startsWith('/api/v1/uploads/') || raw.startsWith('api/v1/uploads/')) {
    const normalized = raw.startsWith('/') ? raw : `/${raw}`
    return getImageUrl(normalized)
  }
  if (raw.startsWith('/uploads/') || raw.startsWith('uploads/')) {
    return getImageUrl(raw.startsWith('/') ? `/api/v1${raw}` : `/api/v1/${raw}`)
  }
  if (raw.startsWith('/')) {
    return getImageUrl(raw)
  }
  return undefined
}

function resolveArtifactResultUrl(snapshot: Record<string, any> | null | undefined): string | undefined {
  if (!snapshot || typeof snapshot !== 'object') {
    return undefined
  }
  const directUrl = String(snapshot.result_url || snapshot.resultUrl || '').trim()
  if (directUrl) {
    return directUrl
  }
  const resultUrls = Array.isArray(snapshot.result_urls)
    ? snapshot.result_urls
    : (Array.isArray(snapshot.resultUrls) ? snapshot.resultUrls : [])
  const firstResultUrl = String(resultUrls[0] || '').trim()
  if (firstResultUrl) {
    return firstResultUrl
  }
  const plannedResultUrl = String(snapshot.planned_result_url || snapshot.plannedResultUrl || '').trim()
  if (plannedResultUrl) {
    return plannedResultUrl
  }
  const artifact = snapshot.artifact && typeof snapshot.artifact === 'object'
    ? snapshot.artifact as Record<string, any>
    : {}
  const baseDir = String(artifact.base_dir || artifact.baseDir || '').trim()
  const relativePath = String(artifact.relative_path || artifact.relativePath || '').trim()
  if (relativePath && (!baseDir || baseDir === 'FILES_DIR')) {
    return relativePath
  }
  return String(artifact.absolute_path || artifact.absolutePath || '').trim() || undefined
}

async function resolveEcommercePreviewUrl(
  sourceUrl: string,
  conversationId?: string | number | null,
): Promise<string | undefined> {
  const uploadUrl = normalizeUploadPreviewUrl(sourceUrl)
  if (uploadUrl) {
    return uploadUrl
  }
  if (isArtifactRef(sourceUrl)) {
    if (!conversationId) {
      return undefined
    }
    const response = await agentApi.getHarnessGenerationArtifactTask(String(conversationId), sourceUrl)
    const resultUrl = resolveArtifactResultUrl(response.data)
    return resultUrl ? resolveEcommercePreviewUrl(resultUrl, conversationId) : undefined
  }
  if (isHarnessWorkspaceRelativePath(sourceUrl) && !conversationId) {
    return undefined
  }
  if (!conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
    return resolveHarnessWorkspaceUrl(conversationId, sourceUrl) || sourceUrl
  }
  const { preview_token } = await agentApi.createWorkspacePreviewToken(String(conversationId))
  return agentApi.getWorkspacePreviewFileUrl(
    String(conversationId),
    normalizeHarnessWorkspacePath(sourceUrl),
    preview_token,
    { width: 256 },
  )
}

async function resolveEcommercePreviewTargetUrl(
  sourceUrl: string,
  conversationId?: string | number | null,
): Promise<string | undefined> {
  if (!isArtifactRef(sourceUrl)) {
    return sourceUrl
  }
  if (!conversationId) {
    return undefined
  }
  const response = await agentApi.getHarnessGenerationArtifactTask(String(conversationId), sourceUrl)
  const resultUrl = resolveArtifactResultUrl(response.data)
  if (!resultUrl) {
    return undefined
  }
  return isArtifactRef(resultUrl)
    ? resolveEcommercePreviewTargetUrl(resultUrl, conversationId)
    : resultUrl
}

function useEcommercePreviewUrl(
  sourceUrl: string,
  conversationId?: string | number | null,
): string | undefined {
  const initialUrl = React.useMemo(() => {
    const uploadUrl = normalizeUploadPreviewUrl(sourceUrl)
    if (uploadUrl) {
      return uploadUrl
    }
    if (isArtifactRef(sourceUrl)) {
      return undefined
    }
    if (isHarnessWorkspaceRelativePath(sourceUrl) && !conversationId) {
      return undefined
    }
    if (!conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
      return resolveHarnessWorkspaceUrl(conversationId, sourceUrl) || sourceUrl
    }
    return undefined
  }, [conversationId, sourceUrl])
  const [resolvedUrl, setResolvedUrl] = React.useState<string | undefined>(initialUrl)

  React.useEffect(() => {
    const uploadUrl = normalizeUploadPreviewUrl(sourceUrl)
    if (uploadUrl) {
      setResolvedUrl(uploadUrl)
      return
    }
    if (isArtifactRef(sourceUrl)) {
      if (!conversationId) {
        setResolvedUrl(undefined)
        return
      }
      let active = true
      setResolvedUrl(undefined)
      resolveEcommercePreviewUrl(sourceUrl, conversationId)
        .then((displayUrl) => {
          if (active) {
            setResolvedUrl(displayUrl)
          }
        })
        .catch(() => {
          if (active) {
            setResolvedUrl(undefined)
          }
        })
      return () => {
        active = false
      }
    }
    if (isHarnessWorkspaceRelativePath(sourceUrl) && !conversationId) {
      setResolvedUrl(undefined)
      return
    }
    if (!conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
      setResolvedUrl(resolveHarnessWorkspaceUrl(conversationId, sourceUrl) || sourceUrl)
      return
    }

    let active = true
    const normalizedPath = normalizeHarnessWorkspacePath(sourceUrl)
    setResolvedUrl(undefined)
    agentApi.createWorkspacePreviewToken(String(conversationId))
      .then(({ preview_token }) => {
        if (!active) {
          return
        }
        setResolvedUrl(agentApi.getWorkspacePreviewFileUrl(
          String(conversationId),
          normalizedPath,
          preview_token,
          { width: 256 },
        ))
      })
      .catch(() => {
        if (active) {
          setResolvedUrl(resolveHarnessWorkspaceUrl(conversationId, sourceUrl) || sourceUrl)
        }
      })
    return () => {
      active = false
    }
  }, [conversationId, sourceUrl])

  return resolvedUrl
}

function clampGenerationCount(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min
  }
  return Math.min(Math.max(Math.round(value), min), max)
}

function taxonomyPayload(taxonomy: ReferenceTaxonomyRead | undefined, prefix: 'category' | 'style') {
  return {
    [`${prefix}_id`]: taxonomy?.id ?? null,
    [`${prefix}_name`]: taxonomy?.name ?? '',
    [`${prefix}_prompt`]: taxonomy?.prompt ?? '',
  }
}

function totalReferenceCount(sections: Record<ReferenceSectionKey, string[]>): number {
  return sections.background.length + sections.model.length + sections.otherMain.length
}

function CardShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="w-full max-w-[720px] rounded-lg border border-border bg-card p-4 text-card-foreground shadow-sm">
      <div className="mb-4 flex items-start gap-2">
        <div className="mt-0.5 rounded-md border border-border bg-muted p-1.5 text-muted-foreground">
          <PackageCheck className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-5">{title}</div>
          {subtitle ? <div className="mt-0.5 text-xs leading-5 text-muted-foreground">{subtitle}</div> : null}
        </div>
      </div>
      {children}
    </div>
  )
}

function SubmittedNotice() {
  const { t } = useTranslation()
  return (
    <div className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-muted px-2.5 py-1.5 text-xs text-muted-foreground">
      <Check className="h-3.5 w-3.5" aria-hidden="true" />
      {t('agent.ecommerceInteraction.submitted')}
    </div>
  )
}

function TaxonomySelect({
  id,
  label,
  placeholder,
  items,
  value,
  disabled,
  loading,
  onValueChange,
}: {
  id: string
  label: string
  placeholder: string
  items: ReferenceTaxonomyRead[]
  value: string
  disabled?: boolean
  loading?: boolean
  onValueChange: (value: string) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </Label>
      <Select value={value} onValueChange={onValueChange} disabled={disabled || loading}>
        <SelectTrigger id={id} className="h-9 w-full">
          <SelectValue placeholder={loading ? `${placeholder}...` : placeholder} />
        </SelectTrigger>
        <SelectContent position="popper" className="z-[2147483647]">
          {items.map((item) => (
            <SelectItem key={item.id} value={String(item.id)}>
              {item.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function ToggleRow({
  label,
  checked,
  disabled,
  onCheckedChange,
}: {
  label: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/30 px-3 py-2">
      <span className="min-w-0 text-sm leading-5">{label}</span>
      <Switch checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} aria-label={label} />
    </div>
  )
}

function EditableReferenceImageItem({
  url,
  index,
  disabled,
  conversationId,
  onPreviewImage,
  onRemove,
}: {
  url: string
  index: number
  disabled: boolean
  conversationId?: string | number | null
  onPreviewImage?: EcommerceInteractionCardProps['onPreviewImage']
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const displayUrl = useEcommercePreviewUrl(url, conversationId)
  const alt = t('agent.ecommerceInteraction.imageAlt', { index: index + 1 })
  const handlePreview = React.useCallback(() => {
    if (!onPreviewImage) {
      return
    }
    void resolveEcommercePreviewTargetUrl(url, conversationId)
      .then((targetUrl) => onPreviewImage(targetUrl || displayUrl || url))
      .catch(() => onPreviewImage(displayUrl || url))
  }, [conversationId, displayUrl, onPreviewImage, url])
  return (
    <div className="group relative aspect-square overflow-hidden rounded-md border border-border bg-muted">
      <button
        type="button"
        className={cn('h-full w-full', onPreviewImage ? 'cursor-zoom-in' : 'cursor-default')}
        disabled={!onPreviewImage}
        onClick={handlePreview}
        aria-label={alt}
      >
        {displayUrl ? (
          <CachedImage
            src={displayUrl}
            alt={alt}
            className="h-full w-full object-cover"
            loading="lazy"
            draggable={false}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <ImageIcon className="h-5 w-5" aria-hidden="true" />
          </div>
        )}
      </button>
      <Button
        type="button"
        variant="secondary"
        size="icon-sm"
        onClick={onRemove}
        disabled={disabled}
        aria-label={t('agent.ecommerceInteraction.actions.removeReference')}
        className="absolute right-1.5 top-1.5 h-7 w-7 rounded-full bg-background/90 p-0 opacity-0 shadow-sm transition-opacity hover:bg-background group-hover:opacity-100 focus-visible:opacity-100"
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
    </div>
  )
}

function ReferenceImageSection({
  label,
  urls,
  setUrls,
  disabled,
  conversationId,
  onRequestReferenceImages,
  onUploadReferenceImage,
  maxReferenceImages,
  usedReferenceCount,
  onPreviewImage,
}: {
  label: string
  urls: string[]
  setUrls: React.Dispatch<React.SetStateAction<string[]>>
  disabled: boolean
  conversationId?: string | number | null
  onRequestReferenceImages?: EcommerceInteractionCardProps['onRequestReferenceImages']
  onUploadReferenceImage?: EcommerceInteractionCardProps['onUploadReferenceImage']
  maxReferenceImages?: number
  usedReferenceCount: number
  onPreviewImage?: EcommerceInteractionCardProps['onPreviewImage']
}) {
  const { t } = useTranslation()
  const fileInputRef = React.useRef<HTMLInputElement | null>(null)
  const [isUploading, setIsUploading] = React.useState(false)
  const resolvedLimit = typeof maxReferenceImages === 'number' ? Math.max(0, maxReferenceImages) : undefined
  const remainingSlots = resolvedLimit !== undefined ? Math.max(0, resolvedLimit - usedReferenceCount) : Number.POSITIVE_INFINITY
  const canAddMore = !disabled && remainingSlots > 0
  const canUseLocalUpload = canAddMore && !!onUploadReferenceImage && !isUploading

  const appendReferences = React.useCallback((next: string[]) => {
    const normalizedNext = uniqueImageUrls(next)
    if (!normalizedNext.length) {
      return
    }
    setUrls((current) => {
      const currentUnique = uniqueImageUrls(current)
      const allowedAdditional = resolvedLimit === undefined
        ? normalizedNext.length
        : Math.max(0, resolvedLimit - usedReferenceCount)
      const merged = uniqueImageUrls([...currentUnique, ...normalizedNext]).slice(0, currentUnique.length + allowedAdditional)
      if (resolvedLimit !== undefined && normalizedNext.length > allowedAdditional) {
        toast.info(t('agent.ecommerceInteraction.references.limitReached', { count: resolvedLimit }))
      }
      return merged
    })
  }, [resolvedLimit, setUrls, t, usedReferenceCount])

  const requestLibraryReferences = (source: EcommerceReferenceImageSource) => {
    if (!canAddMore || !onRequestReferenceImages) {
      return
    }
    onRequestReferenceImages(
      source,
      appendReferences,
      { maxSelection: Number.isFinite(remainingSlots) ? remainingSlots : undefined },
    )
  }

  const handleLocalFilesSelected = async (files: FileList | null) => {
    if (!files || !onUploadReferenceImage || !canAddMore) {
      return
    }
    const selectedFiles = Array.from(files).filter((file) => file.type.startsWith('image/'))
    const allowedFiles = Number.isFinite(remainingSlots)
      ? selectedFiles.slice(0, remainingSlots)
      : selectedFiles
    if (!allowedFiles.length) {
      return
    }
    setIsUploading(true)
    try {
      const uploadedUrls: string[] = []
      for (const file of allowedFiles) {
        const uploadedUrl = await onUploadReferenceImage(file)
        if (uploadedUrl) {
          uploadedUrls.push(uploadedUrl)
        }
      }
      appendReferences(uploadedUrls)
    } catch {
      toast.error(t('agent.ecommerceInteraction.references.uploadFailed'))
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-background/40 p-3" data-testid={`ecommerce-reference-section-${label}`}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple={resolvedLimit === undefined || remainingSlots > 1}
        className="hidden"
        data-testid="ecommerce-reference-local-upload-input"
        onChange={(event) => {
          void handleLocalFilesSelected(event.target.files)
        }}
      />
      <div
        className="grid max-h-[360px] grid-cols-3 gap-2 overflow-y-auto pr-1 sm:grid-cols-4"
        data-testid="ecommerce-reference-grid"
        onWheel={handleNestedScrollBoundaryWheel}
      >
        {urls.map((url, index) => (
          <EditableReferenceImageItem
            key={`${url}-${index}`}
            url={url}
            index={index}
            disabled={disabled}
            conversationId={conversationId}
            onPreviewImage={onPreviewImage}
            onRemove={() => setUrls((current) => current.filter((_item, itemIndex) => itemIndex !== index))}
          />
        ))}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              disabled={!canAddMore || isUploading}
              className={cn(
                'flex aspect-square min-h-[76px] cursor-pointer flex-col items-center justify-center gap-1.5 rounded-md border border-dashed text-xs transition-colors',
                canAddMore && !isUploading
                  ? 'border-border bg-muted/40 text-muted-foreground hover:border-primary/40 hover:bg-muted'
                  : 'cursor-not-allowed border-border/60 bg-muted/20 text-muted-foreground/50',
              )}
              aria-label={t('agent.ecommerceInteraction.actions.addReference')}
            >
              {isUploading ? (
                <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
              ) : (
                <Plus className="h-5 w-5" aria-hidden="true" />
              )}
              <span className="max-w-full px-1 text-center leading-4">
                {isUploading
                  ? t('agent.ecommerceInteraction.references.uploading')
                  : t('agent.ecommerceInteraction.references.addCard')}
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" sideOffset={8} className="z-[2147483647] w-44">
            <DropdownMenuItem
              disabled={!canUseLocalUpload}
              onSelect={() => fileInputRef.current?.click()}
            >
              <Upload className="h-4 w-4" aria-hidden="true" />
              {t('agent.ecommerceInteraction.references.localUpload')}
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!canAddMore || !onRequestReferenceImages}
              onSelect={() => requestLibraryReferences('asset_library')}
            >
              <ImageIcon className="h-4 w-4" aria-hidden="true" />
              {t('agent.ecommerceInteraction.actions.pickFromAssetLibrary')}
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!canAddMore || !onRequestReferenceImages}
              onSelect={() => requestLibraryReferences('reference_gallery')}
            >
              <Images className="h-4 w-4" aria-hidden="true" />
              {t('agent.ecommerceInteraction.actions.pickFromReferenceGallery')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {resolvedLimit !== undefined ? (
        <div className="text-[11px] leading-4 text-muted-foreground">
          {t('agent.ecommerceInteraction.references.limitHint', {
            current: usedReferenceCount,
            count: resolvedLimit,
          })}
        </div>
      ) : null}
    </div>
  )
}

export function isEcommerceInteractionKind(kind?: string | null): boolean {
  return ECOMMERCE_INTERACTION_KINDS.has(String(kind || '').trim())
}

export function EcommerceInteractionCard({
  interaction,
  disabled = false,
  isSubmitting = false,
  conversationId,
  onRequestReferenceImages,
  onUploadReferenceImage,
  maxReferenceImages,
  onPreviewImage,
  onRespond,
}: EcommerceInteractionCardProps) {
  const { t } = useTranslation()
  const requestId = String(interaction.request_id || interaction.requestId || '').trim()
  const kind = String(interaction.kind || '').trim()
  const submitted = isSubmitted(interaction)
  const isLocked = disabled || submitted || isSubmitting
  const source = interaction as Record<string, any>
  const initialAnswers = submittedAnswersValue(source)
  const defaults = (source.defaults && typeof source.defaults === 'object') ? source.defaults as Record<string, any> : {}
  const minCount = numberValue(defaults, 1, 'generation_count_min', 'generationCountMin')
  const maxCount = numberValue(defaults, 6, 'generation_count_max', 'generationCountMax')
  const defaultCount = clampGenerationCount(
    numberValue(defaults, 4, 'generation_count', 'generationCount'),
    minCount,
    maxCount,
  )
  const [categories, setCategories] = React.useState<ReferenceTaxonomyRead[]>([])
  const [styles, setStyles] = React.useState<ReferenceTaxonomyRead[]>([])
  const [taxonomiesLoading, setTaxonomiesLoading] = React.useState(false)
  const [selectedCategoryId, setSelectedCategoryId] = React.useState(() => String(initialAnswers.category_id ?? ''))
  const [selectedStyleId, setSelectedStyleId] = React.useState(() => String(initialAnswers.style_id ?? ''))
  const [enableBackgroundReference, setEnableBackgroundReference] = React.useState(() => booleanValue(initialAnswers, false, 'enable_background_reference'))
  const [enableModelReference, setEnableModelReference] = React.useState(() => booleanValue(initialAnswers, false, 'enable_model_reference'))
  const [enableOtherMainImageReference, setEnableOtherMainImageReference] = React.useState(() => booleanValue(initialAnswers, false, 'enable_other_main_image_reference'))
  const [generationCount, setGenerationCount] = React.useState(() => clampGenerationCount(
    numberValue(initialAnswers, defaultCount, 'generation_count', 'generationCount'),
    minCount,
    maxCount,
  ))
  const [backgroundReferenceUrls, setBackgroundReferenceUrls] = React.useState<string[]>(() => stringListValue(initialAnswers, 'background_reference_image_urls'))
  const [modelReferenceUrls, setModelReferenceUrls] = React.useState<string[]>(() => stringListValue(initialAnswers, 'model_reference_image_urls'))
  const [otherMainReferenceUrls, setOtherMainReferenceUrls] = React.useState<string[]>(() => stringListValue(initialAnswers, 'other_main_image_reference_image_urls'))

  React.useEffect(() => {
    let active = true
    setTaxonomiesLoading(true)
    Promise.all([
      referenceGalleryApi.listCategories(),
      referenceGalleryApi.listStyles(),
    ])
      .then(([categoryResponse, styleResponse]) => {
        if (!active) {
          return
        }
        setCategories(categoryResponse.data || [])
        setStyles(styleResponse.data || [])
      })
      .catch(() => {
        if (active) {
          toast.error(t('agent.ecommerceInteraction.taxonomy.loadFailed'))
        }
      })
      .finally(() => {
        if (active) {
          setTaxonomiesLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [t])

  React.useEffect(() => {
    if (enableBackgroundReference) {
      return
    }
    setBackgroundReferenceUrls([])
  }, [enableBackgroundReference])

  React.useEffect(() => {
    if (enableModelReference) {
      return
    }
    setModelReferenceUrls([])
  }, [enableModelReference])

  React.useEffect(() => {
    if (enableOtherMainImageReference) {
      return
    }
    setOtherMainReferenceUrls([])
  }, [enableOtherMainImageReference])

  if (!requestId || !isEcommerceInteractionKind(kind)) {
    return null
  }

  const referenceSections = {
    background: backgroundReferenceUrls,
    model: modelReferenceUrls,
    otherMain: otherMainReferenceUrls,
  }
  const usedReferenceCount = totalReferenceCount(referenceSections)
  const selectedCategory = categories.find((item) => String(item.id) === selectedCategoryId)
  const selectedStyle = styles.find((item) => String(item.id) === selectedStyleId)
  const canSubmit = !isLocked && !!selectedCategory && !!selectedStyle

  const submit = () => {
    if (!selectedCategory || !selectedStyle) {
      return
    }
    const answers = {
      action: 'confirm',
      ...taxonomyPayload(selectedCategory, 'category'),
      ...taxonomyPayload(selectedStyle, 'style'),
      enable_background_reference: enableBackgroundReference,
      background_reference_image_urls: enableBackgroundReference ? backgroundReferenceUrls : [],
      enable_model_reference: enableModelReference,
      model_reference_image_urls: enableModelReference ? modelReferenceUrls : [],
      enable_other_main_image_reference: enableOtherMainImageReference,
      other_main_image_reference_image_urls: enableOtherMainImageReference ? otherMainReferenceUrls : [],
      generation_count: generationCount,
    }
    void onRespond(
      requestId,
      'confirm',
      t('agent.ecommerceInteraction.actions.submit'),
      answers,
    )
  }

  const cancel = () => {
    void onRespond(
      requestId,
      'cancel',
      t('agent.ecommerceInteraction.actions.cancel'),
      { action: 'cancel' },
    )
  }

  return (
    <CardShell
      title={t('agent.ecommerceInteraction.options.title')}
      subtitle={t('agent.ecommerceInteraction.options.subtitle')}
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <TaxonomySelect
            id={`ecommerce-category-${requestId}`}
            label={t('agent.ecommerceInteraction.options.category')}
            placeholder={t('agent.ecommerceInteraction.options.categoryPlaceholder')}
            items={categories}
            value={selectedCategoryId}
            disabled={isLocked}
            loading={taxonomiesLoading}
            onValueChange={setSelectedCategoryId}
          />
          <TaxonomySelect
            id={`ecommerce-style-${requestId}`}
            label={t('agent.ecommerceInteraction.options.style')}
            placeholder={t('agent.ecommerceInteraction.options.stylePlaceholder')}
            items={styles}
            value={selectedStyleId}
            disabled={isLocked}
            loading={taxonomiesLoading}
            onValueChange={setSelectedStyleId}
          />
        </div>

        <div className="grid gap-2">
          <ToggleRow
            label={t('agent.ecommerceInteraction.options.enableBackground')}
            checked={enableBackgroundReference}
            disabled={isLocked}
            onCheckedChange={setEnableBackgroundReference}
          />
          {enableBackgroundReference ? (
            <ReferenceImageSection
              label={t('agent.ecommerceInteraction.references.background')}
              urls={backgroundReferenceUrls}
              setUrls={setBackgroundReferenceUrls}
              disabled={isLocked}
              conversationId={conversationId}
              onRequestReferenceImages={onRequestReferenceImages}
              onUploadReferenceImage={onUploadReferenceImage}
              maxReferenceImages={maxReferenceImages}
              usedReferenceCount={usedReferenceCount}
              onPreviewImage={onPreviewImage}
            />
          ) : null}

          <ToggleRow
            label={t('agent.ecommerceInteraction.options.enableModel')}
            checked={enableModelReference}
            disabled={isLocked}
            onCheckedChange={setEnableModelReference}
          />
          {enableModelReference ? (
            <ReferenceImageSection
              label={t('agent.ecommerceInteraction.references.model')}
              urls={modelReferenceUrls}
              setUrls={setModelReferenceUrls}
              disabled={isLocked}
              conversationId={conversationId}
              onRequestReferenceImages={onRequestReferenceImages}
              onUploadReferenceImage={onUploadReferenceImage}
              maxReferenceImages={maxReferenceImages}
              usedReferenceCount={usedReferenceCount}
              onPreviewImage={onPreviewImage}
            />
          ) : null}

          <ToggleRow
            label={t('agent.ecommerceInteraction.options.enableOtherMain')}
            checked={enableOtherMainImageReference}
            disabled={isLocked}
            onCheckedChange={setEnableOtherMainImageReference}
          />
          {enableOtherMainImageReference ? (
            <ReferenceImageSection
              label={t('agent.ecommerceInteraction.references.otherMain')}
              urls={otherMainReferenceUrls}
              setUrls={setOtherMainReferenceUrls}
              disabled={isLocked}
              conversationId={conversationId}
              onRequestReferenceImages={onRequestReferenceImages}
              onUploadReferenceImage={onUploadReferenceImage}
              maxReferenceImages={maxReferenceImages}
              usedReferenceCount={usedReferenceCount}
              onPreviewImage={onPreviewImage}
            />
          ) : null}
        </div>

        <div className="max-w-[180px] space-y-1.5">
          <Label htmlFor={`ecommerce-generation-count-${requestId}`} className="text-xs font-medium text-muted-foreground">
            {t('agent.ecommerceInteraction.options.generationCount')}
          </Label>
          <Input
            id={`ecommerce-generation-count-${requestId}`}
            type="number"
            min={minCount}
            max={maxCount}
            value={generationCount}
            disabled={isLocked}
            onChange={(event) => setGenerationCount(clampGenerationCount(Number(event.target.value), minCount, maxCount))}
          />
        </div>

        {!submitted ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={submit} disabled={!canSubmit}>
              <Check className="h-4 w-4" aria-hidden="true" />
              {t('agent.ecommerceInteraction.actions.submit')}
            </Button>
            <Button size="sm" variant="ghost" onClick={cancel} disabled={isLocked}>
              <X className="h-4 w-4" aria-hidden="true" />
              {t('agent.ecommerceInteraction.actions.cancel')}
            </Button>
          </div>
        ) : null}
        {submitted ? <SubmittedNotice /> : null}
      </div>
    </CardShell>
  )
}
