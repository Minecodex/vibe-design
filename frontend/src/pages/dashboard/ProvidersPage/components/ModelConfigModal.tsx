import { useTranslation } from 'react-i18next'
import { providersApi } from '@/api/endpoints/providers'
import type { ModelRead, CredentialRead } from '@/api/endpoints/providers'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

interface Props {
  isOpen: boolean
  onClose: () => void
  providerCode: string
  model: ModelRead
  logoUrl: string
  credentials: CredentialRead[]
}

export default function ModelConfigModal({ isOpen, onClose, providerCode, model, logoUrl, credentials }: Props) {
  const { t } = useTranslation()
  const [selectedCredentialId, setSelectedCredentialId] = useState<string>(model.credential_id?.toString() || '')
  const [submitting, setSubmitting] = useState(false)

  const handleSave = async () => {
    setSubmitting(true)
    try {
      await providersApi.updateModel(providerCode, model.id, {
        credential_id: selectedCredentialId ? parseInt(selectedCredentialId) : null
      })
      toast.success(t('providers.saveSuccess'))
      onClose()
    } catch {
      toast.error(t('providers.saveFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleRemove = async () => {
    try {
      await providersApi.deleteModel(providerCode, model.id)
      toast.success(t('providers.deleteSuccess'))
      onClose()
    } catch {
      toast.error(t('providers.deleteFailed'))
    }
  }

  const typeLabel = model.model_type === 'text2image'
    ? t('providers.textToImage')
    : model.model_type === 'multimodal'
      ? t('providers.multimodal')
      : t('providers.textToVideo')

  return (
    <Dialog open={isOpen} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent noDarken className="max-w-[600px] glass-modal-unified">
        <DialogHeader>
          <DialogTitle>{t('providers.configureModel')}</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-3 mb-6 mt-4">
          <img src={logoUrl} alt={model.model_name} className="w-6 h-6 rounded object-contain" />
          <span className="text-base font-medium text-foreground">{model.model_name}</span>
          <span className="rounded-[var(--app-radius-xs)] border border-[var(--app-border)] bg-[var(--app-control)] px-2 py-0.5 text-xs text-muted-foreground">
            {typeLabel}
          </span>
        </div>

        <div className="mb-6 flex items-center justify-between rounded-[var(--app-radius-md)] border border-[var(--app-primary)] bg-[color-mix(in_srgb,var(--app-primary)_9%,var(--app-surface))] p-4">
          <div className="flex items-center gap-4">
            <img src={logoUrl} alt="Credential" className="w-7 h-7 rounded" />
            <div className="flex flex-col">
              <span className="text-sm font-medium text-foreground">{t('providers.specifyModelCredential')}</span>
              <span className="text-[13px] text-muted-foreground">{t('providers.useConfiguredCredential')}</span>
            </div>
          </div>
          <Select value={selectedCredentialId} onValueChange={setSelectedCredentialId}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder={t('providers.selectCredential')} />
            </SelectTrigger>
            <SelectContent>
              {credentials.map((c) => (
                <SelectItem key={c.id} value={c.id.toString()}>
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                    {c.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <DialogFooter className="flex !justify-between items-center">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">
                {t('providers.removeModel')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('providers.confirmDelete')}</AlertDialogTitle>
                <AlertDialogDescription>{t('providers.confirmDelete')}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('providers.no')}</AlertDialogCancel>
                <AlertDialogAction onClick={handleRemove}>{t('providers.yes')}</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <div className="flex gap-3">
            <Button variant="outline" onClick={onClose}>{t('providers.cancel')}</Button>
            <Button onClick={handleSave} disabled={submitting}>
              {submitting ? '...' : t('providers.save')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
