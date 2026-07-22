import { describe, it, expect } from 'vitest'
import { buildHarnessUiMessages } from '../homeHarnessStoreSession'
import { applyPresentationOpToSession } from './reducer'
import type { ProjectionSessionLike } from './types'

// The backend stores user-visible messages under `stored_message_id(message_key)`,
// which hashes any key longer than 40 chars (the default assistant key
// `${conversation_id}:${run_id}:assistant` always exceeds that). The durable
// `message_key` is preserved in metadata. The live presentation reducer keys
// messages by the *raw* message_key, so after a snapshot reload a resumed stream
// must still target the same message instead of forking a duplicate bubble.

describe('reload + live op consistency (C1)', () => {
  it('appends a resumed text delta to the reloaded assistant message instead of duplicating it', () => {
    const messageKey = 'conv-abcdef0123456789abcdef0123456789:run-abcdef0123456789abcdef0123456789:assistant'

    const reloaded = buildHarnessUiMessages([
      {
        id: 'msg:v2:0123456789abcdef0123456789abcdef', // backend stored_message_id (hashed)
        role: 'assistant',
        content: 'Hello',
        blocks: [
          {
            id: 'text:1',
            kind: 'text',
            order: 0,
            status: 'running',
            visible: true,
            ui_kind: 'text',
            payload: { text: 'Hello' },
          },
        ],
        metadata: {
          render_kind: 'presentation_v2',
          protocol_version: 2,
          message_key: messageKey,
        },
        created_at: '2026-06-07T00:00:00.000Z',
      } as any,
    ])

    expect(reloaded).toHaveLength(1)

    const session: ProjectionSessionLike = {
      messages: reloaded as ProjectionSessionLike['messages'],
      streamingBlocks: [],
      lastSequence: 5,
      appliedPresentationOps: [],
    }

    const next = applyPresentationOpToSession(session, {
      type: 'presentation.block.delta',
      source_sequence: 10,
      op_id: 'op-resume-delta-1',
      data: {
        message_key: messageKey,
        block_key: 'text:1',
        payload: { field: 'text', delta: ' world' },
      },
    })

    // Today this FAILS: the reloaded message id is the hashed stored id, the live
    // op keys by the raw message_key, so a second assistant message is forked.
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].blocks?.[0]?.payload?.text).toBe('Hello world')
  })

  it('updates a reloaded render-only progress card in place instead of duplicating it', () => {
    const reloaded = buildHarnessUiMessages([
      {
        id: 'msg:v2:progress00000000000000000000000000',
        role: 'assistant',
        content: null,
        blocks: [
          {
            id: 'home-user-progress-card',
            kind: 'content',
            order: 1,
            status: 'in_progress',
            visible: true,
            ui_kind: 'user_progress_card',
            render_key: 'home-user-progress',
            payload: { message: '生成中', status: 'in_progress' },
          },
        ],
        metadata: {
          render_kind: 'presentation_v2',
          protocol_version: 2,
          render_only: true,
          render_key: 'home-user-progress',
          message_key: 'home-user-progress',
        },
        created_at: '2026-06-07T00:00:00.000Z',
      } as any,
    ])

    // Reload keys the card as `render:home-user-progress`.
    expect(reloaded).toHaveLength(1)
    expect(String(reloaded[0].id)).toBe('render:home-user-progress')

    const session: ProjectionSessionLike = {
      messages: reloaded as ProjectionSessionLike['messages'],
      streamingBlocks: [],
      lastSequence: 1,
      appliedPresentationOps: [],
    }

    const next = applyPresentationOpToSession(session, {
      type: 'presentation.block.patch',
      source_sequence: 7,
      op_id: 'op-progress-complete',
      data: {
        message_key: 'home-user-progress',
        block_key: 'home-user-progress-card',
        status: 'completed',
        payload: { status: 'completed', payload: { status: 'completed', message: '已完成' } },
      },
    })

    // The live op keys by the raw `home-user-progress`; without render-id
    // equivalence this forks a second progress card.
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].blocks?.[0]?.payload?.status).toBe('completed')
  })
})
