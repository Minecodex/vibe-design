import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Folder,
  User,
  LogOut,
  Globe,
  Moon,
  Sun,
  Check,
  Home,
  LayoutGrid,
  Users,
  Image,
  GalleryHorizontalEnd,
  ChevronRight,
  X,
  AlertCircle
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useGlobalStore } from '@/store/globalStore'
import { useTranslation } from 'react-i18next'
import { getImageUrl } from '@/utils/imageUrl'
import { canAccessHomeAgent } from '@/utils/licenseAccess'
import { formatCnyFromCents } from '@/utils/money'
import { OrganizationModal } from './OrganizationModal'
import { BillingModal } from './BillingModal'
import { cn } from '@/lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from '@/components/ui/avatar'
import { BrandMark } from '@/components/common/BrandMark'
import { AppSurface, GlassPanel, IconButton, StatusBadge } from '@/components/common/ui'

export function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout, refreshBalance, fetchDeployType, deployType, licenseEdition, providerBalanceSyncEnabled } = useAuthStore()
  const { t, i18n } = useTranslation()
  const { theme: appTheme, setTheme, dismissedBalanceAlert, setDismissedBalanceAlert } = useGlobalStore()
  const [isOrgModalOpen, setIsOrgModalOpen] = useState(false)
  const [isBillingModalOpen, setIsBillingModalOpen] = useState(false)
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)

  const isAdmin = user?.role === 'admin'
  const showBilling = true
  const isLowBalance = user !== null && !providerBalanceSyncEnabled && (user.balance_cents ?? 0) < 700 && (deployType !== 'private' || isAdmin)

  // Refresh deploy mode before rendering billing surfaces from persisted auth state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    void fetchDeployType()
    void refreshBalance()
    const balanceRefreshTimer = window.setInterval(() => {
      void refreshBalance()
    }, 300_000)
    return () => window.clearInterval(balanceRefreshTimer)
  }, [fetchDeployType, refreshBalance])

  const [systemIsDark, setSystemIsDark] = useState(
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemIsDark(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  const isCurrentDark = appTheme === 'system' ? systemIsDark : appTheme === 'dark'

  const handleMenuClick = (path: string) => {
    navigate(path)
  }

  const handleLogout = async () => {
    await logout()
    navigate('/')
  }

  const handleUserMenuOpenChange = (open: boolean) => {
    setIsUserMenuOpen(open)
    if (open) {
      void refreshBalance()
    }
  }

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng)
  }

  const isZh = i18n.language.startsWith('zh')

  const sidebarItems = [
    { key: 'projects', icon: <Folder className="w-4 h-4" />, path: '/dashboard/projects', label: t('menu.projects', '项目') },
    { key: 'assets', icon: <Image className="w-4 h-4" />, path: '/dashboard/assets', label: t('menu.assets', '资产库') },
    { key: 'reference-gallery', icon: <GalleryHorizontalEnd className="w-4 h-4" />, path: '/dashboard/reference-gallery', label: t('menu.referenceGallery', '参考图库') },
    { key: 'providers', icon: <LayoutGrid className="w-4 h-4" />, path: '/dashboard/providers', label: t('layout.providers', '模型供应商') },
  ]
  if (canAccessHomeAgent(licenseEdition)) {
    sidebarItems.unshift({ key: 'home', icon: <Home className="w-4 h-4" />, path: '/dashboard/home', label: t('menu.home', '主页') })
  }

  return (
    <div className="min-h-screen h-screen flex flex-col overflow-hidden transition-colors duration-500">
      {/* Fixed gradient background */}
      <div className={cn(
        'fixed inset-0 -z-10 transition-colors duration-500',
        'bg-[radial-gradient(circle_at_48%_0%,color-mix(in_srgb,var(--app-primary)_12%,transparent),transparent_28%),linear-gradient(145deg,var(--app-bg-soft),var(--app-bg)_68%)]'
      )} />
      {/* Logo in top left */}
      <div 
        onClick={() => navigate('/dashboard/projects')}
        className="fixed top-6 left-6 z-50 flex items-center justify-center w-12 cursor-pointer transition-transform hover:scale-105"
      >
        <BrandMark isDark={isCurrentDark} className="w-7 h-7" />
      </div>

      {/* Floating Low Balance Alert */}
      {isLowBalance && !dismissedBalanceAlert && (
        <div className={cn(
            "fixed top-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-1.5 rounded-full border border-[color-mix(in_srgb,var(--app-warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--app-warning)_12%,var(--app-glass))] text-[var(--app-warning)] shadow-[var(--app-shadow-control)] backdrop-blur-md transition-all animate-in fade-in slide-in-from-top-2"
        )}>
          <AlertCircle className="w-4 h-4" />
          <span className="text-[13px] font-medium">{t('billing.low_alert', '余额低于 ¥7.00，请及时充值')}</span>
          <button
            onClick={() => setDismissedBalanceAlert(true)}
            className={cn(
              "p-0.5 rounded-full hover:bg-[var(--app-control-hover)] transition-colors"
            )}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Floating Avatar, Theme and i18n at Bottom Left */}
      <div className="fixed bottom-6 left-6 flex flex-col items-center gap-3 z-50 group">
        <div className="flex flex-col items-center gap-3 opacity-0 translate-y-3 pointer-events-none group-hover:opacity-100 group-hover:translate-y-0 group-hover:pointer-events-auto transition-all duration-300">
          <TooltipProvider>
            {/* Theme Toggle */}
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  onClick={() => setTheme(isCurrentDark ? 'light' : 'dark')}
                  className="flex items-center justify-center w-10 h-10 rounded-full cursor-pointer text-[var(--app-foreground-muted)] transition-colors hover:bg-[var(--app-control-hover)] hover:text-foreground"
                >
                  {isCurrentDark ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
                </div>
              </TooltipTrigger>
              <TooltipContent side="right">{t('layout.themeToggle', '切换主题')}</TooltipContent>
            </Tooltip>
  
            {/* Language Switcher */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center justify-center w-10 h-10 rounded-full cursor-pointer text-[var(--app-foreground-muted)] transition-colors hover:bg-[var(--app-control-hover)] hover:text-foreground">
                        <Globe className="w-5 h-5" />
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="right">{t('layout.language', '语言')}</TooltipContent>
                  </Tooltip>
                </div>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="end" sideOffset={16}>
                <DropdownMenuItem onClick={() => changeLanguage('zh-CN')} className="flex items-center justify-between min-w-[120px]">
                  简体中文
                  {isZh && <Check className="w-4 h-4" />}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => changeLanguage('en-US')} className="flex items-center justify-between min-w-[120px]">
                  English
                  {!isZh && <Check className="w-4 h-4" />}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </TooltipProvider>
        </div>

        <DropdownMenu open={isUserMenuOpen} onOpenChange={handleUserMenuOpenChange}>
          <DropdownMenuTrigger asChild>
            <button className="relative rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 transition-transform hover:scale-110">
              <Avatar className="w-7 h-7 cursor-pointer border border-[var(--app-border)] shadow-sm">
                <AvatarImage src={user && 'avatar_url' in user ? getImageUrl((user as unknown as Record<string, unknown>).avatar_url as string) : undefined} />
                <AvatarFallback className="bg-[var(--app-primary)] text-white text-xs">
                  {user?.nickname?.[0]?.toUpperCase() || user?.username?.[0]?.toUpperCase() || <User className="w-3.5 h-3.5" />}
                </AvatarFallback>
              </Avatar>
              {isLowBalance && dismissedBalanceAlert && (
                <div className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-[var(--app-danger)] border-2 border-[var(--app-bg)] rounded-full flex items-center justify-center animate-in zoom-in">
                  <span className="text-[8px] font-bold text-white">!</span>
                </div>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            side="right"
            align="end"
            sideOffset={16}
            className={cn(
              "w-[280px] p-2"
            )}
          >
            <AppSurface variant="muted" className="flex items-center gap-3 p-3 mb-2 rounded-[var(--app-radius-sm)] transition-colors">
              <Avatar className="w-10 h-10 border border-[var(--app-border)]">
                <AvatarImage src={user && 'avatar_url' in user ? getImageUrl((user as unknown as Record<string, unknown>).avatar_url as string) : undefined} />
                <AvatarFallback className="bg-[var(--app-primary)] text-white">
                  {user?.nickname?.[0]?.toUpperCase() || user?.username?.[0]?.toUpperCase() || <User className="w-4 h-4" />}
                </AvatarFallback>
              </Avatar>
              <div className="flex flex-col flex-1 min-w-0">
                <span className="text-sm font-semibold truncate">{user?.nickname || user?.username}</span>
                <span className="text-[11px] text-muted-foreground truncate">{user?.email}</span>
              </div>
            </AppSurface>

            {showBilling && (
              <div
                onClick={() => {
                  setIsUserMenuOpen(false)
                  setIsBillingModalOpen(true)
                }}
                className="flex flex-col p-3 mb-2 rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-control)] cursor-pointer transition-all hover:scale-[1.02] hover:bg-[var(--app-control-hover)] active:scale-[0.98]">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium">{t('billing.balance', '余额')}</span>
                  <span className="flex items-center text-sm font-bold">
                    {formatCnyFromCents(user?.balance_cents ?? 0)} <ChevronRight className="w-4 h-4 ml-1 text-[var(--app-foreground-subtle)]" />
                  </span>
                </div>
                {isLowBalance && (
                  <StatusBadge variant="warning" className="mt-2 w-fit">{t('billing.low_hint', '余额不足请及时充值')}</StatusBadge>
                )}
              </div>
            )}

            <div className="space-y-1">
              <DropdownMenuItem
                onClick={() => { if (user?.id) navigate(`/dashboard/users/${user.id}`) }}
                className="py-2.5 px-3 cursor-pointer transition-colors"
              >
                <User className="w-4 h-4 mr-2 text-[var(--app-foreground-muted)]" />
                <span className="text-sm">{t('layout.personalSettings', '个人设置')}</span>
              </DropdownMenuItem>
              {user?.role === 'admin' && (
                <DropdownMenuItem
                  onClick={() => setIsOrgModalOpen(true)}
                  className="py-2.5 px-3 cursor-pointer transition-colors"
                >
                  <Users className="w-4 h-4 mr-2 text-[var(--app-foreground-muted)]" />
                  <span className="text-sm">{t('organization.management', '组织管理')}</span>
                </DropdownMenuItem>
              )}
              <div className="h-px my-1 bg-[var(--app-border)]" />
              <DropdownMenuItem
                onClick={handleLogout}
                className="py-2.5 px-3 cursor-pointer transition-colors text-destructive focus:text-destructive"
              >
                <LogOut className="w-4 h-4 mr-2" />
                <span className="text-sm font-medium">{t('layout.logout', '退出登录')}</span>
              </DropdownMenuItem>
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden flex flex-row p-0 bg-transparent border-none w-full h-full relative z-0">
        {/* Floating Sidebar Container */}
        <div className="w-6 mr-6 shrink-0 relative">
          <TooltipProvider>
            <div className="fixed left-6 top-1/2 -translate-y-1/2 flex flex-col items-center gap-3 h-fit z-40">
              {/* Navigation Pill */}
              <GlassPanel className="w-12 rounded-3xl flex flex-col items-center py-2.5 gap-3">
                {sidebarItems.map(item => {
                  const isActive = location.pathname.startsWith(item.path)
                  return (
                    <Tooltip key={item.key}>
                      <TooltipTrigger asChild>
                        <IconButton
                          onClick={() => handleMenuClick(item.path)}
                          className={cn('w-9 h-9 rounded-[18px] text-base', isActive && 'bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]')}
                        >
                          {item.icon}
                        </IconButton>
                      </TooltipTrigger>
                      <TooltipContent side="right">{item.label}</TooltipContent>
                    </Tooltip>
                  )
                })}
              </GlassPanel>
            </div>
          </TooltipProvider>
        </div>

        <div className="flex-1 min-h-0 overflow-hidden m-0 p-0 flex flex-col">
          <Outlet />
        </div>
      </div>
      <OrganizationModal open={isOrgModalOpen} onCancel={() => setIsOrgModalOpen(false)} />
      <BillingModal open={isBillingModalOpen} onCancel={() => setIsBillingModalOpen(false)} />
    </div>
  )
}


