import { legacyHarnessEvent } from './testing/legacyHarnessEvent'
import type { TurnCompletionOverrides } from './testing/harnessEventFixtures'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/i18n', () => ({
  default: {
    t: (_key: string, fallback?: string) => fallback ?? '',
  },
}))
import {
  applyHomeHarnessEvent,
  createHomeHarnessProjectionState,
} from './homeHarnessProjection'
import type { HomeHarnessProjectionEvent, HomeHarnessProjectionState } from './homeHarnessProjection'
import { replayHomeHarnessEvents } from './__tests__/harnessProjectionReplay'
import { isSessionHtmlFile } from '@/pages/dashboard/HomeHarnessAgent/components/homeChatWorkspaceFileKinds'

function turnCompleted(
  status: 'completed' | 'failed' | 'blocked' | 'cancelled' | 'waiting_input',
  data: Omit<TurnCompletionOverrides, 'terminal_error'> & { terminal_error?: string | { message?: string } } = {},
): HomeHarnessProjectionEvent {
  const conversationId = String(data.conversation_id || 'conv-1')
  const runId = String(data.run_id || 'run-1')
  const summary = String(data.summary || data.message || (typeof data.terminal_error === 'object' ? data.terminal_error.message : undefined) || data.terminal_error || '')
  return {
    type: 'turn_completed',
    sequence: data.sequence,
    run_id: runId,
    lane: 'user',
    data: {
      conversation_id: conversationId,
      run_id: runId,
      turn_id: runId,
      status,
      error: status === 'failed' || status === 'blocked'
        ? {
          error_type: data.error_type || (status === 'blocked' ? 'Blocked' : 'Failed'),
          summary,
          user_visible: data.user_visible !== false,
          failure_signature: data.failure_signature ?? null,
        }
        : null,
      runtime_snapshot: {
        runtime_status: status,
        run_state: status,
        turn_status: status,
        ...(data.runtime_snapshot || {}),
      },
      completed_at: '2026-05-01T00:00:00.000Z',
      duration_ms: null,
    },
  }
}

