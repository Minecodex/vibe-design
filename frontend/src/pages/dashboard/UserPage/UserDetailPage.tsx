import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Pencil, Check, X, Lock, UserCircle } from 'lucide-react'
import { usersApi, User as UserType } from '@/api/endpoints/users'
import { getImageUrl } from '@/utils/imageUrl'
import { useAuthStore } from '@/store/authStore'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { formatApiErrorDetail } from '@/utils/apiErrors'
import { hasRequiredPasswordComplexity } from '@/utils/userValidation'
import { validateUploadFileSize } from '@/utils/uploadLimits'
import {
    Avatar,
    AvatarFallback,
    AvatarImage,
} from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'

const ItemRow = ({ label, children, rightAlign = false, last = false }: any) => (
    <div className={cn(
        'flex items-center py-6',
        !last && 'border-b border-[var(--app-border)]'
    )}>
        <div className="ml-1 w-[140px] shrink-0 text-[13px] font-bold text-muted-foreground">
            {label}
        </div>
        <div className={cn('flex-1 flex items-center min-w-0', rightAlign ? 'justify-end' : 'justify-start')}>
            {children}
        </div>
    </div>
)

const SectionTitle = ({ icon: Icon, title }: any) => (
    <div className="flex items-center gap-2 mb-4 mt-8 first:mt-0">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-[13px] font-black uppercase tracking-widest text-muted-foreground">
            {title}
        </span>
    </div>
)

