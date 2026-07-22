import type { ProjectionSessionLike } from './types'

export function hydratePresentationSnapshot<T extends ProjectionSessionLike>(session: T): T {
  return {
    ...session,
    appliedPresentationOps: [],
  }
}

