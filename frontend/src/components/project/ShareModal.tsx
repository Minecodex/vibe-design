import { useState } from 'react'
import { Users, Eye, Copy } from 'lucide-react'
import { shareApi } from '@/api/endpoints/share'
import { ProjectRead } from '@/api/endpoints/projects'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface ShareModalProps {
    open: boolean
    onClose: () => void
    project: ProjectRead | null
    onUpdate: (project: ProjectRead) => void
}

function mergeShareProjectUpdate(project: ProjectRead, updatedProject: ProjectRead): ProjectRead {
    return {
        ...project,
        ...updatedProject,
        canvas_data: updatedProject.canvas_data ?? project.canvas_data,
        thumbnail_url: updatedProject.thumbnail_url ?? project.thumbnail_url,
        users: updatedProject.users ?? project.users,
    }
}

export function ShareModal({ open, onClose, project, onUpdate }: ShareModalProps) {
    const { t } = useTranslation()
    const [loadingEditor, setLoadingEditor] = useState(false)
    const [loadingViewer, setLoadingViewer] = useState(false)

    const generateAndCopy = async (permission: 'editor' | 'viewer') => {
        if (!project) return
        const setLoading = permission === 'editor' ? setLoadingEditor : setLoadingViewer
        try {
            setLoading(true)
            const res = await shareApi.generateLink(project.id, permission)
            const updatedProject = mergeShareProjectUpdate(project, res.data)
            onUpdate(updatedProject)
            const link = `${window.location.origin}/share/${updatedProject.share_token}`
            await navigator.clipboard.writeText(link)
            toast.success(t('projectsPage.shareLinkCopied'))
        } catch {
            toast.error(t('projectsPage.shareLinkFailed'))
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
            <DialogContent noDarken className="max-w-[500px] p-0 overflow-hidden glass-modal-unified">
                <div className="p-10 flex flex-col gap-8">
                    <DialogHeader>
                        <DialogTitle className="text-2xl font-bold tracking-tight text-foreground">
                            {t('projectsPage.projectShare')}
                        </DialogTitle>
                    </DialogHeader>

                    <div className="flex flex-col gap-4">
                        <p className="pl-1 text-[14px] font-medium text-muted-foreground">
                           {t('projectsPage.shareLinkHint')}
                        </p>

                        <div className="flex flex-col gap-3">
                            <Button
                                variant="outline"
                                className="flex h-[72px] w-full items-center justify-start gap-4 px-6 text-left"
                                disabled={loadingEditor}
                                onClick={() => generateAndCopy('editor')}
                            >
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--app-tint-primary)]">
                                    <Users className="h-5 w-5 text-[var(--app-primary)]" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-bold text-[15px] text-foreground">{t('projectsPage.shareEditorLink')}</div>
                                    <div className="text-[12px] text-muted-foreground font-medium">{t('projectsPage.shareEditorDesc')}</div>
                                </div>
                                    <Copy className="w-4 h-4 text-[var(--app-foreground-subtle)] shrink-0" />
                            </Button>

                            <Button
                                variant="outline"
                                className="flex h-[72px] w-full items-center justify-start gap-4 px-6 text-left"
                                disabled={loadingViewer}
                                onClick={() => generateAndCopy('viewer')}
                            >
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--app-tint-primary)]">
                                    <Eye className="h-5 w-5 text-[var(--app-primary)]" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-bold text-[15px] text-foreground">{t('projectsPage.shareViewerLink')}</div>
                                    <div className="text-[12px] text-muted-foreground font-medium">{t('projectsPage.shareViewerDesc')}</div>
                                </div>
                                    <Copy className="w-4 h-4 text-[var(--app-foreground-subtle)] shrink-0" />
                            </Button>
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
