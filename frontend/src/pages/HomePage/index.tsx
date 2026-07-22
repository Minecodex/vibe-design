import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useIsDarkMode } from '@/hooks/useTheme'
import { useGlobalStore } from '@/store/globalStore'
import { useAuthStore } from '@/store/authStore'
import { storage } from '@/utils/storage'
import { Moon, Sun, Globe, Check } from 'lucide-react'
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

import heroImg from '@/image/homepage/hero_mockup.png'
import showcaseImg from '@/image/homepage/design_showcase.png'
import clickEditImg from '@/image/homepage/feature_click_edit.png'
import styleConsImg from '@/image/homepage/feature_style_consistency.png'
import textEditImg from '@/image/homepage/feature_text_edit.png'
import visualInsightImg from '@/image/homepage/feature_visual_insight.png'

import { LoginModal } from './LoginModal'

import { cn } from '@/lib/utils'
import { useAppConfigStore } from '@/store/appConfigStore'
import { getLocalizedAppName } from '@/config/brand'
import './HomePage.css'

// Rotating headline pairs: [subject, object]
const ROTATING_ITEMS_ZH = [
  ['街角咖啡馆', '品牌视觉系统'],
  ['新生代运动品牌', '商品详情页'],
  ['独立音乐厂牌', '专辑封面'],
  ['精品民宿', '宣传手册'],
  ['潮流服饰品牌', '社交媒体素材'],

]
const ROTATING_ITEMS_EN = [
  ['a corner café', 'a brand identity system'],
  ['a sports brand', 'a product detail page'],
  ['an indie music label', 'an album cover'],
  ['a boutique hotel', 'a promotional brochure'],
  ['a streetwear brand', 'social media assets'],
]

function MeshBackground() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none" style={{ zIndex: -1 }}>
      <div className="hp-mesh-blob top-[-10%] left-[-10%] animate-[mesh-blob-1_20s_infinite_ease-in-out]" />
      <div className="hp-mesh-blob hp-mesh-blob-secondary bottom-[10%] right-[-5%] animate-[mesh-blob-1_25s_infinite_ease-in-out_reverse]" />
      <div className="hp-mesh-blob hp-mesh-blob-tertiary top-[20%] right-[10%] animate-[mesh-blob-1_30s_infinite_ease-in-out_2s]" />
    </div>
  )
}

