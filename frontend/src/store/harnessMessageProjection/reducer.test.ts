import { describe, expect, it } from 'vitest'
import { createPresentationDeltaBuffer } from './deltaBuffer'
import { extractPresentationConversationPatch } from './conversationPatch'
import { applyPresentationOpToSession } from './reducer'
import {
  assertDefaultPresentationRenderers,
  createPresentationRendererRegistry,
  normalizePresentationUiKind,
} from './rendererRegistry'
import { shouldApplyRuntimeAdapterEvent } from './protocol'
import type { ProjectionSessionLike } from './types'

function emptySession(): ProjectionSessionLike {
  return {
    messages: [],
    streamingBlocks: [],
    lastSequence: 0,
    appliedPresentationOps: [],
  }
}

describe('harnessMessageProjection reducer', () => {
  it('applies multiple ops with the same source sequence by op_id', () => {
    const first = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.delta',
      sequence: 7,
      data: {
        op_id: 'op-1',
        source_sequence: 7,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { field: 'text', delta: 'Hello' },
      },
    })
    const second = applyPresentationOpToSession(first, {
      type: 'presentation.block.delta',
      sequence: 7,
      data: {
        op_id: 'op-2',
        source_sequence: 7,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { field: 'text', delta: ' world' },
      },
    })

    expect(second.lastSequence).toBe(7)
    expect(second.messages[0].blocks?.[0].payload.text).toBe('Hello world')
    expect(second.appliedPresentationOps).toEqual(['op-1', 'op-2'])
  })

  it('dedupes replayed ops by op_id instead of appending delta again', () => {
    const event = {
      type: 'presentation.block.delta',
      sequence: 3,
      data: {
        op_id: 'op-repeat',
        source_sequence: 3,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { field: 'text', delta: 'Only once' },
      },
    }

    const once = applyPresentationOpToSession(emptySession(), event)
    const twice = applyPresentationOpToSession(once, event)

    expect(twice.messages[0].blocks?.[0].payload.text).toBe('Only once')
    expect(twice.appliedPresentationOps).toEqual(['op-repeat'])
  })

  it('treats placeholder source_sequence 0 as unassigned when deduping live ops', () => {
    const first = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.upsert',
      sequence: 10,
      data: {
        op_id: 'op-placeholder-seq0',
        source_sequence: 0,
        message_key: 'home-user-plan:plan-1:v1',
        block_key: 'home-user-plan-card:plan-1:v1',
        block: {
          id: 'home-user-plan-card:plan-1:v1',
          kind: 'content',
          ui_kind: 'user_plan_card',
          status: 'planning_ready',
          revision: 0,
          source_sequence: 0,
          payload: {
            plan_instance_id: 'plan-1',
            outline_version: 1,
            title: 'Initial plan',
            status: 'planning_ready',
          },
        },
      },
    })
    const second = applyPresentationOpToSession(first, {
      type: 'presentation.block.upsert',
      sequence: 11,
      data: {
        op_id: 'op-placeholder-seq0',
        source_sequence: 0,
        message_key: 'home-user-plan:plan-1:v1',
        block_key: 'home-user-plan-card:plan-1:v1',
        block: {
          id: 'home-user-plan-card:plan-1:v1',
          kind: 'content',
          ui_kind: 'user_plan_card',
          status: 'planning_ready',
          revision: 0,
          source_sequence: 0,
          payload: {
            plan_instance_id: 'plan-1',
            outline_version: 1,
            title: 'Updated plan',
            status: 'planning_ready',
          },
        },
      },
    })

    expect(second.messages[0].blocks?.[0].payload.title).toBe('Updated plan')
    expect(second.messages[0].blocks?.[0].revision).toBe(11)
    expect(second.appliedPresentationOps).toEqual([
      'presentation.block.upsert:10:home-user-plan-card:plan-1:v1',
      'presentation.block.upsert:11:home-user-plan-card:plan-1:v1',
    ])
  })

  it('does not let an older patch overwrite a newer block revision', () => {
    const withComplete = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.complete',
      sequence: 10,
      data: {
        op_id: 'op-complete-10',
        source_sequence: 10,
        revision: 10,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        block: {
          id: 'answer',
          kind: 'text',
          ui_kind: 'text',
          status: 'completed',
          payload: { text: 'new text' },
          revision: 10,
          source_sequence: 10,
        },
      },
    })

    const afterStalePatch = applyPresentationOpToSession(withComplete, {
      type: 'presentation.block.patch',
      sequence: 9,
      data: {
        op_id: 'op-patch-9',
        source_sequence: 9,
        revision: 9,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { payload: { text: 'old text' } },
      },
    })

    expect(afterStalePatch.messages[0].blocks?.[0].payload.text).toBe('new text')
    expect(afterStalePatch.messages[0].blocks?.[0].revision).toBe(10)
  })

  it('keeps live presentation ops and refreshed snapshot shape consistent', () => {
    const live = [
      {
        type: 'presentation.block.delta',
        sequence: 4,
        data: {
          op_id: 'op-delta-4',
          source_sequence: 4,
          message_key: 'assistant:run-1',
          block_key: 'answer',
          payload: { field: 'text', delta: 'Hello' },
        },
      },
      {
        type: 'presentation.block.complete',
        sequence: 5,
        data: {
          op_id: 'op-complete-5',
          source_sequence: 5,
          message_key: 'assistant:run-1',
          block_key: 'answer',
          block: {
            id: 'answer',
            kind: 'text',
            ui_kind: 'text',
            status: 'completed',
            payload: { text: 'Hello world' },
            revision: 5,
            source_sequence: 5,
          },
        },
      },
    ].reduce((session, event) => applyPresentationOpToSession(session, event), emptySession())

    const snapshot = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.message.upsert',
      sequence: 5,
      data: {
        op_id: 'op-snapshot-5',
        source_sequence: 5,
        message_key: 'assistant:run-1',
        role: 'assistant',
        payload: {
          blocks: [
            {
              id: 'answer',
              kind: 'text',
              ui_kind: 'text',
              status: 'completed',
              payload: { text: 'Hello world' },
              revision: 5,
              source_sequence: 5,
            },
          ],
        },
      },
    })

    expect(live.messages[0].blocks).toEqual(snapshot.messages[0].blocks)
    expect(live.messages[0].content).toBe(snapshot.messages[0].content)
  })

  it('does not bubble subagent tool child text into assistant message content', () => {
    const session = [
      {
        type: 'presentation.block.upsert',
        sequence: 1,
        data: {
          op_id: 'op-subagent',
          source_sequence: 1,
          message_key: 'assistant:run-1',
          block_key: 'subagent:quality-review-1',
          block: {
            id: 'subagent:quality-review-1',
            kind: 'content',
            ui_kind: 'subagent_card',
            status: 'running',
            payload: { status: 'running', task_id: 'quality-review-1' },
          },
        },
      },
      {
        type: 'presentation.block.complete',
        sequence: 2,
        data: {
          op_id: 'op-analysis',
          source_sequence: 2,
          message_key: 'assistant:run-1',
          block_key: 'analyze-image-text-call-1',
          parent_block_key: 'subagent:quality-review-1',
          block: {
            id: 'analyze-image-text-call-1',
            kind: 'text',
            ui_kind: 'text',
            status: 'completed',
            payload: {
              text: 'image analysis should stay inside the card',
              toolName: 'analyze_image',
            },
          },
        },
      },
    ].reduce((current, event) => applyPresentationOpToSession(current, event), emptySession())

    expect(session.messages[0].content).toBeNull()
    expect(session.messages[0].blocks?.[0].children?.[0].payload.text).toBe('image analysis should stay inside the card')
  })

  it('moves parented blocks out of the top-level assistant block list', () => {
    const initial = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.upsert',
      sequence: 1,
      data: {
        op_id: 'op-stray-analysis',
        source_sequence: 1,
        message_key: 'assistant:run-1',
        block_key: 'analyze-image-text-call-1',
        block: {
          id: 'analyze-image-text-call-1',
          kind: 'text',
          ui_kind: 'text',
          status: 'running',
          payload: {
            text: 'image analysis',
            toolName: 'analyze_image',
          },
        },
      },
    })

    const next = applyPresentationOpToSession(initial, {
      type: 'presentation.block.complete',
      sequence: 2,
      data: {
        op_id: 'op-parented-analysis',
        source_sequence: 2,
        message_key: 'assistant:run-1',
        block_key: 'analyze-image-text-call-1',
        parent_block_key: 'subagent:quality-review-1',
        block: {
          id: 'analyze-image-text-call-1',
          kind: 'text',
          ui_kind: 'text',
          status: 'completed',
          payload: {
            text: 'image analysis',
            toolName: 'analyze_image',
          },
        },
      },
    })

    expect(next.messages[0].content).toBeNull()
    expect(next.messages[0].blocks).toHaveLength(1)
    expect(next.messages[0].blocks?.[0].id).toBe('subagent:quality-review-1')
    expect(next.messages[0].blocks?.[0].children?.[0].id).toBe('analyze-image-text-call-1')
  })

  it('commits an optimistic user message instead of appending a duplicate', () => {
    const initial: ProjectionSessionLike = {
      ...emptySession(),
      messages: [
        {
          id: 'temp-123',
          role: 'user',
          content: '生成一个设计公司的落地页',
          attachments: [{ type: 'image', url: '/uploads/1.png', name: 'ref.png' }],
          createdAt: '2026-06-07T05:23:25.000Z',
        },
      ],
    }

    const committed = applyPresentationOpToSession(initial, {
      type: 'presentation.message.upsert',
      sequence: 3,
      data: {
        op_id: 'op-user-3',
        source_sequence: 3,
        message_key: 'conversation:run-1:user',
        role: 'user',
        content: '生成一个设计公司的落地页',
        payload: {
          content: '生成一个设计公司的落地页',
          attachments: [{ name: 'ref.png', url: '/uploads/1.png', type: 'image' }],
          blocks: [],
        },
      },
    })

    expect(committed.messages).toHaveLength(1)
    expect(committed.messages[0].id).toBe('conversation:run-1:user')
    expect(committed.messages[0].createdAt).toBe('2026-06-07T05:23:25.000Z')
    expect(committed.messages[0].content).toBe('生成一个设计公司的落地页')
  })

  it('commits an optimistic user message when local attachment preview fields differ', () => {
    const reference = {
      id: 'home-asset:/api/v1/uploads/canvas/6/background.png',
      kind: 'home_asset',
      media_type: 'image',
      display_name: 'background.png',
      source: {
        type: 'home_asset',
        url: '/api/v1/uploads/canvas/6/background.png',
      },
    }
    const initial: ProjectionSessionLike = {
      ...emptySession(),
      messages: [
        {
          id: 'temp-asset-preview',
          role: 'user',
          content: '根据这张背景图生成一张电商平铺图',
          attachments: [{
            type: 'image',
            url: '/api/v1/uploads/canvas/6/background.png',
            name: 'background.png',
            preview_url: '/api/v1/uploads/canvas/6/background__list_320.webp',
            reference,
          }],
          createdAt: '2026-06-21T16:07:51.000Z',
        },
      ],
    }

    const committed = applyPresentationOpToSession(initial, {
      type: 'presentation.message.upsert',
      sequence: 105,
      data: {
        op_id: 'op-user-105',
        source_sequence: 105,
        message_key: 'conversation:run-2:user',
        role: 'user',
        content: '根据这张背景图生成一张电商平铺图',
        payload: {
          content: '根据这张背景图生成一张电商平铺图',
          attachments: [{
            type: 'image',
            url: '/api/v1/uploads/canvas/6/background.png',
            name: 'background.png',
            reference,
          }],
          blocks: [],
        },
      },
    })

    expect(committed.messages).toHaveLength(1)
    expect(committed.messages[0].id).toBe('conversation:run-2:user')
    expect(committed.messages[0].createdAt).toBe('2026-06-21T16:07:51.000Z')
    expect(committed.messages[0].attachments?.[0]).toMatchObject({
      type: 'image',
      url: '/api/v1/uploads/canvas/6/background.png',
      reference,
    })
  })

  it('replaces the current plan card during live manual patch ops', () => {
    const initial = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.upsert',
      sequence: 21,
      data: {
        op_id: 'op-plan-v1',
        source_sequence: 21,
        message_key: 'home-user-plan:plan-1:v1',
        block_key: 'home-user-plan-card:plan-1:v1',
        block: {
          id: 'home-user-plan-card:plan-1:v1',
          kind: 'content',
          ui_kind: 'user_plan_card',
          status: 'active',
          payload: {
            plan_instance_id: 'plan-1',
            planInstanceId: 'plan-1',
            outline_version: 1,
            outlineVersion: 1,
            title: 'Initial plan',
            snapshot_status: 'active',
            snapshotStatus: 'active',
          },
          revision: 21,
          source_sequence: 21,
        },
        payload: {
          plan_instance_id: 'plan-1',
          planInstanceId: 'plan-1',
          outline_version: 1,
          outlineVersion: 1,
        },
      },
    })

    const patched = applyPresentationOpToSession(initial, {
      type: 'presentation.block.upsert',
      sequence: 22,
      data: {
        op_id: 'op-plan-v2-manual',
        source_sequence: 22,
        message_key: 'home-user-plan:plan-1:v2',
        block_key: 'home-user-plan-card:plan-1:v2',
        block: {
          id: 'home-user-plan-card:plan-1:v2',
          kind: 'content',
          ui_kind: 'user_plan_card',
          status: 'active',
          payload: {
            plan_instance_id: 'plan-1',
            planInstanceId: 'plan-1',
            outline_version: 2,
            outlineVersion: 2,
            title: 'Patched plan',
            snapshot_status: 'active',
            snapshotStatus: 'active',
            replace_current: true,
          },
          revision: 22,
          source_sequence: 22,
        },
        payload: {
          plan_instance_id: 'plan-1',
          planInstanceId: 'plan-1',
          outline_version: 2,
          outlineVersion: 2,
          replace_current: true,
        },
      },
    })

    expect(patched.messages).toHaveLength(1)
    expect(patched.messages[0].id).toBe('home-user-plan:plan-1:v1')
    expect(patched.messages[0].blocks?.[0].id).toBe('home-user-plan-card:plan-1:v2')
    expect(patched.messages[0].blocks?.[0].payload.title).toBe('Patched plan')
  })

  it('hydrates current outline runtime from live user plan cards', () => {
    const next = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.upsert',
      sequence: 43,
      data: {
        op_id: 'op-plan-ready',
        source_sequence: 43,
        message_key: 'home-user-plan:plan-1:v1',
        block_key: 'home-user-plan-card:plan-1:v1',
        block: {
          id: 'home-user-plan-card:plan-1:v1',
          kind: 'content',
          ui_kind: 'user_plan_card',
          status: 'planning_ready',
          payload: {
            plan_instance_id: 'plan-1',
            planInstanceId: 'plan-1',
            outline_version: 1,
            outlineVersion: 1,
            snapshot_status: 'active',
            snapshotStatus: 'active',
            title: 'Landing page plan',
            summary: 'Build and verify the page.',
            artifact_type: 'html',
            items: [
              { id: 'section-1', title: 'Hero', summary: 'Hero section summary.' },
            ],
            outline_state: {
              plan_instance_id: 'plan-1',
              version: 1,
              title: 'Landing page plan',
              status: 'planning_ready',
            },
            projection_state: {
              plan_instance_id: 'plan-1',
              outline_version: 1,
              status: 'planning_ready',
              readonly: false,
            },
            execution_state: {
              status: 'planning_ready',
              steps: [{ id: 'step-1', title: 'Build', status: 'pending' }],
            },
          },
          revision: 43,
          source_sequence: 43,
        },
      },
    })

    expect(next.activeUserPlan?.plan_instance_id).toBe('plan-1')
    expect(next.outlineRuntime?.current_outline?.version).toBe(1)
    expect(next.outlineRuntime?.projection_state?.readonly).toBe(false)
    expect(next.outlineRuntime?.execution_state?.status).toBe('planning_ready')
    expect(next.runtimeState?.phase).toBe('planning_ready')
  })

  it('hydrates planning draft state from live planning draft cards', () => {
    const next = applyPresentationOpToSession(emptySession(), {
      type: 'presentation.block.upsert',
      sequence: 22,
      data: {
        op_id: 'op-draft',
        source_sequence: 22,
        message_key: 'home-planning-draft',
        block_key: 'home-planning-draft-card',
        block: {
          id: 'home-planning-draft-card',
          kind: 'content',
          ui_kind: 'planning_draft_card',
          status: 'draft',
          payload: {
            summary: 'Collect requirements before approval.',
            confirmed_inputs: { audience: 'founders' },
            assumptions: ['Use placeholder images.'],
            draft_outline: [
              { id: 'section-1', title: 'Hero', summary: 'Hero section summary.' },
            ],
            open_questions: [],
            updated_at: '2026-06-07T10:52:10+00:00',
          },
          revision: 22,
          source_sequence: 22,
        },
      },
    })

    expect(next.planningDraft?.summary).toBe('Collect requirements before approval.')
    expect(next.planningDraft?.confirmed_inputs?.audience).toBe('founders')
    expect(next.planningDraft?.draft_outline?.[0]?.title).toBe('Hero')
    expect(next.planningDraft?.open_questions).toEqual([])
  })

  it('flushes buffered delta ops through the shared projection reducer', () => {
    const buffer = createPresentationDeltaBuffer()
    expect(buffer.push({
      type: 'presentation.block.delta',
      sequence: 11,
      data: {
        op_id: 'op-buffer-1',
        source_sequence: 11,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { field: 'text', delta: 'Buffered' },
      },
    })).toBe(true)
    expect(buffer.push({
      type: 'presentation.block.delta',
      sequence: 12,
      data: {
        op_id: 'op-buffer-2',
        source_sequence: 12,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { field: 'text', delta: ' delta' },
      },
    })).toBe(true)
    expect(buffer.size()).toBe(2)

    const flushed = buffer.flush(emptySession())

    expect(buffer.size()).toBe(0)
    expect(flushed.messages[0].blocks?.[0].payload.text).toBe('Buffered delta')
    expect(flushed.appliedPresentationOps).toEqual(['op-buffer-1', 'op-buffer-2'])
  })

  it('does not append a buffered replayed delta after the op id was already applied', () => {
    const event = {
      type: 'presentation.block.delta',
      sequence: 13,
      data: {
        op_id: 'op-buffer-replay',
        source_sequence: 13,
        message_key: 'assistant:run-1',
        block_key: 'answer',
        payload: { field: 'text', delta: 'Once' },
      },
    }
    const applied = applyPresentationOpToSession(emptySession(), event)
    const buffer = createPresentationDeltaBuffer()
    buffer.push(event)

    const flushed = buffer.flush(applied)

    expect(flushed.messages[0].blocks?.[0].payload.text).toBe('Once')
    expect(flushed.appliedPresentationOps).toEqual(['op-buffer-replay'])
  })

  it('applies conversation patch ops only to cursor state', () => {
    const initial: ProjectionSessionLike = {
      ...emptySession(),
      streamingBlocks: [{
        id: 'answer',
        kind: 'text',
        order: 0,
        status: 'running',
        visible: true,
        uiKind: 'text',
        payload: { text: 'streaming' },
      }],
    }
    const event = {
      type: 'presentation.conversation.patch',
      sequence: 1,
      data: {
        op_id: 'op-skill-selection',
        source_sequence: 1,
        payload: {
          patch: {
            skill_id: 'open-design-landing',
            resolved_skill_id: 'open-design-landing',
            skill_selection_mode: 'auto',
            last_skill_decision_confidence: 0.95,
          },
        },
      },
    }

    const next = applyPresentationOpToSession(initial, event)

    expect(next.messages).toEqual([])
    expect(next.streamingBlocks).toEqual(initial.streamingBlocks)
    expect(next.lastSequence).toBe(1)
    expect(next.appliedPresentationOps).toEqual(['op-skill-selection'])
    expect(extractPresentationConversationPatch(event)).toMatchObject({
      skill_id: 'open-design-landing',
      resolved_skill_id: 'open-design-landing',
      skill_selection_mode: 'auto',
      last_skill_decision_confidence: 0.95,
    })
  })

  it('keeps a submitted interaction form submitted when a later pending op replays', () => {
    const pendingForm = (opId: string, sourceSequence: number) => ({
      type: 'presentation.block.upsert' as const,
      data: {
        op_id: opId,
        source_sequence: sourceSequence,
        message_key: 'interaction:req-1',
        block_key: 'interaction-form:req-1',
        status: 'pending',
        block: {
          id: 'interaction-form:req-1',
          block_key: 'interaction-form:req-1',
          ui_kind: 'interaction_form',
          status: 'pending',
          order: 0,
          payload: { request_id: 'req-1', status: 'pending' },
        },
      },
    })

    // 1) Form arrives pending. 2) User submits -> patched to submitted w/ answers.
    let session = applyPresentationOpToSession(emptySession(), pendingForm('op-form-pending', 5))
    session = applyPresentationOpToSession(session, {
      type: 'presentation.block.patch',
      data: {
        op_id: 'op-form-submitted',
        source_sequence: 6,
        message_key: 'interaction:req-1',
        block_key: 'interaction-form:req-1',
        status: 'submitted',
        payload: { status: 'submitted', payload: { status: 'submitted', answers: { q1: 'Yes' } } },
      },
    })
    expect(session.messages[0].blocks?.[0]?.payload.status).toBe('submitted')

    // 3) A newer pending upsert replays (snapshot/SSE re-delivery) — the form must
    // not regress to pending and must retain its submitted answers.
    session = applyPresentationOpToSession(session, pendingForm('op-form-pending-replay', 9))

    const finalBlock = session.messages[0].blocks?.[0]
    expect(finalBlock?.payload.status).toBe('submitted')
    expect(finalBlock?.payload.answers).toEqual({ q1: 'Yes' })
  })
})

