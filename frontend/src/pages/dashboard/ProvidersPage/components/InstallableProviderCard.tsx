import { ArrowUpRight } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface Props {
  name: string
  author: string
  description: string
  logoUrl: string
  onInstall: () => void
}

export default function InstallableProviderCard({ name, author, description, logoUrl, onInstall }: Props) {
  const [isHovered, setIsHovered] = useState(false)
  const { t } = useTranslation()

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'flex h-full cursor-pointer flex-col rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-5 shadow-[var(--app-shadow-control)] transition-all',
        isHovered
          ? 'border-[var(--app-primary)] shadow-[0_4px_12px_var(--app-tint-primary)]'
          : 'hover:border-[var(--app-border-strong)]'
      )}
    >
      <div className="flex items-start gap-4 mb-4">
        <img src={logoUrl} alt={name} className="w-11 h-11 rounded-lg object-contain" />
        <div className="flex flex-col">
          <span className="text-base font-semibold text-foreground">{name}</span>
          <span className="mt-1 text-[13px] text-muted-foreground">{author}</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col justify-end min-h-[48px]">
        {isHovered ? (
          <div className="flex gap-3 animate-in fade-in duration-200">
            <Button className="flex-1" onClick={onInstall}>{t('providers.install')}</Button>
            <Button variant="outline" className="flex-1 gap-1">
              {t('providers.details')} <ArrowUpRight className="w-3 h-3" />
            </Button>
          </div>
        ) : (
          <p className="line-clamp-2 text-[13px] leading-5 text-muted-foreground">
            {description}
          </p>
        )}
      </div>
    </div>
  )
}
