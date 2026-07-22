import { describe, expect, it } from 'vitest'
import { applyPresentationOpToSession } from './reducer'
import type { ProjectionSessionLike } from './types'

// B1: when the backend streams a `user_plan_card` presentation op live, the
// reducer must render the plan-card message AND hydrate `activeUserPlan` /
// `outlineRuntime` so the plan shows in real time (not only after a reload).

function emptySession(): ProjectionSessionLike {
  return {
    messages: [],
    streamingBlocks: [],
    lastSequence: 0,
    appliedPresentationOps: [],
  }
}

function planPayload() {
  return {
    plan_instance_id: 'plan-1',
    outline_version: 1,
    status: 'planning_ready',
    snapshot_status: 'active',
    title: 'Landing page',
    summary: 'Build a landing page.',
    items: [{ id: 'section-1', title: 'Hero', summary: 'Hero section.' }],
    projection_state: { plan_instance_id: 'plan-1', outline_version: 1, status: 'planning_ready', readonly: false },
  }
}

function planCardOp() {
  const payload = planPayload()
  return {
    type: 'presentation.block.upsert',
    sequence: 10,
    data: {
      op_id: 'plan-op-1',
      source_sequence: 10,
      message_key: 'home-user-plan:plan-1:v1',
      block_key: 'home-user-plan-card:plan-1:v1',
      status: 'planning_ready',
      order: 0,
      block: {
        id: 'home-user-plan-card:plan-1:v1',
        block_key: 'home-user-plan-card:plan-1:v1',
        ui_kind: 'user_plan_card',
        uiKind: 'user_plan_card',
        status: 'planning_ready',
        payload,
      },
      payload,
    },
  }
}

describe('live plan card presentation op', () => {
  it('renders the plan-card message and hydrates activeUserPlan', () => {
    const next = applyPresentationOpToSession(emptySession(), planCardOp())

    const planMessage = next.messages.find((message) =>
      (message.blocks || []).some((block) => block.uiKind === 'user_plan_card'),
    )
    expect(planMessage).toBeTruthy()
    expect(next.activeUserPlan?.plan_instance_id).toBe('plan-1')
    expect(next.outlineRuntime?.current_outline?.plan_instance_id).toBe('plan-1')
  })

  it('is idempotent for the same op id (no duplicate plan message)', () => {
    const once = applyPresentationOpToSession(emptySession(), planCardOp())
    const twice = applyPresentationOpToSession(once, planCardOp())
    const planMessages = twice.messages.filter((message) =>
      (message.blocks || []).some((block) => block.uiKind === 'user_plan_card'),
    )
    expect(planMessages).toHaveLength(1)
  })
})
