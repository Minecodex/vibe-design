import { useState, useEffect, useCallback } from 'react'
import { Pencil, Ban, CheckCircle, Plus, Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usersApi, User } from '@/api/endpoints/users'
import { UserFormModal } from './UserFormModal'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { StatusBadge } from '@/components/common/ui'

interface OrganizationModalProps {
    open: boolean
    onCancel: () => void
}

export function OrganizationModal({ open, onCancel }: OrganizationModalProps) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [data, setData] = useState<User[]>([])
    const [total, setTotal] = useState(0)
    const [page, setPage] = useState(1)
    const [pageSize, setPageSize] = useState(10)
    const [search, setSearch] = useState('')

    const [formModalOpen, setFormModalOpen] = useState(false)
    const [editingUser, setEditingUser] = useState<User | null>(null)

    const fetchData = useCallback(async () => {
        setLoading(true)
        try {
            const res = await usersApi.getUsers({ page, page_size: pageSize, search: search || undefined })
            setData(res.data.items)
            setTotal(res.data.total)
        } catch {
            toast.error(t('organization.fetch_failed', '获取用户列表失败'))
        } finally {
            setLoading(false)
        }
    }, [page, pageSize, search, t])

    useEffect(() => {
        if (open) {
            fetchData()
        }
    }, [open, fetchData])

    const handleSearch = (value: string) => {
        setSearch(value)
        setPage(1)
    }

    const toggleUserStatus = async (record: User) => {
        try {
            await usersApi.updateUser(record.id, { is_active: !record.is_active })
            toast.success(t('organization.status_updated', '状态更新成功'))
            fetchData()
        } catch {
            toast.error(t('organization.status_failed', '状态更新失败'))
        }
    }

    const totalPages = Math.ceil(total / pageSize)

    return (
        <>
            <Dialog open={open} onOpenChange={(v) => { if (!v) onCancel() }}>
                <DialogContent noDarken className={cn(
                    "max-w-[90vw] sm:max-w-[850px] p-0 overflow-hidden flex flex-col max-h-[85vh] glass-modal-unified"
                )}>
                    <DialogHeader className="p-6 pb-2 border-b border-[var(--app-border)] shrink-0">
                        <DialogTitle className="text-xl font-bold">
                            {t('organization.management', '组织管理')}
                        </DialogTitle>
                        <p className="text-sm text-muted-foreground mt-1">
                            {t('organization.description', '查看并更新用户的账号状态与基本信息')}
                        </p>
                    </DialogHeader>

                    <div className="p-6 flex flex-col min-h-0 min-w-0 flex-1">
                        <div className="flex justify-between items-center mb-6 gap-4 shrink-0">
                            <div className="relative flex-1 max-w-[360px]">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                <Input
                                    placeholder={t('organization.search_placeholder', '通过用户名/邮箱/昵称搜索')}
                                    className="pl-9 shrink-0"
                                    value={search}
                                    onChange={(e) => handleSearch(e.target.value)}
                                />
                            </div>
                            <Button
                                variant="primary"
                                onClick={() => {
                                    setEditingUser(null)
                                    setFormModalOpen(true)
                                }}
                                className="px-5 whitespace-nowrap"
                            >
                                <Plus className="w-4 h-4 mr-2" />
                                {t('organization.add_user', '新增用户')}
                            </Button>
                        </div>

                        <div className="overflow-hidden flex-1 flex flex-col min-h-0">
                            <div className="overflow-y-auto flex-1">
                                <Table>
                                    <TableHeader className="sticky top-0 z-10">
                                        <TableRow className="hover:bg-transparent">
                                            <TableHead>{t('users.labels.username', '用户名')}</TableHead>
                                            <TableHead>{t('users.labels.email', '邮箱')}</TableHead>
                                            <TableHead>{t('users.labels.nickname', '昵称')}</TableHead>
                                            <TableHead>{t('organization.status', '状态')}</TableHead>
                                            <TableHead className="w-[180px]">{t('organization.actions', '操作')}</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {loading ? (
                                            <TableRow>
                                                <TableCell colSpan={5} className="text-center py-12 text-muted-foreground italic">
                                                    {t('common.loading', '加载中...')}
                                                </TableCell>
                                            </TableRow>
                                        ) : data.length === 0 ? (
                                            <TableRow>
                                                <TableCell colSpan={5} className="text-center py-12 text-muted-foreground font-medium">
                                                    {t('common.no_data', '暂无数据')}
                                                </TableCell>
                                            </TableRow>
                                        ) : (
                                            data.map((record) => (
                                                <TableRow key={record.id}>
                                                    <TableCell className="font-semibold text-sm py-5">{record.username}</TableCell>
                                                    <TableCell className="text-sm text-[var(--app-foreground-subtle)] py-5">{record.email}</TableCell>
                                                    <TableCell className="text-sm py-5">{record.nickname}</TableCell>
                                                    <TableCell>
                                                        <StatusBadge variant={record.is_active ? 'success' : 'default'}>
                                                            {record.is_active ? t('organization.active', '正常') : t('organization.disabled', '禁用')}
                                                        </StatusBadge>
                                                    </TableCell>
                                                    <TableCell>
                                                        <div className="flex items-center gap-1.5">
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                onClick={() => {
                                                                    setEditingUser(record)
                                                                    setFormModalOpen(true)
                                                                }}
                                                                className="h-8 font-bold text-[12px]"
                                                            >
                                                                <Pencil className="w-3.5 h-3.5 mr-1.5" />
                                                                {t('organization.edit', '修改')}
                                                            </Button>
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                disabled={record.username === 'admin'}
                                                                className={cn(
                                                                    "h-8 font-bold text-[12px]",
                                                                    record.is_active ? 'text-destructive hover:bg-[var(--app-tint-danger)]' : 'text-[var(--app-primary)] hover:bg-[var(--app-tint-primary)]'
                                                                )}
                                                                onClick={() => toggleUserStatus(record)}
                                                            >
                                                                {record.is_active
                                                                    ? <><Ban className="w-3.5 h-3.5 mr-1.5" />{t('organization.disable', '禁用')}</>
                                                                    : <><CheckCircle className="w-3.5 h-3.5 mr-1.5" />{t('organization.enable', '启用')}</>
                                                                }
                                                            </Button>
                                                        </div>
                                                    </TableCell>
                                                </TableRow>
                                            ))
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        </div>

                        {/* Pagination */}
                        <div className="flex items-center justify-between mt-6 shrink-0 px-2">
                            <span className="text-[12px] text-muted-foreground">
                                {t('common.total', '共')} <span className="font-bold text-foreground">{total}</span> {t('common.items', '条')}
                            </span>
                            <div className="flex items-center gap-4">
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        disabled={page <= 1}
                                        onClick={() => setPage(p => p - 1)}
                                        className="h-8 w-8 rounded-full"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                    </Button>
                                    <span className="inline-flex items-center justify-center min-w-[32px] h-8 px-2 rounded-[var(--app-radius-sm)] bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] text-[12px] font-bold shadow-[var(--app-shadow-selected)]">
                                        {page}
                                    </span>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        disabled={page >= totalPages || totalPages === 0}
                                        onClick={() => setPage(p => p + 1)}
                                        className="h-8 w-8 rounded-full"
                                    >
                                        <ChevronRight className="w-4 h-4" />
                                    </Button>
                                </div>
                                <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1) }}>
                                    <SelectTrigger className="w-[100px] h-8 text-[11px] font-bold shrink-0">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="rounded-xl">
                                        <SelectItem value="10">10 {t('common.per_page')}</SelectItem>
                                        <SelectItem value="20">20 {t('common.per_page')}</SelectItem>
                                        <SelectItem value="50">50 {t('common.per_page')}</SelectItem>
                                        <SelectItem value="100">100 {t('common.per_page')}</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            <UserFormModal
                open={formModalOpen}
                user={editingUser}
                onCancel={() => setFormModalOpen(false)}
                onSuccess={() => {
                    setFormModalOpen(false)
                    fetchData()
                }}
            />
        </>
    )
}
