import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useIsDarkMode } from '@/hooks/useTheme'
import { useGlobalStore } from '@/store/globalStore'
import { useAuthStore } from '@/store/authStore'
import { Globe, Moon, Sun, AlertCircle, X, Check } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { LoginRequest } from '@/api/types/auth'

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
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useAppConfigStore } from '@/store/appConfigStore'
import { getLocalizedAppName } from '@/config/brand'
import backgroundVideo from '@/image/60f53aed34c133842c4d9bb4d05f0b31.mp4'

import './LoginPage.css'

/*
// 暂时移除动态图片变换逻辑，保留结构供后续参考
const SCENES = [
  { 
    base: '/home_bg/bg_base_beverage.png', 
    element: '/home_bg/element_logo.png',
    blendMode: 'multiply',
    width: '12vw',
    minWidth: '120px',
    top: '52%',
    left: '50%'
  },
  { 
    base: '/home_bg/bg_base_clothes.png', 
    element: '/home_bg/element_print.png',
    blendMode: 'multiply',
    width: '14vw',
    minWidth: '140px',
    top: '40%',
    left: '49%'
  },
  { 
    base: '/home_bg/bg_base_interior.png', 
    element: '/home_bg/element_art.png',
    blendMode: 'normal',
    width: '18vw',
    minWidth: '160px',
    top: '40%',
    left: '50%'
  },
  { 
    base: '/home_bg/bg_base_street.png', 
    element: '/home_bg/element_neon.png',
    blendMode: 'screen',
    width: '20vw',
    minWidth: '200px',
    top: '55%',
    left: '50%'
  }
]
*/

