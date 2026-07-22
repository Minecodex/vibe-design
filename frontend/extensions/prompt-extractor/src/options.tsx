import { FormEvent, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { loginWithPassword } from './lib/auth'
import { DEFAULT_SERVER_BASE_URL, normalizeServerBaseUrl } from './lib/config'
import { loadSession, saveSession } from './lib/storage'

type StatusTone = 'neutral' | 'info' | 'success' | 'error' | 'loading'

interface Copywriting {
  badge: string
  title: string
  subtitle: string
  intro: string
  server: string
  account: string
  password: string
  submit: string
  idle: string
  saving: string
  saved: string
  success: string
  failed: string
  helper: string
}

interface OptionsAppProps {
  initialSessionState?: 'idle' | 'saved'
}

function getCopy(): Copywriting {
  const isZh = navigator.language.toLowerCase().startsWith('zh')

  return isZh
    ? {
        badge: '网页登录提示词提取',
        title: '提取插件',
        subtitle: 'Prompt Extractor',
        intro: '登录后即可在网页图片上右键提取文生图提示词，支持中英文切换并重新生成。',
        server: '服务地址',
        account: '账号',
        password: '密码',
        submit: '登录',
        idle: '请输入账号与密码完成登录',
        saving: '登录中...',
        saved: '已保存登录状态',
        success: '登录成功',
        failed: '登录失败',
        helper: '使用主站账号体系登录，服务地址默认指向当前站点。',
      }
    : {
        badge: 'Web prompt extraction',
        title: 'Prompt Extractor',
        subtitle: '提取插件',
        intro: 'Sign in once to right-click images on the web and extract text-to-image prompts in Chinese or English.',
        server: 'Server URL',
        account: 'Account',
        password: 'Password',
        submit: 'Sign in',
        idle: 'Enter your account credentials to continue',
        saving: 'Signing in...',
        saved: 'Session restored',
        success: 'Signed in successfully',
        failed: 'Sign in failed',
        helper: 'The extension reuses your main-site account and defaults to the current service address.',
      }
}

function getStatusStyles(tone: StatusTone) {
  if (tone === 'success') {
    return {
      color: '#155b3f',
      background: 'rgba(223, 252, 233, 0.9)',
      border: '1px solid rgba(53, 153, 99, 0.28)',
    }
  }

  if (tone === 'error') {
    return {
      color: '#8a2233',
      background: 'rgba(255, 233, 238, 0.95)',
      border: '1px solid rgba(196, 64, 93, 0.22)',
    }
  }

  if (tone === 'loading') {
    return {
      color: '#855b17',
      background: 'rgba(255, 244, 214, 0.94)',
      border: '1px solid rgba(214, 166, 62, 0.24)',
    }
  }

  if (tone === 'info') {
    return {
      color: '#21466b',
      background: 'rgba(232, 243, 255, 0.96)',
      border: '1px solid rgba(69, 126, 196, 0.2)',
    }
  }

  return {
    color: '#4b5563',
    background: 'rgba(255, 255, 255, 0.74)',
    border: '1px solid rgba(148, 163, 184, 0.18)',
  }
}

function getInputStyle() {
  return {
    width: '100%',
    height: 50,
    borderRadius: 14,
    border: '1px solid rgba(17, 24, 39, 0.1)',
    background: 'rgba(248, 250, 252, 0.86)',
    boxSizing: 'border-box' as const,
    padding: '0 16px',
    fontSize: 15,
    color: '#0f172a',
    outline: 'none',
    boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.55)',
  }
}

