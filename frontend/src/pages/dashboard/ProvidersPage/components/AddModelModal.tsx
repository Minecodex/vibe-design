import { useTranslation } from 'react-i18next'
import { providersApi } from '@/api/endpoints/providers'
import type { ModelOption, CredentialRead } from '@/api/endpoints/providers'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
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

interface Props {
  isOpen: boolean
  onClose: () => void
  providerCode: string
  providerName: string
  logoUrl: string
  registry: Record<string, ModelOption[]>
  credentials: CredentialRead[]
  existingModels: Array<{ model_name: string; model_type: string }>
  requiresEndpoint?: boolean
}

export default function AddModelModal({ isOpen, onClose, providerCode, providerName, logoUrl, registry, credentials, existingModels, requiresEndpoint = false }: Props) {
  const { t } = useTranslation()
  const [submitting, setSubmitting] = useState(false)
  const [selectedType, setSelectedType] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [selectedCredentialId, setSelectedCredentialId] = useState<string>('')
  const [endpoint, setEndpoint] = useState<string>('')

  const existingModelNames = new Set(
    existingModels
      .filter(m => m.model_type === selectedType)
      .map(m => m.model_name)
  )
  const availableModels = selectedType
    ? (registry[selectedType] || []).filter(m => !existingModelNames.has(m.model_name))
    : []

  const handleSubmit = async () => {
    if (!selectedType || !selectedModel) {
      toast.error(t('providers.modelTypePlaceholder'))
      return
    }
    if (requiresEndpoint && !endpoint.trim()) {
      toast.error(t('providers.endpointRequired'))
      return
    }
    setSubmitting(true)
    try {
      await providersApi.createModel(providerCode, {
        model_name: selectedModel,
        model_type: selectedType,
        credential_id: selectedCredentialId ? parseInt(selectedCredentialId) : null,
        endpoint: requiresEndpoint ? endpoint.trim() : null,
      })
      toast.success(t('providers.addSuccess'))
      handleCancel()
    } catch {
      toast.error(t('providers.saveFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = () => {
    setSelectedType('')
    setSelectedModel('')
    setSelectedCredentialId('')
    setEndpoint('')
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={(v) => { if (!v) handleCancel() }}>
      <DialogContent noDarken className="max-w-[600px] glass-modal-unified">
        <DialogHeader>
          <DialogTitle>{t('providers.addModelTitle')}</DialogTitle>
          <div className="flex items-center gap-2 mt-2">
            <img src={logoUrl} alt={providerName} className="w-5 h-5 rounded object-contain" />
            <span className="text-sm text-muted-foreground">{providerName}</span>
          </div>
        </DialogHeader>

        <div className="space-y-4 mt-4 max-h-[60vh] overflow-y-auto">
          <div className="space-y-2">
            <Label className="font-medium">{t('providers.modelType')} <span className="text-red-500">*</span></Label>
            <Select value={selectedType} onValueChange={(v) => { setSelectedType(v); setSelectedModel('') }}>
              <SelectTrigger><SelectValue placeholder={t('providers.modelTypePlaceholder')} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="text2image">{t('providers.textToImage')}</SelectItem>
                <SelectItem value="text2video">{t('providers.textToVideo')}</SelectItem>
                <SelectItem value="multimodal">{t('providers.multimodal')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label className="font-medium">{t('providers.modelName')} <span className="text-red-500">*</span></Label>
            <Select value={selectedModel} onValueChange={setSelectedModel} disabled={!selectedType}>
              <SelectTrigger><SelectValue placeholder={t('providers.modelNamePlaceholder')} /></SelectTrigger>
              <SelectContent>
                {availableModels.map((m) => (
                  <SelectItem key={m.model_name} value={m.model_name}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {requiresEndpoint && (
            <div className="space-y-2">
              <Label className="font-medium">{t('providers.endpoint')} <span className="text-red-500">*</span></Label>
              <Input
                placeholder={t('providers.endpointPlaceholder')}
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
              />
            </div>
          )}

          {credentials.length > 0 && (
            <div className="space-y-2">
              <Label className="font-medium">{t('providers.modelCredential')}</Label>
              <Select value={selectedCredentialId} onValueChange={setSelectedCredentialId}>
                <SelectTrigger><SelectValue placeholder={t('providers.selectCredential')} /></SelectTrigger>
                <SelectContent>
                  {credentials.map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()}>
                      {c.name} ({c.access_key_hint})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={handleCancel}>{t('providers.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? '...' : t('providers.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