export function LoginPage() {
  const { t, i18n } = useTranslation()
  const isDark = useIsDarkMode()
  const navigate = useNavigate()
  const { theme, setTheme } = useGlobalStore()

  // Theme logic
  const [systemIsDark, setSystemIsDark] = useState(
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemIsDark(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])
  const isCurrentDark = theme === 'system' ? systemIsDark : theme === 'dark'

  // Auth logic
  const { login, isLoading, error, clearError, isAuthenticated } = useAuthStore()
  
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard/projects', { replace: true })
    }
  }, [isAuthenticated, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (!account.trim() || !password.trim()) return
      await login({ account, password } as LoginRequest)
    } catch {
      // error handled by store
    }
  }

  /*
  // Animation Stage Logic
  // 'BASE' (img only) -> 'APPEAR' (img + floating element) -> 'MERGE' (img + merged element)
  const [sceneIndex, setSceneIndex] = useState(0)
  const [animStage, setAnimStage] = useState<'BASE' | 'APPEAR' | 'MERGE'>('BASE')

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = []
    let isCancelled = false
    
    // Cycle every 6s
    const cycle = () => {
      setAnimStage('BASE')
      
      timers.push(setTimeout(() => {
        if (!isCancelled) setAnimStage('APPEAR')
      }, 1000))

      timers.push(setTimeout(() => {
        if (!isCancelled) setAnimStage('MERGE')
      }, 2500))

      timers.push(setTimeout(() => {
        if (!isCancelled) {
          setSceneIndex(s => (s + 1) % SCENES.length)
          cycle()
        }
      }, 6000))
    }
    
    cycle()

    return () => {
      isCancelled = true
      timers.forEach(clearTimeout)
    }
  }, [])
  */

  const changeLanguage = (lng: string) => i18n.changeLanguage(lng)
  const isZh = i18n.language.startsWith('zh')
  const appName = useAppConfigStore((s) => s.appName)
  const appNameEn = useAppConfigStore((s) => s.appNameEn)
  const appDisplayName = getLocalizedAppName(i18n.language, { appName, appNameEn })

  return (
    <div className={cn('login-page-container', isDark && 'dark')}>
      <div className="login-bg-slider">
        <video
          className="login-bg-video"
          data-testid="login-background-video"
          autoPlay
          loop
          muted
          playsInline
          aria-hidden="true"
        >
          <source src={backgroundVideo} type="video/mp4" />
        </video>
        {/*
        {SCENES.map((scene, idx) => (
          <div 
            key={idx} 
            className={cn(
              'bg-scene', 
              idx === sceneIndex && 'active',
              `stage-${idx === sceneIndex ? animStage : 'BASE'}`
            )}
          >
            <img src={scene.base} alt={`bg-base-${idx}`} className="bg-base-img" />
            
            <div 
              className="bg-element-container"
              style={{
                top: scene.top,
                left: scene.left,
                width: scene.width,
                minWidth: scene.minWidth,
              }}
            >
              <img 
                src={scene.element} 
                alt={`bg-element-${idx}`} 
                className="bg-element-img"
                style={{
                  mixBlendMode: scene.blendMode as any
                }}
              />
            </div>
          </div>
        ))}
        */}
      </div>
      <div className="login-bg-overlay" />

      <div className="login-page-logo">
        <div className="login-logo-icon">M</div>
        {appDisplayName}
      </div>
      <div className="login-top-actions">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                onClick={() => setTheme(isCurrentDark ? 'light' : 'dark')}
                className={cn(
                  'glass-header flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-[var(--app-glass)] text-foreground backdrop-blur-md transition-colors hover:bg-[var(--app-control-hover)]'
                )}
              >
                {isCurrentDark ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom">{t('layout.themeToggle', 'Toggle Theme')}</TooltipContent>
          </Tooltip>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <div
                className={cn(
                  'glass-header flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-[var(--app-glass)] text-foreground backdrop-blur-md transition-colors hover:bg-[var(--app-control-hover)]'
                )}
              >
                <Globe className="w-5 h-5" />
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => changeLanguage('zh-CN')} className="flex items-center justify-between min-w-[120px]">
                简体中文 {isZh && <Check className="w-4 h-4" />}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => changeLanguage('en-US')} className="flex items-center justify-between min-w-[120px]">
                English {!isZh && <Check className="w-4 h-4" />}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </TooltipProvider>
      </div>

      <div className="login-content-wrapper">
        <div className="login-glass-panel">
          <div className="text-center mb-6">
            <h3 className="text-2xl font-bold mb-2">
              {t('login.modal_title', 'Welcome back')}
            </h3>
            <p className="text-sm text-[var(--app-foreground-muted)]">
              {t('login.modal_subtitle', 'Enter your email to sign in to your dashboard')}
            </p>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-6 text-left">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="flex items-center justify-between w-full">
                <span>{error}</span>
                <button type="button" onClick={clearError} className="ml-2"><X className="w-4 h-4" /></button>
              </AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="text-left space-y-4">
            <div className="space-y-2">
              <Label className="font-medium">{t('login.account_label', 'Username or Email')}</Label>
              <Input
                placeholder={t('login.account_input_placeholder', 'Please enter username or email')}
                value={account}
                onChange={(e) => { setAccount(e.target.value); if(error) clearError() }}
                className="h-12 rounded-[var(--app-radius-sm)] border-none bg-[var(--app-control)] font-medium text-foreground focus:bg-[var(--app-control-hover)]"
              />
            </div>

            <div className="space-y-2">
              <Label className="font-medium">{t('login.password_label', 'Password')}</Label>
              <Input
                type="password"
                placeholder={t('login.password_input_placeholder', 'Please enter password')}
                value={password}
                onChange={(e) => { setPassword(e.target.value); if(error) clearError() }}
                className="h-12 rounded-[var(--app-radius-sm)] border-none bg-[var(--app-control)] font-medium text-foreground focus:bg-[var(--app-control-hover)]"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              className="mt-4 h-12 w-full rounded-[var(--app-radius-sm)] font-bold shadow-lg transition-all active:scale-[0.98]"
              disabled={isLoading}
            >
              {isLoading ? '...' : t('login.submit', 'Sign In')}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <span className="text-sm text-[var(--app-foreground-muted)]">
              {t('login.contact_admin_to_register', '请联系管理员开通账号')}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
