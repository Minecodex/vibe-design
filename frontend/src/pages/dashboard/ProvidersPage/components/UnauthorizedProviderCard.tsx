import { Settings, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

interface Props {
  name: string
  logoUrl: string
  tags: string[]
  onSetup: () => void
}

export default function UnauthorizedProviderCard({ name, logoUrl, tags, onSetup }: Props) {
  const { t } = useTranslation()

  return (
    <div className="overflow-hidden rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] shadow-[var(--app-shadow-control)]">
      <div className="px-6 py-5 flex justify-between items-center">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <img src={logoUrl} alt={name} className="w-8 h-8 rounded-md object-contain" />
            <span className="text-base font-semibold text-foreground">{name}</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {tags.map(tag => (
              <span key={tag} className="rounded-[var(--app-radius-xs)] border border-[var(--app-border)] bg-[var(--app-control)] px-2 py-0.5 text-xs text-muted-foreground">
                {tag}
              </span>
            ))}
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-1.5 rounded-[var(--app-radius-xs)] bg-[var(--app-tint-danger)] px-2 py-0.5 text-[13px] text-[var(--app-danger)]">
            <span>{t('providers.unauthorized')}</span>
            <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
          </div>
          <Button variant="outline" size="sm" className="gap-1.5 text-blue-500 border-blue-500 w-full justify-center" onClick={onSetup}>
            <Settings className="w-4 h-4" />{t('providers.setup')}
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-[var(--app-border)] bg-[var(--app-surface-muted)] px-6 py-3">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] font-bold">i</div>
          <span className="text-[13px] text-muted-foreground">
            {t('providers.pleaseConfigureAPIKey')}
          </span>
        </div>
        <div className="flex cursor-not-allowed items-center gap-1 text-[13px] text-[var(--app-foreground-subtle)]">
          <Plus className="w-3 h-3" />
          <span>{t('providers.addModel')}</span>
        </div>
      </div>
    </div>
  )
}
