import { describe, expect, it } from 'vitest'

import type { OpenWorkspaceOfficeSessionResponse } from '@/api/endpoints/agent'
import type { HomeChatOfficeWorkbookSheetSnapshot } from './components/homeChatOfficeSnapshots'
import { buildSheetOfficeSessionSnapshot, isHomeChatOfficeSheetSnapshot, summarizeConversationRuntime } from './homeHarnessPageUtils'

describe('homeHarnessPageUtils', () => {
  const t = (key: string, fallback: string) => ({
    'home.runtime.activity.searching': '搜索中',
    'home.runtime.activity.answering': '回答中',
    'home.runtime.activity.planning_outline': '规划中',
    'home.runtime.status.completed': '已完成',
  }[key] || fallback)

  it('prioritizes running activity over stale planning phase', () => {
    expect(summarizeConversationRuntime({
      runtime_status: 'running',
      run_state: 'executing',
      phase: 'planning',
      activity: 'searching',
    }, t, 'zh-CN')).toBe('搜索中')
  })

  it('shows planning only for explicit planning activity while running', () => {
    expect(summarizeConversationRuntime({
      runtime_status: 'running',
      run_state: 'planning',
      phase: 'planning',
      activity: 'planning_outline',
    }, t, 'zh-CN')).toBe('规划中')
  })

  it('lets terminal completion override stale activity and phase', () => {
    expect(summarizeConversationRuntime({
      runtime_status: 'completed',
      run_state: 'completed',
      phase: 'planning',
      activity: 'searching',
    }, t, 'zh-CN')).toBe('已完成')
  })

  it('does not show planning for stale non-running planning phase alone', () => {
    expect(summarizeConversationRuntime({
      runtime_status: 'idle',
      run_state: 'idle',
      phase: 'planning',
    }, t, 'zh-CN')).toBe('Idle')
  })

  it('normalizes workbook payload fallback snapshots for home sheet preview', async () => {
    const session: OpenWorkspaceOfficeSessionResponse = {
      session_id: 'session-1',
      file_path: 'project/test.xlsx',
      file_kind: 'sheet',
      engine: 'univer',
      source_blob: 'not-base64',
      source_mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      snapshot: {
        kind: 'sheet',
        styles: {
          style1: { numFmt: '0.00' },
        },
        sheets: [
          {
            id: 'sheet-a',
            name: 'Sheet A',
            rows: {
              '0': { h: 32 },
              '1': { ignored: true },
            },
            cols: {
              '0': { w: 120 },
              '1': { ignored: true },
            },
            cells: {
              '0:0': { v: 'hello', t: 's', styleId: 'style1' },
            },
            merges: [{ startRow: 0, startCol: 0, endRow: 0, endCol: 1 }],
            freeze: { rowSplit: 1, colSplit: 0 },
          },
        ],
      },
      warnings: ['fallback warning'],
    }

    const normalized = await buildSheetOfficeSessionSnapshot(session, 'test.xlsx')
    expect(isHomeChatOfficeSheetSnapshot(normalized.snapshot)).toBe(true)

    if (!isHomeChatOfficeSheetSnapshot(normalized.snapshot) || Array.isArray(normalized.snapshot.sheets)) {
      throw new Error('Expected normalized workbook snapshot')
    }

    const snapshot = normalized.snapshot as HomeChatOfficeWorkbookSheetSnapshot

    expect(snapshot.sheetOrder).toEqual(['sheet-a'])
    expect(snapshot.sheets['sheet-a']).toEqual({
      id: 'sheet-a',
      name: 'Sheet A',
      rows: { '0': { h: 32 } },
      cols: { '0': { w: 120 } },
      cells: {
        '0:0': { v: 'hello', t: 's', styleId: 'style1' },
      },
      merges: [{ startRow: 0, startCol: 0, endRow: 0, endCol: 1 }],
      freeze: { rowSplit: 1, colSplit: 0 },
    })
    expect(snapshot.styles).toEqual({
      style1: { numFmt: '0.00' },
    })
    expect(snapshot.warning).toBe('fallback warning')
  })
})
