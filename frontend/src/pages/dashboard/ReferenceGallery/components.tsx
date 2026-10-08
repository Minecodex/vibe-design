import { apiErrorMessage, imageLabels } from './referenceGalleryUtils'
import { useEffect, useRef, useState } from 'react'
import {
  FolderUp,
  ImagePlus,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import {
  referenceGalleryApi,
  type ReferenceImageRead,
  type ReferenceTaxonomyKind,
  type ReferenceTaxonomyRead,
} from '@/api/endpoints/referenceGallery'
import { Button } from '@/components/ui/button'
import { CachedImage } from '@/components/ui/CachedImage'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'


const ALL_VALUE = '__all__'





export function TaxonomySelect({
  items,
  value,
  allLabel,
  placeholder,
  onChange,
}: {
  items: ReferenceTaxonomyRead[]
  value: number | null
  allLabel?: string
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
      <SelectContent>
        {allLabel ? <SelectItem value={ALL_VALUE}>{allLabel}</SelectItem> : null}
        {items.map((item) => (
          <SelectItem key={item.id} value={String(item.id)}>
            {item.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function PromptEditor({
  value,
  placeholder,
  onChange,
}: {
  value: string
  placeholder: string
  onChange: (value: string) => void
}) {
  return (
    <textarea
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className="min-h-[180px] w-full resize-y rounded-xl border border-[var(--app-border)] bg-[var(--app-control)] px-4 py-3 text-sm leading-6 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-[var(--app-primary)] focus:ring-2 focus:ring-[var(--app-focus-ring)]"
    />
  )
}

export function UploadReferenceDialog({
  open,
  categories,
  styles,
  classifications,
  pendingFiles,
  submitting,
  onOpenChange,
  onFilesChange,
  onSubmit,
}: {
  open: boolean
  categories: ReferenceTaxonomyRead[]
  styles: ReferenceTaxonomyRead[]
  classifications: ReferenceTaxonomyRead[]
  pendingFiles: File[]
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onFilesChange: (files: File[]) => void
  onSubmit: (categoryId: number, styleId: number | null, classificationId: number | null) => Promise<void>
}) {
  const { t } = useTranslation()
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [styleId, setStyleId] = useState<number | null>(null)
  const [classificationId, setClassificationId] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) {
      setCategoryId(null)
      setStyleId(null)
      setClassificationId(null)
    }
  }, [open])

  const disabled = submitting || !categoryId || pendingFiles.length === 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-modal-unified text-foreground sm:max-w-2xl">
        <DialogTitle>{t('referenceGallery.upload.title')}</DialogTitle>
        <DialogDescription>{t('referenceGallery.upload.description')}</DialogDescription>
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t('referenceGallery.category')}</div>
              <TaxonomySelect
                items={categories}
                value={categoryId}
                placeholder={t('referenceGallery.selectCategory')}
                onChange={setCategoryId}
              />
            </div>
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t('referenceGallery.style')}</div>
              <TaxonomySelect
                items={styles}
                value={styleId}
                allLabel={t('referenceGallery.noStyle')}
                placeholder={t('referenceGallery.selectStyle')}
                onChange={setStyleId}
              />
            </div>
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t('referenceGallery.classification')}</div>
              <TaxonomySelect
                items={classifications}
                value={classificationId}
                allLabel={t('referenceGallery.noClassification')}
                placeholder={t('referenceGallery.selectClassification')}
                onChange={setClassificationId}
              />
            </div>
          </div>

          <div className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4">
            <div className="mb-3 text-sm text-muted-foreground">
              {pendingFiles.length > 0
                ? t('referenceGallery.upload.selected', { count: pendingFiles.length })
                : t('referenceGallery.upload.empty')}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
                <ImagePlus className="h-4 w-4" /> {t('referenceGallery.upload.images')}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => folderInputRef.current?.click()}>
                <FolderUp className="h-4 w-4" /> {t('referenceGallery.upload.folder')}
              </Button>
              {pendingFiles.length > 0 ? (
                <Button type="button" variant="ghost" size="sm" onClick={() => onFilesChange([])}>
                  <RotateCcw className="h-4 w-4" /> {t('referenceGallery.reset')}
                </Button>
              ) : null}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(event) => onFilesChange(Array.from(event.target.files || []))}
            />
            <input
              ref={folderInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              // @ts-expect-error webkitdirectory is supported by Chromium.
              webkitdirectory=""
              onChange={(event) => onFilesChange(Array.from(event.target.files || []))}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" disabled={submitting} onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="button" disabled={disabled} onClick={() => categoryId && void onSubmit(categoryId, styleId, classificationId)}>
            {submitting ? t('referenceGallery.upload.uploading') : t('referenceGallery.upload.submit')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function EditReferenceImageDialog({
  open,
  image,
  categories,
  styles,
  classifications,
  submitting,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  image: ReferenceImageRead | null
  categories: ReferenceTaxonomyRead[]
  styles: ReferenceTaxonomyRead[]
  classifications: ReferenceTaxonomyRead[]
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (categoryId: number, styleId: number | null, classificationId: number | null) => Promise<void>
}) {
  const { t } = useTranslation()
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [styleId, setStyleId] = useState<number | null>(null)
  const [classificationId, setClassificationId] = useState<number | null>(null)

  useEffect(() => {
    if (!open || !image) return
    setCategoryId(image.category_id || null)
    setStyleId(image.style_id || null)
    setClassificationId(image.classification_id || null)
  }, [image, open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-modal-unified text-foreground sm:max-w-2xl">
        <DialogTitle>{t('referenceGallery.editImage.title')}</DialogTitle>
        <DialogDescription>{t('referenceGallery.editImage.description')}</DialogDescription>
        <div className="space-y-4">
          {image ? (
            <div className="flex items-center gap-3 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-3">
              <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-muted">
                <CachedImage src={image.list_preview_url || image.url} alt={image.name} className="h-full w-full object-cover" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{image.name || t('referenceGallery.untitled')}</div>
                <div className="mt-1 flex flex-wrap gap-1 text-xs text-muted-foreground">
                  {imageLabels(image).map((label) => <span key={label}>{label}</span>)}
                </div>
              </div>
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t('referenceGallery.category')}</div>
              <TaxonomySelect
                items={categories}
                value={categoryId}
                placeholder={t('referenceGallery.selectCategory')}
                onChange={setCategoryId}
              />
            </div>
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t('referenceGallery.style')}</div>
              <TaxonomySelect
                items={styles}
                value={styleId}
                allLabel={t('referenceGallery.noStyle')}
                placeholder={t('referenceGallery.selectStyle')}
                onChange={setStyleId}
              />
            </div>
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">{t('referenceGallery.classification')}</div>
              <TaxonomySelect
                items={classifications}
                value={classificationId}
                allLabel={t('referenceGallery.noClassification')}
                placeholder={t('referenceGallery.selectClassification')}
                onChange={setClassificationId}
              />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" disabled={submitting} onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="button" disabled={submitting || !categoryId} onClick={() => categoryId && void onSubmit(categoryId, styleId, classificationId)}>
            {submitting ? t('referenceGallery.editImage.saving') : t('referenceGallery.editImage.submit')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function TaxonomyManager({
  kind,
  items,
  isAdmin,
  createOpen = false,
  onCreateOpenChange,
  onChanged,
}: {
  kind: ReferenceTaxonomyKind
  items: ReferenceTaxonomyRead[]
  isAdmin: boolean
  createOpen?: boolean
  onCreateOpenChange?: (open: boolean) => void
  onChanged: () => Promise<void>
}) {
  const { t } = useTranslation()
  const [newName, setNewName] = useState('')
  const [newPrompt, setNewPrompt] = useState('')
  const [editing, setEditing] = useState<ReferenceTaxonomyRead | null>(null)
  const [editingName, setEditingName] = useState('')
  const [editingPrompt, setEditingPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const title = kind === 'category'
    ? t('referenceGallery.category')
    : kind === 'style'
      ? t('referenceGallery.style')
      : t('referenceGallery.classification')
  const requiresPrompt = kind !== 'category'

  const run = async (action: () => Promise<unknown>, success?: string) => {
    setBusy(true)
    try {
      await action()
      await onChanged()
      if (success) toast.success(success)
    } catch (error) {
      toast.error(apiErrorMessage(error, t('referenceGallery.taxonomy.saveFailed')))
    } finally {
      setBusy(false)
    }
  }

  const handleCreateOpenChange = (open: boolean) => {
    onCreateOpenChange?.(open)
    if (!open) {
      setNewName('')
      setNewPrompt('')
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {items.length === 0 ? (
        <div className="flex h-64 items-center justify-center rounded-[var(--app-radius-md)] border border-[var(--app-border)] text-sm text-muted-foreground">
          {t('referenceGallery.taxonomy.empty', { type: title })}
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
          {items.map((item) => (
            <div key={item.id} className="rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-4 shadow-[var(--app-shadow-control)]">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{item.name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {t('referenceGallery.taxonomy.imageCount', { count: item.image_count })}
                  </div>
                </div>
                {isAdmin ? (
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      aria-label={t('referenceGallery.edit')}
                      onClick={() => {
                      setEditing(item)
                      setEditingName(item.name)
                      setEditingPrompt(item.prompt || '')
                    }}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-destructive"
                      aria-label={t('referenceGallery.delete')}
                      disabled={busy}
                      onClick={() => void run(() => referenceGalleryApi.deleteTaxonomy(item.id), t('referenceGallery.taxonomy.deleted'))}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ) : null}
              </div>
              {item.prompt ? <div className="mt-3 line-clamp-4 text-sm text-muted-foreground">{item.prompt}</div> : null}
            </div>
          ))}
        </div>
      )}

      {isAdmin ? (
        <Dialog open={createOpen} onOpenChange={handleCreateOpenChange}>
          <DialogContent className="glass-modal-unified text-foreground sm:max-w-2xl">
            <DialogTitle>{t('referenceGallery.taxonomy.createTitle', { type: title })}</DialogTitle>
            <div className="space-y-3">
              <Input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder={t('referenceGallery.taxonomy.namePlaceholder', { type: title })}
                className="h-9 rounded-xl"
              />
              {requiresPrompt ? (
                <PromptEditor
                  value={newPrompt}
                  onChange={setNewPrompt}
                  placeholder={t('referenceGallery.taxonomy.promptPlaceholder')}
                />
              ) : null}
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" disabled={busy} onClick={() => handleCreateOpenChange(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                type="button"
                disabled={busy || !newName.trim() || (requiresPrompt && !newPrompt.trim())}
                onClick={() => void run(async () => {
                  await referenceGalleryApi.createTaxonomy(kind, newName, requiresPrompt ? newPrompt : null)
                  handleCreateOpenChange(false)
                }, t('referenceGallery.taxonomy.created'))}
              >
                <Plus className="h-4 w-4" /> {t('referenceGallery.add')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}

      <Dialog open={!!editing} onOpenChange={(next) => !next && setEditing(null)}>
        <DialogContent className="glass-modal-unified text-foreground sm:max-w-2xl">
          <DialogTitle>{t('referenceGallery.taxonomy.editTitle', { type: title })}</DialogTitle>
          <div className="space-y-3">
            <Input value={editingName} onChange={(event) => setEditingName(event.target.value)} className="h-9 rounded-xl" />
            {requiresPrompt ? (
              <PromptEditor
                value={editingPrompt}
                onChange={setEditingPrompt}
                placeholder={t('referenceGallery.taxonomy.promptPlaceholder')}
              />
            ) : null}
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              disabled={busy || !editingName.trim() || (requiresPrompt && !editingPrompt.trim())}
              onClick={() => {
                if (!editing) return
                void run(async () => {
                  await referenceGalleryApi.updateTaxonomy(editing.id, {
                    name: editingName,
                    ...(requiresPrompt ? { prompt: editingPrompt } : {}),
                  })
                  setEditing(null)
                }, t('referenceGallery.taxonomy.saved'))
              }}
            >
              {t('common.save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
