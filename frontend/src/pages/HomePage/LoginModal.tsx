import { useState } from 'react'
import { useAuthStore } from '@/store/authStore'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import type { LoginRequest } from '@/api/types/auth'

import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, X } from 'lucide-react'

interface LoginModalProps {
  open: boolean
  onCancel: () => void
}

export function LoginModal({ open, onCancel }: LoginModalProps) {
  const { login, isLoading, error, clearError } = useAuthStore()
  const { t } = useTranslation()
  const navigate = useNavigate()

  // Form state
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')

  const resetForm = () => {
    setAccount('')
    setPassword('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (!account.trim() || !password.trim()) return
      await login({ account, password } as LoginRequest)
      handleClose()
      navigate('/dashboard/projects', { replace: true })
    } catch {
      // error is set in store
    }
  }

  const handleClose = () => {
    if (error) clearError()
    resetForm()
    onCancel()
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose() }}>
      <DialogContent noDarken className={cn(
        'p-0 gap-0 border-none overflow-hidden rounded-[32px] sm:rounded-[40px] glass-modal-unified max-w-[420px]'
      )}>
        <div className="text-center px-8 pt-10 pb-8">
          <div className={cn(
            'mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-[var(--app-radius-md)] bg-[var(--app-control-selected)] text-2xl font-black text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]'
          )}>
            M
          </div>
          <h3 className="text-xl font-bold mb-2">
            {t('login.modal_title', 'Welcome back')}
          </h3>
          <p className="text-sm text-muted-foreground mb-6">
            {t('login.modal_subtitle', 'Enter your email to sign in to your dashboard')}
          </p>

          {error && (
            <Alert variant="destructive" className="mb-6 text-left">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="flex items-center justify-between">
                <span>{error}</span>
                <button onClick={clearError} className="ml-2"><X className="w-4 h-4" /></button>
              </AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="text-left space-y-4">
            <div className="space-y-2">
              <Label className="font-medium">{t('login.account_label', 'Username or Email')}</Label>
              <Input
                placeholder={t('login.account_input_placeholder', 'Please enter username or email')}
                value={account}
                onChange={(e) => { setAccount(e.target.value); if (error) clearError() }}
                className="h-12 rounded-[var(--app-radius-sm)] border-none bg-[var(--app-control)] font-medium text-foreground focus:bg-[var(--app-control-hover)]"
              />
            </div>

            <div className="space-y-2">
              <Label className="font-medium">{t('login.password_label', 'Password')}</Label>
              <Input
                type="password"
                placeholder={t('login.password_input_placeholder', 'Please enter password')}
                value={password}
                onChange={(e) => { setPassword(e.target.value); if (error) clearError() }}
                className="h-12 rounded-[var(--app-radius-sm)] border-none bg-[var(--app-control)] font-medium text-foreground focus:bg-[var(--app-control-hover)]"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              className="mt-4 h-12 w-full rounded-[var(--app-radius-sm)] font-bold shadow-lg transition-all active:scale-[0.98]"
              disabled={isLoading}
            >
              {isLoading ? '...' : t('login.submit')}
            </Button>
          </form>

          <div className="mt-4 text-center">
            <span className="text-sm text-muted-foreground">
              {t('login.contact_admin_to_register', '请联系管理员开通账号')}
            </span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