export function HomePage() {
  const { t, i18n } = useTranslation()
  const isDark = useIsDarkMode()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { theme: appTheme, setTheme } = useGlobalStore()

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

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng)
  }

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [headerScrolled, setHeaderScrolled] = useState(false)
  const [rotatingIndex, setRotatingIndex] = useState(0)
  const [animKey, setAnimKey] = useState(0)
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false)

  // Auto-open login modal when redirected with ?login=true
  useEffect(() => {
    if (searchParams.get('login') === 'true' && !isAuthenticated) {
      setIsLoginModalOpen(true)
      // Clean up the query parameter
      searchParams.delete('login')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, isAuthenticated, setSearchParams])

  const isZh = i18n.language.startsWith('zh')
  const rotatingItems = isZh ? ROTATING_ITEMS_ZH : ROTATING_ITEMS_EN
  const appName = useAppConfigStore((s) => s.appName)
  const appNameEn = useAppConfigStore((s) => s.appNameEn)
  const appDisplayName = getLocalizedAppName(i18n.language, { appName, appNameEn })

  const handleCTA = useCallback(() => {
    if (isAuthenticated) {
      // Verify the token actually exists; if not, the persisted auth state is stale
      const token = storage.getToken()
      if (!token) {
        // Clear stale auth state and show login modal
        useAuthStore.setState({ user: null, isAuthenticated: false, error: null })
        setIsLoginModalOpen(true)
        return
      }
      navigate('/dashboard/projects')
    } else {
      setIsLoginModalOpen(true)
    }
  }, [isAuthenticated, navigate])

  // Header scroll detection
  useEffect(() => {
    const onScroll = () => setHeaderScrolled(window.scrollY > 60)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Rotating text
  useEffect(() => {
    const timer = setInterval(() => {
      setRotatingIndex((prev) => (prev + 1) % rotatingItems.length)
      setAnimKey((prev) => prev + 1)
    }, 3000)
    return () => clearInterval(timer)
  }, [rotatingItems.length])

  // Scroll reveal
  useEffect(() => {
    const reveals = document.querySelectorAll('.hp-reveal')
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible')
          }
        })
      },
      { threshold: 0.15 }
    )
    reveals.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  const currentItem = rotatingItems[rotatingIndex]

  return (
    <div className={`homepage ${isDark ? 'dark' : 'light'}`}>
      <MeshBackground />
      {/* ===== Header ===== */}
      <header className={cn('hp-header transition-all duration-500', headerScrolled && 'glass-header glass-effect scrolled')}>
        <div className="hp-logo">
          <span className="hp-logo-icon">M</span>
          {appDisplayName}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TooltipProvider>
            <div className="flex items-center gap-1.5">
              {/* Theme Toggle */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    onClick={() => setTheme(isCurrentDark ? 'light' : 'dark')}
                    className={cn(
                      'flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-[var(--app-control-hover)] hover:text-foreground'
                    )}
                  >
                    {isCurrentDark ? <Moon className="w-4.5 h-4.5" /> : <Sun className="w-4.5 h-4.5" />}
                  </div>
                </TooltipTrigger>
                <TooltipContent side="bottom">{t('layout.themeToggle', '切换主题')}</TooltipContent>
              </Tooltip>

              {/* Language Switcher */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <div>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className={cn(
                          'flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-[var(--app-control-hover)] hover:text-foreground'
                        )}>
                          <Globe className="w-4.5 h-4.5" />
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">{t('layout.language', '语言')}</TooltipContent>
                    </Tooltip>
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
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
            </div>
          </TooltipProvider>

          <button className="hp-header-cta" style={{ marginLeft: '8px' }} onClick={handleCTA}>
            {t('homepage.start_experience')}
          </button>
        </div>
      </header>

      {/* ===== Hero ===== */}
      <section className="hp-hero">
        <p className="hp-hero-subtitle">{t('homepage.hero_subtitle')}</p>
        <h1 className="hp-hero-title">
          {isZh ? (
            <>
              {t('homepage.hero_prefix')}
              <span className="rotating-text" key={animKey}>
                <span className="rotating-word">{currentItem[0]}</span>
              </span>
              <sup>({rotatingIndex + 1})</sup>
              <br />
              {t('homepage.hero_suffix')}
              <span className="rotating-text" key={animKey + 'b'}>
                <span className="rotating-word">{currentItem[1]}</span>
              </span>
            </>
          ) : (
            <>
              {t('homepage.hero_design')}
              <span className="rotating-text" key={animKey + 'c'}>
                <span className="rotating-word">{currentItem[1]}</span>
              </span>
              <sup>({rotatingIndex + 1})</sup>
              <br />
              {t('homepage.hero_for')}
              <span className="rotating-text" key={animKey + 'd'}>
                <span className="rotating-word">{currentItem[0]}</span>
              </span>
            </>
          )}
        </h1>
        <button className="hp-cta-btn" onClick={handleCTA}>
          {t('homepage.design_now')}
        </button>
        <div className="hp-hero-mockup">
          <img src={heroImg} alt="AI Design Interface" />
        </div>
      </section>

      {/* ===== System Thinking ===== */}
      <section className="hp-section hp-reveal glass-effect">
        <p className="hp-section-label">{t('homepage.system_label')}</p>
        <h2 className="hp-section-title">{t('homepage.system_title')}</h2>
        <p className="hp-section-desc">{t('homepage.system_desc')}</p>
        <div className="hp-system-grid">
          {[showcaseImg, clickEditImg, styleConsImg, visualInsightImg].map(
            (img, i) => (
              <div className="hp-system-card" key={i}>
                <img src={img} alt={`Design showcase ${i + 1}`} />
              </div>
            )
          )}
        </div>
      </section>

      {/* ===== Features ===== */}
      <section className="hp-features">
        <div className="hp-features-header hp-reveal">
          <p className="hp-section-label">{t('homepage.features_label')}</p>
          <h2 className="hp-section-title">{t('homepage.features_title')}</h2>
          <p className="hp-section-desc" style={{ margin: '0 auto' }}>
            {t('homepage.features_subtitle')}
          </p>
        </div>

        {/* Feature 1: Click Edit */}
        <div className="hp-feature-card hp-reveal glass-card glass-effect">
          <div className="hp-feature-info">
            <p className="hp-feature-label">{t('homepage.f1_label')}</p>
            <h3 className="hp-feature-title">{t('homepage.f1_title')}</h3>
            <p className="hp-feature-desc">{t('homepage.f1_desc')}</p>
            <button className="hp-feature-btn" onClick={handleCTA}>
              {t('homepage.f1_btn')}
            </button>
          </div>
          <div className="hp-feature-image">
            <img src={clickEditImg} alt="Click Edit Feature" />
          </div>
        </div>

        {/* Feature 2: Style Consistency */}
        <div className="hp-feature-card reverse hp-reveal glass-card glass-effect">
          <div className="hp-feature-info">
            <p className="hp-feature-label">{t('homepage.f2_label')}</p>
            <h3 className="hp-feature-title">{t('homepage.f2_title')}</h3>
            <p className="hp-feature-desc">{t('homepage.f2_desc')}</p>
            <button className="hp-feature-btn" onClick={handleCTA}>
              {t('homepage.start_experience')}
            </button>
          </div>
          <div className="hp-feature-image">
            <img src={styleConsImg} alt="Style Consistency Feature" />
          </div>
        </div>

        {/* Feature 3: Text Editing */}
        <div className="hp-feature-card hp-reveal glass-card glass-effect">
          <div className="hp-feature-info">
            <p className="hp-feature-label">{t('homepage.f3_label')}</p>
            <h3 className="hp-feature-title">{t('homepage.f3_title')}</h3>
            <p className="hp-feature-desc">{t('homepage.f3_desc')}</p>
            <button className="hp-feature-btn" onClick={handleCTA}>
              {t('homepage.start_experience')}
            </button>
          </div>
          <div className="hp-feature-image">
            <img src={textEditImg} alt="Text Editing Feature" />
          </div>
        </div>

        {/* Feature 4: Visual Insight */}
        <div className="hp-feature-card reverse hp-reveal glass-card glass-effect">
          <div className="hp-feature-info">
            <p className="hp-feature-label">{t('homepage.f4_label')}</p>
            <h3 className="hp-feature-title">{t('homepage.f4_title')}</h3>
            <p className="hp-feature-desc">{t('homepage.f4_desc')}</p>
            <button className="hp-feature-btn" onClick={handleCTA}>
              {t('homepage.start_experience')}
            </button>
          </div>
          <div className="hp-feature-image">
            <img src={visualInsightImg} alt="Visual Insight Feature" />
          </div>
        </div>
      </section>

      {/* ===== Showcase CTA ===== */}
      <section className="hp-showcase hp-reveal glass-card glass-effect" style={{ margin: '0 48px', borderRadius: '40px' }}>
        <h2 className="hp-showcase-title">{t('homepage.showcase_title')}</h2>
        <p className="hp-showcase-subtitle">{t('homepage.showcase_subtitle')}</p>
        <button className="hp-cta-btn" onClick={handleCTA}>
          {t('homepage.start_experience')}
        </button>
      </section>

      {/* ===== Footer ===== */}
      <footer className="hp-footer">
        <div className="hp-footer-content">
          <div className="hp-footer-brand">
            <div className="hp-logo">
              <span className="hp-logo-icon">M</span>
              {appDisplayName}
            </div>
            <p>{t('homepage.footer_desc')}</p>
          </div>
          <div className="hp-footer-column">
            <h4>{t('homepage.footer_company')}</h4>
            <ul>
              <li><a href="#" onClick={(e) => { e.preventDefault(); handleCTA() }}>{t('homepage.footer_pricing')}</a></li>
              <li><a href="#" onClick={(e) => { e.preventDefault() }}>{t('homepage.footer_blog')}</a></li>
              <li><a href="#" onClick={(e) => { e.preventDefault() }}>{t('homepage.footer_docs')}</a></li>
            </ul>
          </div>
          <div className="hp-footer-column">
            <h4>{t('homepage.footer_legal')}</h4>
            <ul>
              <li><a href="#" onClick={(e) => { e.preventDefault() }}>{t('homepage.footer_terms')}</a></li>
              <li><a href="#" onClick={(e) => { e.preventDefault() }}>{t('homepage.footer_privacy')}</a></li>
            </ul>
          </div>
        </div>
        <div className="hp-footer-bottom">
          <span>© 2026 {appDisplayName}. {t('homepage.footer_rights')}</span>
        </div>
      </footer>

      <LoginModal
        open={isLoginModalOpen}
        onCancel={() => setIsLoginModalOpen(false)}
      />
    </div>
  )
}
