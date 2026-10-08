import type { ProjectListItemRead } from '@/api/endpoints/projects'

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
