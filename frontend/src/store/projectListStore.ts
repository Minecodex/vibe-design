import { create } from 'zustand'

import type { ProjectListItemRead } from '@/api/endpoints/projects'
import {
  fetchProjectListPage,
  mergeProjectPageItems,
  PROJECT_LIST_PAGE_SIZE,
  PROJECT_LIST_STALE_TIME_MS,
  shouldRevalidateProjectList,
} from '@/services/projects/projectListService'

interface ProjectListState {
  projects: ProjectListItemRead[]
  loading: boolean
  loadingMore: boolean
  page: number
  hasMore: boolean
  initialized: boolean
  lastFetchedAt: number | null
}

interface FetchProjectPageOptions {
  reset?: boolean
  silent?: boolean
}

interface EnsureFreshOptions {
  silent?: boolean
  staleTimeMs?: number
}

interface ProjectListActions {
  fetchPage: (page: number, options?: FetchProjectPageOptions) => Promise<boolean>
  ensureFresh: (options?: EnsureFreshOptions) => Promise<boolean>
  replaceProject: (project: ProjectListItemRead) => void
  removeProject: (projectId: number) => void
  updateProjectUsers: (
    projectId: number,
    users: NonNullable<ProjectListItemRead['users']>,
  ) => void
}

type ProjectListStore = ProjectListState & ProjectListActions

const createInitialProjectListState = (): ProjectListState => ({
  projects: [],
  loading: true,
  loadingMore: false,
  page: 1,
  hasMore: false,
  initialized: false,
  lastFetchedAt: null,
})

let refreshRequest: Promise<boolean> | null = null
const loadMoreRequests = new Map<number, Promise<boolean>>()

export const useProjectListStore = create<ProjectListStore>()((set, get) => ({
  ...createInitialProjectListState(),

  fetchPage: async (page, options = {}) => {
    const { reset = false, silent = false } = options

    const runRequest = async () => {
      set(state => {
        if (reset) {
          if (silent && state.initialized && state.projects.length > 0) {
            return {}
          }

          return {
            loading: true,
          }
        }

        return {
          loadingMore: true,
        }
      })

      try {
        const pageData = await fetchProjectListPage(page, PROJECT_LIST_PAGE_SIZE)

        set(state => ({
          projects: mergeProjectPageItems(state.projects, pageData.items, reset),
          page: pageData.page,
          hasMore: pageData.page < pageData.totalPages,
          initialized: true,
          lastFetchedAt: Date.now(),
          loading: false,
          loadingMore: false,
        }))

        return true
      } catch {
        set({
          loading: false,
          loadingMore: false,
        })

        return false
      }
    }

    if (reset) {
      if (refreshRequest) {
        return refreshRequest
      }

      refreshRequest = runRequest().finally(() => {
        refreshRequest = null
      })

      return refreshRequest
    }

    if (loadMoreRequests.has(page)) {
      return loadMoreRequests.get(page)!
    }

    const loadMoreRequest = runRequest().finally(() => {
      loadMoreRequests.delete(page)
    })
    loadMoreRequests.set(page, loadMoreRequest)
    return loadMoreRequest
  },

  ensureFresh: async (options = {}) => {
    const { silent = true, staleTimeMs = PROJECT_LIST_STALE_TIME_MS } = options
    const state = get()

    if (!shouldRevalidateProjectList({
      initialized: state.initialized,
      lastFetchedAt: state.lastFetchedAt,
      staleTimeMs,
    })) {
      return true
    }

    return get().fetchPage(1, { reset: true, silent })
  },

  replaceProject: (project) => {
    set(state => ({
      projects: state.projects.map(item => (item.id === project.id ? project : item)),
    }))
  },

  removeProject: (projectId) => {
    set(state => ({
      projects: state.projects.filter(project => project.id !== projectId),
    }))
  },

  updateProjectUsers: (projectId, users) => {
    set(state => ({
      projects: state.projects.map(project => (
        project.id === projectId
          ? { ...project, users }
          : project
      )),
    }))
  },
}))

export function resetProjectListStore() {
  refreshRequest = null
  loadMoreRequests.clear()
  useProjectListStore.setState(createInitialProjectListState())
}
