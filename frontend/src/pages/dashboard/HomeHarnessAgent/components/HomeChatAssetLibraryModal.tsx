import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronLeft, Folder } from 'lucide-react'

import { assetsApi, getAssetListMediaUrl, type AssetProjectSummaryRead, type AssetRead } from '@/api/endpoints/assets'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { CachedImage } from '@/components/ui/CachedImage'

export interface HomeChatLibraryAsset {
  id: number
  url: string
  type: 'image' | 'video'
  origin_kind: AssetRead['origin_kind']
  source_asset_id?: number | null
  name?: string | null
  list_preview_url?: string | null
}

interface HomeChatAssetLibraryModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isDark: boolean
  onSelect: (assets: HomeChatLibraryAsset[]) => void
  assetType?: 'image' | 'video'
  lockAssetType?: boolean
  maxSelection?: number
}

type FilterMode = 'all' | 'favorites'
type SelectedProject = Pick<AssetProjectSummaryRead, 'project_id' | 'project_name' | 'asset_count'>

const PAGE_SIZE = 24

export function HomeChatAssetLibraryModal({
  open,
  onOpenChange,
  isDark,
  onSelect,
  assetType: forcedAssetType,
  lockAssetType = false,
  maxSelection = 0,
}: HomeChatAssetLibraryModalProps) {
  const { t } = useTranslation()
  const [assetType, setAssetType] = useState<'image' | 'video'>('image')
  const [filter, setFilter] = useState<FilterMode>('all')
  const [selectedProject, setSelectedProject] = useState<SelectedProject | null>(null)
  const [projects, setProjects] = useState<AssetProjectSummaryRead[]>([])
  const [assets, setAssets] = useState<AssetRead[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [skip, setSkip] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)

  const effectiveAssetType = lockAssetType ? (forcedAssetType || 'image') : assetType

  const resetLoadedData = useCallback(() => {
    setProjects([])
    setAssets([])
    setSelectedIds(new Set())
    setSkip(0)
    setHasMore(false)
  }, [])

  const fetchCurrentView = useCallback(async (
    nextSkip: number,
    reset = false,
    project: SelectedProject | null = null,
  ) => {
    if (reset) {
      setLoading(true)
    } else {
      setLoadingMore(true)
    }

    try {
      const params = {
        asset_type: effectiveAssetType,
        favorite_only: filter === 'favorites' ? true : undefined,
        skip: nextSkip,
        limit: PAGE_SIZE,
      }

      if (project) {
        const res = await assetsApi.list(project.project_id, params)
        const nextAssets = res.data || []
        setAssets(prev => (reset ? nextAssets : [...prev, ...nextAssets]))
        setHasMore(nextAssets.length === PAGE_SIZE)
        setSkip(nextSkip + nextAssets.length)
        if (reset) {
          setProjects([])
        }
        return
      }

      const res = await assetsApi.listProjectSummaries(params)
      const nextProjects = res.data || []
      setProjects(prev => (reset ? nextProjects : [...prev, ...nextProjects]))
      setHasMore(nextProjects.length === PAGE_SIZE)
      setSkip(nextSkip + nextProjects.length)
      if (reset) {
        setAssets([])
      }
    } finally {
      if (reset) {
        setLoading(false)
      } else {
        setLoadingMore(false)
      }
    }
  }, [effectiveAssetType, filter])

  useEffect(() => {
    if (!open) {
      resetLoadedData()
      setSelectedProject(null)
      return
    }

    resetLoadedData()
    setSelectedProject(null)
    void fetchCurrentView(0, true, null)
  }, [open, effectiveAssetType, filter, fetchCurrentView, resetLoadedData])

  useEffect(() => {
    const target = loadMoreRef.current
    if (!open || !target || loading || loadingMore || !hasMore) {
      return
    }

    const observer = new IntersectionObserver((entries) => {
      const [entry] = entries
      if (entry?.isIntersecting) {
        void fetchCurrentView(skip, false, selectedProject)
      }
    }, {
      rootMargin: '0px 0px 240px 0px',
    })

    observer.observe(target)
    return () => observer.disconnect()
  }, [fetchCurrentView, hasMore, loading, loadingMore, open, selectedProject, skip])

  const openProject = async (project: SelectedProject) => {
    setSelectedProject(project)
    resetLoadedData()
    await fetchCurrentView(0, true, project)
  }

  const backToProjects = async () => {
    setSelectedProject(null)
    resetLoadedData()
    await fetchCurrentView(0, true, null)
  }

  const handleConfirm = () => {
    const selectedAssets = assets
      .filter(asset => selectedIds.has(asset.id))
      .map(asset => ({
        id: asset.id,
        url: asset.url,
        type: asset.asset_type,
        origin_kind: asset.origin_kind,
        source_asset_id: asset.source_asset_id,
        name: getAssetNameFromUrl(asset.url),
        list_preview_url: asset.list_preview_url ?? null,
      }))

    onSelect(selectedAssets)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        noDarken
        className={cn(
          'sm:max-w-[1400px] w-[90vw] h-[85vh] flex flex-col p-8 glass-modal-unified !rounded-2xl app-text',
        )}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="text-xl font-medium">{t('home.chat.asset_library', 'Asset Library')}</div>
          <DialogTitle className="sr-only">{t('home.chat.asset_library', 'Asset Library')}</DialogTitle>
          <DialogDescription className="sr-only">
            {t('home.chat.asset_library_description', 'Browse project assets and attach one to the homepage chat composer.')}
          </DialogDescription>
        </div>

        <Tabs
          value={effectiveAssetType}
          onValueChange={(value) => {
            if (!lockAssetType) {
              setAssetType(value as 'image' | 'video')
            }
          }}
          className="flex-1 flex flex-col min-h-0"
        >
          {!lockAssetType ? (
            <TabsList className="self-start mb-6 p-1 rounded-xl h-auto inline-flex bg-[var(--app-control)]">
              <TabsTrigger value="image" className="rounded-lg px-8 py-2 text-[15px] font-medium data-[state=active]:shadow-sm">
                {t('canvas.asset_library.images', 'Images')}
              </TabsTrigger>
              <TabsTrigger value="video" className="rounded-lg px-8 py-2 text-[15px] font-medium data-[state=active]:shadow-sm">
                {t('canvas.asset_library.videos', 'Videos')}
              </TabsTrigger>
            </TabsList>
          ) : null}

          <div className="flex items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-3 min-w-0">
              {selectedProject ? (
                <Button type="button" variant="ghost" size="icon" onClick={() => { void backToProjects() }} className="rounded-xl shrink-0">
                  <ChevronLeft className="w-4 h-4" />
                </Button>
              ) : null}
              <div className="app-chip px-4 py-1.5 rounded-md text-sm truncate">
                {selectedProject?.project_name || t('home.chat.projects', 'Projects')}
              </div>
            </div>
            <label className={cn('inline-flex items-center gap-2 text-sm cursor-pointer', isDark ? 'text-gray-300' : 'text-gray-700')}>
              <Checkbox
                checked={filter === 'favorites'}
                onCheckedChange={(checked) => setFilter(checked ? 'favorites' : 'all')}
                aria-label={t('canvas.asset_library.favorites', 'Favorites')}
              />
              <span>{t('canvas.asset_library.favorites', 'Favorites')}</span>
            </label>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-full text-gray-400">{t('common.loading', 'Loading...')}</div>
            ) : selectedProject ? (
              assets.length === 0 ? (
                <div className="flex items-center justify-center h-full text-gray-400">{t('canvas.asset_library.no_assets', 'No assets')}</div>
              ) : (
                <div className="grid grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
                  {assets.map((asset) => {
                    const selected = selectedIds.has(asset.id)
                    const listMediaUrl = getAssetListMediaUrl(asset)
                    return (
                      <button
                        key={asset.id}
                        type="button"
                        onClick={() => {
                          setSelectedIds((current) => {
                            if (!lockAssetType) {
                              return new Set(selected ? [] : [asset.id])
                            }
                            const next = new Set(current)
                            if (next.has(asset.id)) {
                              next.delete(asset.id)
                              return next
                            }
                            if (maxSelection > 0 && next.size >= maxSelection) {
                              return next
                            }
                            next.add(asset.id)
                            return next
                          })
                        }}
                        className={cn(
                          'relative aspect-square rounded-lg overflow-hidden cursor-pointer group border-2 transition-all',
                          selected ? 'app-outline-primary' : 'border-transparent',
                        )}
                      >
                        {asset.asset_type === 'video' ? (
                          <video src={asset.url} className="w-full h-full object-cover" muted />
                        ) : (
                          <CachedImage src={listMediaUrl} alt={`asset-${asset.id}`} className="w-full h-full object-cover" />
                        )}
                        <div className={cn(
                          'absolute top-2 left-2 w-5 h-5 rounded flex items-center justify-center border border-[var(--app-media-border)]',
                          selected ? 'bg-[var(--app-primary)]' : 'app-media-control',
                        )}>
                          {selected ? <Check size={14} className="text-[var(--app-primary-foreground)]" /> : null}
                        </div>
                      </button>
                    )
                  })}
                </div>
              )
            ) : projects.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-400">{t('home.chat.no_projects', 'No projects')}</div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5">
                {projects.map((project) => (
                  <button
                    key={project.project_id}
                    type="button"
                    onClick={() => { void openProject(project) }}
                    className={cn(
                      'app-card text-left rounded-2xl p-5 transition-all hover:bg-[var(--app-control-hover)]',
                    )}
                  >
                    <div className={cn(
                      'w-12 h-12 rounded-2xl flex items-center justify-center mb-4',
                      isDark ? 'bg-blue-500/10 text-blue-300' : 'bg-blue-50 text-blue-500',
                    )}>
                      <Folder className="w-6 h-6" />
                    </div>
                    <div className="text-sm font-semibold truncate">{project.project_name || 'Untitled Project'}</div>
                    <div className="app-muted mt-2 text-xs">
                      {t('home.chat.asset_count', {
                        count: project.asset_count,
                        defaultValue: '{{count}} items',
                      })}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {!loading && ((selectedProject && assets.length > 0) || (!selectedProject && projects.length > 0)) ? (
              <>
                <div ref={loadMoreRef} className="h-4 w-full" aria-hidden="true" />
                <div className="py-6 flex justify-center text-sm text-gray-400">
                  {loadingMore ? t('common.loading', 'Loading...') : !hasMore ? t('home.chat.all_loaded', 'All loaded') : ''}
                </div>
              </>
            ) : null}
          </div>
        </Tabs>

        <div className="app-divider mt-4 pt-4 flex items-center justify-between border-t">
          <div className="app-muted text-sm">
            {t('home.chat.selected_items', {
              count: selectedIds.size,
              defaultValue: 'Selected {{count}} items',
            })}
          </div>
          <Button onClick={handleConfirm} disabled={selectedIds.size === 0}>
            {t('common.confirm', 'Confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function getAssetNameFromUrl(url: string): string | null {
  const path = String(url || '').split('?')[0]
  const parts = path.split('/')
  return parts[parts.length - 1] || null
}