export function UserDetailPage() {
    const { id } = useParams<{ id: string }>()
    const [user, setUser] = useState<UserType | null>(null)
    const [loading, setLoading] = useState(true)
    const { user: authUser, updateUser } = useAuthStore()
    const { t } = useTranslation()

    const [editingNickname, setEditingNickname] = useState(false)
    const [nicknameValue, setNicknameValue] = useState('')
    const [editingBio, setEditingBio] = useState(false)
    const [bioValue, setBioValue] = useState('')

    const [isPasswordModalVisible, setIsPasswordModalVisible] = useState(false)
    const [oldPassword, setOldPassword] = useState('')
    const [newPassword, setNewPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')

    const fileInputRef = useRef<HTMLInputElement>(null)

    const fetchUser = useCallback(async (userId: number) => {
        try {
            setLoading(true)
            const { data } = await usersApi.getUser(userId)
            setUser(data)
            setNicknameValue(data.nickname || '')
            setBioValue(data.bio || '')
        } catch {
            toast.error(t('users.fetch_detail_failed'))
        } finally {
            setLoading(false)
        }
    }, [t])

    useEffect(() => {
        if (id) {
            fetchUser(parseInt(id))
        }
    }, [id, fetchUser])

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file || !user) return
        if (!validateUploadFileSize(file, 'avatar_max_bytes', t)) return
        try {
            const { data } = await usersApi.uploadAvatar(user.id, file)
            setUser(data)
            if (authUser?.id === data.id) {
                updateUser(data)
            }
            toast.success(t('users.avatar_upload_success'))
        } catch {
            toast.error(t('users.avatar_upload_failed'))
        }
    }

    const saveProfile = async () => {
        if (!user) return
        try {
            const { data } = await usersApi.updateUser(user.id, {
                nickname: nicknameValue.trim(),
                bio: bioValue.trim()
            })
            setUser(data)
            if (authUser?.id === data.id) {
                updateUser(data)
            }
            toast.success(t('users.updateSuccess', '更新成功'))
            setEditingNickname(false)
            setEditingBio(false)
        } catch {
            toast.error(t('users.updateFailed', '更新失败'))
        }
    }

    const handleChangePassword = async () => {
        if (!user) return
        if (!oldPassword || !newPassword || !confirmPassword) {
            toast.error(t('users.fillAllFields'))
            return
        }
        if (newPassword.length < 8) {
            toast.error(t('users.passwordMin', '密码至少 8 位'))
            return
        }
        if (!hasRequiredPasswordComplexity(newPassword)) {
            toast.error(t('users.passwordPattern', '密码需包含大写字母和数字'))
            return
        }
        if (newPassword !== confirmPassword) {
            toast.error(t('users.passwordMismatch', '两次输入的密码不一致'))
            return
        }
        try {
            await usersApi.changePassword(user.id, {
                old_password: oldPassword,
                new_password: newPassword
            })
            toast.success(t('users.passwordChangeSuccess', '密码修改成功'))
            setIsPasswordModalVisible(false)
            setOldPassword('')
            setNewPassword('')
            setConfirmPassword('')
        } catch (error: any) {
            toast.error(formatApiErrorDetail(error?.response?.data?.detail, t('users.passwordChangeFailed', '密码修改失败')))
        }
    }

    if (loading) {
        return (
            <div className="p-10 space-y-8 max-w-[900px]">
                <div className="flex items-center gap-6">
                    <Skeleton className="w-20 h-20 rounded-full" />
                    <div className="space-y-3">
                        <Skeleton className="w-[240px] h-6" />
                        <Skeleton className="w-[360px] h-4" />
                    </div>
                </div>
                <div className="space-y-4">
                    <Skeleton className="w-full h-12 rounded-xl" />
                    <Skeleton className="w-full h-12 rounded-xl" />
                    <Skeleton className="w-full h-12 rounded-xl" />
                </div>
            </div>
        )
    }

    if (!user) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center p-10 text-[var(--app-foreground-subtle)]">
                <UserCircle className="w-16 h-16 mb-4" />
                <h4 className="text-xl font-bold">{t('users.not_found', '用户不存在')}</h4>
            </div>
        )
    }

    const isAdminProfileLocked = user.username === 'admin'

    return (
        <div className="flex-1 flex flex-col h-full overflow-y-auto overflow-x-hidden bg-transparent">
            <div className="px-6 py-10 sm:px-10 max-w-[900px]">


                {/* Main Content Box */}
                <div className="relative rounded-[var(--app-radius-xl)] border border-[var(--app-border)] bg-[var(--app-glass)] p-8 shadow-[var(--app-shadow-panel)] backdrop-blur-2xl transition-all sm:p-12">
                    {/* Basic Info Section */}
                    <SectionTitle icon={UserCircle} title={t('users.basic_info')} />
                    
                    <ItemRow label={t('users.labels.avatar')}>
                        <div
                            className="cursor-pointer relative group"
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <Avatar className="h-20 w-20 border-4 border-[var(--app-border)] bg-[var(--app-control)]">
                                <AvatarImage src={getImageUrl(user.avatar_url)} />
                                <AvatarFallback className="bg-primary/10 text-primary uppercase font-black text-2xl">
                                    {user.nickname?.[0] || user.username[0]}
                                </AvatarFallback>
                            </Avatar>
                            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-[var(--app-media-scrim)] opacity-0 transition-opacity group-hover:opacity-100">
                                <Pencil className="w-6 h-6 text-white" />
                            </div>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={handleFileChange}
                            />
                        </div>
                    </ItemRow>

                    <ItemRow label={t('users.labels.nickname', '昵称')}>
                        {editingNickname ? (
                            <div className="flex gap-2 items-center w-full max-w-[360px]">
                                <Input
                                    value={nicknameValue}
                                    onChange={(e) => setNicknameValue(e.target.value)}
                                    className="h-10 rounded-[var(--app-radius-sm)]"
                                    autoFocus
                                    onKeyDown={(e) => { if (e.key === 'Enter') saveProfile() }}
                                />
                                <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full shrink-0" onClick={saveProfile}>
                                    <Check className="w-4 h-4 text-green-500" />
                                </Button>
                                <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full shrink-0" onClick={() => {
                                    setEditingNickname(false)
                                    setNicknameValue(user.nickname || '')
                                }}>
                                    <X className="w-4 h-4 text-red-500" />
                                </Button>
                            </div>
                        ) : (
                            <div
                                className={cn('flex gap-2 items-center', !isAdminProfileLocked && 'cursor-pointer group')}
                                onClick={isAdminProfileLocked ? undefined : () => setEditingNickname(true)}
                            >
                                <span className="text-[15px] font-bold">{user.nickname}</span>
                                {!isAdminProfileLocked && (
                                    <Pencil className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-60" />
                                )}
                            </div>
                        )}
                    </ItemRow>

                    <ItemRow label={t('users.labels.bio')}>
                        {editingBio ? (
                            <div className="flex gap-2 items-start w-full max-w-[500px]">
                                <textarea
                                    value={bioValue}
                                    onChange={(e) => setBioValue(e.target.value)}
                                    className="min-h-[80px] max-h-[160px] flex-1 resize-none rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-control)] px-3 py-2 text-sm text-foreground outline-none transition focus:border-[var(--app-primary)] focus:ring-2 focus:ring-[var(--app-focus-ring)]"
                                    autoFocus
                                />
                                <div className="flex flex-col gap-1">
                                    <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full" onClick={saveProfile}>
                                        <Check className="w-4 h-4 text-green-500" />
                                    </Button>
                                    <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full" onClick={() => {
                                        setEditingBio(false)
                                        setBioValue(user.bio || '')
                                    }}>
                                        <X className="w-4 h-4 text-red-500" />
                                    </Button>
                                </div>
                            </div>
                        ) : (
                            <div
                                className={cn('flex gap-2 items-start', !isAdminProfileLocked && 'cursor-pointer group')}
                                onClick={isAdminProfileLocked ? undefined : () => setEditingBio(true)}
                            >
                                <span className="text-[14px] leading-relaxed text-[var(--app-foreground-muted)] max-w-[500px]">
                                    {user.bio || t('users.noBio', '暂无简介')}
                                </span>
                                {!isAdminProfileLocked && (
                                    <Pencil className="mt-1 h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-60" />
                                )}
                            </div>
                        )}
                    </ItemRow>

                    <ItemRow label={t('users.labels.username')}>
                        <span className="text-[14px] font-mono text-[var(--app-foreground-subtle)]">{user.username}</span>
                    </ItemRow>

                    <ItemRow label={t('users.labels.id')} last={true}>
                        <span className="text-[14px] font-mono text-[var(--app-foreground-subtle)]">{user.id}</span>
                    </ItemRow>

                    {/* Security Section */}
                    <SectionTitle icon={Lock} title={t('users.security')} />

                    <ItemRow label={t('users.labels.email')}>
                        <span className="text-[14px] font-medium">{user.email}</span>
                    </ItemRow>

                    <ItemRow label={t('users.labels.password')} last={true}>
                        <Button 
                            variant="outline" 
                            size="sm" 
                            onClick={() => setIsPasswordModalVisible(true)}
                            className="rounded-xl px-5 h-9 font-bold"
                        >
                            {t('users.changePassword')}
                        </Button>
                    </ItemRow>

                </div>
            </div>

            <Dialog open={isPasswordModalVisible} onOpenChange={(v) => {
                if (!v) {
                    setIsPasswordModalVisible(false)
                    setOldPassword('')
                    setNewPassword('')
                    setConfirmPassword('')
                }
            }}>
                <DialogContent noDarken className="glass-modal-unified overflow-hidden border p-0 sm:max-w-[420px]">
                    <DialogHeader className="border-b border-[var(--app-border)] p-6 pb-2">
                        <DialogTitle className="text-xl font-bold text-foreground">
                            {t('users.changePassword', '修改密码')}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="p-6 space-y-5">
                        <div className="space-y-2">
                            <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('users.oldPassword', '原密码')}</Label>
                            <Input 
                                type="password" 
                                value={oldPassword} 
                                onChange={(e) => setOldPassword(e.target.value)} 
                                className="h-11 rounded-[var(--app-radius-sm)]"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('users.newPassword', '新密码')}</Label>
                            <Input 
                                type="password" 
                                value={newPassword} 
                                onChange={(e) => setNewPassword(e.target.value)} 
                                className="h-11 rounded-[var(--app-radius-sm)]"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('users.confirmPassword', '确认新密码')}</Label>
                            <Input 
                                type="password" 
                                value={confirmPassword} 
                                onChange={(e) => setConfirmPassword(e.target.value)} 
                                className="h-11 rounded-[var(--app-radius-sm)]"
                            />
                        </div>
                    </div>
                    <DialogFooter className="p-6 pt-2">
                        <div className="flex justify-end gap-3 w-full">
                            <Button 
                                variant="outline" 
                                onClick={() => {
                                    setIsPasswordModalVisible(false)
                                    setOldPassword('')
                                    setNewPassword('')
                                    setConfirmPassword('')
                                }}
                                className="rounded-xl px-6 h-10 font-bold"
                            >
                                {t('users.cancel', '取消')}
                            </Button>
                            <Button 
                                onClick={handleChangePassword}
                                variant="primary"
                                className="h-10 rounded-[var(--app-radius-sm)] px-8 font-bold"
                            >
                                {t('users.submit', '确定')}
                            </Button>
                        </div>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
