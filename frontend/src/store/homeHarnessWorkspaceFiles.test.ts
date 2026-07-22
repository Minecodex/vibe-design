import { describe, expect, it } from 'vitest'
import type { WorkspaceFileRead } from '@/api/endpoints/agent'

import { mergeWorkspaceFileLists } from './homeHarnessWorkspaceFiles'

const file = (overrides: Partial<WorkspaceFileRead>): WorkspaceFileRead => ({
  file_id: '',
  name: '',
  path: '',
  type: 'other',
  size: 0,
  created_at: '',
  updated_at: null,
  current_version_id: '',
  versions: [],
  source: 'test',
  ...overrides,
})

describe('mergeWorkspaceFileLists', () => {
  it('deduplicates by file identity and preserves existing versions when updates omit them', () => {
    const merged = mergeWorkspaceFileLists(
      [
        file({
          file_id: 'file-1',
          name: 'report.docx',
          versions: [
            {
              version_id: 'v1',
              label: 'v1',
              size: 1,
              sha256: 'a',
              created_at: 'now',
              created_by: 'agent',
              run_id: null,
              parent_version_id: null,
              parent_input_asset_ids: [],
              referenced_asset_ids: [],
              note: null,
            },
          ],
        }),
      ],
      [
        file({
          file_id: 'file-1',
          name: 'report-final.docx',
          versions: [],
        }),
      ]
    )

    expect(merged).toHaveLength(1)
    expect(merged[0]?.name).toBe('report-final.docx')
    expect(merged[0]?.versions?.map((version) => version.version_id)).toEqual(['v1'])
  })
})