describe('homeHarnessProjection', () => {

    it('upserts file_version_created payloads without changing visible file shape', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'file_version_created',
        sequence: 1,
        data: {
          file_id: 'f_report',
          name: 'report.md',
          path: 'file_versions/f_report/v0001/source.md',
          type: 'markdown',
          size: 10,
          current_version_id: 'v0001',
          versions: [
            {
              version_id: 'v0001',
              label: 'Version 1',
              path: 'file_versions/f_report/v0001/source.md',
              size: 10,
              sha256: 'x',
              created_at: '2026-04-30T00:00:00Z',
            },
          ],
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(projection.workspaceFiles).toHaveLength(1)
    expect(projection.workspaceFiles[0]?.file_id).toBe('f_report')
    expect(projection.workspaceFiles[0]?.name).toBe('report.md')
    expect(projection.workspaceFiles[0]?.current_version_id).toBe('v0001')
  })

    it('preserves web bundle metadata from realtime file_version_created events', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'file_version_created',
        sequence: 1,
        data: {
          file_id: 'f_8b40f57dbc',
          name: 'index.zip',
          path: 'published/f_8b40f57dbc/v0001/source.zip',
          type: 'web',
          size: 23147,
          current_version_id: 'v0001',
          artifact_kind: 'web_bundle',
          artifact_metadata: {
            artifact_kind: 'web_bundle',
            bundle_format: 'zip',
            entry: 'index.html',
            source_path: 'html-ppt-prepared/index.html',
            members_count: 6,
          },
          current_version: {
            version_id: 'v0001',
            label: '版本 1',
            size: 23147,
            sha256: 'f8d1bd8ca1da33106c660d424e19754142cf321a181bd514fcfa740e570fa345',
            created_at: '2026-05-23T13:50:22.682529+00:00',
            created_by: 'agent',
            artifact_metadata: {
              artifact_kind: 'web_bundle',
              bundle_format: 'zip',
              entry: 'index.html',
              source_path: 'html-ppt-prepared/index.html',
              members_count: 6,
            },
          },
          versions: [
            {
              version_id: 'v0001',
              label: '版本 1',
              size: 23147,
              sha256: 'f8d1bd8ca1da33106c660d424e19754142cf321a181bd514fcfa740e570fa345',
              created_at: '2026-05-23T13:50:22.682529+00:00',
              created_by: 'agent',
              artifact_metadata: {
                artifact_kind: 'web_bundle',
                bundle_format: 'zip',
                entry: 'index.html',
                source_path: 'html-ppt-prepared/index.html',
                members_count: 6,
              },
            },
          ],
        },
      },
    ] , createHomeHarnessProjectionState())

    const file = projection.workspaceFiles[0]
    expect(file?.artifact_kind).toBe('web_bundle')
    expect(file?.artifact_metadata).toMatchObject({ bundle_format: 'zip', entry: 'index.html' })
    expect(file?.versions?.[0]?.artifact_metadata).toMatchObject({ bundle_format: 'zip', entry: 'index.html' })
    expect(file ? isSessionHtmlFile(file) : false).toBe(true)
  })

    it('upserts unified workspace_file_upserted payloads from realtime snapshots', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'workspace_file_upserted',
        sequence: 2,
        data: {
          file_id: 'generated_image_001',
          name: 'image.png',
          path: 'references/generated/generated_image_001/original.png',
          type: 'image',
          size: 512,
          created_at: '2026-06-07T17:15:31.605301+00:00',
          current_version_id: '',
          versions: [],
          source: 'reference_asset',
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(projection.workspaceFiles).toHaveLength(1)
    expect(projection.workspaceFiles[0]).toMatchObject({
      file_id: 'generated_image_001',
      name: 'image.png',
      path: 'references/generated/generated_image_001/original.png',
      type: 'image',
      source: 'reference_asset',
    })
  })

    it('normalizes asset_registered payloads into workspace files', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'asset_registered',
        sequence: 3,
        data: {
          asset_id: 'web_image_001',
          kind: 'reference',
          original_name: 'search-result.jpg',
          path: 'references/sources/web_image_001/original.jpg',
          mime_type: 'image/jpeg',
          size: 1024,
          created_at: '2026-06-07T17:15:31.605301+00:00',
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(projection.workspaceFiles).toHaveLength(1)
    expect(projection.workspaceFiles[0]).toMatchObject({
      file_id: 'web_image_001',
      name: 'search-result.jpg',
      path: 'references/sources/web_image_001/original.jpg',
      type: 'image',
      source: 'reference_asset',
    })
  })

    it('removes workspace files when asset_removed matches either path or file_id', () => {
    const initial = {
      ...createHomeHarnessProjectionState(),
      workspaceFiles: [
        {
          file_id: 'old-id',
          name: 'report.html',
          path: 'outputs/report.html',
          type: 'web',
          size: 12,
          created_at: '2026-05-01T00:00:00.000Z',
        },
        {
          file_id: 'keep-id',
          name: 'keep.html',
          path: 'outputs/keep.html',
          type: 'web',
          size: 10,
          created_at: '2026-05-01T00:00:00.000Z',
        },
      ],
    }

    const projection = applyHomeHarnessEvent(initial, {
      type: 'asset_removed',
      sequence: 4,
      data: {
        path: 'outputs/report.html',
        file_id: 'newer-id',
      },
    }  )

    expect(projection.workspaceFiles.map((file) => file.file_id)).toEqual(['keep-id'])
  })

  it('marks subagent design jury cards completed on critique round completion', () => {
    const initial: HomeHarnessProjectionState = {
      ...createHomeHarnessProjectionState(),
      messages: [
        {
          id: 'assistant:run-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-01T00:00:00.000Z',
          blocks: [
            {
              id: 'subagent:quality-review-1',
              kind: 'content',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'subagent_card',
              payload: { status: 'running', task_id: 'quality-review-1' },
              children: [],
            },
          ],
        },
      ],
    }

    const next = applyHomeHarnessEvent(initial, {
      type: 'critique.round_completed',
      sequence: 9,
      lane: 'user',
      data: {
        critique_run_id: 'critique-1',
        subagent_task_id: 'quality-review-1',
        status: 'running',
        round: 1,
        max_rounds: 3,
        score_scale: 10,
      },
    }  )

    const subagent = next.messages[0]?.blocks?.[0]
    const designJury = subagent?.children?.[0]
    expect(next.critique?.status).toBe('completed')
    expect(next.critique?.displayStatus).toBe('round_completed')
    expect(subagent?.status).toBe('completed')
    expect(subagent?.payload.status).toBe('completed')
    expect(designJury?.uiKind).toBe('design_jury_card')
    expect(designJury?.status).toBe('completed')
    expect(designJury?.payload.status).toBe('completed')
    expect(designJury?.payload.displayStatus).toBe('round_completed')
  })

  it('adds shipped critique results as subagent design jury cards', () => {
    const initial: HomeHarnessProjectionState = {
      ...createHomeHarnessProjectionState(),
      messages: [
        {
          id: 'assistant:run-1',
          role: 'assistant',
          content: null,
          createdAt: '2026-05-01T00:00:00.000Z',
          blocks: [
            {
              id: 'subagent:quality-review-1',
              kind: 'content',
              order: 0,
              status: 'running',
              visible: true,
              uiKind: 'subagent_card',
              payload: { status: 'running', task_id: 'quality-review-1' },
              children: [],
            },
          ],
        },
      ],
    }

    const next = applyHomeHarnessEvent(initial, {
      type: 'critique.shipped',
      sequence: 10,
      lane: 'user',
      data: {
        critique_run_id: 'critique-1',
        subagent_task_id: 'quality-review-1',
        status: 'shipped',
        round: 1,
        max_rounds: 3,
        score_scale: 10,
        scores: { critic: 8.2, brand: 8.4, a11y: 8, copy: 8.1 },
      },
    }  )

    const subagent = next.messages[0]?.blocks?.[0]
    const designJury = subagent?.children?.[0]
    expect(next.critique?.status).toBe('shipped')
    expect(subagent?.status).toBe('completed')
    expect(subagent?.payload.status).toBe('completed')
    expect(subagent?.expanded).toBe(true)
    expect(designJury?.uiKind).toBe('design_jury_card')
    expect(designJury?.status).toBe('shipped')
    expect(designJury?.payload.status).toBe('shipped')
    expect(designJury?.payload.scores).toEqual({ critic: 8.2, brand: 8.4, a11y: 8, copy: 8.1 })
  })


    it('updates current version from file_current_version_changed payloads', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'file_version_created',
        sequence: 1,
        data: {
          file_id: 'f_report',
          name: 'report.md',
          path: 'file_versions/f_report/v0001/source.md',
          type: 'markdown',
          current_version_id: 'v0001',
          versions: [
            { version_id: 'v0001', label: 'Version 1', path: 'file_versions/f_report/v0001/source.md' },
            { version_id: 'v0002', label: 'Version 2', path: 'file_versions/f_report/v0002/source.md' },
          ],
        },
      },
      {
        type: 'file_current_version_changed',
        sequence: 2,
        data: {
          file_id: 'f_report',
          current_version_id: 'v0002',
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(projection.workspaceFiles).toHaveLength(1)
    expect(projection.workspaceFiles[0]?.name).toBe('report.md')
    expect(projection.workspaceFiles[0]?.current_version_id).toBe('v0002')
    expect(projection.workspaceFiles[0]?.versions).toHaveLength(2)
  })

    it('keeps execution-completed outline updates and terminal events completed', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'run_started',
        sequence: 1,
        run_id: '4091b6c0f6de',
        lane: 'user',
        data: { conversation_id: '1779543310412_af4e26' },
      },
      {
        type: 'file_version_created',
        sequence: 248,
        run_id: '4091b6c0f6de',
        lane: 'user',
        data: {
          file_id: 'f_8b40f57dbc',
          name: 'index.zip',
          path: 'published/f_8b40f57dbc/v0001/source.zip',
          type: 'web',
          size: 23147,
          current_version_id: 'v0001',
          artifact_kind: 'web_bundle',
          artifact_metadata: { artifact_kind: 'web_bundle', bundle_format: 'zip', entry: 'index.html' },
          versions: [
            {
              version_id: 'v0001',
              label: '版本 1',
              size: 23147,
              sha256: 'x',
              created_at: '2026-05-23T13:50:22.682529+00:00',
              created_by: 'agent',
              artifact_metadata: { artifact_kind: 'web_bundle', bundle_format: 'zip', entry: 'index.html' },
            },
          ],
        },
      },
      legacyHarnessEvent({
        type: 'message_done',
        sequence: 265,
        run_id: '4091b6c0f6de',
        lane: 'user',
        data: { status: 'completed' },
      }),
      {
        type: 'current_outline_updated',
        sequence: 266,
        run_id: '4091b6c0f6de',
        lane: 'user',
        data: {
          change_source: 'execution_completed',
          outline: {
            outline_id: 'outline-da1cd6308bbf',
            title: '设计行业 5 页商业演示',
            status: 'completed',
            items: [],
          },
          projection: {
            status: 'completed',
            execution_plan_id: 'exec-d293955e68eb',
          },
          execution_state: {
            status: 'completed',
            execution_plan_id: 'exec-d293955e68eb',
          },
        },
      },
      turnCompleted('completed', {
        sequence: 267,
        run_id: '4091b6c0f6de',
        conversation_id: '1779543310412_af4e26',
      }),
    ] , createHomeHarnessProjectionState())

    expect(projection.runStatus).toBe('completed')
    expect(projection.isStreaming).toBe(false)
    expect(projection.runtimeState?.runtime_status).toBe('completed')
    expect(projection.runtimeState?.run_state).toBe('completed')
    expect(projection.runtimeState?.run_status).toBe('completed')
    expect(projection.runtimeState?.phase).toBe('completed')
    expect(projection.runtimeState?.activity).toBe('completed')
    expect(projection.workspaceFiles[0] ? isSessionHtmlFile(projection.workspaceFiles[0]) : false).toBe(true)
  })

    it('outline updates do not pause the run before turn_completed', () => {
    const runningState = replayHomeHarnessEvents([
      {
        type: 'turn_started',
        sequence: 1,
        run_id: 'run-waiting',
        lane: 'user',
        data: {
          conversation_id: 'conv-waiting',
          run_id: 'run-waiting',
          turn_id: 'run-waiting',
          status: 'running',
          runtime_profile: 'home',
          started_at: '2026-01-01T00:00:00.000Z',
        },
      },
      {
        type: 'current_outline_updated',
        sequence: 2,
        run_id: 'run-waiting',
        lane: 'user',
        data: {
          change_source: 'initial_plan',
          outline: {
            outline_id: 'outline-waiting',
            title: 'Plan',
            status: 'pending',
            items: [],
          },
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(runningState.runStatus).toBe('running')
    expect(runningState.isStreaming).toBe(true)

    for (const type of ['turn_completed'] as const) {
      const completed = applyHomeHarnessEvent(runningState, {
        type,
        sequence: 3,
        run_id: 'run-waiting',
        lane: 'user',
        data: turnCompleted('completed', { conversation_id: 'conv-waiting', run_id: 'run-waiting' }).data,
      }  )
      expect(completed.runStatus).toBe('completed')
      expect(completed.isStreaming).toBe(false)
      expect(completed.runtimeState?.runtime_status).toBe('completed')
    }
  })


    it('updates home generation cards from generation events without regressing on stale replay', () => {
    const initial = {
      ...createHomeHarnessProjectionState(),
      messages: [
        {
          id: 'assistant-generation',
          role: 'assistant' as const,
          content: '',
          createdAt: '2026-04-20T00:00:00.000Z',
          blocks: [
            {
              id: 'generation-task-1',
              kind: 'content' as const,
              order: 0,
              status: 'processing',
              visible: true,
              uiKind: 'generation_task',
              taskId: 'task-1',
              payload: {
                taskId: 'task-1',
                status: 'processing',
                progress: 40,
                resultUrl: null,
              },
            },
          ],
        },
      ],
    }

    const completed = replayHomeHarnessEvents([
      {
        type: 'generation_completed',
        sequence: 8,
        data: {
          task_id: 'task-1',
          status: 'completed',
          progress: 100,
          result_url: '/api/v1/uploads/home/67/logo-finished.png',
          artifact_ref: 'artifact_ref:home-1',
        },
      },
    ] , initial)

    const stale = replayHomeHarnessEvents([
      {
        type: 'generation_started',
        sequence: 3,
        data: {
          task_id: 'task-1',
          status: 'processing',
          progress: 55,
        },
      },
    ] , completed)

    const card = stale.messages[0]?.blocks?.[0]
    expect(card?.status).toBe('completed')
    expect(card?.payload.status).toBe('completed')
    expect(card?.payload.progress).toBe(100)
    expect(card?.payload.resultUrl).toBe('/api/v1/uploads/home/67/logo-finished.png')
    expect(card?.payload.artifactRef).toBe('artifact_ref:home-1')
  })

    it('ignores internal tool_result events when rebuilding the homepage projection', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'tool_result',
        sequence: 1,
        data: {
          tool: 'file_read',
          call_id: 'call-file-read-1',
          status: 'failed',
          result: {
            error_message: 'File not found: /app/app/services/agent_harness/skills/pptx/pptxgenjs.md',
          },
        },
      },
      legacyHarnessEvent({
        type: 'message_done',
        sequence: 2,
        data: { conversation_id: 'conv-ignore-tool-result' },
      }),
    ] , createHomeHarnessProjectionState())

    expect(projection.messages).toEqual([])
    expect(projection.streamingBlocks).toEqual([])
  })

  it.each([
    [
      'selection_resolved',
      {
        type: 'selection_resolved',
        sequence: 1,
        data: {
          skill_id: 'html-ppt',
          resolved_skill_id: 'html-ppt',
          phase: 'planning',
        },
      },
    ],
    [
      'plan',
      {
        type: 'plan',
        sequence: 1,
        data: {
          plan_id: 1,
          summary: 'Build a report',
          steps: [],
        },
      },
    ],
    [
      'plan_revision_started',
      {
        type: 'plan_revision_started',
        sequence: 1,
        data: {},
      },
    ],
    [
      'execution_started',
      {
        type: 'execution_started',
        sequence: 1,
        data: {
          outline: {
            artifact_type: 'markdown',
            title: 'Report',
            summary: 'Draft report',
            status: 'in_progress',
            items: [],
          },
        },
      },
    ],
    [
      'interaction_submitted',
      legacyHarnessEvent({
        type: 'interaction_submitted',
        sequence: 1,
        data: {
          request_id: 'ask-1',
          question: 'Continue?',
          answer: 'Continue',
          display_label: 'Continue',
        },
      }),
    ],
  ] as Array<[string, HomeHarnessProjectionEvent]>)('does not start an idle turn from %s without turn_started', (_name, event) => {
    const nextState = applyHomeHarnessEvent(createHomeHarnessProjectionState(), event)

    expect(nextState.runStatus).toBe('idle')
    expect(nextState.isStreaming).toBe(false)
  })

  it('keeps waiting_input paused until the next explicit turn_started event', () => {
    const waitingState: HomeHarnessProjectionState = {
      ...createHomeHarnessProjectionState(),
      runStatus: 'waiting_input',
      isStreaming: false,
      userInteraction: {
        request_id: 'ask-1',
        question: 'Continue?',
        content: null,
        kind: 'ask_user',
        schema: null,
        answers: null,
        status: 'pending',
      },
      pendingInteraction: {
        request_id: 'ask-1',
        question: 'Continue?',
        content: null,
        kind: 'ask_user',
        schema: null,
        answers: null,
        status: 'pending',
      },
    }

    const submitted = applyHomeHarnessEvent(waitingState, legacyHarnessEvent({
      type: 'interaction_submitted',
      sequence: 1,
      data: {
        request_id: 'ask-1',
        question: 'Continue?',
        answer: 'Continue',
        display_label: 'Continue',
      },
    })  )

    expect(submitted.runStatus).toBe('waiting_input')
    expect(submitted.isStreaming).toBe(false)

    const resumed = applyHomeHarnessEvent(submitted, {
      type: 'turn_started',
      sequence: 2,
      run_id: 'run-next',
      data: {
        conversation_id: 'conv-1',
        run_id: 'run-next',
        turn_id: 'run-next',
        status: 'running',
        runtime_profile: 'home',
        started_at: '2026-05-01T00:00:00.000Z',
      },
    }  )

    expect(resumed.runStatus).toBe('running')
    expect(resumed.isStreaming).toBe(true)
  })

    it('marks the projection failed as soon as a turn_completed failed event arrives', () => {
    const nextState = applyHomeHarnessEvent({
      ...createHomeHarnessProjectionState(),
      isStreaming: true,
      runStatus: 'running',
      streamingBlocks: [
        {
          id: 'assistant-main',
          kind: 'text',
          order: 0,
          status: 'running',
          visible: true,
          uiKind: 'assistant_text',
          payload: {
            text: 'Still working',
          },
        },
      ],
    }, turnCompleted('failed', {
      sequence: 1,
      terminal_error: 'tool crashed',
      summary: 'tool crashed',
      failure_signature: 'sig-run-failed-1',
    }))

    expect(nextState.runStatus).toBe('failed')
    expect(nextState.isStreaming).toBe(false)
    expect(nextState.messages.some((message) => message.content?.includes('Still working'))).toBe(true)
    expect(nextState.messages[nextState.messages.length - 1]?.content).toContain('tool crashed')
  })

    it('does not append a visible error bubble when a failure is marked internal-only', () => {
    const nextState = applyHomeHarnessEvent({
      ...createHomeHarnessProjectionState(),
      isStreaming: true,
      runStatus: 'running',
    }, turnCompleted('failed', {
      sequence: 7,
      message: '执行失败',
      summary: '执行失败',
      user_visible: false,
      failure_signature: 'sig-hidden-failure',
    }))

    expect(nextState.runStatus).toBe('failed')
    expect(nextState.messages).toHaveLength(0)
  })

    it('dedupes repeated terminal failures by failure signature instead of message substring matching', () => {
    const initial = applyHomeHarnessEvent(createHomeHarnessProjectionState(), turnCompleted('failed', {
      sequence: 5,
      summary: 'Timed out while generating report.',
      failure_signature: 'sig-repeat-failure',
    }))

    const nextState = applyHomeHarnessEvent(initial, turnCompleted('failed', {
      sequence: 6,
      summary: 'Timed out while generating report.',
      failure_signature: 'sig-repeat-failure',
    }))

    expect(nextState.messages.filter((message) => message.content?.includes('Timed out while generating report.'))).toHaveLength(1)
  })

    it('marks the projection cancelled as soon as a turn_completed(cancelled) event arrives', () => {
    const nextState = applyHomeHarnessEvent({
      ...createHomeHarnessProjectionState(),
      isStreaming: true,
      runStatus: 'running',
      streamingBlocks: [
        {
          id: 'assistant-main',
          kind: 'text',
          order: 0,
          status: 'running',
          visible: true,
          uiKind: 'assistant_text',
          payload: {
            text: 'Preparing response',
          },
        },
      ],
    }, turnCompleted('cancelled', { sequence: 1 }))

    expect(nextState.runStatus).toBe('cancelled')
    expect(nextState.isStreaming).toBe(false)
    expect(nextState.messages[nextState.messages.length - 1]?.content).toContain('Preparing response')
  })

    it('restores the projection to running when a new run starts after a cancelled run', () => {
    const projection = replayHomeHarnessEvents([
      legacyHarnessEvent({
        type: 'message_appended',
        sequence: 1,
        data: {
          message: {
            id: 'user-first',
            role: 'user',
            content: '你好',
            created_at: '2026-05-19T14:44:43.000Z',
          },
        },
      }),
      {
        type: 'turn_started',
        sequence: 2,
        run_id: 'run-old',
        data: {
          runtime_status: 'running',
        },
      },
      turnCompleted('cancelled', {
        sequence: 3,
        run_id: 'run-old',
      }),
      legacyHarnessEvent({
        type: 'message_appended',
        sequence: 4,
        data: {
          message: {
            id: 'user-second',
            role: 'user',
            content: '鹦鹉咖啡',
            created_at: '2026-05-19T14:44:51.000Z',
          },
        },
      }),
      {
        type: 'turn_started',
        sequence: 5,
        run_id: 'run-new',
        data: {
          runtime_status: 'running',
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(projection.runStatus).toBe('running')
    expect(projection.isStreaming).toBe(true)
  })

    it('ignores a stale turn_completed(cancelled) event after a newer run has started', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'turn_started',
        sequence: 1,
        run_id: 'run-old',
        data: {
          runtime_status: 'running',
        },
      },
      {
        type: 'turn_started',
        sequence: 2,
        run_id: 'run-new',
        data: {
          runtime_status: 'running',
        },
      },
      turnCompleted('cancelled', {
        sequence: 3,
        run_id: 'run-old',
      }),
    ] , createHomeHarnessProjectionState())

    expect(projection.runStatus).toBe('running')
    expect(projection.isStreaming).toBe(true)
    expect(projection.runtimeState?.run_id).toBe('run-new')
    expect(projection.lastSequence).toBe(3)
  })


    it('ignores non-user lane plan events during replay', () => {
    const projection = replayHomeHarnessEvents([
      {
        type: 'current_outline_updated',
        lane: 'internal',
        sequence: 1,
        data: {
          change_source: 'approval_requested',
          outline: {
            artifact_type: 'word',
            title: 'Should Stay Hidden',
            summary: 'internal event',
            status: 'planning_ready',
            items: [{ id: 's1', title: 'Hidden' }],
          },
        },
      },
    ] , createHomeHarnessProjectionState())

    expect(projection.activeUserPlan).toBeNull()
    expect(projection.messages).toHaveLength(0)
  })


    it('run_preparing does not resurrect a completed conversation', () => {
    // Regression: previously run_preparing went through the same projection
    // branch as run_started and flipped runStatus to 'running' /
    // isStreaming to true. On a GET /stream subscription opened against a
    // completed conversation, this resurrected the run on the client,
    // triggered an infinite reconnect loop, and pinned the UI on "thinking".
    // Now run_preparing is a transient handshake and must leave the
    // run-lifecycle state alone.
    const completedState = replayHomeHarnessEvents([
      {
        type: 'run_started',
        sequence: 1,
        run_id: 'run-1',
        lane: 'user',
        data: { conversation_id: 'conv-handshake' },
      },
      turnCompleted('completed', { sequence: 2, conversation_id: 'conv-handshake', run_id: 'run-1' }),
    ] , createHomeHarnessProjectionState())

    expect(completedState.runStatus).toBe('completed')
    expect(completedState.isStreaming).toBe(false)

    const afterHandshake = applyHomeHarnessEvent(completedState, {
      type: 'run_preparing',
      run_id: 'run-1',
      lane: 'user',
      data: {
        conversation_id: 'conv-handshake',
        // Mirrors the old server payload that hardcoded "running".
        runtime_status: 'running',
      },
    }  )

    expect(afterHandshake.runStatus).toBe('completed')
    expect(afterHandshake.isStreaming).toBe(false)
    expect(afterHandshake.runtimeState?.runtime_status).not.toBe('running')
  })

  })
