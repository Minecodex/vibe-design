import { useTranslation } from 'react-i18next'
import { providersApi } from '@/api/endpoints/providers'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface Props {
  isOpen: boolean
  onClose: () => void
  providerCode: string
  providerName: string
  credentialTypes?: string[]
}

export default function AuthConfigModal({ isOpen, onClose, providerCode, providerName, credentialTypes = ['ak_sk'] }: Props) {
  const { t } = useTranslation()
  const [submitting, setSubmitting] = useState(false)
  const [credentialName, setCredentialName] = useState('')
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [authType, setAuthType] = useState<string>(credentialTypes[0] || 'ak_sk')

  const supportsMultipleAuthTypes = credentialTypes.length > 1

  const resetForm = () => {
    setCredentialName('')
    setAccessKey('')
    setSecretKey('')
    setAuthType(credentialTypes[0] || 'ak_sk')
  }

  const handleSubmit = async () => {
    if (authType === 'api_key') {
      if (!accessKey.trim()) {
        toast.error(t('providers.apiKeyPlaceholder'))
        return
      }
    } else {
      if (!accessKey.trim() || !secretKey.trim()) {
        toast.error(t('providers.accessKeyPlaceholder'))
        return
      }
    }
    setSubmitting(true)
    try {
      await providersApi.createCredential(providerCode, {
        name: credentialName || `${providerName} Key`,
        access_key: accessKey,
        secret_key: authType === 'api_key' ? '' : secretKey,
        auth_type: authType,
      })
      toast.success(t('providers.saveSuccess'))
      resetForm()
      onClose()
    } catch {
      toast.error(t('providers.saveFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(v) => { if (!v) { resetForm(); onClose() } }}>
      <DialogContent noDarken className="max-w-[600px] glass-modal-unified">
        <DialogHeader>
          <DialogTitle>{t('providers.modalTitle')}</DialogTitle>
          <DialogDescription className="text-[13px]">
            {t('providers.modalDesc')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          <div className="space-y-2">
            <Label className="font-medium">{t('providers.credentialName')}</Label>
            <Input
              placeholder={t('providers.credentialNamePlaceholder')}
              value={credentialName}
              onChange={(e) => setCredentialName(e.target.value)}
            />
          </div>

          {supportsMultipleAuthTypes && (
            <div className="space-y-2">
              <Label className="font-medium">{t('providers.authType')} <span className="text-red-500">*</span></Label>
              <Select value={authType} onValueChange={setAuthType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {credentialTypes.map((ct) => (
                    <SelectItem key={ct} value={ct}>
                      {ct === 'api_key' ? t('providers.authTypeApiKey') : t('providers.authTypeAkSk')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {authType === 'api_key' ? (
            <div className="space-y-2">
              <Label className="font-medium">{t('providers.apiKey')} <span className="text-red-500">*</span></Label>
              <Input
                placeholder={t('providers.apiKeyPlaceholder')}
                value={accessKey}
                onChange={(e) => setAccessKey(e.target.value)}
              />
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label className="font-medium">Access Key <span className="text-red-500">*</span></Label>
                <Input
                  placeholder={t('providers.accessKeyPlaceholder')}
                  value={accessKey}
                  onChange={(e) => setAccessKey(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label className="font-medium">{t('providers.secretAccessKey')} <span className="text-red-500">*</span></Label>
                <Input
                  type="password"
                  placeholder={t('providers.secretAccessKeyPlaceholder')}
                  value={secretKey}
                  onChange={(e) => setSecretKey(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter className="mt-6">
          <Button variant="outline" onClick={() => { resetForm(); onClose() }}>{t('providers.cancel')}</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? '...' : t('providers.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
