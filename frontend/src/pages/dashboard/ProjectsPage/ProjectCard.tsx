import { memo, useMemo, useState, type MouseEvent, type ReactNode } from 'react'
import { Info, MoreVertical, Share2, Trash2, UserCog, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { type ProjectListItemRead, type ProjectRead } from '@/api/endpoints/projects'
import { cn } from '@/lib/utils'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useProjectCardVisibility } from './useProjectCardVisibility'
import { CachedImage } from '@/components/ui/CachedImage'
import { IconButton } from '@/components/common/ui'

type AuthUser = {
  id: number
  username: string
  role: string
} | null

type ProjectCardProps = {
  currentUser: AuthUser
  formatDate: (dateStr: string) => string
  onDelete: (event: MouseEvent, projectId: number) => void
  onOpenDetails: (project: ProjectRead) => void
  onOpenMembers: (project: ProjectRead) => void
  onOpenShare: (project: ProjectRead) => void
  onProjectClick: (project: ProjectRead) => void
  ownerOnlyHint: string
  project: ProjectListItemRead
}

function ProjectCardComponent({
  currentUser,
  formatDate,
  onDelete,
  onOpenDetails,
  onOpenMembers,
  onOpenShare,
  onProjectClick,
  ownerOnlyHint,
  project,
}: ProjectCardProps) {
  const { t } = useTranslation()
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false)
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)

  const preview = useMemo(() => {
    const previewItems = project.project_preview_items || []
    const imageUrls = previewItems
      .filter(item => item.asset_type === 'image')
      .map(item => ({
        src: item.list_preview_url || item.url,
        originalUrl: item.url,
      }))

    const videoUrl = imageUrls.length === 0
      ? previewItems.find(item => item.asset_type === 'video')?.url || null
      : null

    if (previewItems.length > 0) {
      return {
        count: Math.min(imageUrls.length, 4),
        imageUrls,
        videoUrl,
      }
    }

    return {
      count: 0,
      imageUrls: [],
      videoUrl: null,
    }
  }, [project.project_preview_items])

  const hasHeavyPreview = preview.count > 0 || Boolean(preview.videoUrl)
  const previewContentKey = useMemo(() => {
    if (!hasHeavyPreview) {
      return 'light-preview'
    }

    return JSON.stringify({
      imageUrls: preview.imageUrls,
      videoUrl: preview.videoUrl,
    })
  }, [hasHeavyPreview, preview.imageUrls, preview.videoUrl])

  const { isActive, ref } = useProjectCardVisibility<HTMLDivElement>({
    disabled: !hasHeavyPreview,
    resetKey: previewContentKey,
  })

  const actionClassName = 'flex w-full items-center gap-2.5 rounded-[var(--app-radius-sm)] px-3.5 py-3 text-left text-[13px] font-semibold transition-colors'
  const enabledActionClassName = `${actionClassName} cursor-pointer text-foreground hover:bg-[var(--app-control-hover)]`
  const disabledActionClassName = `${actionClassName} cursor-not-allowed bg-transparent text-[var(--app-foreground-subtle)]`

  const renderOwnerOnlyAction = (
    icon: ReactNode,
    label: string,
    onClick: () => void
  ) => {
    const canManageProject = currentUser && (
      project.user_id === currentUser.id || currentUser.role === 'admin'
    )

    if (canManageProject) {
      return (
        <DropdownMenuItem
          className={enabledActionClassName}
          onSelect={() => {
            setIsMoreMenuOpen(false)
            onClick()
          }}
        >
          {icon}{label}
        </DropdownMenuItem>
      )
    }

    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span title={ownerOnlyHint}>
              <DropdownMenuItem
                disabled
                aria-disabled="true"
                title={ownerOnlyHint}
                className={disabledActionClassName}
              >
                {icon}{label}
              </DropdownMenuItem>
            </span>
          </TooltipTrigger>
          <TooltipContent side="left">{ownerOnlyHint}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <div
      ref={ref}
      className={cn(
        'relative z-0 flex h-[260px] transform-gpu cursor-pointer flex-col rounded-[var(--app-radius-lg)] border border-[var(--app-border)] bg-[var(--app-surface)] shadow-sm transition-transform transition-shadow hover:-translate-y-0.5 hover:z-20 hover:shadow-[var(--app-shadow-panel)]'
      )}
      style={{
        contain: 'layout style',
        containIntrinsicSize: '260px',
        contentVisibility: 'auto',
      }}
      onClick={() => onProjectClick(project)}
    >
      <div
        className={cn(
          'absolute inset-0 z-0 overflow-hidden rounded-[var(--app-radius-lg)] bg-[var(--app-surface-muted)]'
        )}
      >
        {preview.count > 0 && isActive ? (
          <div
            className="w-full h-full grid gap-[2px] relative"
            style={{
              gridTemplateColumns: preview.count === 1 ? '1fr' : '1fr 1fr',
              gridTemplateRows: preview.count <= 2 ? '1fr' : '1fr 1fr',
            }}
          >
            {preview.imageUrls.slice(0, 4).map((image, idx) => (
              <div
                key={`${image.originalUrl}-${idx}`}
                className="relative overflow-hidden w-full h-full"
                style={{
                  ...(preview.count === 1 ? { gridColumn: '1 / -1', gridRow: '1 / -1' } : {}),
                  ...(preview.count === 3 && idx === 0 ? { gridRow: '1 / -1' } : {}),
                }}
              >
                <CachedImage
                  src={image.src}
                  alt=""
                  className="w-full h-full object-cover"
                  draggable={false}
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        ) : preview.videoUrl && isActive ? (
          <video src={preview.videoUrl} className="w-full h-full object-cover" muted preload="metadata" />
        ) : hasHeavyPreview ? null : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--app-foreground-subtle)]">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          </div>
        )}
      </div>

      <div
        className={cn(
          'absolute left-4 top-4 z-10 h-3 w-3 rounded-full border-[1.5px] border-[var(--app-surface-solid)] shadow-sm',
          project.status === 'in_progress' ? 'bg-[var(--app-primary)]' :
          project.status === 'completed' ? 'bg-[var(--app-success)]' : 'bg-[var(--app-foreground-subtle)]'
        )}
      />

      <div className="absolute top-3 right-3 z-20 group/people" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-1.5 rounded-full border border-[var(--app-border)] bg-[var(--app-glass)] px-3 py-1.5 text-[13px] font-medium text-foreground shadow-[var(--app-shadow-control)] backdrop-blur-2xl transition-colors hover:bg-[var(--app-control-hover)]">
          <Users className="w-3.5 h-3.5" />
          <span>{t('projectsPage.usersCount', { count: (project.users?.length || 1) })}</span>
        </div>
        <div className="invisible absolute right-0 top-full z-30 mt-2 flex min-w-[140px] max-w-[200px] origin-top-right flex-col gap-1 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-glass)] p-1.5 opacity-0 shadow-[var(--app-shadow-panel)] backdrop-blur-2xl transition-opacity duration-150 pointer-events-none group-hover/people:pointer-events-auto group-hover/people:visible group-hover/people:opacity-100">
          {(project.users || []).map((person, i) => {
            const name = person.nickname || person.username || '\u672a\u77e5'
            const colorClass = ['bg-blue-400', 'bg-green-400', 'bg-indigo-400', 'bg-purple-400', 'bg-pink-400'][i % 5]
            return (
              <div key={i} className="flex cursor-default items-center gap-2.5 rounded-[var(--app-radius-sm)] px-2.5 py-2 hover:bg-[var(--app-control-hover)]" title={name}>
                <div className={`w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center text-[11px] text-white font-medium ${colorClass} shadow-inner overflow-hidden`}>
                  {person.avatar_url ? (
                    <img
                      src={person.avatar_url}
                      alt=""
                      className="w-full h-full object-cover"
                      decoding="async"
                      loading="lazy"
                    />
                  ) : (
                    name[0]?.toUpperCase()
                  )}
                </div>
                <span className="truncate pr-1 text-sm font-medium text-foreground">{name}</span>
              </div>
            )
          })}
        </div>
      </div>

        <div
          className={cn(
            'absolute bottom-0 left-0 right-0 z-10 flex h-[86px] items-center justify-between rounded-b-[var(--app-radius-lg)] border-t border-[var(--app-border)] bg-[color-mix(in_srgb,var(--app-glass)_82%,transparent)] px-5 text-foreground backdrop-blur-2xl'
          )}
        >
        <div className="flex flex-col gap-1 justify-center h-full overflow-hidden">
          <div className="truncate text-[15px] font-bold tracking-tight text-foreground">
            {project.title}
          </div>
          <div className="text-[11px] font-medium text-[var(--app-foreground-muted)]">
            {t('projectsPage.updatedAt', { date: formatDate(project.updated_at) })}
          </div>
        </div>

        <div className="relative flex items-center gap-2" onClick={e => e.stopPropagation()}>
          <DropdownMenu open={isMoreMenuOpen} onOpenChange={setIsMoreMenuOpen}>
            <DropdownMenuTrigger asChild>
              <IconButton
                aria-label="More actions"
                size="icon-sm"
                className="text-[var(--app-foreground-muted)]"
                onPointerDown={event => {
                  event.preventDefault()
                }}
                onClick={() => setIsMoreMenuOpen(current => !current)}
              >
                <MoreVertical className="w-5 h-5" />
              </IconButton>
            </DropdownMenuTrigger>

            <DropdownMenuContent
              align="end"
              side="top"
              sideOffset={10}
              className="w-[150px] p-1.5"
              onClick={event => event.stopPropagation()}
            >
              {renderOwnerOnlyAction(
                <UserCog className="w-4 h-4" />,
                t('projectsPage.userConfig'),
                () => onOpenMembers(project)
              )}
              {renderOwnerOnlyAction(
                <Share2 className="w-4 h-4" />,
                t('projectsPage.projectShare'),
                () => onOpenShare(project)
              )}
              <DropdownMenuItem
                className={enabledActionClassName}
                onSelect={() => {
                  setIsMoreMenuOpen(false)
                  onOpenDetails(project)
                }}
              >
                <Info className="w-4 h-4" />{t('projectsPage.projectDetails')}
              </DropdownMenuItem>

              {currentUser && (project.user_id === currentUser.id || currentUser.role === 'admin') && (
                <>
                  <DropdownMenuSeparator className="my-1" />
                  <DropdownMenuItem
                    className="flex w-full items-center gap-2.5 rounded-2xl px-3.5 py-3 text-left text-[13px] font-semibold text-red-500 transition-colors hover:bg-red-500/10 focus:bg-red-500/10"
                    onSelect={() => {
                      setIsMoreMenuOpen(false)
                      setIsDeleteDialogOpen(true)
                    }}
                  >
                    <Trash2 className="w-4 h-4 text-red-500" />{t('projectsPage.delete')}
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
            <AlertDialogContent noDarken className={cn(
              'max-w-[420px] p-7'
            )}>
              <AlertDialogHeader className="space-y-3">
                <AlertDialogTitle className="text-xl font-bold tracking-tight text-foreground">
                  {t('projectsPage.deleteConfirmTitle')}
                </AlertDialogTitle>
                <AlertDialogDescription className="text-sm font-medium leading-relaxed text-muted-foreground">
                  {t('projectsPage.deleteConfirmDesc')}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter className="mt-6 gap-3 sm:justify-end">
                <AlertDialogCancel className="h-11 px-7 text-sm font-bold">
                  {t('projectsPage.cancel')}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={e => onDelete(e as unknown as MouseEvent, project.id)}
                  variant="destructive"
                  className="h-11 px-7 text-sm font-bold"
                >
                  {t('projectsPage.confirm')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
    </div>
  )
}

export const ProjectCard = memo(ProjectCardComponent)
