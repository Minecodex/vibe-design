import type { WorkspaceFileRead } from '@/api/endpoints/agent'

export function mergeWorkspaceFileLists(
  primary: WorkspaceFileRead[],
  secondary: WorkspaceFileRead[]
): WorkspaceFileRead[] {
  const output: WorkspaceFileRead[] = []
  const indexes = new Map<string, number>()
  const keyForFile = (file: WorkspaceFileRead) => String(file.file_id || file.path || file.name)

  for (const file of [...primary, ...secondary]) {
    const key = keyForFile(file)
    if (!key) {
      continue
    }
    const existingIndex = indexes.get(key)
    if (existingIndex == null) {
      indexes.set(key, output.length)
      output.push(file)
    } else {
      output[existingIndex] = {
        ...output[existingIndex],
        ...file,
        versions: file.versions?.length ? file.versions : output[existingIndex].versions,
      }
    }
  }

  return output
}
