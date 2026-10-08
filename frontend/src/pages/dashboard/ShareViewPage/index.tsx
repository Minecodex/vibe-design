import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { shareApi, ShareInfo } from '@/api/endpoints/share'
import { CanvasPage } from '../CanvasPage'
import { ProjectDetailsView } from '@/components/project/ProjectDetailsView'
import { useAuthStore } from '@/store/authStore'
import { useGlobalStore } from '@/store/globalStore'
import { useIsDarkMode } from '@/hooks/useTheme'
import { toast } from 'sonner'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, AlertCircle, Globe, Moon, Sun } from 'lucide-react'

export function ShareViewPage() {
    const { token } = useParams<{ token: string }>()
    const navigate = useNavigate()
    const isDark = useIsDarkMode()
    const { i18n } = useTranslation()
    const isAuthenticated = useAuthStore(state => state.isAuthenticated)
    const theme = useGlobalStore(state => state.theme)
    const setTheme = useGlobalStore(state => state.setTheme)

    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [requirePassword, setRequirePassword] = useState(false)
    const [password, setPassword] = useState('')
    const [shareInfo, setShareInfo] = useState<ShareInfo | null>(null)
    const [joinDialogOpen, setJoinDialogOpen] = useState(false)
    const [joinInfo, setJoinInfo] = useState<ShareInfo | null>(null)

    const toggleTheme = () => {
        setTheme(isDark ? 'light' : 'dark')
    }

    const toggleLanguage = () => {
        i18n.changeLanguage(i18n.language.startsWith('zh') ? 'en-US' : 'zh-CN')
    }

    const guestToolbar = (
        <div className="fixed top-6 right-6 z-50 flex items-center gap-3">
            <button
                type="button"
                aria-label="切换主题"
                onClick={toggleTheme}
                className="flex h-11 w-11 items-center justify-center rounded-full border border-[var(--app-border)] bg-[var(--app-glass)] text-foreground shadow-[var(--app-shadow-control)] backdrop-blur-xl transition-colors hover:bg-[var(--app-control-hover)]"
            >
                {theme === 'dark' || (theme === 'system' && isDark) ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
            </button>
            <button
                type="button"
                aria-label="切换语言"
                onClick={toggleLanguage}
                className="flex h-11 w-11 items-center justify-center rounded-full border border-[var(--app-border)] bg-[var(--app-glass)] text-foreground shadow-[var(--app-shadow-control)] backdrop-blur-xl transition-colors hover:bg-[var(--app-control-hover)]"
            >
                <Globe className="h-5 w-5" />
            </button>
        </div>
    )

    const access = useCallback(async (shareToken: string, pwd?: string) => {
        try {
            setLoading(true)
            const res = await shareApi.accessProject(shareToken, { password: pwd })
            setShareInfo(res.data)
            setRequirePassword(false)

            if (res.data.permission === 'editor' && res.data.is_member) {
                navigate(`/canvas/${res.data.project.id}`)
                return
            }
            if (res.data.permission === 'editor') {
                setJoinInfo(res.data)
                setJoinDialogOpen(true)
            }
        } catch (err: any) {
            if (err.response?.status === 403) {
                toast.error('密码错误')
                setRequirePassword(true)
            } else if (err.response?.status === 410) {
                setError('分享链接已过期')
            } else {
                setError(err.response?.data?.detail || '访问项目失败')
            }
        } finally {
            setLoading(false)
        }
    }, [navigate])

    useEffect(() => {
        const fetchInfo = async () => {
            if (!token) return

            try {
                setLoading(true)
                const res = await shareApi.getInfo(token)
                if (res.data.require_password) {
                    setRequirePassword(true)
                    setLoading(false)
                } else {
                    await access(token)
                }
            } catch (err: any) {
                const detail = err.response?.data?.detail || '访问分享链接失败'
                if (err.response?.status === 410) {
                    setError('分享链接已过期')
                } else {
                    setError(detail)
                }
                setLoading(false)
            }
        }

        fetchInfo()
    }, [token, access])

    const handleJoin = async () => {
        if (!isAuthenticated) {
            toast.info('请先登录再加入项目')
            navigate('/')
            return
        }

        try {
            const res = await shareApi.joinProject(token!)
            toast.success('已成功加入项目')
            navigate(`/canvas/${res.data.project_id}`)
        } catch (err: any) {
            if (err.response?.data?.detail) {
                toast.error(err.response.data.detail)
            } else {
                toast.error('加入失败')
            }
        }

        setJoinDialogOpen(false)
    }

    if (error) {
        return (
            <>
                {guestToolbar}
                <div className="flex h-screen flex-col items-center justify-center bg-background">
                    <AlertCircle className="mb-4 h-16 w-16 text-destructive" />
                    <h3 className="mb-2 text-lg font-semibold text-foreground">无法访问分享内容</h3>
                    <p className="mb-6 text-sm text-muted-foreground">{error}</p>
                    <Button onClick={() => navigate('/')}>返回首页</Button>
                </div>
            </>
        )
    }

    if (requirePassword) {
        return (
            <>
                {guestToolbar}
                <div className="flex h-screen flex-col items-center bg-background pt-[15vh]">
                    <div className="w-[400px] rounded-[var(--app-radius-lg)] border border-[var(--app-border)] bg-[var(--app-glass)] p-8 shadow-[var(--app-shadow-panel)] backdrop-blur-2xl">
                        <h4 className="mb-6 text-center text-lg font-semibold text-foreground">请输入访问密码</h4>
                        <Input
                            type="password"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            placeholder="分享链接密码"
                            className="mb-6"
                            onKeyDown={e => {
                                if (e.key === 'Enter') access(token!, password)
                            }}
                        />
                        <Button className="w-full" onClick={() => access(token!, password)} disabled={loading}>
                            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                            验证并访问
                        </Button>
                    </div>
                </div>
            </>
        )
    }

    if (loading) {
        return (
            <>
                {guestToolbar}
                <div className="flex h-screen items-center justify-center bg-background">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            </>
        )
    }

    return (
        <>
            {guestToolbar}
            {shareInfo && shareInfo.permission === 'viewer' && (
                <ProjectDetailsView
                    project={shareInfo.project}
                    onBack={() => {}}
                    onUpdate={() => {}}
                    mode="share-readonly"
                    shareToken={token}
                />
            )}
            {shareInfo && shareInfo.permission !== 'viewer' && <CanvasPage isGuest={true} guestProject={shareInfo.project} />}

            <AlertDialog open={joinDialogOpen} onOpenChange={setJoinDialogOpen}>
                <AlertDialogContent noDarken className="glass-modal-unified !top-0 !translate-y-0">
                    <AlertDialogHeader>
                        <AlertDialogTitle>加入项目</AlertDialogTitle>
                        <AlertDialogDescription>
                            是否加入项目 &quot;{joinInfo?.project.title}&quot;？加入后您可以直接编辑该项目。
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={() => setLoading(false)}>取消</AlertDialogCancel>
                        <AlertDialogAction onClick={handleJoin}>加入项目</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}
