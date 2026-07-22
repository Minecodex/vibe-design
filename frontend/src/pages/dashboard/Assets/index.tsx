import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { assetsApi, type AssetProjectSummaryRead, type AssetRead } from '@/api/endpoints/assets';
import { streamRealtimeEvents } from '@/api/endpoints/realtime';
import { AssetGrid } from './AssetGrid';
import { ProjectFolderGrid } from './ProjectFolderGrid';
import { AssetPreviewModal } from '@/components/project/AssetPreviewModal';
import { useTranslation } from 'react-i18next';
import { useIsDarkMode } from '@/hooks/useTheme';
import { Video, ImageIcon, LayoutGrid, Download, Trash2, FolderOpen, ChevronLeft, Heart } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { DeleteAssetsConfirmDialog } from './DeleteAssetsConfirmDialog';
import { EmptyState, IconButton, SegmentedControl } from '@/components/common/ui';

export function AssetsPage() {
    const pageSize = 24;
    const { t } = useTranslation();
    useIsDarkMode();

    const [viewMode, setViewMode] = useState<'grid' | 'folder'>('grid');
    const [selectedProjectId, setSelectedProjectId] = useState<number | undefined>();
    const [selectedProjectName, setSelectedProjectName] = useState<string | undefined>();
    const [activeTab, setActiveTab] = useState<'all' | 'image' | 'video'>('all');
    const [originKind, setOriginKind] = useState<'ai_generated' | 'local_upload'>('ai_generated');
    const [favoritesOnly, setFavoritesOnly] = useState(false);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(false);
    const [skip, setSkip] = useState(0);
    const [assets, setAssets] = useState<AssetRead[]>([]);
    const [projectSummaries, setProjectSummaries] = useState<AssetProjectSummaryRead[]>([]);

    const [isBatchMode, setIsBatchMode] = useState(false);
    const [isBatchDeleteDialogOpen, setIsBatchDeleteDialogOpen] = useState(false);
    const [selectedAssets, setSelectedAssets] = useState<Set<number>>(new Set());
    const [previewIndex, setPreviewIndex] = useState<number | null>(null);
    const loadMoreRef = useRef<HTMLDivElement | null>(null);
    const scrollContainerRef = useRef<HTMLDivElement | null>(null);

    const currentDataMode = useMemo<'assets' | 'projects'>(() => {
        return viewMode === 'folder' && !selectedProjectId ? 'projects' : 'assets';
    }, [viewMode, selectedProjectId]);

    const loadCurrentView = useCallback(async (nextSkip: number, reset = false) => {
        if (reset) {
            setLoading(true);
        } else {
            setLoadingMore(true);
        }

        try {
            const params: Record<string, string | boolean | number> = { 
                origin_kind: originKind,
                skip: nextSkip,
                limit: pageSize,
            };
            if (activeTab !== 'all') params.asset_type = activeTab;
            if (favoritesOnly) params.favorite_only = true;

            if (currentDataMode === 'projects') {
                const res = await assetsApi.listProjectSummaries(params);
                const nextItems = res.data || [];
                setProjectSummaries(prev => reset ? nextItems : [...prev, ...nextItems]);
                if (reset) {
                    setAssets([]);
                }
                setHasMore(nextItems.length === pageSize);
                setSkip(nextSkip + nextItems.length);
            } else {
                const res = selectedProjectId
                    ? await assetsApi.list(selectedProjectId, params)
                    : await assetsApi.listAll(params);
                const nextItems = res.data || [];
                setAssets(prev => reset ? nextItems : [...prev, ...nextItems]);
                if (reset) {
                    setProjectSummaries([]);
                }
                setHasMore(nextItems.length === pageSize);
                setSkip(nextSkip + nextItems.length);
            }
        } catch (err) {
            console.error('Failed to load assets', err);
            toast.error(t('failed_to_load_assets', 'Failed to load assets'));
        } finally {
            if (reset) {
                setLoading(false);
            } else {
                setLoadingMore(false);
            }
        }
    }, [originKind, activeTab, favoritesOnly, selectedProjectId, t, pageSize, currentDataMode]);

    const reloadCurrentView = useCallback(async () => {
        setSelectedAssets(new Set());
        setPreviewIndex(null);
        setSkip(0);
        setHasMore(false);
        await loadCurrentView(0, true);
    }, [loadCurrentView]);

    useEffect(() => {
        void reloadCurrentView();
    }, [reloadCurrentView]);

    useEffect(() => {
        const controller = new AbortController();
        let reloadTimer: number | undefined;
        const projectId = selectedProjectId ?? null;

        const scheduleReload = () => {
            window.clearTimeout(reloadTimer);
            reloadTimer = window.setTimeout(() => {
                void reloadCurrentView();
            }, 250);
        };

        void (async () => {
            try {
                for await (const event of streamRealtimeEvents({ projectId, signal: controller.signal })) {
                    const notification = event.data;
                    if (
                        event.type === 'realtime_notification'
                        && notification?.name === 'asset.preview.updated'
                        && notification.resource?.type === 'asset'
                    ) {
                        scheduleReload();
                    }
                }
            } catch (err) {
                if (!controller.signal.aborted) {
                    console.error('Realtime asset refresh stream failed', err);
                }
            }
        })();

        return () => {
            controller.abort();
            window.clearTimeout(reloadTimer);
        };
    }, [reloadCurrentView, selectedProjectId]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isBatchMode) {
                setIsBatchMode(false);
                setSelectedAssets(new Set());
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isBatchMode]);

    useEffect(() => {
        if (currentDataMode === 'projects') {
            setIsBatchMode(false);
            setSelectedAssets(new Set());
        }
    }, [currentDataMode]);

    useEffect(() => {
        const target = loadMoreRef.current;
        if (!target || loading || loadingMore || !hasMore) {
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            const [entry] = entries;
            if (entry?.isIntersecting) {
                void loadCurrentView(skip, false);
            }
        }, {
            root: null,
            rootMargin: '0px 0px 240px 0px',
        });

        observer.observe(target);
        return () => observer.disconnect();
    }, [hasMore, loadCurrentView, loading, loadingMore, skip]);

    const handleBatchOperationClick = () => {
        setIsBatchMode(!isBatchMode);
        setSelectedAssets(new Set());
    };

    const handleBatchAction = async (action: 'delete' | 'favorite' | 'unfavorite' | 'download') => {
        if (selectedAssets.size === 0) return;
        try {
            if (action === 'download') {
                const assetsToDownload = assets.filter(a => selectedAssets.has(a.id));
                for (const asset of assetsToDownload) {
                    try {
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
                    } catch (e) {
                        console.error(`Failed to download asset ${asset.id}`, e);
                    }
                }
                toast.success(t('batch_operation_success', 'Batch operation successful'));
            } else {
                if (selectedProjectId) {
                    await assetsApi.batch(selectedProjectId, {
                        asset_ids: Array.from(selectedAssets),
                        action
                    });
                } else {
                    await assetsApi.globalBatch({
                        asset_ids: Array.from(selectedAssets),
                        action
                    });
                }
                toast.success(t('batch_operation_success', 'Batch operation successful'));
            }
            await reloadCurrentView();
            setSelectedAssets(new Set());
            setIsBatchMode(false);
        } catch (err: unknown) {
            console.error(err);
            const error = err as { response?: { data?: { detail?: string } } };
            toast.error(error.response?.data?.detail || t('batch_operation_failed', 'Batch operation failed'));
        }
    };

    const handleFolderClick = (projectId: number, projectName: string) => {
        setSelectedProjectId(projectId);
        setSelectedProjectName(projectName);
    };

    const handleBackToFolders = () => {
        setSelectedProjectId(undefined);
        setSelectedProjectName(undefined);
    };

    const handleViewToggle = () => {
        const nextMode = viewMode === 'grid' ? 'folder' : 'grid';
        setViewMode(nextMode);
        if (nextMode === 'grid') {
            setSelectedProjectId(undefined);
            setSelectedProjectName(undefined);
        }
    };

    return (
        <div data-testid="assets-page-scroll" className={cn(
            'flex-1 min-h-0 overflow-y-auto overflow-x-hidden pt-6 px-12 pb-6 transition-colors duration-500 bg-transparent text-foreground'
        )} ref={scrollContainerRef}>
            {(viewMode === 'folder' && selectedProjectId) && (
                <header className="flex justify-between items-center mb-4">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <IconButton size="icon" onClick={handleBackToFolders}>
                                <ChevronLeft className="w-5 h-5" />
                            </IconButton>
                            <h2 className="text-xl font-bold">{selectedProjectName}</h2>
                        </div>
                    </div>
                </header>
            )}
            
            {/* Origin Tabs */}
            <div className="flex justify-center items-center gap-2 mb-6">
                <SegmentedControl
                    aria-label={t('asset_origin_filter', 'Asset origin filter')}
                    value={originKind}
                    onValueChange={(value) => setOriginKind(value)}
                    options={[
                        { key: 'ai_generated', label: t('creative_assets', 'Creative Assets') },
                        { key: 'local_upload', label: t('local_upload', 'Local Upload') },
                    ]}
                    className="sticky top-0 z-10"
                    itemClassName="min-w-[120px] px-6"
                />

                <IconButton
                    size="icon"
                    onClick={handleViewToggle}
                    className="ml-2 rounded-[var(--app-radius-sm)]"
                    title={viewMode === 'grid' ? t('switch_to_folder_view', 'Switch to Folder View') : t('switch_to_grid_view', 'Switch to Grid View')}
                >
                    {viewMode === 'grid' ? <FolderOpen className="w-4 h-4" /> : <LayoutGrid className="w-4 h-4" />}
                </IconButton>
            </div>

            {/* Type & Favorites Filters */}
            <div className="flex justify-between items-center gap-2 mb-6">
                <div className="flex items-center gap-2">
                    <SegmentedControl
                        aria-label={t('asset_type_filter', 'Asset type filter')}
                        value={activeTab}
                        onValueChange={(value) => setActiveTab(value)}
                        options={[
                        { key: 'all', label: t('all', 'All'), icon: LayoutGrid },
                        { key: 'image', label: t('images', 'Images'), icon: ImageIcon },
                        { key: 'video', label: t('videos', 'Videos'), icon: Video },
                        ]}
                    />

                    <button 
                        type="button"
                        className={cn(
                            "flex h-11 items-center gap-3 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-control-track)] px-4 text-sm font-bold text-[var(--app-foreground-muted)] shadow-[var(--app-shadow-control)] transition-all hover:text-foreground",
                            favoritesOnly && "text-[var(--app-primary)]"
                        )}
                        onClick={() => setFavoritesOnly(!favoritesOnly)}
                    >
                        <Heart className={cn('w-4 h-4 transition-all', favoritesOnly && 'fill-[var(--app-primary)] text-[var(--app-primary)]')} />
                        <span>{t('my_favorites', 'My Favorites')}</span>
                        <div className={cn(
                            'relative h-[18px] w-8 rounded-full p-0.5 transition-all',
                            favoritesOnly ? 'bg-[var(--app-primary)]' : 'bg-[var(--app-surface-raised)]'
                        )}>
                            <div className={cn(
                                'h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-all',
                                favoritesOnly && 'translate-x-3.5'
                            )} />
                        </div>
                    </button>
                </div>

                <div className="flex items-center gap-2">
                    {currentDataMode === 'assets' && isBatchMode ? (
                        <>
                            <Button variant="destructive" size="sm" onClick={() => setIsBatchDeleteDialogOpen(true)} className="rounded-xl">
                                <Trash2 className="w-4 h-4 mr-1" />{t('delete_selected', 'Delete Selected')}
                            </Button>
                            <Button size="sm" onClick={() => handleBatchAction('download')}>
                                <Download className="w-4 h-4 mr-1" />{t('download_selected', 'Download Selected')}
                            </Button>
                            <Button size="sm" onClick={() => handleBatchAction('favorite')}>
                                <Heart className="w-4 h-4 mr-1" />{t('favorite_selected', 'Favorite Selected')}
                            </Button>
                            <Button variant="ghost" size="sm" onClick={handleBatchOperationClick}>
                                {t('cancel', 'Cancel')}
                            </Button>
                        </>
                    ) : currentDataMode === 'assets' ? (
                        <Button size="sm" onClick={handleBatchOperationClick} className="px-6">
                            {t('batch_operation', 'Batch Operation')}
                        </Button>
                    ) : null}
                </div>
            </div>

            {/* Content */}
            <div className="mt-6">
                {loading ? (
                    <div className="flex flex-wrap gap-6">
                        {[...Array(12)].map((_, i) => (
                            <Skeleton
                                key={i}
                                className={cn(
                                    "rounded-xl",
                                    activeTab === 'video' ? "w-[322px] h-[230px]" : "w-[200px] h-[250px]"
                                )}
                            />
                        ))}
                    </div>
                ) : currentDataMode === 'projects' ? (
                    <ProjectFolderGrid
                        projects={projectSummaries}
                        onFolderClick={handleFolderClick}
                    />
                ) : assets.length === 0 ? (
                    <EmptyState
                        icon={<LayoutGrid className="w-8 h-8" />}
                        title={t('no_assets_found', 'No assets found.')}
                        className="min-h-[60vh]"
                    />
                ) : (
                    <>
                        <AssetGrid
                            assets={assets}
                            isBatchMode={isBatchMode}
                            selectedAssets={selectedAssets}
                            onSelectAsset={(id, selected) => {
                                const newSelection = new Set(selectedAssets);
                                if (selected) newSelection.add(id);
                                else newSelection.delete(id);
                                setSelectedAssets(newSelection);
                            }}
                            onRefresh={reloadCurrentView}
                            projectId={selectedProjectId}
                            activeTab={activeTab}
                            onPreview={(index) => setPreviewIndex(index)}
                            scrollContainerRef={scrollContainerRef}
                        />
                        <div className="py-20 flex justify-center w-full">
                            {loadingMore ? (
                                <p className="text-muted-foreground/60 text-sm font-medium">{t('loading', 'Loading...')}</p>
                            ) : !hasMore ? (
                                <p className="text-muted-foreground/40 text-sm font-medium">{t('no_more_assets', 'All assets loaded')}</p>
                            ) : null}
                        </div>
                    </>
                )}
                {!loading && (currentDataMode === 'projects' ? projectSummaries.length > 0 : assets.length > 0) ? (
                    <div ref={loadMoreRef} className="h-4 w-full" aria-hidden="true" />
                ) : null}
                {currentDataMode === 'projects' && !loading ? (
                    <div className="py-20 flex justify-center w-full">
                        {loadingMore ? (
                            <p className="text-muted-foreground/60 text-sm font-medium">{t('loading', 'Loading...')}</p>
                        ) : !hasMore && projectSummaries.length > 0 ? (
                            <p className="text-muted-foreground/40 text-sm font-medium">{t('no_more_assets', 'All assets loaded')}</p>
                        ) : null}
                    </div>
                ) : null}
            </div>

            {previewIndex !== null && (
                <AssetPreviewModal 
                    assets={assets}
                    initialIndex={previewIndex}
                    onClose={() => setPreviewIndex(null)}
                />
            )}
            <DeleteAssetsConfirmDialog
                count={selectedAssets.size}
                open={isBatchDeleteDialogOpen}
                onOpenChange={setIsBatchDeleteDialogOpen}
                onConfirm={() => void handleBatchAction('delete')}
                variant="batch"
            />
        </div>
    );
}
