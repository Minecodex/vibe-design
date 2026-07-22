import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Check, Globe } from 'lucide-react'

import { licenseApi } from '@/api/endpoints/license'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/store/authStore'
import { isLicenseActive } from '@/utils/licenseAccess'

export function ActivationPage() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const licenseStatus = useAuthStore((state) => state.licenseStatus)
  const licenseExpiresAt = useAuthStore((state) => state.licenseExpiresAt)
  const fetchDeployType = useAuthStore((state) => state.fetchDeployType)

  const [code, setCode] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasCheckedStatus, setHasCheckedStatus] = useState(false)

  const isZh = i18n.language.startsWith('zh')

  useEffect(() => {
    fetchDeployType()
      .catch(() => undefined)
      .finally(() => setHasCheckedStatus(true))
  }, [fetchDeployType])

  useEffect(() => {
    if (hasCheckedStatus && isLicenseActive(licenseStatus)) {
      navigate(isAuthenticated ? '/dashboard/projects' : '/', { replace: true })
    }
  }, [hasCheckedStatus, isAuthenticated, licenseStatus, navigate])

  const activationTitle = licenseStatus === 'expired'
    ? t('activation.expired_title')
    : t('activation.inactive_title')
  const activationSubtitle = licenseStatus === 'expired'
    ? t('activation.expired_subtitle')
    : t('activation.inactive_subtitle')

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!code.trim()) return

    setIsSubmitting(true)
    setError(null)
    try {
      await licenseApi.activate({ code: code.trim() })
      await fetchDeployType()
      navigate(isAuthenticated ? '/dashboard/projects' : '/', { replace: true })
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('activation.error'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-background px-4 py-10 text-foreground md:px-8">
      <div className="mx-auto flex max-w-4xl justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="mb-5 inline-flex items-center gap-2 rounded-full border border-[var(--app-border)] bg-[var(--app-glass)] px-4 py-2 text-sm shadow-[var(--app-shadow-control)] backdrop-blur-xl transition hover:bg-[var(--app-control-hover)]"
            >
              <Globe className="h-4 w-4" />
              {isZh ? t('lang.zh') : t('lang.en')}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => i18n.changeLanguage('zh-CN')} className="flex items-center justify-between min-w-[120px]">
              {t('lang.zh')}
              {isZh ? <Check className="h-4 w-4" /> : null}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => i18n.changeLanguage('en-US')} className="flex items-center justify-between min-w-[120px]">
              {t('lang.en')}
              {!isZh ? <Check className="h-4 w-4" /> : null}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="mx-auto flex min-h-[72vh] max-w-4xl items-center justify-center">
        <div className="w-full rounded-[28px] border border-[var(--app-border)] bg-[var(--app-glass)] p-8 shadow-[var(--app-shadow-panel)] backdrop-blur md:p-12">
          <div className="mx-auto max-w-xl space-y-8 text-center">
            <div className="space-y-3">
              <div className="text-sm font-medium tracking-[0.24em] text-slate-500 uppercase">
                {t('activation.badge')}
              </div>
              <h1 className="text-3xl font-semibold leading-tight text-slate-900 md:text-4xl">
                {activationTitle}
              </h1>
              <p className="text-base leading-7 text-slate-600">
                {activationSubtitle}
              </p>
              {licenseExpiresAt ? (
                <p className="text-sm text-slate-500">
                  {t('activation.last_expiration', { value: licenseExpiresAt })}
                </p>
              ) : null}
            </div>

            <form className="space-y-5 text-left" onSubmit={handleSubmit}>
              {error ? (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="activation-code">{t('activation.code_label')}</Label>
                <Input
                  id="activation-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder={t('activation.code_placeholder')}
                  autoComplete="off"
                  className="h-12 rounded-xl"
                />
              </div>

              <Button type="submit" className="h-12 w-full rounded-xl" disabled={isSubmitting || !code.trim()}>
                {isSubmitting ? t('activation.submitting') : t('activation.submit')}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