describe('presentation renderer registry', () => {
  const Renderer = () => null

  it('normalizes legacy ui kinds to canonical v2 renderer keys', () => {
    expect(normalizePresentationUiKind('assistant_final_answer')).toBe('text')
    expect(normalizePresentationUiKind('user_plan_card')).toBe('plan_card')
    expect(normalizePresentationUiKind('generation_task')).toBe('artifact_card')
  })

  it('resolves aliases through the shared registry contract', () => {
    const registry = createPresentationRendererRegistry({
      text: Renderer,
      plan_card: Renderer,
    })

    expect(registry.resolve('assistant_text')).toBe(Renderer)
    expect(registry.resolve('plan_artifact')).toBe(Renderer)
    expect(registry.resolve('subagent_card')).toBeNull()
  })

  it('guards the default v2 ui kinds at adapter registration time', () => {
    const registry = createPresentationRendererRegistry({
      text: Renderer,
      tool_call: Renderer,
      tool_result: Renderer,
      subagent_card: Renderer,
      interaction_form: Renderer,
      plan_card: Renderer,
      progress_card: Renderer,
      artifact_card: Renderer,
      error_card: Renderer,
    })

    expect(() => assertDefaultPresentationRenderers(registry)).not.toThrow()
  })
})

describe('presentation protocol runtime adapter gate', () => {
  it('rejects display/streaming events that are not runtime-adapter events', () => {
    expect(shouldApplyRuntimeAdapterEvent({ type: 'message_block_delta' })).toBe(false)
    expect(shouldApplyRuntimeAdapterEvent({ type: 'subagent_completed' })).toBe(false)
  })

  it('keeps non-display runtime events available to page adapters', () => {
    expect(shouldApplyRuntimeAdapterEvent({ type: 'turn_completed' })).toBe(true)
    expect(shouldApplyRuntimeAdapterEvent({ type: 'critique.degraded' })).toBe(true)
    expect(shouldApplyRuntimeAdapterEvent({ type: 'user_interaction_requested' })).toBe(false)
    expect(shouldApplyRuntimeAdapterEvent({ type: 'some_future_display_event' })).toBe(false)
  })
})
