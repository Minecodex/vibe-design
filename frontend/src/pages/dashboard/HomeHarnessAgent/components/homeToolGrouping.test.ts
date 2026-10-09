import { createTranslationFixture } from '@/store/testing/translationFixture'
import { describe, expect, it } from 'vitest'

import type { MessageBlock } from '@/store/homeHarnessStore'

import { groupHomeReadonlyToolBlocks, summarizeToolGroup, TOOL_GROUP_UI_KIND } from './homeToolGrouping'

const t = createTranslationFixture({})

function toolBlock(id: string, tool: string, status = 'completed'): MessageBlock {
  return {
    id,
    kind: 'tool',
    order: 0,
    status,
    visible: true,
    uiKind: 'tool_result',
    payload: { tool, status },
  }
}

function textBlock(id: string): MessageBlock {
  return {
    id,
    kind: 'text',
    order: 0,
    status: 'completed',
    visible: true,
    uiKind: 'assistant_text',
    payload: { text: 'narration' },
  }
}

describe('groupHomeReadonlyToolBlocks', () => {
  it('collapses 2+ consecutive readonly tool blocks into one group', () => {
    const result = groupHomeReadonlyToolBlocks([
      toolBlock('a', 'read_file'),
      toolBlock('b', 'read_file'),
      toolBlock('c', 'grep_files'),
    ])
    expect(result).toHaveLength(1)
    expect(result[0].uiKind).toBe(TOOL_GROUP_UI_KIND)
    expect(result[0].children).toHaveLength(3)
  })

  it('keeps a lone readonly tool as its own row', () => {
    const result = groupHomeReadonlyToolBlocks([toolBlock('a', 'read_file')])
    expect(result).toHaveLength(1)
    expect(result[0].uiKind).toBe('tool_result')
  })

  it('breaks the group on a text block (turn boundary)', () => {
    const result = groupHomeReadonlyToolBlocks([
      toolBlock('a', 'read_file'),
      toolBlock('b', 'read_file'),
      textBlock('t'),
      toolBlock('c', 'read_file'),
      toolBlock('d', 'read_file'),
    ])
    expect(result.map((block) => block.uiKind)).toEqual([
      TOOL_GROUP_UI_KIND,
      'assistant_text',
      TOOL_GROUP_UI_KIND,
    ])
  })

  it('breaks the group on a write/exec tool block', () => {
    const result = groupHomeReadonlyToolBlocks([
      toolBlock('a', 'read_file'),
      toolBlock('b', 'read_file'),
      toolBlock('w', 'write_file'),
      toolBlock('c', 'read_file'),
    ])
    expect(result.map((block) => block.uiKind)).toEqual([
      TOOL_GROUP_UI_KIND,
      'tool_result',
      'tool_result',
    ])
  })
})

describe('summarizeToolGroup', () => {
  it('counts reads and searches separately', () => {
    const summary = summarizeToolGroup(
      [toolBlock('a', 'read_file'), toolBlock('b', 'read_file'), toolBlock('c', 'grep_files')],
      t,
    )
    expect(summary).toContain('读取 2 个文件')
    expect(summary).toContain('搜索 1 处')
  })
})
