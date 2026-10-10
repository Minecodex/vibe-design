import { describe, expect, it } from 'vitest'

import {
  createInitialAgentGeneratedMediaState,
  findExistingAgentGeneratedMedia,
  hasDeletedAgentMediaKey,
  hydrateAgentGeneratedMediaState,
  normalizeDeletedAgentMediaKeys,
  normalizeAgentGeneratedMediaItems,
  planAgentGeneratedMediaInsertion,
  recordDeletedAgentMediaKey,
} from './agentGeneratedMedia'

describe('agentGeneratedMedia', () => {
  it('matches existing media by canvas item id before an agent media key is assigned', () => {
    const existing = {
      id: 'image-placeholder',
      type: 'image_generator' as const,
      url: '',
      x: 0,
      y: 0,
      width: 1024,
      height: 1024,
    }

    expect(findExistingAgentGeneratedMedia([existing], { id: 'image-placeholder' })).toBe(existing)
  })

  it('reuses the same conversation session when the incoming message changes within the same conversation', () => {
    const current = {
      conversationId: 1,
      messageId: 'message-a',
      items: [{ id: 'old-item', name: 'Old item', order: 0 }],
      groupId: null,
    }

    const result = planAgentGeneratedMediaInsertion({
      currentState: {
        sessions: {
          'conversation:1:message:message-a': current,
        },
      },
      conversationId: 1,
      messageId: 'message-b',
      incomingId: 'new-item',
      incomingName: 'New item',
      fallbackGroupId: 'group-new',
    })

    expect(result.shouldInsert).toBe(true)
    expect(result.nextSession).toEqual({
      conversationId: 1,
      messageId: 'message-b',
      items: [
        { id: 'old-item', name: 'Old item', order: 0 },
        { id: 'new-item', name: 'New item', order: 1 },
      ],
      groupId: 'group-new',
    })
    expect(result.currentCount).toBe(2)
    expect(result.createdGroupId).toBe('group-new')
  })

  it('skips duplicate inserts for the same message session', () => {
    const current = {
      conversationId: 1,
      messageId: 'message-a',
      items: [{ id: 'existing-item', name: 'Existing item', order: 0 }],
      groupId: null,
    }

    const result = planAgentGeneratedMediaInsertion({
      currentState: {
        sessions: {
          'conversation:1:message:message-a': current,
        },
      },
      conversationId: 1,
      messageId: 'message-a',
      incomingId: 'existing-item',
      incomingName: 'Duplicate item',
      fallbackGroupId: 'group-new',
    })

    expect(result.shouldInsert).toBe(false)
    expect(result.nextSession).toEqual(current)
    expect(result.currentCount).toBe(1)
    expect(result.createdGroupId).toBeNull()
  })

  it('creates a group when the second item for a message is inserted', () => {
    const current = {
      conversationId: 1,
      messageId: 'message-a',
      items: [{ id: 'item-1', name: 'First item', order: 0 }],
      groupId: null,
    }

    const result = planAgentGeneratedMediaInsertion({
      currentState: {
        sessions: {
          'conversation:1:message:message-a': current,
        },
      },
      conversationId: 1,
      messageId: 'message-a',
      incomingId: 'item-2',
      incomingName: 'Second item',
      fallbackGroupId: 'group-2',
    })

    expect(result.shouldInsert).toBe(true)
    expect(result.currentCount).toBe(2)
    expect(result.createdGroupId).toBe('group-2')
    expect(result.nextSession.groupId).toBe('group-2')
    expect(result.nextSession.items).toEqual([
      { id: 'item-1', name: 'First item', order: 0 },
      { id: 'item-2', name: 'Second item', order: 1 },
    ])
  })

  it('keeps the existing group when more items arrive in the same session', () => {
    const current = {
      conversationId: 1,
      messageId: 'message-a',
      items: [
        { id: 'item-1', name: 'First item', order: 0 },
        { id: 'item-2', name: 'Second item', order: 1 },
      ],
      groupId: 'group-existing',
    }

    const result = planAgentGeneratedMediaInsertion({
      currentState: {
        sessions: {
          'conversation:1:message:message-a': current,
        },
      },
      conversationId: 1,
      messageId: 'message-a',
      incomingId: 'item-3',
      incomingName: 'Third item',
      fallbackGroupId: 'group-new',
    })

    expect(result.shouldInsert).toBe(true)
    expect(result.currentCount).toBe(3)
    expect(result.createdGroupId).toBeNull()
    expect(result.nextSession.groupId).toBe('group-existing')
  })

  it('uses an explicit agent group key to join ecommerce white-background media across messages', () => {
    let state = createInitialAgentGeneratedMediaState()

    const first = planAgentGeneratedMediaInsertion({
      currentState: state,
      conversationId: 'conv-1',
      messageId: 'message-master',
      groupKey: 'ecommerce_white_background',
      incomingId: 'master-white',
      incomingName: 'Master white background',
      fallbackGroupId: 'group-white',
    })
    state = first.nextState

    const second = planAgentGeneratedMediaInsertion({
      currentState: state,
      conversationId: 'conv-1',
      messageId: 'message-views',
      groupKey: 'ecommerce_white_background',
      incomingId: 'left-white',
      incomingName: 'Left white background',
      fallbackGroupId: 'group-white-next',
    })

    expect(second.currentCount).toBe(2)
    expect(second.createdGroupId).toBe('group-white-next')
    expect(second.nextSession.groupId).toBe('group-white-next')
    expect(second.nextSession.items.map((item) => item.id)).toEqual(['master-white', 'left-white'])
  })

  it('hydrates explicit agent group keys independently from message ids and canvas group ids', () => {
    const hydrated = hydrateAgentGeneratedMediaState([
      {
        id: 'master-white',
        type: 'image_generator',
        url: '',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        asset_origin: 'ai_generated',
        agent_message_id: 'message-master',
        agent_conversation_id: 'conv-1',
        agent_group_key: 'ecommerce_white_background',
        agent_group_order: 0,
      },
      {
        id: 'left-white',
        type: 'image_generator',
        url: '',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        asset_origin: 'ai_generated',
        agent_message_id: 'message-views',
        agent_conversation_id: 'conv-1',
        agent_group_key: 'ecommerce_white_background',
        agent_group_order: 1,
      },
    ])

    const result = planAgentGeneratedMediaInsertion({
      currentState: hydrated,
      conversationId: 'conv-1',
      messageId: 'message-views-2',
      groupKey: 'ecommerce_white_background',
      incomingId: 'right-white',
      incomingName: 'Right white background',
      fallbackGroupId: 'group-white',
    })

    expect(result.currentCount).toBe(3)
    expect(result.createdGroupId).toBe('group-white')
    expect(result.nextSession.groupId).toBe('group-white')
    expect(result.nextSession.items.map((item) => item.id)).toEqual(['master-white', 'left-white', 'right-white'])
  })

  it('provides an empty initial state helper', () => {
    expect(createInitialAgentGeneratedMediaState()).toEqual({
      sessions: {},
    })
  })

  it('starts a new session when the incoming conversation changes even if the message id is reused', () => {
    const current = {
      conversationId: 1,
      messageId: 'streaming',
      items: [{ id: 'item-1', name: 'First item', order: 0 }],
      groupId: 'group-existing',
    }

    const result = planAgentGeneratedMediaInsertion({
      currentState: {
        sessions: {
          'conversation:1:message:streaming': current,
        },
      },
      conversationId: 2,
      messageId: 'streaming',
      incomingId: 'item-2',
      incomingName: 'Second item',
      fallbackGroupId: 'group-new',
    })

    expect(result.shouldInsert).toBe(true)
    expect(result.currentCount).toBe(1)
    expect(result.createdGroupId).toBeNull()
    expect(result.nextSession).toEqual({
      conversationId: 2,
      messageId: 'streaming',
      items: [{ id: 'item-2', name: 'Second item', order: 0 }],
      groupId: null,
    })
  })

  it('does not infer legacy groups during steady-state hydration', () => {
    const hydrated = hydrateAgentGeneratedMediaState([
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: 20,
        y: 40,
        width: 400,
        height: 260,
      },
      {
        id: 'img-1',
        type: 'image',
        url: '/1.png',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
      },
      {
        id: 'img-2',
        type: 'image',
        url: '/2.png',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
      },
    ])

    expect(hydrated.sessions).toEqual({})
  })

  it('normalizes legacy history items and lets the next insert reuse the existing group after refresh', () => {
    const normalized = normalizeAgentGeneratedMediaItems([
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: 20,
        y: 40,
        width: 400,
        height: 260,
      },
      {
        id: 'img-2',
        type: 'image',
        url: '/2.png',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
      },
      {
        id: 'img-1',
        type: 'image',
        url: '/1.png',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
      },
    ])
    const hydrated = hydrateAgentGeneratedMediaState(normalized)

    const result = planAgentGeneratedMediaInsertion({
      currentState: hydrated,
      conversationId: 9,
      messageId: 'message-1',
      incomingId: 'img-3',
      incomingName: 'Third image',
      fallbackGroupId: 'group-new',
    })

    expect(result.currentCount).toBe(3)
    expect(result.createdGroupId).toBeNull()
    expect(result.nextSession.groupId).toBe('group-1')
    expect(result.nextSession.conversationId).toBe(9)
    expect(result.nextSession.items.map((item) => item.id)).toEqual(['img-1', 'img-2', 'img-3'])
    expect(result.nextSession.items.map((item) => item.order)).toEqual([0, 1, 2])
  })

  it('hydrates a grouped conversation and lets later messages in that conversation append into the same group', () => {
    const hydrated = hydrateAgentGeneratedMediaState([
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: 20,
        y: 40,
        width: 400,
        height: 260,
        group_layout_mode: 'agent_grid',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
      },
      {
        id: 'img-1',
        type: 'image',
        url: '/1.png',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 0,
      },
      {
        id: 'img-2',
        type: 'image',
        url: '/2.png',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 1,
      },
      {
        id: 'img-3',
        type: 'image',
        url: '/3.png',
        x: 360,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 2,
      },
    ])

    const result = planAgentGeneratedMediaInsertion({
      currentState: hydrated,
      conversationId: 85,
      messageId: 'message-monkey',
      incomingId: 'img-4',
      incomingName: 'Monkey image',
      fallbackGroupId: 'group-new',
    })

    expect(result.shouldInsert).toBe(true)
    expect(result.currentCount).toBe(4)
    expect(result.createdGroupId).toBeNull()
    expect(result.nextSession.groupId).toBe('group-1')
    expect(result.nextSession.items.map((item) => item.id)).toEqual(['img-1', 'img-2', 'img-3', 'img-4'])
    expect(result.nextSession.messageId).toBe('message-monkey')
  })

  it('preserves string harness conversation ids when hydrating and appending grouped media sessions', () => {
    const hydrated = hydrateAgentGeneratedMediaState([
      {
        id: 'group-string-1',
        type: 'group',
        url: '',
        x: 20,
        y: 40,
        width: 400,
        height: 260,
        group_layout_mode: 'agent_grid',
        agent_message_id: 'message-canvas-1',
        agent_conversation_id: 'conv-canvas-1',
      },
      {
        id: 'img-string-1',
        type: 'image',
        url: '/1.png',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-string-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-canvas-1',
        agent_conversation_id: 'conv-canvas-1',
      },
      {
        id: 'img-string-2',
        type: 'image',
        url: '/2.png',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-string-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-canvas-1',
        agent_conversation_id: 'conv-canvas-1',
      },
    ])

    const result = planAgentGeneratedMediaInsertion({
      currentState: hydrated,
      conversationId: 'conv-canvas-1',
      messageId: 'message-canvas-2',
      incomingId: 'img-string-3',
      incomingName: 'Third image',
      fallbackGroupId: 'group-new',
    })

    expect(result.nextSession.conversationId).toBe('conv-canvas-1')
    expect(result.nextSession.groupId).toBe('group-string-1')
    expect(result.nextSession.items.map((item) => item.id)).toEqual([
      'img-string-1',
      'img-string-2',
      'img-string-3',
    ])
  })

  it('keeps images moved outside the group out of later automatic reordering', () => {
    const hydrated = hydrateAgentGeneratedMediaState([
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: 20,
        y: 40,
        width: 400,
        height: 260,
        group_layout_mode: 'agent_grid',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
      },
      {
        id: 'img-1',
        type: 'image',
        url: '/1.png',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 0,
      },
      {
        id: 'img-2',
        type: 'image',
        url: '/2.png',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 1,
      },
      {
        id: 'img-moved-out',
        type: 'image',
        url: '/moved-out.png',
        x: 700,
        y: 320,
        width: 100,
        height: 100,
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 2,
      },
    ])

    const result = planAgentGeneratedMediaInsertion({
      currentState: hydrated,
      conversationId: 85,
      messageId: 'message-monkey',
      incomingId: 'img-3',
      incomingName: 'New image',
      fallbackGroupId: 'group-new',
    })

    expect(result.shouldInsert).toBe(true)
    expect(result.currentCount).toBe(3)
    expect(result.nextSession.groupId).toBe('group-1')
    expect(result.nextSession.items.map((item) => item.id)).toEqual(['img-1', 'img-2', 'img-3'])
  })

  it('hydrates a mixed-message agent grid group using persisted group order', () => {
    const hydrated = hydrateAgentGeneratedMediaState([
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: 20,
        y: 40,
        width: 900,
        height: 260,
        group_layout_mode: 'agent_grid',
        agent_message_id: 'message-latest',
        agent_conversation_id: 85,
      },
      {
        id: 'horse-1',
        type: 'image',
        url: '/horse-1.png',
        x: 80,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 0,
      },
      {
        id: 'horse-2',
        type: 'image',
        url: '/horse-2.png',
        x: 220,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 1,
      },
      {
        id: 'horse-3',
        type: 'image',
        url: '/horse-3.png',
        x: 360,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-horse',
        agent_conversation_id: 85,
        agent_group_order: 2,
      },
      {
        id: 'peach-1',
        type: 'image',
        url: '/peach-1.png',
        x: 500,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-peach',
        agent_conversation_id: 85,
        agent_group_order: 5,
      },
      {
        id: 'banana-1',
        type: 'image',
        url: '/banana-1.png',
        x: 640,
        y: 120,
        width: 100,
        height: 100,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-banana',
        agent_conversation_id: 85,
        agent_group_order: 4,
      },
    ])

    const result = planAgentGeneratedMediaInsertion({
      currentState: hydrated,
      conversationId: 85,
      messageId: 'message-elephant',
      incomingId: 'elephant-1',
      incomingName: 'Elephant image',
      fallbackGroupId: 'group-new',
    })

    expect(result.currentCount).toBe(6)
    expect(result.nextSession.groupId).toBe('group-1')
    expect(result.nextSession.items.map((item) => item.id)).toEqual([
      'horse-1',
      'horse-2',
      'horse-3',
      'banana-1',
      'peach-1',
      'elephant-1',
    ])
    expect(result.nextSession.items.map((item) => item.order)).toEqual([0, 1, 2, 4, 5, 6])
  })

  it('upgrades legacy grouped agent media with deterministic order and agent grid mode', () => {
    const normalized = normalizeAgentGeneratedMediaItems([
      {
        id: 'group-legacy',
        type: 'group',
        url: '',
        x: 40,
        y: 50,
        width: 480,
        height: 280,
      },
      {
        id: 'img-b',
        type: 'image',
        url: '/b.png',
        x: 240,
        y: 140,
        width: 120,
        height: 80,
        groupId: 'group-legacy',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-legacy',
      },
      {
        id: 'img-a',
        type: 'image',
        url: '/a.png',
        x: 80,
        y: 140,
        width: 100,
        height: 90,
        groupId: 'group-legacy',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-legacy',
      },
    ])

    const group = normalized.find((item) => item.id === 'group-legacy')
    const imgA = normalized.find((item) => item.id === 'img-a')
    const imgB = normalized.find((item) => item.id === 'img-b')

    expect(group?.group_layout_mode).toBe('agent_grid')
    expect(imgA?.agent_group_order).toBe(0)
    expect(imgB?.agent_group_order).toBe(1)
    expect(imgA?.x).toBe(120)
    expect(imgB?.x).toBe(240)
    expect(imgA?.y).toBe(130)
    expect(imgB?.y).toBe(130)
  })

  it('normalizes persisted deleted agent media keys into a clean unique string list', () => {
    expect(normalizeDeletedAgentMediaKeys(['item-1', null, 'item-1', 42, ''])).toEqual(['item-1', '42'])
  })

  it('records deleted agent media keys without duplicates', () => {
    expect(recordDeletedAgentMediaKey(['item-1'], 'item-2')).toEqual(['item-1', 'item-2'])
    expect(recordDeletedAgentMediaKey(['item-1'], 'item-1')).toEqual(['item-1'])
  })

  it('recognizes when a generated media key was previously deleted from the canvas', () => {
    expect(hasDeletedAgentMediaKey(['item-1', 'item-2'], 'item-2')).toBe(true)
    expect(hasDeletedAgentMediaKey(['item-1', 'item-2'], 'item-3')).toBe(false)
  })
})
