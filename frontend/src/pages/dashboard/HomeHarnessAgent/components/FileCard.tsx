import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { type WorkspaceFileRead } from '@/api/endpoints/agent'
import {
    Presentation,
    FileText,
    TableProperties,
    LayoutTemplate,
    FileCode,
    File,
    Image,
    Video,
    Download,
    Play,
} from 'lucide-react'
import { useHarnessMediaSource } from './useHarnessMediaSource'
import { inferHomeHarnessAttachmentKind } from './homeChatAttachmentKinds'

interface FileCardProps {
    conversationId?: string | number | null
    file: WorkspaceFileRead
    previewUrl?: string
    isDark: boolean
    onDownload?: (file: WorkspaceFileRead) => void
    onClick?: (file: WorkspaceFileRead) => void
}

const FILE_TYPE_CONFIG: Record<string, { icon: typeof File; color: string; bg: string }> = {
    ppt: { icon: Presentation, color: 'text-rose-500', bg: 'bg-rose-500' },
    pptx: { icon: Presentation, color: 'text-rose-500', bg: 'bg-rose-500' },
    presentation: { icon: Presentation, color: 'text-rose-500', bg: 'bg-rose-500' },
    document: { icon: FileText, color: 'text-indigo-500', bg: 'bg-indigo-500' },
    doc: { icon: FileText, color: 'text-indigo-500', bg: 'bg-indigo-500' },
    docx: { icon: FileText, color: 'text-indigo-500', bg: 'bg-indigo-500' },
    spreadsheet: { icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500' },
    sheet: { icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500' },
    xls: { icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500' },
    xlsx: { icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500' },
    csv: { icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500' },
    web: { icon: LayoutTemplate, color: 'text-purple-500', bg: 'bg-purple-500' },
    html: { icon: LayoutTemplate, color: 'text-purple-500', bg: 'bg-purple-500' },
    htm: { icon: LayoutTemplate, color: 'text-purple-500', bg: 'bg-purple-500' },
    code: { icon: FileCode, color: 'text-blue-500', bg: 'bg-blue-500' },
    text: { icon: FileText, color: 'text-zinc-500', bg: 'bg-zinc-500' },
    image: { icon: Image, color: 'text-purple-500', bg: 'bg-purple-500' },
    video: { icon: Video, color: 'text-sky-500', bg: 'bg-sky-500' },
    other: { icon: File, color: 'text-zinc-400', bg: 'bg-zinc-400' },
}

function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

function inferWorkspaceFileKind(file: WorkspaceFileRead): 'image' | 'video' | 'other' {
    const kind = inferHomeHarnessAttachmentKind(file)
    if (kind === 'image') {
        return 'image'
    }
    if (kind === 'video') {
        return 'video'
    }
    return 'other'
}

type RepresentativeFileKind = 'spreadsheet' | 'document' | 'presentation' | 'html' | 'code' | 'text'

function inferRepresentativeFileKind(file: WorkspaceFileRead): RepresentativeFileKind | null {
    const kind = inferHomeHarnessAttachmentKind(file)
    if (kind === 'spreadsheet' || kind === 'document' || kind === 'presentation' || kind === 'html' || kind === 'code' || kind === 'text') {
        return kind
    }
    return null
}

function RepresentativeFileIcon({ kind, isDark }: { kind: RepresentativeFileKind; isDark: boolean }) {
    const modeConfig = {
        spreadsheet: {
            icon: TableProperties,
            color: 'text-emerald-500',
            bg: isDark ? 'bg-emerald-500/10' : 'bg-emerald-50',
            testId: 'workspace-file-spreadsheet-icon',
        },
        document: {
            icon: FileText,
            color: 'text-indigo-500',
            bg: isDark ? 'bg-indigo-500/10' : 'bg-indigo-50',
            testId: 'workspace-file-document-icon',
        },
        presentation: {
            icon: Presentation,
            color: 'text-rose-500',
            bg: isDark ? 'bg-rose-500/10' : 'bg-rose-50',
            testId: 'workspace-file-presentation-icon',
        },
        html: {
            icon: LayoutTemplate,
            color: 'text-purple-500',
            bg: isDark ? 'bg-purple-500/10' : 'bg-purple-50',
            testId: 'workspace-file-html-icon',
        },
        code: {
            icon: FileCode,
            color: 'text-blue-500',
            bg: isDark ? 'bg-blue-500/10' : 'bg-blue-50',
            testId: 'workspace-file-code-icon',
        },
        text: {
            icon: FileText,
            color: 'text-zinc-500',
            bg: isDark ? 'bg-zinc-500/10' : 'bg-zinc-50',
            testId: 'workspace-file-text-icon',
        },
    }[kind]
    const ModeIcon = modeConfig.icon

    return (
        <div
            data-testid={modeConfig.testId}
            className={cn(
                'w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 shadow-sm transition-all',
                modeConfig.bg,
                modeConfig.color,
            )}
        >
            <ModeIcon className="w-6 h-6" />
        </div>
    )
}

export function FileCard({ conversationId, file, previewUrl, isDark, onDownload, onClick }: FileCardProps) {
    const mediaKind = inferWorkspaceFileKind(file)
    const representativeKind = inferRepresentativeFileKind(file)
    const fileTypeKey = representativeKind || String(file.type || '').toLowerCase()
    const config = FILE_TYPE_CONFIG[fileTypeKey] || FILE_TYPE_CONFIG[mediaKind] || FILE_TYPE_CONFIG.other
    const Icon = config.icon
    const [resolvedSize, setResolvedSize] = useState<number>(file.size)
    const displayPreviewUrl = useHarnessMediaSource(conversationId, previewUrl || file.path)

    useEffect(() => {
        setResolvedSize(file.size)
    }, [file.size, file.path])

    useEffect(() => {
        if (file.size > 0 || !displayPreviewUrl) {
            return
        }

        let cancelled = false

        const resolveSize = async () => {
            try {
                const headResponse = await fetch(displayPreviewUrl, { method: 'HEAD' })
                const contentLength = Number(headResponse.headers.get('content-length') || '')
                if (!cancelled && Number.isFinite(contentLength) && contentLength > 0) {
                    setResolvedSize(contentLength)
                    return
                }
            } catch {
                // Fall back to downloading the response when HEAD metadata is unavailable.
            }

            try {
                const response = await fetch(displayPreviewUrl)
                const blob = await response.blob()
                if (!cancelled && blob.size > 0) {
                    setResolvedSize(blob.size)
                }
            } catch {
                // Leave the original size when preview metadata cannot be resolved.
            }
        }

        void resolveSize()

        return () => {
            cancelled = true
        }
    }, [displayPreviewUrl, file.size])

    return (
        <div
            onClick={() => onClick?.(file)}
            className={cn(
                'flex items-center gap-3 p-3 rounded-xl transition-all group cursor-pointer hover:bg-[var(--app-control-hover)]',
            )}
        >
            {mediaKind === 'image' && displayPreviewUrl ? (
                <div className="app-card-muted w-14 h-14 rounded-xl overflow-hidden shrink-0">
                    <img
                        src={displayPreviewUrl}
                        alt={file.name}
                        className="w-full h-full object-cover"
                    />
                </div>
            ) : mediaKind === 'video' && displayPreviewUrl ? (
                <div className="app-card-muted relative w-14 h-14 rounded-xl overflow-hidden shrink-0">
                    <video
                        data-testid="workspace-file-video-preview"
                        src={displayPreviewUrl}
                        className="w-full h-full object-cover"
                        muted
                        playsInline
                        preload="metadata"
                    />
                    <div className="app-media-scrim absolute inset-0 flex items-center justify-center">
                        <Play className="w-4 h-4 text-white fill-white" />
                    </div>
                </div>
            ) : representativeKind ? (
                <RepresentativeFileIcon kind={representativeKind} isDark={isDark} />
            ) : (
                <div className={cn(
                    'w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-white shadow-sm',
                    config.bg,
                )}>
                    <Icon className="w-5 h-5" />
                </div>
            )}
            <div className="flex-1 min-w-0">
                <p className={cn(
                    'text-sm font-medium truncate',
                    isDark ? 'text-zinc-200' : 'text-zinc-800',
                )}>
                    {file.name}
                </p>
                <p className="text-xs text-zinc-500">
                    {formatFileSize(resolvedSize)}
                </p>
            </div>
            <button
                aria-label={`Download ${file.name}`}
                onClick={(e) => {
                    e.stopPropagation()
                    onDownload?.(file)
                }}
                className={cn(
                    'app-muted p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--app-control-hover)]',
                )}
            >
                <Download className="w-4 h-4" />
            </button>
        </div>
    )
}

interface FileListProps {
    files: WorkspaceFileRead[]
    isDark: boolean
    onDownload?: (file: WorkspaceFileRead) => void
    onClick?: (file: WorkspaceFileRead) => void
}

export function FileList({ files, isDark, onDownload, onClick }: FileListProps) {
    if (files.length === 0) return null

    return (
        <div className={cn(
            'app-card overflow-hidden rounded-2xl',
        )}>
            <div className={cn(
                'app-divider app-muted px-4 py-2.5 border-b text-xs font-medium',
            )}>
                Files ({files.length})
            </div>
            <div className="p-1">
                {files.map((file) => (
                    <FileCard
                        conversationId={undefined}
                        key={file.path}
                        file={file}
                        previewUrl={undefined}
                        isDark={isDark}
                        onDownload={onDownload}
                        onClick={onClick}
                    />
                ))}
            </div>
        </div>
    )
}