export function OptionsApp({ initialSessionState = 'idle' }: OptionsAppProps) {
  const copy = getCopy()
  const [serverBaseUrl, setServerBaseUrl] = useState(DEFAULT_SERVER_BASE_URL)
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState(initialSessionState === 'saved' ? copy.saved : copy.idle)
  const [statusTone, setStatusTone] = useState<StatusTone>(initialSessionState === 'saved' ? 'success' : 'neutral')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const previousBody = {
      margin: document.body.style.margin,
      minHeight: document.body.style.minHeight,
      background: document.body.style.background,
      fontFamily: document.body.style.fontFamily,
    }
    const previousRoot = {
      margin: document.documentElement.style.margin,
      minHeight: document.documentElement.style.minHeight,
      background: document.documentElement.style.background,
    }

    document.documentElement.style.margin = '0'
    document.documentElement.style.minHeight = '100%'
    document.documentElement.style.background = '#f3f5f9'
    document.body.style.margin = '0'
    document.body.style.minHeight = '100vh'
    document.body.style.background = '#f3f5f9'
    document.body.style.fontFamily = '"Plus Jakarta Sans", "Segoe UI", sans-serif'

    return () => {
      document.body.style.margin = previousBody.margin
      document.body.style.minHeight = previousBody.minHeight
      document.body.style.background = previousBody.background
      document.body.style.fontFamily = previousBody.fontFamily
      document.documentElement.style.margin = previousRoot.margin
      document.documentElement.style.minHeight = previousRoot.minHeight
      document.documentElement.style.background = previousRoot.background
    }
  }, [])

  useEffect(() => {
    if (initialSessionState === 'saved') {
      return
    }

    void loadSession().then((session) => {
      if (!session) {
        return
      }
      setServerBaseUrl(session.serverBaseUrl)
      setStatus(copy.saved)
      setStatusTone('success')
    })
  }, [copy.saved, initialSessionState])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setStatus(copy.saving)
    setStatusTone('loading')

    try {
      const tokens = await loginWithPassword({
        serverBaseUrl,
        account,
        password,
      })
      const normalizedServerBaseUrl = normalizeServerBaseUrl(serverBaseUrl)
      await saveSession({
        serverBaseUrl: normalizedServerBaseUrl,
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      })
      setServerBaseUrl(normalizedServerBaseUrl)
      setPassword('')
      setStatus(copy.success)
      setStatusTone('success')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : copy.failed)
      setStatusTone('error')
    } finally {
      setSubmitting(false)
    }
  }

  const statusStyle = getStatusStyles(statusTone)

  return (
    <main
      data-testid="options-shell"
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        background: [
          'radial-gradient(circle at top left, rgba(255,255,255,0.92), rgba(255,255,255,0) 30%)',
          'radial-gradient(circle at 85% 15%, rgba(193, 219, 255, 0.55), rgba(193, 219, 255, 0) 28%)',
          'linear-gradient(180deg, #eef3f9 0%, #f7f8fb 100%)',
        ].join(', '),
      }}
    >
      <div
        data-testid="options-card"
        style={{
          width: '100%',
          maxWidth: 460,
          borderRadius: 32,
          padding: '32px 32px 28px',
          boxSizing: 'border-box',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.96), rgba(249,250,252,0.92))',
          border: '1px solid rgba(255,255,255,0.72)',
          boxShadow: '0 28px 60px rgba(15, 23, 42, 0.14)',
          backdropFilter: 'blur(18px)',
        }}
      >
        <div style={{ marginBottom: 28 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 18,
              padding: '7px 12px',
              borderRadius: 999,
              background: 'rgba(15, 23, 42, 0.06)',
              color: '#334155',
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: '0.03em',
              textTransform: 'uppercase',
            }}
          >
            {copy.badge}
          </div>

          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 18,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'linear-gradient(135deg, #111827, #2b3446)',
              color: '#fff',
              fontSize: 24,
              fontWeight: 800,
              boxShadow: '0 18px 28px rgba(15, 23, 42, 0.24)',
              marginBottom: 18,
            }}
          >
            提
          </div>

          <h1 style={{ margin: 0, fontSize: 34, lineHeight: 1.08, color: '#0f172a', fontWeight: 800 }}>
            {copy.title}
          </h1>
          <p style={{ margin: '8px 0 0', color: '#475569', fontSize: 16, fontWeight: 600 }}>
            {copy.subtitle}
          </p>
          <p style={{ margin: '14px 0 0', color: '#64748b', lineHeight: 1.65, fontSize: 15 }}>
            {copy.intro}
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }}>
          <label style={{ display: 'grid', gap: 8 }}>
            <span style={{ color: '#0f172a', fontSize: 14, fontWeight: 700 }}>{copy.server}</span>
            <input
              aria-label={copy.server}
              value={serverBaseUrl}
              onChange={(event) => setServerBaseUrl(event.target.value)}
              style={getInputStyle()}
            />
          </label>

          <label style={{ display: 'grid', gap: 8 }}>
            <span style={{ color: '#0f172a', fontSize: 14, fontWeight: 700 }}>{copy.account}</span>
            <input
              aria-label={copy.account}
              value={account}
              onChange={(event) => setAccount(event.target.value)}
              style={getInputStyle()}
            />
          </label>

          <label style={{ display: 'grid', gap: 8 }}>
            <span style={{ color: '#0f172a', fontSize: 14, fontWeight: 700 }}>{copy.password}</span>
            <input
              aria-label={copy.password}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              style={getInputStyle()}
            />
          </label>

          <button
            type="submit"
            disabled={submitting}
            style={{
              marginTop: 4,
              height: 52,
              border: 'none',
              borderRadius: 16,
              background: submitting
                ? 'linear-gradient(135deg, #5b6472, #70798a)'
                : 'linear-gradient(135deg, #111827, #1f2937)',
              color: '#fff',
              fontSize: 16,
              fontWeight: 800,
              cursor: submitting ? 'wait' : 'pointer',
              boxShadow: '0 16px 28px rgba(15, 23, 42, 0.22)',
            }}
          >
            {submitting ? copy.saving : copy.submit}
          </button>
        </form>

        <div
          data-testid="options-status"
          style={{
            marginTop: 18,
            padding: '12px 14px',
            borderRadius: 16,
            fontSize: 14,
            lineHeight: 1.5,
            ...statusStyle,
          }}
        >
          {status}
        </div>

        <p style={{ margin: '16px 2px 0', color: '#64748b', fontSize: 13, lineHeight: 1.6 }}>
          {copy.helper}
        </p>
      </div>
    </main>
  )
}

const rootElement = document.getElementById('root')
if (rootElement) {
  createRoot(rootElement).render(<OptionsApp />)
}
