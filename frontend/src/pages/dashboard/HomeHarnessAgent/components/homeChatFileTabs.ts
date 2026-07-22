import type { WorkspaceFileRead } from '@/api/endpoints/agent'

export type HomeChatFileTab = 'all' | 'outputs' | 'inputs' | 'references'

export const HOME_CHAT_FILE_TABS: HomeChatFileTab[] = [
  'all',
  'outputs',
  'inputs',
  'references',
]

export function getFileTabForFile(file: WorkspaceFileRead): Exclude<HomeChatFileTab, 'all'> {
  const source = String(file.source || '')
  if (source === 'input_asset') {
    return 'inputs'
  }
  if (source === 'reference_asset') {
    return 'references'
  }
  return 'outputs'
}

export function filterFilesByTab<T extends WorkspaceFileRead>(files: T[], tab: HomeChatFileTab): T[] {
  if (tab === 'all') {
    return files
  }
  return files.filter((file) => getFileTabForFile(file) === tab)
}

export function getFileTabCounts(files: WorkspaceFileRead[]): Record<HomeChatFileTab, number> {
  const counts: Record<HomeChatFileTab, number> = {
    all: files.length,
    outputs: 0,
    inputs: 0,
    references: 0,
  }
  for (const file of files) {
    counts[getFileTabForFile(file)] += 1
  }
  return counts
}
