import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { providersApi } from '@/api/endpoints/providers'
import type { CredentialRead } from '@/api/endpoints/providers'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
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
  providerName: string
  logoUrl: string
  credentials: CredentialRead[]
  onAddCredential: () => void
  onRefresh: () => void
}

export default function ManageCredentialsModal({ isOpen, onClose, providerCode, providerName, logoUrl, credentials, onAddCredential, onRefresh }: Props) {
  const { t } = useTranslation()

  const handleDelete = async (credId: number) => {
    try {
      await providersApi.deleteCredential(providerCode, credId)
      toast.success(t('providers.deleteSuccess'))
      onRefresh()
    } catch {
      toast.error(t('providers.deleteFailed'))
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent noDarken className="max-w-[600px] glass-modal-unified">
        <DialogHeader>
          <DialogTitle>{t('providers.manageCredentialsTitle')}</DialogTitle>
          <div className="flex items-center gap-2 mt-2">
            <img src={logoUrl} alt={providerName} className="w-5 h-5 rounded object-contain" />
            <span className="text-sm text-muted-foreground">{providerName}</span>
          </div>
        </DialogHeader>

        <div className="max-h-[50vh] overflow-y-auto">
          <div className="flex flex-col gap-4">
            {credentials.map((cred) => (
              <div key={cred.id} className="flex items-center justify-between rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-4">
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-foreground">{cred.name}</span>
                    <span className="text-xs text-muted-foreground">AK: {cred.access_key_hint}</span>
                  </div>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>{t('providers.confirmDelete')}</AlertDialogTitle>
                      <AlertDialogDescription>{t('providers.confirmDelete')}</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>{t('providers.no')}</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleDelete(cred.id)}>{t('providers.yes')}</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))}
          </div>

          {credentials.length === 0 && (
            <p className="text-center py-6 text-muted-foreground">{t('providers.noCredentials')}</p>
          )}

          <Button
            variant="outline"
            className="mt-6 h-10 w-full gap-2 border-dashed border-[var(--app-primary)] bg-[var(--app-tint-primary)] text-[var(--app-primary)]"
            onClick={onAddCredential}
          >
            <Plus className="w-4 h-4" />{t('providers.addCredential')}
          </Button>
        </div>

        <Separator className="my-4" />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('providers.cancel')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
