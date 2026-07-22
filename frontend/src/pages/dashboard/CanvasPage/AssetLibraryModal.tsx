import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ChevronLeft, Folder } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { assetsApi, AssetGroupSummaryRead, AssetProjectSummaryRead, AssetRead } from '@/api/endpoints/assets'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { CachedImage } from '@/components/ui/CachedImage'

export type AssetLibrarySelectedAsset = {
  id: number
  project_id?: number
  url: string
  type: 'image' | 'video'
  origin_kind: AssetRead['origin_kind']
  source_asset_id?: number | null
  canvas_item_id?: string | null
  canvas_group_id?: string | null
  canvas_group_name?: string | null
  name?: string | null
  list_preview_url?: string | null
  source_kind?: 'asset_library' | 'reference_gallery'
}

interface AssetLibraryModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onImport: (assets: AssetLibrarySelectedAsset[]) => void
  isDark: boolean
  mode?: 'canvas-import' | 'generator-pick'
  assetType?: 'image' | 'video'
  selectionMode?: 'single' | 'multiple'
  maxSelection?: number
  onSelect?: (assets: AssetLibrarySelectedAsset[]) => void
  initialProject?: SelectedProject | null
  allowEmptySelection?: boolean
}

type FilterMode = 'all' | 'favorites'
type SelectedProject = Pick<AssetProjectSummaryRead, 'project_id' | 'project_name' | 'asset_count'>
type AssetGroupFilter = { kind: 'all' } | { kind: 'group'; groupId: string } | { kind: 'ungrouped' }
type LibraryAssetItem = Pick<AssetRead,
  | 'id'
  | 'project_id'
  | 'url'
  | 'asset_type'
  | 'origin_kind'
  | 'source_asset_id'
  | 'list_preview_url'
  | 'canvas_item_id'
  | 'canvas_group_id'
  | 'canvas_group_name'
  | 'is_favorite'
> & { name?: string | null }

const PAGE_SIZE = 24
const ASSET_LIBRARY_MODAL_Z_INDEX = 2147483647
const ASSET_GROUP_FILTER_ALL_VALUE = 'all'
const ASSET_GROUP_FILTER_UNGROUPED_VALUE = 'ungrouped'
const ASSET_GROUP_FILTER_GROUP_PREFIX = 'group:'
const RECENT_ASSET_LIBRARY_KEY = 'canvas.assetLibrary.recentImages.v1'
const MAX_RECENT_ASSETS = 10

