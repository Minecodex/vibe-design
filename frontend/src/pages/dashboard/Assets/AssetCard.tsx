import { useState, useRef } from 'react';
import { Download, Heart, Trash2, Settings, Video, ImageIcon } from 'lucide-react';
import { type AssetRead, assetsApi, getAssetListMediaUrl } from '@/api/endpoints/assets';
import { useTranslation } from 'react-i18next';
import { useIsDarkMode } from '@/hooks/useTheme';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { DeleteAssetsConfirmDialog } from './DeleteAssetsConfirmDialog';
import { CachedImage } from '@/components/ui/CachedImage';
import { StatusBadge } from '@/components/common/ui';
import {
    ContextMenu,
    ContextMenuContent,
    ContextMenuItem,
    ContextMenuSeparator,
    ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { Checkbox } from '@/components/ui/checkbox';

interface AssetCardProps {
    asset: AssetRead;
    isBatchMode: boolean;
    isSelected: boolean;
    onSelect: (selected: boolean) => void;
    onRefresh: () => void;
    projectId?: number;
    activeTab?: string;
    onClick?: (assetId: number) => void;
}

export function AssetCard({
    asset,
    isBatchMode,
    isSelected,
    onSelect,
    onRefresh,
    projectId,
    activeTab,
    onClick
}: AssetCardProps) {
    const { t } = useTranslation();
    useIsDarkMode();
    const [isHovered, setIsHovered] = useState(false);
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
    const videoRef = useRef<HTMLVideoElement>(null);
    const listMediaUrl = getAssetListMediaUrl(asset)

    const [duration, setDuration] = useState<string>('');

    const formatDuration = (seconds: number) => {
        if (isNaN(seconds)) return '00:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    const formatCreatedAt = (dateStr: string) => {
        const now = new Date();
        const safeDateStr = dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T');
        const date = new Date(safeDateStr);
        const diffMs = now.getTime() - date.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
        } else if (diffDays === 1) {
            return t('yesterday', 'Yesterday');
        } else if (diffDays < 7) {
            return t('days_ago', '{{count}} days ago', { count: diffDays });
        } else {
            return date.toLocaleDateString();
        }
    };

    const handleLoadedMetadata = () => {
        if (videoRef.current) {
            setDuration(formatDuration(videoRef.current.duration));
        }
    };

    const handleMouseEnter = () => {
        setIsHovered(true);
        if (asset.asset_type === 'video' && videoRef.current) {
            videoRef.current.play().catch(() => { });
        }
    };

    const handleMouseLeave = () => {
        setIsHovered(false);
        if (asset.asset_type === 'video' && videoRef.current) {
            videoRef.current.pause();
            videoRef.current.currentTime = 0;
        }
    };


    const handleAction = async (action: 'favorite' | 'download' | 'delete' | 'copy') => {
        try {
            if (action === 'delete') {
                if (projectId) {
                    await assetsApi.batch(projectId, { asset_ids: [asset.id], action: 'delete' });
                } else {
                    await assetsApi.globalBatch({ asset_ids: [asset.id], action: 'delete' });
                }
                toast.success(t('delete_success', 'Deleted successfully'));
                onRefresh();
            } else if (action === 'favorite') {
                const newAction = asset.is_favorite ? 'unfavorite' : 'favorite';
                if (projectId) {
                    await assetsApi.batch(projectId, { asset_ids: [asset.id], action: newAction });
                } else {
                    await assetsApi.globalBatch({ asset_ids: [asset.id], action: newAction });
                }
                toast.success(t('favorite_updated', 'Favorite status updated'));
                onRefresh();
            } else if (action === 'download') {
                const response = await fetch(asset.url);
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `asset_${asset.id}.${asset.asset_type === 'video' ? 'mp4' : 'png'}`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else if (action === 'copy') {
                await navigator.clipboard.writeText(asset.url);
                toast.success(t('copied_to_clipboard', 'Copied to clipboard'));
            }
        } catch (err: unknown) {
            const error = err as { response?: { data?: { detail?: string } } };
            toast.error(error.response?.data?.detail || t('action_failed', 'Action failed'));
        }
    };

    const handleCardClick = () => {
        if (isBatchMode) {
            onSelect(!isSelected);
        } else if (onClick) {
            onClick(asset.id);
        }
    };

    const cardContent = (
        <div
            className={cn(
                'group relative aspect-square min-w-[250px] min-h-[250px] w-full cursor-pointer overflow-hidden rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-surface-solid)] shadow-sm transition-all duration-300 hover:z-10 hover:scale-[1.02] hover:border-[var(--app-border-strong)] hover:shadow-[var(--app-shadow-panel)]'
            )}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            onClick={handleCardClick}
        >
            {/* Media Container */}
            <div className="absolute inset-0 bg-black overflow-hidden h-full w-full">
                {asset.asset_type === 'video' ? (
                    <video
                        ref={videoRef}
                        src={asset.url}
                        className="w-full h-full object-cover"
                        muted
                        loop
                        playsInline
                        onLoadedMetadata={handleLoadedMetadata}
                    />
                ) : (
                    <CachedImage src={listMediaUrl} alt="Asset" className="w-full h-full object-cover" />
                )}

                {/* Local Upload Badge */}
                {asset.origin_kind === 'local_upload' && (
                    <div className="absolute top-4 left-4 z-20">
                      <StatusBadge variant="default" className="border border-[color-mix(in_srgb,var(--app-border)_55%,transparent)] bg-[color-mix(in_srgb,var(--app-bg)_72%,transparent)] text-[10px] uppercase tracking-widest text-foreground backdrop-blur-md">
                        {t('local_upload_badge', '本地上传')}
                      </StatusBadge>
                    </div>
                )}

                {/* Batch Checkbox */}
                {isBatchMode && (
                    <div className={cn(
                        'absolute top-4 left-4 z-30 transition-all duration-300',
                        isSelected ? 'opacity-100 scale-110' : 'opacity-80 scale-100'
                    )}>
                        <div className={cn(
                            "w-6 h-6 rounded-md flex items-center justify-center transition-all",
                            isSelected
                                ? "bg-[var(--app-primary)] border-[var(--app-primary)] shadow-lg shadow-[var(--app-tint-primary-hover)]" 
                                : "border-2 border-[color-mix(in_srgb,var(--app-primary-foreground)_78%,transparent)] bg-[color-mix(in_srgb,var(--app-primary-foreground)_42%,transparent)] backdrop-blur-md"
                        )}>
                            {isSelected && <Checkbox checked={true} className="border-none w-4 h-4 shadow-none data-[state=checked]:bg-transparent data-[state=checked]:text-white" />}
                        </div>
                    </div>
                )}

                {activeTab === 'all' && (
                    <div className="absolute top-4 right-4 z-20">
                        <div className="flex h-8 w-8 items-center justify-center rounded-[var(--app-radius-xs)] border border-[color-mix(in_srgb,var(--app-primary-foreground)_22%,transparent)] bg-[color-mix(in_srgb,var(--app-bg)_34%,transparent)] text-[var(--app-primary-foreground)]/80 backdrop-blur-sm">
                            {asset.asset_type === 'video' ? <Video className="w-4 h-4" /> : <ImageIcon className="w-4 h-4" />}
                        </div>
                    </div>
                )}

                <div className="pointer-events-none absolute inset-0 z-20 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                <div className="invisible absolute inset-0 z-20 group-hover:visible">
                    <div className="absolute bottom-4 left-4 right-4 translate-y-3 transition-transform duration-150 group-hover:translate-y-0">
                        <div className="flex h-14 w-full items-center gap-3 rounded-[var(--app-radius-md)] border border-[color-mix(in_srgb,var(--app-primary-foreground)_16%,transparent)] bg-[color-mix(in_srgb,var(--app-bg)_44%,transparent)] p-3 text-[var(--app-primary-foreground)] backdrop-blur-2xl">
                            {/* Creator Avatar */}
                            <div className="flex-shrink-0">
                                {asset.adder_avatar ? (
                                    <img src={asset.adder_avatar} alt="avatar" className="h-8 w-8 rounded-full border border-[color-mix(in_srgb,var(--app-primary-foreground)_22%,transparent)] object-cover" />
                                ) : (
                                    <div className="flex h-8 w-8 items-center justify-center rounded-full border border-[color-mix(in_srgb,var(--app-primary-foreground)_22%,transparent)] bg-[var(--app-primary)] text-xs font-bold text-[var(--app-primary-foreground)]">
                                        {asset.adder_nickname?.charAt(0) || 'U'}
                                    </div>
                                )}
                            </div>

                            {/* Creator & Project Info */}
                            <div className="flex flex-col min-w-0 flex-1">
                                <span className="text-sm font-semibold truncate">
                                    {asset.adder_nickname || t('unknown_user', 'Unknown')}
                                </span>
                                {asset.project_name && (
                                    <span className="text-[11px] font-medium text-[var(--app-media-foreground-muted)] truncate">
                                        {asset.project_name}
                                    </span>
                                )}
                            </div>

                            {/* Creation Time (Far Right) */}
                            <div className="flex-shrink-0 text-[11px] font-medium text-[var(--app-media-foreground-muted)]">
                                {formatCreatedAt(asset.updated_at || asset.created_at)}
                            </div>
                        </div>
                    </div>
                </div>

                {isHovered && !isBatchMode && asset.asset_type === 'video' && (
                    <>
                        {duration && (
                            <div className="absolute right-4 top-14 z-20 rounded-[var(--app-radius-xs)] border border-[color-mix(in_srgb,var(--app-primary-foreground)_16%,transparent)] bg-[color-mix(in_srgb,var(--app-bg)_44%,transparent)] px-2 py-1 text-[10px] font-medium text-[var(--app-primary-foreground)] backdrop-blur-md">
                                {duration}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );

    return (
        <>
            {isBatchMode ? (
                cardContent
            ) : (
                <ContextMenu>
                    <ContextMenuTrigger asChild>
                        {cardContent}
                    </ContextMenuTrigger>
                    <ContextMenuContent className="w-56 rounded-[var(--app-radius-md)] p-1.5">
                        <ContextMenuItem 
                            onClick={() => handleAction('download')}
                            className="py-2.5 transition-all cursor-pointer"
                        >
                            <Download className="w-4 h-4 mr-3" />
                            <span className="font-medium">{t('download', 'Download')}</span>
                        </ContextMenuItem>

                        <ContextMenuItem 
                            onClick={() => handleAction('favorite')}
                            className="py-2.5 transition-all cursor-pointer"
                        >
                            <Heart className={cn('w-4 h-4 mr-3', asset.is_favorite && 'text-[var(--app-primary)] fill-[var(--app-primary)]')} />
                            <span className="font-medium">{asset.is_favorite ? t('unfavorite', 'Unfavorite') : t('favorite', 'Favorite')}</span>
                        </ContextMenuItem>

                        <ContextMenuSeparator className="my-1" />
                        
                        <ContextMenuItem 
                            onClick={() => handleAction('copy')}
                            className="py-2.5 transition-all cursor-pointer"
                        >
                            <Settings className="w-4 h-4 mr-3" />
                            <span className="font-medium">{t('copy_link', 'Copy Link')}</span>
                        </ContextMenuItem>

                        <ContextMenuSeparator className="my-1" />
                        
                        <ContextMenuItem 
                            variant="destructive"
                            className="py-2.5 transition-all cursor-pointer"
                            onClick={() => setIsDeleteDialogOpen(true)}
                        >
                            <Trash2 className="w-4 h-4 mr-3" />
                            <span className="font-medium">{t('delete', 'Delete')}</span>
                        </ContextMenuItem>
                    </ContextMenuContent>
                </ContextMenu>
            )}
            <DeleteAssetsConfirmDialog
                count={1}
                open={isDeleteDialogOpen}
                onOpenChange={setIsDeleteDialogOpen}
                onConfirm={() => void handleAction('delete')}
                variant="single"
            />
        </>
    );
}
