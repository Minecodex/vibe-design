import { lazy, Suspense, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, Circle, Clock3, Plus, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { projectsApi, type ProjectListItemRead, type ProjectRead } from '@/api/endpoints/projects'
import { useAuthStore } from '@/store/authStore'
import { useProjectListStore } from '@/store/projectListStore'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { ProjectCard } from './ProjectCard'
import { AppSurface, SegmentedControl } from '@/components/common/ui'

const ShareModal = lazy(() => import('@/components/project/ShareModal').then(module => ({ default: module.ShareModal })))
const MembersModal = lazy(() => import('@/components/project/MembersModal').then(module => ({ default: module.MembersModal })))
const ProjectDetailsView = lazy(() => import('@/components/project/ProjectDetailsView').then(module => ({ default: module.ProjectDetailsView })))

export function applyProjectUsersUpdate(
  projects: ProjectListItemRead[],
  projectId: number,
  users: NonNullable<ProjectListItemRead['users']>,
) {
  return projects.map(project => (
    project.id === projectId
      ? { ...project, users }
      : project
  ))
}

export function getNextRenderedProjectCount({
  currentRenderedCount,
  projectRenderChunkSize,
  visibleProjectCount,
}: {
  currentRenderedCount: number
  projectRenderChunkSize: number
  visibleProjectCount: number
}) {
  if (visibleProjectCount <= projectRenderChunkSize) {
    return visibleProjectCount
  }

  return Math.max(
    projectRenderChunkSize,
    Math.min(currentRenderedCount, visibleProjectCount)
  )
}

export function ProjectsPage() {
  const projectRenderChunkSize = 6
  const { t } = useTranslation()
  const navigate = useNavigate()
  const currentUser = useAuthStore(state => state.user)
  const projects = useProjectListStore(state => state.projects)
  const loading = useProjectListStore(state => state.loading)
  const loadingMore = useProjectListStore(state => state.loadingMore)
  const page = useProjectListStore(state => state.page)
  const hasMore = useProjectListStore(state => state.hasMore)
  const ensureFresh = useProjectListStore(state => state.ensureFresh)
  const fetchPage = useProjectListStore(state => state.fetchPage)
  const replaceProject = useProjectListStore(state => state.replaceProject)
  const removeProject = useProjectListStore(state => state.removeProject)
  const updateProjectUsers = useProjectListStore(state => state.updateProjectUsers)
  const [shareOpen, setShareOpen] = useState(false)
  const [membersOpen, setMembersOpen] = useState(false)
  const [selectedProject, setSelectedProject] = useState<ProjectRead | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')
  const [detailOpen, setDetailOpen] = useState(false)
  const [renderedProjectCount, setRenderedProjectCount] = useState(projectRenderChunkSize)
  const loadMoreRef = useRef<HTMLDivElement | null>(null)
  const deferredSearchQuery = useDeferredValue(searchQuery)
  const ownerOnlyHint = t('projectsPage.ownerOnlyHint')

  const showProjectsLoadError = useCallback(() => {
    toast.error(t('projectsPage.loadFailed'))
  }, [t])

  const refreshProjects = useCallback(async ({ force = false }: { force?: boolean } = {}) => {
    const succeeded = force
      ? await fetchPage(1, { reset: true, silent: true })
      : await ensureFresh()
    if (!succeeded) {
      showProjectsLoadError()
    }
  }, [ensureFresh, fetchPage, showProjectsLoadError])

  const loadMoreProjects = useCallback(async (nextPage: number) => {
    const succeeded = await fetchPage(nextPage)
    if (!succeeded) {
      showProjectsLoadError()
    }
  }, [fetchPage, showProjectsLoadError])

  useEffect(() => {
    void refreshProjects({ force: true })
  }, [refreshProjects])

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshProjects()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [refreshProjects])

  useEffect(() => {
    const target = loadMoreRef.current
    if (!target || loading || loadingMore || !hasMore) {
      return
    }

    const observer = new IntersectionObserver(
      entries => {
        const [entry] = entries
        if (entry?.isIntersecting) {
          void loadMoreProjects(page + 1)
        }
      },
      {
        root: null,
        rootMargin: '0px 0px 240px 0px',
      }
    )

    observer.observe(target)
    return () => observer.disconnect()
  }, [hasMore, loadMoreProjects, loading, loadingMore, page])

  const handleCreate = async () => {
    try {
      const res = await projectsApi.create({ title: 'Untitled' })
      navigate(`/canvas/${res.data.id}`)
    } catch {
      toast.error(t('projectsPage.createFailed'))
    }
  }

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    try {
      await projectsApi.delete(id)
      removeProject(id)
      toast.success(t('projectsPage.deleteSuccess'))
    } catch {
      toast.error(t('projectsPage.deleteFailed'))
    }
  }

  const formatDate = useCallback((dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN')
  }, [])

  const handleProjectClick = useCallback((project: ProjectRead) => {
    const isAdmin = currentUser?.role === 'admin'
    const hasJoinedProject = !!currentUser && !!project.users?.some(user => user.id === currentUser.id)

    if (isAdmin && !hasJoinedProject) {
      setSelectedProject(project)
      setDetailOpen(true)
      return
    }

    navigate(`/canvas/${project.id}`)
  }, [currentUser, navigate])

  const handleProjectMembersChange = useCallback((projectId: number, users: NonNullable<ProjectListItemRead['users']>) => {
    updateProjectUsers(projectId, users)
    setSelectedProject(prev => (
      prev && prev.id === projectId
        ? { ...prev, users }
        : prev
    ))
  }, [updateProjectUsers])

  const handleOpenMembers = useCallback((project: ProjectRead) => {
    setSelectedProject(project)
    setMembersOpen(true)
  }, [])

  const handleOpenShare = useCallback((project: ProjectRead) => {
    setSelectedProject(project)
    setShareOpen(true)
  }, [])

  const handleOpenDetails = useCallback((project: ProjectRead) => {
    setSelectedProject(project)
    setDetailOpen(true)
  }, [])

  const visibleProjects = useMemo(() => projects.filter(project => {
    const matchedSearch = project.title.toLowerCase().includes(deferredSearchQuery.toLowerCase())
    const matchedStatus = filterStatus === 'all' || project.status === filterStatus
    return matchedSearch && matchedStatus
  }), [deferredSearchQuery, filterStatus, projects])

  useEffect(() => {
    if (visibleProjects.length <= projectRenderChunkSize) {
      setRenderedProjectCount(visibleProjects.length)
      return
    }

    let cancelled = false
    let timeoutId: number | null = null

    setRenderedProjectCount(current => getNextRenderedProjectCount({
      currentRenderedCount: current,
      projectRenderChunkSize,
      visibleProjectCount: visibleProjects.length,
    }))

    const step = () => {
      if (cancelled) {
        return
      }

      setRenderedProjectCount(current => {
        const baselineCount = getNextRenderedProjectCount({
          currentRenderedCount: current,
          projectRenderChunkSize,
          visibleProjectCount: visibleProjects.length,
        })
        const nextCount = Math.min(baselineCount + projectRenderChunkSize, visibleProjects.length)
        if (nextCount < visibleProjects.length) {
          timeoutId = window.setTimeout(step, 32)
        }
        return nextCount
      })
    }

    timeoutId = window.setTimeout(step, 32)

    return () => {
      cancelled = true
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId)
      }
    }
  }, [projectRenderChunkSize, visibleProjects])

  const stagedVisibleProjects = visibleProjects.slice(0, renderedProjectCount)

  if (detailOpen && selectedProject) {
    return (
      <Suspense fallback={null}>
        <ProjectDetailsView
          project={selectedProject}
          onBack={() => {
            setDetailOpen(false)
            void refreshProjects({ force: true })
          }}
          onUpdate={(updated) => {
            replaceProject(updated)
            setSelectedProject(updated)
          }}
        />
      </Suspense>
    )
  }

  return (
    <div data-testid="projects-page-scroll" className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden bg-transparent">
      <div className="px-12 pt-10 pb-12">
        <div className="mb-10 flex items-center justify-between gap-4">
          <SegmentedControl
            aria-label={t('projectsPage.statusFilter')}
            value={filterStatus}
            onValueChange={setFilterStatus}
            options={[
              { key: 'all', label: t('projectsPage.statusAll'), icon: Circle },
              { key: 'pending', label: t('projectsPage.statusPending'), icon: Clock3 },
              { key: 'in_progress', label: t('projectsPage.statusInProgress'), icon: Circle },
              { key: 'completed', label: t('projectsPage.statusCompleted'), icon: CheckCircle2 },
            ]}
          />

          <div className="relative w-[320px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-foreground-subtle)]" />
            <input
              type="text"
              placeholder={t('projectsPage.searchPlaceholder')}
              className={cn(
                'h-10 w-full min-w-0 rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-surface-muted)] py-1 pl-9 pr-3 text-sm font-medium text-foreground outline-none transition-[background,border-color,color,box-shadow]',
                'placeholder:text-[var(--app-foreground-subtle)] focus-visible:border-[var(--app-border-strong)] focus-visible:ring-[3px] focus-visible:ring-[var(--app-focus-ring)]'
              )}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
          <AppSurface
            variant="control"
            className="flex h-[260px] cursor-pointer flex-col items-center justify-center border-dashed transition-all hover:-translate-y-0.5 hover:border-[var(--app-border-strong)] hover:shadow-[var(--app-shadow-panel)]"
            onClick={handleCreate}
          >
            <Plus className="mb-2 h-7 w-7 text-[var(--app-foreground-muted)]" />
            <div className="text-[15px] font-medium text-foreground">
              {t('projectsPage.newProject')}
            </div>
          </AppSurface>

          {loading ? (
            <div className="col-span-full text-center py-10 text-muted-foreground">
              {t('projectsPage.loading')}
            </div>
          ) : (
            <>
              {stagedVisibleProjects.map((project) => (
                <ProjectCard
                  key={project.id}
                  currentUser={currentUser}
                  formatDate={formatDate}
                  onDelete={handleDelete}
                  onOpenDetails={handleOpenDetails}
                  onOpenMembers={handleOpenMembers}
                  onOpenShare={handleOpenShare}
                  onProjectClick={handleProjectClick}
                  ownerOnlyHint={ownerOnlyHint}
                  project={project}
                />
              ))}
              {loadingMore && (
                <div className="col-span-full text-center py-6 text-muted-foreground">
                  {t('projectsPage.loading')}
                </div>
              )}
              {hasMore && <div ref={loadMoreRef} className="col-span-full h-1" aria-hidden="true" />}
            </>
          )}
        </div>

        <Suspense fallback={null}>
          <ShareModal
            open={shareOpen}
            onClose={() => { setShareOpen(false); setTimeout(() => setSelectedProject(null), 300) }}
            project={selectedProject}
            onUpdate={(updated) => {
              replaceProject(updated)
              setSelectedProject(updated)
            }}
          />

          {selectedProject && (
            <MembersModal
              open={membersOpen}
              onClose={() => { setMembersOpen(false); setTimeout(() => setSelectedProject(null), 300) }}
              projectId={selectedProject.id}
              ownerUserId={selectedProject.user_id}
              onMembersChange={(users) => handleProjectMembersChange(selectedProject.id, users)}
            />
          )}
        </Suspense>
      </div>
    </div>
  )
}