export function AssetLibraryModal({
  open,
  onOpenChange,
  onImport,
  isDark,
  mode = 'canvas-import',
  assetType: forcedAssetType,
  selectionMode = 'multiple',
  maxSelection = 0,
  onSelect,
  initialProject = null,
  allowEmptySelection = false,
}: AssetLibraryModalProps) {
  const { t } = useTranslation()
  const [assetType, setAssetType] = useState<'image' | 'video'>('image')
  const [filter, setFilter] = useState<FilterMode>('all')
  const [selectedProject, setSelectedProject] = useState<SelectedProject | null>(null)
  const [projects, setProjects] = useState<AssetProjectSummaryRead[]>([])
  const [assetGroups, setAssetGroups] = useState<AssetGroupSummaryRead[]>([])
  const [groupFilter, setGroupFilter] = useState<AssetGroupFilter>({ kind: 'all' })
  const [assets, setAssets] = useState<AssetRead[]>([])
  const [recentAssets, setRecentAssets] = useState<LibraryAssetItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [skip, setSkip] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const loadMoreRef = useRef<HTMLDivElement | null>(null)
  const groupFilterRef = useRef<AssetGroupFilter>({ kind: 'all' })

  const effectiveAssetType = mode === 'generator-pick' ? (forcedAssetType || 'image') : assetType
  const effectiveSelectionMode = mode === 'generator-pick' ? selectionMode : 'multiple'

  const resetLoadedData = useCallback(() => {
    setProjects([])
    setAssets([])
    setSkip(0)
    setHasMore(false)
  }, [])

  useEffect(() => {
    groupFilterRef.current = groupFilter
  }, [groupFilter])

  const fetchAssetGroups = useCallback(async (project: SelectedProject) => {
    try {
      const res = await assetsApi.listGroups(project.project_id, {
        asset_type: effectiveAssetType,
        favorite_only: filter === 'favorites' ? true : undefined,
      })
      setAssetGroups(res.data || [])
    } catch (e) {
      console.error('Failed to fetch asset library groups', e)
      setAssetGroups([])
    }
  }, [effectiveAssetType, filter])

  const fetchCurrentView = useCallback(async (
    nextSkip: number,
    reset = false,
    project: SelectedProject | null = null,
    nextGroupFilter: AssetGroupFilter = groupFilterRef.current,
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
        const res = await assetsApi.list(project.project_id, {
          ...params,
          ...getAssetGroupFilterParams(nextGroupFilter),
        })
        const nextItems = res.data || []
        setAssets(prev => (reset ? nextItems : [...prev, ...nextItems]))
        if (reset) {
          setProjects([])
        }
        setHasMore(nextItems.length === PAGE_SIZE)
        setSkip(nextSkip + nextItems.length)
        return
      }

      const res = await assetsApi.listProjectSummaries(params)
      const nextItems = res.data || []
      setProjects(prev => (reset ? nextItems : [...prev, ...nextItems]))
      if (reset) {
        setAssets([])
      }
      setHasMore(nextItems.length === PAGE_SIZE)
      setSkip(nextSkip + nextItems.length)
    } catch (e) {
      console.error('Failed to fetch asset library data', e)
    } finally {
      if (reset) {
        setLoading(false)
      } else {
        setLoadingMore(false)
      }
    }
  }, [effectiveAssetType, filter])

  const openProject = useCallback(async (project: SelectedProject) => {
    const nextGroupFilter: AssetGroupFilter = { kind: 'all' }
    setSelectedProject(project)
    setSelectedIds(new Set())
    setGroupFilter(nextGroupFilter)
    groupFilterRef.current = nextGroupFilter
    resetLoadedData()
    await Promise.all([
      fetchCurrentView(0, true, project, nextGroupFilter),
      fetchAssetGroups(project),
    ])
  }, [fetchAssetGroups, fetchCurrentView, resetLoadedData])

  const backToProjects = useCallback(async () => {
    setSelectedProject(null)
    setSelectedIds(new Set())
    setAssetGroups([])
    const nextGroupFilter: AssetGroupFilter = { kind: 'all' }
    setGroupFilter(nextGroupFilter)
    groupFilterRef.current = nextGroupFilter
    resetLoadedData()
    await fetchCurrentView(0, true, null)
  }, [fetchCurrentView, resetLoadedData])

  useEffect(() => {
    if (!open) {
      setSelectedProject(null)
      setSelectedIds(new Set())
      setAssetGroups([])
      const nextGroupFilter: AssetGroupFilter = { kind: 'all' }
      setGroupFilter(nextGroupFilter)
      groupFilterRef.current = nextGroupFilter
      resetLoadedData()
      return
    }

    setRecentAssets(readRecentAssets())
    setSelectedProject(null)
    setSelectedIds(new Set())
    setAssetGroups([])
    const nextGroupFilter: AssetGroupFilter = { kind: 'all' }
    setGroupFilter(nextGroupFilter)
    groupFilterRef.current = nextGroupFilter
    resetLoadedData()
    if (initialProject) {
      setSelectedProject(initialProject)
      void fetchCurrentView(0, true, initialProject, nextGroupFilter)
      void fetchAssetGroups(initialProject)
      return
    }
    void fetchCurrentView(0, true, null)
  }, [open, effectiveAssetType, filter, fetchAssetGroups, fetchCurrentView, initialProject, resetLoadedData])

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
      root: null,
      rootMargin: '0px 0px 240px 0px',
    })

    observer.observe(target)
    return () => observer.disconnect()
  }, [fetchCurrentView, hasMore, loading, loadingMore, open, selectedProject, skip])

  const toggleSelect = (asset: LibraryAssetItem) => {
    setSelectedIds((prev) => {
      if (effectiveSelectionMode === 'single') {
        if (prev.has(asset.id)) {
          return new Set()
        }
        return new Set([asset.id])
      }

      const next = new Set(prev)
      if (next.has(asset.id)) {
        next.delete(asset.id)
      } else {
        if (maxSelection > 0 && next.size >= maxSelection) {
          return next
        }
        next.add(asset.id)
      }
      return next
    })
  }

  const handleGroupFilterChange = (value: string) => {
    const nextGroupFilter = decodeAssetGroupFilter(value)
    setGroupFilter(nextGroupFilter)
    groupFilterRef.current = nextGroupFilter
    setSelectedIds(new Set())
    setAssets([])
    setSkip(0)
    setHasMore(false)

    if (selectedProject) {
      void fetchCurrentView(0, true, selectedProject, nextGroupFilter)
    }
  }

  const handleConfirm = () => {
    const candidates = dedupeLibraryAssets([...recentAssets, ...assets])
    const selectedAssetItems = candidates.filter((asset) => selectedIds.has(asset.id))
    const selectedAssets: AssetLibrarySelectedAsset[] = selectedAssetItems
      .map((asset) => ({
        id: asset.id,
        project_id: asset.project_id,
        url: asset.url,
        type: asset.asset_type,
        origin_kind: asset.origin_kind,
        source_asset_id: asset.source_asset_id ?? null,
        canvas_item_id: asset.canvas_item_id ?? null,
        canvas_group_id: asset.canvas_group_id ?? null,
        canvas_group_name: asset.canvas_group_name ?? null,
        name: getAssetNameFromUrl(asset.url),
        list_preview_url: asset.list_preview_url ?? null,
        source_kind: 'asset_library' as const,
      }))

    const nextRecentAssets = rememberRecentAssets(selectedAssetItems)
    setRecentAssets(nextRecentAssets)

    if (mode === 'generator-pick') {
      onSelect?.(selectedAssets)
    } else {
      onImport(selectedAssets)
    }
    onOpenChange(false)
  }

  const listTitle = selectedProject
    ? selectedProject.project_name || t('untitled_project', 'Untitled Project')
    : t('canvas.asset_library.projects', '项目列表')
  const isConfirmDisabled = !allowEmptySelection && selectedIds.size === 0
  const visibleRecentAssets = effectiveAssetType === 'image' && selectedProject
    ? recentAssets
      .filter((asset) => asset.asset_type === 'image')
      .filter((asset) => asset.project_id === selectedProject.project_id)
      .filter((asset) => filter !== 'favorites' || asset.is_favorite)
      .filter((asset) => matchesAssetGroupFilter(asset, groupFilter))
      .slice(0, MAX_RECENT_ASSETS)
    : []
  const visibleRecentIds = new Set(visibleRecentAssets.map((asset) => asset.id))
  const visibleAssets = assets.filter((asset) => !visibleRecentIds.has(asset.id))
  const hasVisibleAssets = visibleRecentAssets.length > 0 || visibleAssets.length > 0
  const renderAssetTile = (asset: LibraryAssetItem) => {
    const selected = selectedIds.has(asset.id)
    const listMediaUrl = getLibraryAssetListMediaUrl(asset)
    return (
      <div
        key={asset.id}
        onClick={() => toggleSelect(asset)}
        className={cn(
          `relative ${asset.asset_type === 'video' ? 'aspect-video' : 'aspect-square'} rounded-lg overflow-hidden cursor-pointer group border-2 transition-all`,
          selected ? 'app-outline-primary' : 'border-transparent',
        )}
      >
        {asset.asset_type === 'video' ? (
          <video
            src={asset.url}
            className="w-full h-full object-cover"
            muted
            loop
            playsInline
            onMouseEnter={(event) => { event.currentTarget.play().catch(() => {}) }}
            onMouseLeave={(event) => { event.currentTarget.pause() }}
          />
        ) : (
          <CachedImage src={listMediaUrl} alt={`asset-${asset.id}`} className="w-full h-full object-cover" />
        )}
        {asset.origin_kind === 'local_upload' && (
          <div className="app-media-control absolute top-2 right-2 rounded-full px-2.5 py-1 text-[10px] font-medium">
            {t('local_upload_badge', '本地上传')}
          </div>
        )}
        <div className={cn(
          'absolute top-2 left-2 w-5 h-5 rounded flex items-center justify-center transition-colors border border-[var(--app-media-border)]',
          selected ? 'bg-[var(--app-primary)]' : 'app-media-control',
        )}>
          {selected && <Check size={14} className="text-[var(--app-primary-foreground)]" />}
        </div>
      </div>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        noDarken
        overlayClassName={`!z-[${ASSET_LIBRARY_MODAL_Z_INDEX}]`}
        className={cn(
          `sm:max-w-[1400px] w-[90vw] h-[85vh] flex flex-col p-8 glass-modal-unified !rounded-2xl !z-[${ASSET_LIBRARY_MODAL_Z_INDEX}]`,
          'app-text',
        )}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="text-xl font-medium">{t('canvas.asset_library.title', '资产选择')}</div>
          <DialogTitle className="sr-only">{t('canvas.asset_library.title', '资产选择')}</DialogTitle>
        </div>

        <Tabs
          defaultValue="image"
          value={effectiveAssetType}
          onValueChange={(value) => {
            if (mode !== 'generator-pick') {
              setAssetType(value as 'image' | 'video')
            }
          }}
          className="flex-1 flex flex-col min-h-0"
        >
          {mode !== 'generator-pick' && (
            <TabsList className="self-start mb-6 p-1 rounded-xl bg-[var(--app-control)] h-auto inline-flex">
              <TabsTrigger
                value="image"
                className="rounded-lg px-8 py-2 text-[15px] font-medium text-[var(--app-foreground-muted)] transition-all data-[state=active]:bg-[var(--app-control-selected)] data-[state=active]:text-[var(--app-control-selected-foreground)] data-[state=active]:shadow-sm"
              >
                {t('canvas.asset_library.images', '图片')}
              </TabsTrigger>
              <TabsTrigger
                value="video"
                className="rounded-lg px-8 py-2 text-[15px] font-medium text-[var(--app-foreground-muted)] transition-all data-[state=active]:bg-[var(--app-control-selected)] data-[state=active]:text-[var(--app-control-selected-foreground)] data-[state=active]:shadow-sm"
              >
                {t('canvas.asset_library.videos', '视频')}
              </TabsTrigger>
            </TabsList>
          )}

          <div className="flex items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-3 min-w-0">
              {selectedProject ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => { void backToProjects() }}
                  className="rounded-xl shrink-0"
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
              ) : null}
              <div className="app-chip px-4 py-1.5 rounded-md text-sm truncate">
                {listTitle}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {selectedProject && assetGroups.length > 0 ? (
                <Select value={encodeAssetGroupFilter(groupFilter)} onValueChange={handleGroupFilterChange}>
                  <SelectTrigger
                    aria-label={t('canvas.asset_library.group_filter_label', '分组筛选')}
                    className="h-9 w-[180px] rounded-xl bg-[var(--app-control)]"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper" className={`z-[${ASSET_LIBRARY_MODAL_Z_INDEX}]`}>
                    <SelectItem value={ASSET_GROUP_FILTER_ALL_VALUE}>
                      {t('canvas.asset_library.all_groups', '全部分组')}
                    </SelectItem>
                    {assetGroups.map((group) => {
                      const value = group.is_ungrouped
                        ? ASSET_GROUP_FILTER_UNGROUPED_VALUE
                        : encodeAssetGroupFilter({ kind: 'group', groupId: group.group_id || '' })
                      const label = group.is_ungrouped
                        ? t('canvas.asset_library.ungrouped', '未分组')
                        : group.group_name || t('canvas.asset_library.unnamed_group', '未命名分组')
                      return (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      )
                    })}
                  </SelectContent>
                </Select>
              ) : null}
              <label className={`inline-flex items-center gap-2 text-sm cursor-pointer ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Checkbox
                  checked={filter === 'favorites'}
                  onCheckedChange={(checked) => setFilter(checked ? 'favorites' : 'all')}
                  aria-label={t('canvas.asset_library.favorites_checkbox', '收藏')}
                />
                <span>{t('canvas.asset_library.favorites_checkbox', '收藏')}</span>
              </label>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-full text-gray-400">Loading...</div>
            ) : selectedProject ? (
              !hasVisibleAssets ? (
                <div className="flex items-center justify-center h-full text-gray-400">{t('canvas.asset_library.no_assets', '暂无内容')}</div>
              ) : (
                <div className="space-y-7">
                  {visibleRecentAssets.length > 0 ? (
                    <section>
                      <div className="app-muted mb-3 text-sm font-medium">
                        {t('canvas.asset_library.recent_images', '最近常用')}
                      </div>
                      <div className="grid grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
                        {visibleRecentAssets.map(renderAssetTile)}
                      </div>
                    </section>
                  ) : null}
                  {visibleAssets.length > 0 ? (
                    <section>
                      {visibleRecentAssets.length > 0 ? (
                        <div className="app-muted mb-3 text-sm font-medium">
                          {effectiveAssetType === 'image'
                            ? t('canvas.asset_library.all_images', '所有图片')
                            : t('canvas.asset_library.all_videos', '所有视频')}
                        </div>
                      ) : null}
                      <div className="grid grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6">
                        {visibleAssets.map(renderAssetTile)}
                      </div>
                    </section>
                  ) : null}
                </div>
              )
            ) : projects.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-400">{t('canvas.asset_library.no_projects', '暂无项目')}</div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5">
                {projects.map((project) => (
                  <button
                    key={project.project_id}
                    type="button"
                    onClick={() => { void openProject(project) }}
                    className={cn(
                      'app-card text-left rounded-2xl p-5 transition-all hover:bg-[var(--app-control-hover)]'
                    )}
                  >
                    <div className={cn(
                      'w-12 h-12 rounded-2xl flex items-center justify-center mb-4',
                      isDark ? 'bg-blue-500/10 text-blue-300' : 'bg-blue-50 text-blue-500'
                    )}>
                      <Folder className="w-6 h-6" />
                    </div>
                    <div className="text-sm font-semibold truncate">
                      {project.project_name || t('untitled_project', 'Untitled Project')}
                    </div>
                    <div className="app-muted mt-2 text-xs">
                      {project.asset_count} {project.asset_count === 1 ? 'item' : 'items'}
                    </div>
                  </button>
                ))}
              </div>
            )}

            {!loading && ((selectedProject && hasVisibleAssets) || (!selectedProject && projects.length > 0)) ? (
              <>
                <div ref={loadMoreRef} className="h-4 w-full" aria-hidden="true" />
                <div className="py-6 flex justify-center text-sm text-gray-400">
                  {loadingMore ? 'Loading...' : !hasMore ? t('canvas.asset_library.all_loaded', '已全部加载') : ''}
                </div>
              </>
            ) : null}
          </div>
        </Tabs>

        <div className="app-divider mt-4 pt-4 flex items-center justify-between border-t">
          <div className="app-muted text-sm">
            {effectiveAssetType === 'image'
              ? t('canvas.asset_library.selected_images', '已选 {{count}} 张图片', { count: selectedIds.size })
              : t('canvas.asset_library.selected_videos', '已选 {{count}} 个视频', { count: selectedIds.size })}
          </div>
          <Button
            onClick={handleConfirm}
            disabled={isConfirmDisabled}
          >
            {t('common.confirm', '确认')}
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

function getAssetGroupFilterParams(groupFilter: AssetGroupFilter) {
  if (groupFilter.kind === 'group') {
    return { canvas_group_id: groupFilter.groupId }
  }
  if (groupFilter.kind === 'ungrouped') {
    return { ungrouped_only: true }
  }
  return {}
}

function encodeAssetGroupFilter(groupFilter: AssetGroupFilter): string {
  if (groupFilter.kind === 'group') {
    return `${ASSET_GROUP_FILTER_GROUP_PREFIX}${groupFilter.groupId}`
  }
  if (groupFilter.kind === 'ungrouped') {
    return ASSET_GROUP_FILTER_UNGROUPED_VALUE
  }
  return ASSET_GROUP_FILTER_ALL_VALUE
}

function decodeAssetGroupFilter(value: string): AssetGroupFilter {
  if (value === ASSET_GROUP_FILTER_UNGROUPED_VALUE) {
    return { kind: 'ungrouped' }
  }
  if (value.startsWith(ASSET_GROUP_FILTER_GROUP_PREFIX)) {
    return { kind: 'group', groupId: value.slice(ASSET_GROUP_FILTER_GROUP_PREFIX.length) }
  }
  return { kind: 'all' }
}

function matchesAssetGroupFilter(asset: LibraryAssetItem, groupFilter: AssetGroupFilter): boolean {
  if (groupFilter.kind === 'group') {
    return asset.canvas_group_id === groupFilter.groupId
  }
  if (groupFilter.kind === 'ungrouped') {
    return !asset.canvas_group_id
  }
  return true
}

function getLibraryAssetListMediaUrl(asset: LibraryAssetItem): string {
  if (asset.asset_type !== 'image') {
    return asset.url
  }
  return asset.list_preview_url ?? asset.url
}

function readRecentAssets(): LibraryAssetItem[] {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const raw = window.localStorage.getItem(RECENT_ASSET_LIBRARY_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed
      .filter(isRecentAsset)
      .slice(0, MAX_RECENT_ASSETS)
  } catch {
    return []
  }
}

function rememberRecentAssets(selectedAssets: LibraryAssetItem[]): LibraryAssetItem[] {
  const incoming = selectedAssets
    .filter((asset) => asset.asset_type === 'image')
    .map(toRecentAsset)
  const existing = readRecentAssets()
  const merged = dedupeLibraryAssets([...incoming, ...existing]).slice(0, MAX_RECENT_ASSETS)

  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(RECENT_ASSET_LIBRARY_KEY, JSON.stringify(merged))
    } catch {
      // Ignore storage failures; recent assets are a convenience only.
    }
  }

  return merged
}

function dedupeLibraryAssets(assets: LibraryAssetItem[]): LibraryAssetItem[] {
  const seen = new Set<number>()
  const result: LibraryAssetItem[] = []
  for (const asset of assets) {
    if (seen.has(asset.id)) {
      continue
    }
    seen.add(asset.id)
    result.push(asset)
  }
  return result
}

function toRecentAsset(asset: LibraryAssetItem): LibraryAssetItem {
  return {
    id: asset.id,
    project_id: asset.project_id,
    url: asset.url,
    asset_type: asset.asset_type,
    origin_kind: asset.origin_kind,
    source_asset_id: asset.source_asset_id ?? null,
    list_preview_url: asset.list_preview_url ?? null,
    canvas_item_id: asset.canvas_item_id ?? null,
    canvas_group_id: asset.canvas_group_id ?? null,
    canvas_group_name: asset.canvas_group_name ?? null,
    is_favorite: asset.is_favorite,
    name: asset.name ?? getAssetNameFromUrl(asset.url),
  }
}

function isRecentAsset(value: unknown): value is LibraryAssetItem {
  if (!value || typeof value !== 'object') {
    return false
  }
  const asset = value as Partial<LibraryAssetItem>
  return (
    typeof asset.id === 'number'
    && typeof asset.project_id === 'number'
    && typeof asset.url === 'string'
    && asset.asset_type === 'image'
    && typeof asset.origin_kind === 'string'
  )
}
