import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Heart, Clock, LayoutGrid, Image as ImageIcon, Video, BadgeCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { AssetCard } from './AssetCard'
import { AssetPreviewModal } from './AssetPreviewModal'
import { assetsApi, type AssetRead } from '@/api/endpoints/assets'
import { projectMembersApi } from '@/api/endpoints/projectMembers'
import { projectsApi, type ProjectRead } from '@/api/endpoints/projects'
import { shareApi } from '@/api/endpoints/share'
import { toast } from 'sonner'
import { useAuthStore } from '@/store/authStore'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { AppSurface, SegmentedControl } from '@/components/common/ui'
import { getImageUrl } from '@/utils/imageUrl'
import { VirtualizedSectionGrid } from '@/components/ui/VirtualizedSectionGrid'

interface ProjectDetailsViewProps {
  project: ProjectRead
  onBack: () => void
  onUpdate: (project: ProjectRead) => void
  mode?: 'default' | 'share-readonly'
  shareToken?: string
}

export function ProjectDetailsView({
  project,
  onBack,
  onUpdate,
  mode = 'default',
  shareToken,
}: ProjectDetailsViewProps) {
  const { t } = useTranslation()
  const currentUser = useAuthStore(state => state.user)
  const [members, setMembers] = useState<any[]>([])
  const [selectedMemberId, setSelectedMemberId] = useState<number | null>(null)
  const [assets, setAssets] = useState<AssetRead[]>([])
  const [assetType, setAssetType] = useState<'all' | 'image' | 'video'>('all')
  const [loading, setLoading] = useState(false)
  const [skip, setSkip] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [favoriteOnly, setFavoriteOnly] = useState(false)
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const assetScrollContainerRef = useRef<HTMLDivElement | null>(null)
  const LIMIT = 20
  const isShareReadonly = mode === 'share-readonly'

  const isOwner = currentUser?.id === project.user_id
  const isAdmin = currentUser?.username === 'admin'
  const canModifyStatus = isOwner || isAdmin

  useEffect(() => {
    if (isShareReadonly) {
      setMembers([])
      setSelectedMemberId(null)
      return
    }

    const fetchMembers = async () => {
      try {
        const res = await projectMembersApi.list(project.id)
        setMembers(res.data)
        if (selectedMemberId === null && res.data.length > 0) {
          setSelectedMemberId(res.data[0].user_id)
        }
      } catch {
        toast.error(t('projectsPage.loadFailed'))
      }
    }
    fetchMembers()
  }, [isShareReadonly, project.id, selectedMemberId, t])

  useEffect(() => {
    setAssets([])
    setSkip(0)
    setHasMore(true)
  }, [selectedMemberId, assetType, favoriteOnly, isShareReadonly, shareToken])

  useEffect(() => {
    if (!hasMore) return
    if (!isShareReadonly && selectedMemberId === null) return
    if (isShareReadonly && !shareToken) return

    let cancelled = false

    const fetchAssets = async () => {
      setLoading(true)
      try {
        const res = isShareReadonly
          ? await shareApi.listSharedAssets(shareToken!, {
              asset_type: assetType === 'all' ? undefined : assetType,
              skip,
              limit: LIMIT,
            })
          : await assetsApi.list(project.id, {
              user_id: selectedMemberId!,
              asset_type: assetType === 'all' ? undefined : assetType,
              favorite_only: favoriteOnly,
              skip,
              limit: LIMIT
            })

        if (cancelled) return

        const newAssets = res.data
        if (newAssets.length < LIMIT) {
          setHasMore(false)
        }
        setAssets(prev => {
          const existingIds = new Set(prev.map(a => a.id))
          return [...prev, ...newAssets.filter(a => !existingIds.has(a.id))]
        })
      } catch {
        toast.error(t('failed_to_load_assets'))
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    fetchAssets()

    return () => {
      cancelled = true
    }
  }, [assetType, favoriteOnly, hasMore, isShareReadonly, project.id, selectedMemberId, shareToken, skip, t])

  const loadMore = () => {
    if (!loading && hasMore) {
      setSkip(prev => prev + LIMIT)
    }
  }

  const stats = useMemo(() => {
    if (assets.length === 0) return { count: 0, lastUpdate: null, isActive: false }
    const sorted = [...assets].sort(
      (a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime(),
    )
    const lastUpdate = new Date(sorted[0].updated_at || sorted[0].created_at)
    const diff = (Date.now() - lastUpdate.getTime()) / 1000
    const isActive = diff < 2 * 60 * 60
    return {
      count: assets.length,
      lastUpdate,
      isActive
    }
  }, [assets])

  const formatRelativeTime = (date: Date) => {
    const diff = (Date.now() - date.getTime()) / 1000
    if (diff < 60) return `1m`
    if (diff < 3600) return `${Math.floor(diff / 60)}m`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`
    return `${Math.floor(diff / 86400)}d`
  }

  const handleToggleFavorite = async (asset: AssetRead) => {
    if (isShareReadonly) return
    try {
      await assetsApi.batch(project.id, {
        asset_ids: [asset.id],
        action: asset.is_favorite ? 'unfavorite' : 'favorite'
      })
      setAssets(assets.map(a => a.id === asset.id ? { ...a, is_favorite: !a.is_favorite } : a))
      toast.success(t('favorite_updated'))
    } catch {
      toast.error(t('action_failed'))
    }
  }

  const handleStatusChange = async (newStatus: string) => {
    if (!canModifyStatus || isShareReadonly) return
    try {
      const res = await projectsApi.update(project.id, { status: newStatus })
      onUpdate(res.data)
      toast.success(t('organization.status_updated'))
    } catch {
      toast.error(t('organization.status_failed'))
    }
  }

  const statusLabel = useMemo(() => {
    const statusKey = project.status
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join('')
    return t(`projectsPage.status${statusKey}`)
  }, [project.status, t])

  const statusColor = useMemo(() => {
    switch (project.status) {
      case 'completed': return 'bg-[var(--app-primary)] shadow-[0_0_0_4px_var(--app-tint-primary)]'
      case 'in_progress': return 'bg-[var(--app-success)] shadow-[0_0_0_4px_var(--app-tint-success)]'
      default: return 'bg-[var(--app-foreground-subtle)]'
    }
  }, [project.status])

  const getAvatarUrl = (url?: string) => {
    if (!url) return null
    return getImageUrl(url) ?? null
  }

  return (
    <div className="flex h-full flex-col bg-transparent text-foreground">
      <div className="flex items-center justify-between p-4 px-8 h-16">
        {isShareReadonly ? (
          <div className="flex items-center">
            <span className="text-sm font-semibold">{project.title}</span>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-4">
              <span className="text-sm text-[var(--app-foreground-subtle)] hover:text-[var(--app-primary)] cursor-pointer transition-colors" onClick={onBack}>{t('menu.projects')}</span>
              <span className="text-sm text-[var(--app-foreground-subtle)]">/</span>
              <span className="text-sm font-semibold">{project.title}</span>
            </div>
            <button
              onClick={onBack}
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground transition-opacity hover:text-foreground"
            >
              <ArrowLeft className="w-4 h-4" />
              {t('projectDetails.backToProjects')}
            </button>
          </>
        )}
      </div>

      <div className="flex flex-1 overflow-hidden px-8 gap-6 mt-4">
        {!isShareReadonly && (
          <div className="w-[300px] flex flex-col gap-6 pl-2">
            <h4 className="text-[26px] font-bold tracking-tight px-2">{t('projectDetails.teamMembers')}</h4>
            <div className="flex flex-col gap-1.5 overflow-y-auto pr-2 pb-12">
              {members.map((member) => {
                const avatar = getAvatarUrl(member.user?.avatar_url)
                const isActive = selectedMemberId === member.user_id
                return (
                  <div
                    key={member.user_id}
                    onClick={() => setSelectedMemberId(member.user_id)}
                    className={cn(
                      'group relative flex cursor-pointer items-center gap-4 rounded-[var(--app-radius-lg)] border p-4 pr-5 transition-all',
                      isActive
                        ? 'border-[var(--app-border)] bg-[var(--app-surface)] shadow-[var(--app-shadow-control)]'
                        : 'border-transparent bg-transparent text-[var(--app-foreground-muted)] hover:bg-[var(--app-control-hover)] hover:text-foreground'
                    )}
                  >
                    {isActive && (
                      <div className="absolute bottom-[15%] left-0 top-[15%] w-1.5 rounded-r-md bg-[var(--app-primary)]" />
                    )}

                    <div className="h-[52px] w-[52px] flex-shrink-0 overflow-hidden rounded-full border border-[var(--app-border)] bg-[var(--app-surface-muted)] shadow-sm">
                      {avatar ? (
                        <img src={avatar} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-lg font-bold uppercase text-[var(--app-foreground-muted)]">
                          {member.user?.nickname?.[0] || member.user?.username?.[0]}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center justify-between flex-1 min-w-0">
                      <span className="truncate text-[17px] font-bold text-foreground transition-colors">
                        {member.user?.nickname || member.user?.username}
                      </span>
                      {member.role === 'owner' && (
                        <BadgeCheck className="ml-2 h-[22px] w-[22px] flex-shrink-0 text-[var(--app-primary)]" />
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div className="flex-1 flex flex-col gap-6 overflow-hidden">
          <div className="relative h-10 flex items-center">
            <h4 className="text-lg font-bold absolute left-0">{t('projectDetails.assetLibrary')}</h4>

            <div className="flex-1 flex justify-center">
              <div className="flex items-center gap-2">
                <SegmentedControl
                  aria-label={t('projectDetails.assetLibrary')}
                  value={assetType}
                  onValueChange={setAssetType}
                  options={[
                    { key: 'all', label: t('projectDetails.all'), icon: LayoutGrid },
                    { key: 'image', label: t('projectDetails.image'), icon: ImageIcon },
                    { key: 'video', label: t('projectDetails.video'), icon: Video },
                  ]}
                  itemClassName="min-w-[76px]"
                />

                {!isShareReadonly && (
                  <div
                    role="button"
                    tabIndex={0}
                    aria-pressed={favoriteOnly}
                    className={cn(
                      'flex h-11 items-center gap-2 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-control-track)] px-3 text-sm font-bold text-[var(--app-foreground-muted)] shadow-[var(--app-shadow-control)] transition-all hover:text-foreground',
                      favoriteOnly && 'text-[var(--app-primary)]'
                    )}
                    onClick={() => setFavoriteOnly(!favoriteOnly)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setFavoriteOnly(current => !current)
                      }
                    }}
                  >
                    <Heart className={cn('h-4 w-4', favoriteOnly && 'fill-current')} />
                    <span>{t('my_favorites', { defaultValue: '我的收藏' })}</span>
                    <Switch checked={favoriteOnly} onCheckedChange={setFavoriteOnly} onClick={(event) => event.stopPropagation()} />
                  </div>
                )}
              </div>
            </div>
          </div>

          <div ref={assetScrollContainerRef} className="flex-1 overflow-y-auto overflow-x-hidden pb-32">
            {loading && assets.length === 0 ? (
              <div className="flex items-center justify-center h-48 text-[var(--app-foreground-subtle)]">{t('projectsPage.loading')}</div>
            ) : assets.length === 0 ? (
              <div className="flex items-center justify-center h-48 text-[var(--app-foreground-subtle)]">{t('no_assets_found')}</div>
            ) : (
              <>
                <VirtualizedSectionGrid
                  scrollContainerRef={assetScrollContainerRef}
                  sections={[{ key: 'assets', items: assets }]}
                  itemsRowClassName="w-full"
                  renderItem={(asset, absoluteIndex) => (
                    <AssetCard
                      key={asset.id}
                      asset={asset}
                      activeTab={assetType}
                      onToggleFavorite={handleToggleFavorite}
                      onClick={() => setPreviewIndex(absoluteIndex)}
                      showFavoriteAction={!isShareReadonly}
                    />
                  )}
                />

                {hasMore && (
                  <div
                    ref={(el) => {
                      if (el) {
                        const observer = new IntersectionObserver((entries) => {
                          if (entries[0].isIntersecting) {
                            loadMore()
                          }
                        }, { threshold: 0.1 })
                        observer.observe(el)
                      }
                    }}
                    className="h-10 flex items-center justify-center text-[var(--app-foreground-subtle)] text-xs font-bold"
                  >
                    {loading ? t('projectsPage.loading') : ''}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {!isShareReadonly && (
        <div className="fixed bottom-12 right-12 z-50">
          <AppSurface variant="glass" className="flex items-center gap-6 px-6 py-3">
            <div className="flex items-center gap-2 text-sm font-bold text-[var(--app-foreground-muted)]">
              <ImageIcon className="w-4.5 h-4.5 text-[var(--app-primary)]" />
              <span className="tabular-nums">{t('projectDetails.totalWorks', { count: stats.count })}</span>
            </div>

            <div className="flex items-center gap-2.5 text-sm font-bold">
              <div className={cn(
                'w-2 h-2 rounded-full',
                stats.isActive ? 'bg-[var(--app-success)] shadow-[0_0_0_4px_var(--app-tint-success)]' : 'bg-[var(--app-foreground-subtle)]'
              )} />
              <span className={cn(stats.isActive ? 'text-[var(--app-success)]' : 'text-[var(--app-foreground-subtle)]')}>
                {stats.isActive ? t('projectDetails.active') : t('projectDetails.offline')}
              </span>
            </div>

            {stats.lastUpdate && (
              <div className="flex items-center gap-2 text-sm font-bold text-[var(--app-foreground-subtle)]">
                <Clock className="w-4 h-4" />
                <span>
                  {t('projectDetails.recentUpdate', {
                    time: formatRelativeTime(stats.lastUpdate)
                  })}
                </span>
              </div>
            )}

            <div className="mx-1 h-4 w-px bg-[var(--app-border)]" />

            {canModifyStatus ? (
              <Popover>
                <PopoverTrigger asChild>
                  <button className="flex items-center gap-2.5 text-sm font-bold transition-all hover:opacity-100 group">
                    <div className={cn('w-2 h-2 rounded-full transition-transform group-hover:scale-125', statusColor)} />
                    <span className="transition-colors hover:text-[var(--app-primary)]">{statusLabel}</span>
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-32 p-1" side="top" align="end" sideOffset={10}>
                  <div className="flex flex-col gap-1">
                    {['pending', 'in_progress', 'completed'].map((status) => {
                      const statusKey = status
                        .split('_')
                        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
                        .join('')
                      return (
                        <button
                          key={status}
                          onClick={() => handleStatusChange(status)}
                          className={cn(
                            'px-3 py-2 rounded-lg text-xs font-bold text-left transition-all',
                            project.status === status
                              ? 'bg-[var(--app-control-selected)] text-[var(--app-primary)]'
                              : 'text-[var(--app-foreground-muted)] hover:bg-[var(--app-control-hover)] hover:text-foreground'
                          )}
                        >
                          {t(`projectsPage.status${statusKey}`)}
                        </button>
                      )
                    })}
                  </div>
                </PopoverContent>
              </Popover>
            ) : (
              <div className="flex items-center gap-2.5 text-sm font-bold text-[var(--app-foreground-muted)]">
                <div className={cn('w-2 h-2 rounded-full', statusColor)} />
                <span>{statusLabel}</span>
              </div>
            )}
          </AppSurface>
        </div>
      )}

      {previewIndex !== null && (
        <AssetPreviewModal
          assets={assets}
          initialIndex={previewIndex}
          onClose={() => setPreviewIndex(null)}
          canDownload={!isShareReadonly}
        />
      )}
    </div>
  )
}
