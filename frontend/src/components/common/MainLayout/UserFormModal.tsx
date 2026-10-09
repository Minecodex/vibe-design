import { apiErrorDetail } from '@/utils/apiErrors'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usersApi, User, UserCreate, UserUpdate } from '@/api/endpoints/users'
import { toast } from 'sonner'
import { formatApiErrorDetail } from '@/utils/apiErrors'
import { hasMinimumUsernameLength, isValidEmail } from '@/utils/userValidation'
import { useAuthStore } from '@/store/authStore'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'

export interface UserFormModalProps {
    open: boolean
    user: User | null
    onCancel: () => void
    onSuccess: () => void
}

export function UserFormModal({ open, user, onCancel, onSuccess }: UserFormModalProps) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)

    const [username, setUsername] = useState('')
    const [email, setEmail] = useState('')
    const [nickname, setNickname] = useState('')
    const [role, setRole] = useState('user')
    const [password, setPassword] = useState('')
    const [isActive, setIsActive] = useState<string>('true')
    const [apimartKey, setApimartKey] = useState('')
    const [apimartKeyStatus, setApimartKeyStatus] = useState<string | null>(null)
    const [apimartKeyHint, setApimartKeyHint] = useState<string | null>(null)
    const [savingApimartKey, setSavingApimartKey] = useState(false)

    useEffect(() => {
        if (open) {
            if (user) {
                setUsername(user.username)
                setEmail(user.email)
                setNickname(user.nickname || '')
                setRole(user.role)
                setPassword('')
                setIsActive(user.is_active ? 'true' : 'false')
                setApimartKey('')
                setApimartKeyStatus(null)
                setApimartKeyHint(null)
                usersApi.getApimartKeyStatus(user.id).then(({ data }) => {
                    setApimartKeyStatus(data.status || (data.configured ? 'active' : null))
                    setApimartKeyHint(data.key_hint || null)
                }).catch(() => undefined)
            } else {
                setUsername('')
                setEmail('')
                setNickname('')
                setRole('user')
                setPassword('')
                setIsActive('true')
                setApimartKey('')
                setApimartKeyStatus(null)
                setApimartKeyHint(null)
            }
        }
    }, [open, user])

    const handleOk = async () => {
        if (!username.trim()) {
            toast.error(t('register.username_required', '请输入用户名'))
            return
        }
        if (!hasMinimumUsernameLength(username)) {
            toast.error(t('register.username_min', '用户名至少 6 个字符'))
            return
        }
        if (!email.trim()) {
            toast.error(t('register.email_required', '请输入邮箱'))
            return
        }
        if (!isValidEmail(email.trim())) {
            toast.error(t('register.email_invalid', '请输入有效的邮箱地址'))
            return
        }

        try {
            setLoading(true)
            if (user) {
                const updateData: UserUpdate = {
                    username,
                    email,
                    nickname,
                    role,
                    is_active: isActive === 'true',
                }
                if (password) {
                    updateData.password = password
                }
                await usersApi.updateUser(user.id, updateData)
                toast.success(t('organization.update_success', '用户更新成功'))
            } else {
                const createData: UserCreate = {
                    username,
                    email,
                    nickname,
                    password: '123456',
                    role: 'user',
                }
                await usersApi.createUser(createData)
                toast.success(t('organization.create_success', '用户创建成功'))
            }
            onSuccess()
        } catch (error) {
            toast.error(formatApiErrorDetail(apiErrorDetail(error), t('organization.operation_failed', '操作失败')))
        } finally {
            setLoading(false)
        }
    }

    const handleSaveApimartKey = async () => {
        if (!user || !apimartKey.trim()) {
            toast.error(t('organization.apimart_key_required', '请输入 APIMart Key'))
            return
        }
        try {
            setSavingApimartKey(true)
            const { data } = await usersApi.setApimartKey(user.id, apimartKey.trim())
            setApimartKey('')
            setApimartKeyStatus(data.status || 'active')
            setApimartKeyHint(data.key_hint || null)
            toast.success(t('organization.apimart_key_saved', 'APIMart Key 已保存'))
        } catch (error) {
            toast.error(formatApiErrorDetail(apiErrorDetail(error), t('organization.apimart_key_failed', 'APIMart Key 保存失败')))
        } finally {
            setSavingApimartKey(false)
        }
    }

    const handleRevokeApimartKey = async () => {
        if (!user) return
        try {
            setSavingApimartKey(true)
            await usersApi.revokeApimartKey(user.id)
            setApimartKeyStatus(null)
            setApimartKeyHint(null)
            const authState = useAuthStore.getState()
            if (authState.user?.id === user.id) {
                authState.updateUser({ ...authState.user, balance_cents: 0 })
            }
            toast.success(t('organization.apimart_key_revoked', 'APIMart Key 已撤销'))
        } catch (error) {
            toast.error(formatApiErrorDetail(apiErrorDetail(error), t('organization.apimart_key_failed', 'APIMart Key 操作失败')))
        } finally {
            setSavingApimartKey(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) onCancel() }}>
            <DialogContent noDarken className="sm:max-w-[480px] p-0 overflow-hidden glass-modal-unified">
                <DialogHeader className="p-6 pb-2 border-b border-[var(--app-border)] shrink-0">
                    <DialogTitle className="text-xl font-bold text-foreground">
                        {user ? t('organization.edit_user', '编辑用户') : t('organization.add_user', '新增用户')}
                    </DialogTitle>
                </DialogHeader>

                <div className="p-6 space-y-6">
                    <div className="space-y-2">
                        <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('users.labels.username', '用户名')}</Label>
                        <Input
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="h-11"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('users.labels.email', '邮箱')}</Label>
                        <Input
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            type="email"
                            className="h-11"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('users.labels.nickname', '昵称')}</Label>
                        <Input
                            value={nickname}
                            onChange={(e) => setNickname(e.target.value)}
                            className="h-11"
                        />
                    </div>
                    {user && (
                        <>
                            <div className="space-y-2">
                                <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('organization.new_password', '新密码 (不修改请留空)')}</Label>
                                <Input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="h-11"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)] ml-1">{t('organization.status', '状态')}</Label>
                                <Select value={isActive} onValueChange={setIsActive} disabled={user.username === 'admin'}>
                                    <SelectTrigger className="h-11 w-full">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="rounded-xl">
                                        <SelectItem value="true">{t('organization.status_enable', '启用')}</SelectItem>
                                        <SelectItem value="false">{t('organization.status_disable', '禁用')}</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-3 rounded-xl border border-[var(--app-border)] p-4">
                                <div className="flex items-center justify-between gap-3">
                                    <div>
                                        <Label className="text-[13px] font-bold text-[var(--app-foreground-muted)]">{t('organization.apimart_key', 'APIMart Key')}</Label>
                                        <p className="mt-1 text-xs text-muted-foreground">
                                            {apimartKeyHint || t('organization.apimart_key_unconfigured', '未配置')}
                                            {apimartKeyStatus ? ` · ${apimartKeyStatus}` : ''}
                                        </p>
                                    </div>
                                    {apimartKeyStatus ? (
                                        <Button type="button" variant="ghost" size="sm" disabled={savingApimartKey} onClick={handleRevokeApimartKey}>
                                            {t('organization.apimart_key_revoke', '撤销')}
                                        </Button>
                                    ) : null}
                                </div>
                                <Input
                                    type="password"
                                    value={apimartKey}
                                    onChange={(e) => setApimartKey(e.target.value)}
                                    placeholder={t('organization.apimart_key_placeholder', '输入 APIMart Key')}
                                    className="h-11"
                                    autoComplete="new-password"
                                />
                                <Button type="button" variant="outline" disabled={savingApimartKey || !apimartKey.trim()} onClick={handleSaveApimartKey}>
                                    {savingApimartKey ? t('common.saving', '保存中...') : t('organization.apimart_key_save', '保存 APIMart Key')}
                                </Button>
                            </div>
                        </>
                    )}
                </div>

                <DialogFooter className="p-6 pt-2 shrink-0">
                    <div className="flex justify-end gap-3 w-full">
                        <Button
                            variant="outline"
                            onClick={onCancel}
                            className="rounded-xl px-6 h-10 font-bold"
                        >
                            {t('common.cancel', '取消')}
                        </Button>
                        <Button
                            onClick={handleOk}
                            disabled={loading}
                            variant="primary"
                            className="px-8 font-bold"
                        >
                            {loading ? t('common.saving', '保存中...') : t('common.confirm', '确定')}
                        </Button>
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
