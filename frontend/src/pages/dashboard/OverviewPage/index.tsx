import { Plus, ArrowUp, Lock } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

export function OverviewPage() {
  const [activeTab, setActiveTab] = useState('published')
  const { t } = useTranslation()

  const tabs = [
    { key: 'published', label: t('overview.published', '已发布') },
    { key: 'liked', label: t('overview.liked', '赞过'), icon: <Lock className="w-3 h-3 ml-1" /> },
    { key: 'inspiration', label: t('overview.inspiration', '灵感') },
    { key: 'shorts', label: t('overview.shorts', 'AI短片') },
  ]

  return (
    <div className="flex-1 flex flex-col relative h-full font-sans bg-transparent">
      {/* Top Tabs */}
      <div className="flex justify-center pt-6 pb-2.5">
        <div className="flex gap-2">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.key
            return (
              <div
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex cursor-pointer items-center rounded-full px-5 py-2 text-[15px] transition-all',
                  isActive
                    ? 'bg-[var(--app-control-selected)] font-semibold text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]'
                    : 'font-normal text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground'
                )}
              >
                {tab.label}
                {tab.icon && tab.icon}
              </div>
            )
          })}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex px-[60px] py-5 relative">
        <div className="flex-1 flex flex-col items-center justify-center pb-20">
          {/* Gradient circle */}
          <div className="app-ai-orb relative mb-6 flex h-[140px] w-[140px] items-center justify-center overflow-hidden rounded-full">
            <div className="relative z-[2] text-[32px] font-bold italic text-[var(--app-primary)]">
              AI
            </div>
          </div>
          <div className="text-[15px] tracking-wider text-muted-foreground">
            {t('overview.noWorks', '暂无作品，去开启想象')}
          </div>
        </div>
      </div>

      {/* Floating Bottom Input Bar */}
      <div className={cn(
        'absolute bottom-[30px] left-1/2 flex w-[700px] max-w-[90%] -translate-x-1/2 items-center rounded-[30px] border border-[var(--app-border)] bg-[var(--app-glass)] px-2.5 py-2 shadow-[var(--app-shadow-panel)] backdrop-blur-2xl'
      )}>
        <div className={cn(
          'mr-4 flex h-10 w-10 cursor-pointer items-center justify-center rounded-[var(--app-radius-sm)] bg-[var(--app-control)] text-muted-foreground transition-colors hover:bg-[var(--app-control-hover)] hover:text-foreground'
        )}>
          <Plus className="w-[18px] h-[18px]" />
        </div>

        <input
          type="text"
          placeholder={t('overview.promptPlaceholder', '像素重组 2.0 全能参考，视频创意无限可能') as string}
          className="flex-1 border-none bg-transparent text-[15px] text-foreground outline-none placeholder:text-muted-foreground"
        />

        <div className={cn(
          'ml-3 flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border-none bg-[var(--app-control)] text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground'
        )}>
          <ArrowUp className="w-[18px] h-[18px]" />
        </div>
      </div>

      {/* Question mark */}
      <div className="absolute bottom-[30px] right-[30px]">
        <div className={cn(
          'flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-[var(--app-border)] bg-[var(--app-glass)] font-bold text-muted-foreground shadow-[var(--app-shadow-control)] backdrop-blur-2xl hover:bg-[var(--app-control-hover)] hover:text-foreground'
        )}>
          ?
        </div>
      </div>
    </div>
  )
}
