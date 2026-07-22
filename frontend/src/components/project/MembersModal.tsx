import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2 } from 'lucide-react'
import { projectMembersApi, ProjectMemberRead } from '@/api/endpoints/projectMembers'
import type { ProjectRead } from '@/api/endpoints/projects'
import { usersApi, User as UserType } from '@/api/endpoints/users'
import { toast } from 'sonner'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
    Avatar,
    AvatarFallback,
    AvatarImage,
} from '@/components/ui/avatar'
import { AppSurface, IconButton } from '@/components/common/ui'

interface MembersModalProps {
    open: boolean
    onClose: () => void
    projectId: number
    ownerUserId: number
    onMembersChange?: (users: NonNullable<ProjectRead['users']>) => void
}

function toProjectUsers(members: ProjectMemberRead[]): NonNullable<ProjectRead['users']> {
    return members.map(member => ({
        id: member.user_id,
        nickname: member.user?.nickname ?? null,
        username: member.user?.username ?? '',
        avatar_url: member.user?.avatar_url ?? null,
        role: member.role,
    }))
}

export function MembersModal({ open, onClose, projectId, ownerUserId, onMembersChange }: MembersModalProps) {
    const { t } = useTranslation()
    const [members, setMembers] = useState<ProjectMemberRead[]>([])
    const [loading, setLoading] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [searchResults, setSearchResults] = useState<UserType[]>([])
    const [searching, setSearching] = useState(false)

    const fetchMembers = useCallback(async () => {
        try {
            setLoading(true)
            const res = await projectMembersApi.list(projectId)
            setMembers(res.data)
            onMembersChange?.(toProjectUsers(res.data))
            return res.data
        } catch {
            toast.error(t('projectsPage.membersLoadFailed'))
        } finally {
            setLoading(false)
        }
    }, [projectId])

    useEffect(() => {
        if (open && projectId) {
            setSearchQuery('')
            setSearchResults([])
            fetchMembers()
        }
    }, [open, projectId, fetchMembers])

    const handleSearch = async (value: string) => {
        setSearchQuery(value)
        if (!value.trim()) {
            setSearchResults([])
            return
        }
        try {
            setSearching(true)
            const res = await usersApi.search(value)
            setSearchResults(res.data)
        } catch {
            toast.error(t('projectsPage.memberSearchFailed'))
        } finally {
            setSearching(false)
        }
    }

    const handleAddMember = async (userId: number) => {
        try {
            await projectMembersApi.add(projectId, { user_id: userId, role: 'editor' })
            toast.success(t('projectsPage.memberAddSuccess'))
            fetchMembers()
            setSearchQuery('')
            setSearchResults([])
        } catch {
            toast.error(t('projectsPage.memberAddFailed'))
        }
    }

    const handleRemoveMember = async (userId: number) => {
        if (userId === ownerUserId) {
            toast.error(t('projectsPage.ownerCannotRemove'))
            return
        }
        try {
            await projectMembersApi.remove(projectId, userId)
            toast.success(t('projectsPage.memberRemoveSuccess'))
            fetchMembers()
        } catch {
            toast.error(t('projectsPage.memberRemoveFailed'))
        }
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
            <DialogContent noDarken className="max-w-[540px] p-0 overflow-hidden glass-modal-unified">
                <div className="p-10 flex flex-col gap-8">
                    <DialogHeader>
                        <DialogTitle className="text-2xl font-bold tracking-tight text-foreground">
                            {t('projectsPage.manageMembers')}
                        </DialogTitle>
                    </DialogHeader>

                    <div className="flex flex-col gap-6">
                        <div className="space-y-2">
                             <label className="pl-1 text-[13px] font-semibold text-muted-foreground">
                                {t('projectsPage.addMember')}
                             </label>
                             <div className="relative">
                                <Input
                                    placeholder={t('projectsPage.addMemberPlaceholder')}
                                    value={searchQuery}
                                    onChange={(e) => handleSearch(e.target.value)}
                                    className="h-14 px-5 text-[15px]"
                                />
                                {searchQuery && (
                                    <div className="absolute left-0 right-0 top-full z-50 mt-2 max-h-56 overflow-auto rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-glass)] p-1.5 shadow-[var(--app-shadow-panel)] backdrop-blur-2xl">
                                        {searching ? (
                                            <div className="p-4 text-sm text-muted-foreground text-center">{t('projectsPage.searching')}</div>
                                        ) : searchResults.length === 0 ? (
                                            <div className="p-4 text-sm text-muted-foreground text-center">{t('projectsPage.noMemberResults')}</div>
                                        ) : (
                                            searchResults.map((u: UserType) => (
                                                <div
                                                    key={u.id}
                                                    className="flex cursor-pointer items-center gap-3 rounded-[var(--app-radius-sm)] px-3 py-2.5 transition-all hover:bg-[var(--app-control-hover)]"
                                                    onClick={() => handleAddMember(u.id)}
                                                >
                                                    <Avatar className="w-8 h-8">
                                                        <AvatarImage src={u.avatar_url || undefined} />
                                                        <AvatarFallback className="bg-blue-500 text-white text-[10px]">{u.nickname?.[0] || u.username?.[0]}</AvatarFallback>
                                                    </Avatar>
                                                    <div className="flex flex-col">
                                                        <span className="text-sm font-medium text-foreground">{u.nickname || u.username}</span>
                                                        <span className="text-xs text-muted-foreground">{u.email}</span>
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                             </div>
                        </div>

                        <div className="space-y-2">
                             <label className="pl-1 text-[13px] font-semibold text-muted-foreground">
                                {t('projectsPage.currentMembers', { count: members.length })}
                             </label>
                             <AppSurface variant="muted" className="max-h-[240px] overflow-y-auto p-1">
                                {loading ? (
                                    <div className="text-center py-10 text-muted-foreground text-sm">{t('projectsPage.loading')}</div>
                                ) : members.length === 0 ? (
                                    <div className="text-center py-10 text-muted-foreground text-sm">{t('projectsPage.noMembers')}</div>
                                ) : (
                                    members.map((item: ProjectMemberRead) => (
                                        <div key={item.user_id} className="flex items-center gap-3 rounded-[var(--app-radius-sm)] px-3 py-2.5 transition-all hover:bg-[var(--app-control-hover)]">
                                            <Avatar className="w-9 h-9 border-2 border-transparent">
                                                <AvatarImage src={item.user?.avatar_url || undefined} />
                                                <AvatarFallback className="bg-indigo-500 text-white text-xs">{item.user?.nickname?.[0] || item.user?.username?.[0]}</AvatarFallback>
                                            </Avatar>
                                            <div className="flex-1 min-w-0">
                                                <div className="truncate text-[14px] font-semibold text-foreground">
                                                    {item.user?.nickname || item.user?.username}
                                                </div>
                                            <div className="text-[12px] text-muted-foreground truncate">
                                                {item.user?.email}
                                            </div>
                                        </div>
                                            
                                            {item.user_id !== ownerUserId && (
                                            <AlertDialog>
                                                <AlertDialogTrigger asChild>
                                                    <IconButton variant="ghost" size="icon" className="h-9 w-9 hover:bg-red-500/10 hover:text-red-500 transition-all">
                                                        <Trash2 className="w-4.5 h-4.5" />
                                                    </IconButton>
                                                </AlertDialogTrigger>
                                                <AlertDialogContent noDarken className="max-w-[420px] p-6">
                                                    <AlertDialogHeader>
                                                        <AlertDialogTitle className="text-lg font-bold">{t('projectsPage.removeMemberTitle')}</AlertDialogTitle>
                                                        <AlertDialogDescription className="pt-1 text-sm">
                                                            {t('projectsPage.removeMemberDesc')}
                                                        </AlertDialogDescription>
                                                    </AlertDialogHeader>
                                                    <AlertDialogFooter className="mt-5 gap-3">
                                                        <AlertDialogCancel className="h-10 px-6">{t('common.cancel')}</AlertDialogCancel>
                                                        <AlertDialogAction 
                                                            onClick={() => handleRemoveMember(item.user_id)}
                                                            variant="destructive"
                                                            className="h-10 px-6"
                                                        >
                                                            {t('projectsPage.removeMemberConfirm')}
                                                        </AlertDialogAction>
                                                    </AlertDialogFooter>
                                                </AlertDialogContent>
                                            </AlertDialog>
                                            )}
                                        </div>
                                    ))
                                )}
                             </AppSurface>
                        </div>
                    </div>

                    <div className="flex justify-end pt-2">
                        <Button 
                            variant="ghost" 
                            onClick={onClose}
                            className="h-12 px-10 text-[15px] font-semibold"
                        >
                            {t('done')}
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
