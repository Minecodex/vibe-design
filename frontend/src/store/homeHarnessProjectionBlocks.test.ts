import { wireRecord } from './harnessWireFields'
import { describe, expect, it } from 'vitest'

import {
  appendBlockDelta,
  mergeBlockPatch,
  normalizeBlock,
  upsertBlockStart,
} from './homeHarnessProjectionBlocks'

describe('homeHarnessProjectionBlocks', () => {
  it('normalizes snake_case payload fields to camelCase', () => {
    const block = normalizeBlock({
      id: 'block-1',
      kind: 'content',
      ui_kind: 'assistant_text',
      payload: {
        preview_sections: ['a'],
        file_path: 'file_versions/report.md',
      },
    })

    expect(block.uiKind).toBe('assistant_text')
    expect(block.payload.previewSections).toEqual(['a'])
    expect(block.payload.filePath).toBe('file_versions/report.md')
  })

  it('keeps interaction forms visible after history block normalization', () => {
    const blocks = upsertBlockStart([], {
      id: 'interaction-form:quick-brief:conv-1',
      kind: 'interaction',
      order: 0,
      status: 'completed',
      visible: true,
      ui_kind: 'interaction_form',
      payload: {
        request_id: 'quick-brief:conv-1',
        kind: 'quick_brief',
        schema: {
          title: 'Quick brief',
          submit_label: 'Continue',
          fields: [
            {
              id: 'output',
              label: 'Output',
              type: 'text',
              required: true,
            },
          ],
        },
        status: 'pending',
      },
    })

    expect(blocks).toHaveLength(1)
    expect(blocks[0]?.uiKind).toBe('interaction_form')
    expect(blocks[0]?.payload.requestId).toBe('quick-brief:conv-1')
    expect(wireRecord(blocks[0]?.payload.schema)?.submitLabel).toBe('Continue')
  })

  it('applies start, delta, and patch updates consistently', () => {
    const started = upsertBlockStart([], {
      id: 'assistant-main',
      kind: 'text',
      order: 0,
      status: 'running',
      visible: true,
      ui_kind: 'assistant_text',
      payload: { text: '' },
    })

    const withDelta = appendBlockDelta(started, 'assistant-main', 'text', 'hello')
    const withPatch = mergeBlockPatch(withDelta, 'assistant-main', {
      payload: {
        text: 'hello world',
        status: 'completed',
      },
    })

    expect(withPatch[0]?.payload.text).toBe('hello world')
    expect(withPatch[0]?.payload.status).toBe('completed')
  })
})
