import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { apiClient } from '@/api/client'
import { Loader2, Download, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ResultPreviewDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    taskId: number | null
}

interface TaskStatus {
    status: string
    result_url: string | null
    task_type: string
}

export function ResultPreviewDialog({ open, onOpenChange, taskId }: ResultPreviewDialogProps) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [data, setData] = useState<TaskStatus | null>(null)

    useEffect(() => {
        if (open && taskId) {
            fetchStatus()
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, taskId])

    const fetchStatus = async () => {
        setLoading(true)
        try {
            const res = await apiClient.get<TaskStatus>(`/generation-tasks/${taskId}/status`)
            setData(res.data)
        } catch (e) {
            console.error('Failed to fetch task status', e)
        } finally {
            setLoading(false)
        }
    }

    const isImage = data?.task_type === 'text2image' || (data?.result_url && (data.result_url.endsWith('.png') || data.result_url.endsWith('.jpg') || data.result_url.endsWith('.jpeg') || data.result_url.endsWith('.webp')))
    const isVideo = data?.task_type === 'text2video' || data?.task_type === 'image2video' || (data?.result_url && (data.result_url.endsWith('.mp4') || data.result_url.endsWith('.webm')))

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent noDarken className="max-w-[800px] w-[95vw] max-h-[90vh] flex flex-col p-0 overflow-hidden glass-modal-unified">
                <DialogHeader className="p-4 border-b border-[var(--app-border)] shrink-0">
                    <DialogTitle className="text-xl font-bold text-foreground">
                        {t('billing.preview_result')}
                    </DialogTitle>
                </DialogHeader>
                <div className="flex-1 overflow-auto p-8 flex flex-col items-center justify-center min-h-[400px]">
                    {loading ? (
                        <div className="flex flex-col items-center gap-4">
                            <Loader2 className="w-10 h-10 animate-spin text-primary" />
                            <span className="text-sm font-medium text-[var(--app-foreground-subtle)]">{t('common.loading')}</span>
                        </div>
                    ) : !data?.result_url ? (
                        <div className="flex flex-col items-center text-center text-[var(--app-foreground-subtle)]">
                            <p className="text-lg font-bold mb-1">{t('billing.no_result')}</p>
                        </div>
                    ) : (
                        <div className="relative w-full h-full flex items-center justify-center group">
                            {isVideo ? (
                                <video
                                    src={data.result_url}
                                    controls
                                    className="max-w-full max-h-[55vh] rounded-2xl shadow-2xl transition-transform hover:scale-[1.01]"
                                    autoPlay
                                />
                            ) : isImage ? (
                                <img
                                    src={data.result_url}
                                    alt="Result"
                                    className="max-w-full max-h-[55vh] object-contain rounded-2xl shadow-2xl transition-transform hover:scale-[1.01]"
                                />
                            ) : (
                                <div className="flex flex-col items-center gap-6 rounded-[var(--app-radius-xl)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] p-10">
                                    <p className="text-center text-[var(--app-foreground-muted)] max-w-[400px] leading-relaxed">
                                        {t('billing.unsupported_format')}
                                    </p>
                                    <Button asChild variant="primary" className="px-10 font-bold">
                                        <a href={data.result_url} target="_blank" rel="noreferrer">
                                            <ExternalLink className="w-4 h-4 mr-2" />
                                            {t('common.open_link')}
                                        </a>
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}
                </div>
                {data?.result_url && (
                    <div className="p-6 border-t border-[var(--app-border)] flex justify-end gap-3 shrink-0">
                        <Button 
                            variant="outline" 
                            asChild 
                            className="px-6 font-bold"
                        >
                            <a href={data.result_url} target="_blank" rel="noreferrer">
                                <ExternalLink className="w-4 h-4 mr-2" />
                                {t('billing.view_original')}
                            </a>
                        </Button>
                        <Button 
                            asChild 
                            variant="primary"
                            className="px-10 font-bold"
                        >
                            <a href={data.result_url} download={`task_${taskId}`}>
                                <Download className="w-4 h-4 mr-2" />
                                {t('common.download')}
                            </a>
                        </Button>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    )
}
