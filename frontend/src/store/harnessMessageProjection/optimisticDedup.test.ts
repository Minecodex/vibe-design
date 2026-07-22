import { describe, expect, it } from 'vitest'
import { applyPresentationOpToSession } from './reducer'
import { optimisticInteractionSubmissionOps } from './optimistic'
import type { PresentationOpEvent, ProjectionSessionLike } from './types'

// B5: an optimistic interaction-submission bubble (keyed `temp-...`) must be
// reconciled against the server's authoritative submission message (keyed
// `interaction-submission:...:<digest>`) so the user sees exactly one bubble.

function emptySession(): ProjectionSessionLike {
  return {
    messages: [],
    streamingBlocks: [],
    lastSequence: 0,
    appliedPresentationOps: [],
  }
}

function serverSubmissionMessageOp(content: string): PresentationOpEvent {
  return {
    type: 'presentation.message.upsert',
    sequence: 50,
    data: {
      op_id: 'srv-submission-1',
      source_sequence: 50,
      message_key: 'interaction-submission:conv-1:req-9:deadbeefdeadbeef',
      block_key: 'message:interaction-submission:conv-1:req-9:deadbeefdeadbeef',
      role: 'user',
      status: 'completed',
      content,
      payload: {
        content,
        blocks: [],
        attachments: [],
        base_file_versions: [],
        metadata: { source: 'interaction_submitted', request_id: 'req-9' },
      },
    },
  }
}

describe('optimistic interaction-submission dedup', () => {
  it('collapses the optimistic temp bubble into the server submission bubble', () => {
    const label = 'Yes, proceed'
    let session = emptySession()
    for (const op of optimisticInteractionSubmissionOps({
      requestId: 'req-9',
      answer: 'Yes',
      displayLabel: label,
      approved: true,
      kind: 'ask_user',
    })) {
      session = applyPresentationOpToSession(session, op)
    }

    const optimisticBubbles = session.messages.filter((m) => m.role === 'user' && (m.content ?? '').trim() === label)
    expect(optimisticBubbles).toHaveLength(1)
    expect(String(optimisticBubbles[0].id)).toMatch(/^temp-/)

    // Server's authoritative submission message arrives (different key).
    session = applyPresentationOpToSession(session, serverSubmissionMessageOp(label))

    const userBubbles = session.messages.filter((m) => m.role === 'user' && (m.content ?? '').trim() === label)
    expect(userBubbles).toHaveLength(1)
    // The surviving bubble must be the durable server one, not the temp optimistic id.
    expect(String(userBubbles[0].id)).not.toMatch(/^temp-/)
  })

  it('uses the display label for generic interaction bubbles', () => {
    const session = optimisticInteractionSubmissionOps({
      requestId: 'req-choice-1',
      answer: 'yes',
      displayLabel: 'Yes, proceed',
      answers: { choice: 'yes' },
      kind: 'ask_user',
    }).reduce((current, op) => applyPresentationOpToSession(current, op), emptySession())

    expect(session.messages.some((message) => (
      message.role === 'user' && message.content === 'Yes, proceed'
    ))).toBe(true)
    expect(session.messages.some((message) => (
      message.role === 'user' && message.content === 'yes'
    ))).toBe(false)
  })

  it('collapses generic optimistic bubbles into the server submission bubble', () => {
    let session = optimisticInteractionSubmissionOps({
      requestId: 'req-cancel',
      answer: 'cancel',
      displayLabel: 'Cancel',
      answers: { action: 'cancel' },
      kind: null,
    }).reduce((current, op) => applyPresentationOpToSession(current, op), emptySession())

    expect(session.messages.filter((message) => message.role === 'user')).toHaveLength(1)
    expect(session.messages[0]?.content).toBe('Cancel')

    session = applyPresentationOpToSession(session, {
      type: 'presentation.message.upsert',
      sequence: 50,
      data: {
        op_id: 'srv-cancel',
        source_sequence: 50,
        message_key: 'interaction-submission:conv-1:req-cancel:deadbeefdeadbeef',
        block_key: 'message:interaction-submission:conv-1:req-cancel:deadbeefdeadbeef',
        role: 'user',
        status: 'completed',
        content: 'Cancel',
        payload: {
          content: 'Cancel',
          blocks: [],
          attachments: [],
          metadata: {
            source: 'interaction_submitted',
            request_id: 'req-cancel',
          },
        },
      },
    })

    const userBubbles = session.messages.filter((message) => message.role === 'user')
    expect(userBubbles).toHaveLength(1)
    expect(userBubbles[0]?.content).toBe('Cancel')
    expect(String(userBubbles[0]?.id)).not.toMatch(/^temp-/)
  })
})
