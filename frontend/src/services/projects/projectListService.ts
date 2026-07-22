import { projectsApi, type ProjectListItemRead } from '@/api/endpoints/projects'

export const PROJECT_LIST_PAGE_SIZE = 20
export const PROJECT_LIST_STALE_TIME_MS = 60_000

export interface ProjectListPage {
  items: ProjectListItemRead[]
  page: number
  totalPages: number
}

export function mergeProjectPageItems(
  currentProjects: ProjectListItemRead[],
  nextProjects: ProjectListItemRead[],
  reset: boolean,
) {
  if (reset) {
    return nextProjects
  }

  const mergedProjects = [...currentProjects]
  const existingProjectIds = new Set(currentProjects.map(project => project.id))

  nextProjects.forEach(project => {
    if (!existingProjectIds.has(project.id)) {
      mergedProjects.push(project)
    }
  })

  return mergedProjects
}

export function shouldRevalidateProjectList({
  initialized,
  lastFetchedAt,
  staleTimeMs = PROJECT_LIST_STALE_TIME_MS,
  now = Date.now(),
}: {
  initialized: boolean
  lastFetchedAt: number | null
  staleTimeMs?: number
  now?: number
}) {
  if (!initialized || lastFetchedAt === null) {
    return true
  }

  return (now - lastFetchedAt) >= staleTimeMs
}

export async function fetchProjectListPage(page: number, pageSize = PROJECT_LIST_PAGE_SIZE): Promise<ProjectListPage> {
  const response = await projectsApi.list({ page, page_size: pageSize })
  const pageData = response?.data ?? {
    items: [],
    page,
    total_pages: page,
  }

  return {
    items: pageData.items ?? [],
    page: pageData.page ?? page,
    totalPages: pageData.total_pages ?? page,
  }
}
