import { describe, expect, it } from 'vitest'

import type { WorkspaceFileRead } from '@/api/endpoints/agent'
import { filterFilesByTab, getFileTabCounts } from './homeChatFileTabs'

function item(name: string, source: WorkspaceFileRead['source'], path = name): WorkspaceFileRead {
  return {
    file_id: name,
    name,
    path,
    type: 'image',
    size: 1,
    created_at: '2026-04-30T00:00:00.000Z',
    current_version_id: '',
    versions: [],
    source,
  }
}

describe('homeChatFileTabs', () => {
  const files = [
    item('report.pptx', 'versioned_file'),
    item('upload.png', 'input_asset'),
    item('web.jpg', 'reference_asset'),
  ]

  it('filters files by the available modal tabs', () => {
    expect(filterFilesByTab(files, 'all')).toHaveLength(3)
    expect(filterFilesByTab(files, 'outputs')).toEqual([files[0]])
    expect(filterFilesByTab(files, 'inputs')).toEqual([files[1]])
    expect(filterFilesByTab(files, 'references')).toEqual([files[2]])
  })

  it('counts files for every tab', () => {
    expect(getFileTabCounts(files)).toEqual({
      all: 3,
      outputs: 1,
      inputs: 1,
      references: 1,
    })
  })
})
