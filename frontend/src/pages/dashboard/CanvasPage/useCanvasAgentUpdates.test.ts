import { act, renderHook } from '@testing-library/react'
import { useRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { CanvasItem } from '@/api/endpoints/projects'

import { createInitialAgentGeneratedMediaState } from './agentGeneratedMedia'
import {
  layoutAgentGroupMembers,
  resolveAgentGeneratedMediaFocusTarget,
  useCanvasAgentUpdates,
} from './hooks/useCanvasAgentUpdates'

describe('useCanvasAgentUpdates replay guard', () => {
  it('lays out the eleventh member onto a new row in a 10-column grid', () => {
    const members = Array.from({ length: 11 }, (_, index) => ({
      id: `item-${index}`,
      type: 'image',
      url: `/${index}.png`,
      x: 0,
      y: 0,
      width: 100,
      height: 100,
      groupId: 'group-1',
      agent_group_order: index,
    } satisfies CanvasItem))

    const result = layoutAgentGroupMembers(members, { x: 50, y: 70, width: 0, height: 0 }, {
      columns: 10,
      gap: 20,
      padding: 80,
    })

    expect(result.members[9]).toMatchObject({ id: 'item-9', x: 1210, y: 150 })
    expect(result.members[10]).toMatchObject({ id: 'item-10', x: 130, y: 270 })
  })

  it('keeps the current group frame as the anchor when a moved group gets a new image', () => {
    const members = [
      {
        id: 'item-0',
        type: 'image',
        url: '/0.png',
        x: 0,
        y: 0,
        width: 120,
        height: 100,
        groupId: 'group-1',
        agent_group_order: 0,
      },
      {
        id: 'item-1',
        type: 'image',
        url: '/1.png',
        x: 0,
        y: 0,
        width: 80,
        height: 90,
        groupId: 'group-1',
        agent_group_order: 1,
      },
    ] satisfies CanvasItem[]

    const result = layoutAgentGroupMembers(members, { x: 500, y: 300, width: 0, height: 0 }, {
      columns: 10,
      gap: 20,
      padding: 80,
    })

    expect(result.members[0]).toMatchObject({ id: 'item-0', x: 580, y: 380 })
    expect(result.members[1]).toMatchObject({ id: 'item-1', x: 720, y: 380 })
  })

  it('never produces overlapping bounds for mixed-size members', () => {
    const members = [
      {
        id: 'item-0',
        type: 'image',
        url: '/0.png',
        x: 0,
        y: 0,
        width: 150,
        height: 110,
        groupId: 'group-1',
        agent_group_order: 0,
      },
      {
        id: 'item-1',
        type: 'image',
        url: '/1.png',
        x: 0,
        y: 0,
        width: 90,
        height: 180,
        groupId: 'group-1',
        agent_group_order: 1,
      },
      {
        id: 'item-2',
        type: 'image',
        url: '/2.png',
        x: 0,
        y: 0,
        width: 210,
        height: 120,
        groupId: 'group-1',
        agent_group_order: 2,
      },
    ] satisfies CanvasItem[]

    const result = layoutAgentGroupMembers(members, { x: 30, y: 40, width: 0, height: 0 }, {
      columns: 10,
      gap: 20,
      padding: 80,
    })

    for (let index = 0; index < result.members.length; index += 1) {
      for (let compareIndex = index + 1; compareIndex < result.members.length; compareIndex += 1) {
        const first = result.members[index]
        const second = result.members[compareIndex]
        const overlaps =
          first.x < second.x + (second.width || 0)
          && first.x + (first.width || 0) > second.x
          && first.y < second.y + (second.height || 0)
          && first.y + (first.height || 0) > second.y

        expect(overlaps).toBe(false)
      }
    }
  })

  it('focuses the generated item when the result is a single standalone image', () => {
    const nextItems = [
      {
        id: 'image-1',
        type: 'image',
        url: '/1.png',
        x: 120,
        y: 80,
        width: 320,
        height: 240,
      },
    ] satisfies CanvasItem[]

    expect(resolveAgentGeneratedMediaFocusTarget(nextItems, {
      insertedItemId: 'image-1',
      groupId: undefined,
    })).toMatchObject({ id: 'image-1', type: 'image' })
  })

  it('focuses the group when the generated result is inserted into an agent group', () => {
    const nextItems = [
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: 40,
        y: 60,
        width: 980,
        height: 540,
        group_layout_mode: 'agent_grid',
      },
      {
        id: 'image-1',
        type: 'image',
        url: '/1.png',
        x: 120,
        y: 140,
        width: 320,
        height: 240,
        groupId: 'group-1',
      },
      {
        id: 'image-2',
        type: 'image',
        url: '/2.png',
        x: 480,
        y: 140,
        width: 320,
        height: 240,
        groupId: 'group-1',
      },
    ] satisfies CanvasItem[]

    expect(resolveAgentGeneratedMediaFocusTarget(nextItems, {
      insertedItemId: 'image-2',
      groupId: 'group-1',
    })).toMatchObject({ id: 'group-1', type: 'group' })
  })

  it('focuses generated media even when canvas state application is deferred', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let queuedUpdater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[]) | null = null
    const selectAndCenterCanvasItem = vi.fn()
    const saveCanvasItems = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: [],
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems: (updater) => {
          queuedUpdater = updater
        },
        selectAndCenterCanvasItem,
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'image-1',
        type: 'image_generator',
        url: '',
        name: 'agent image',
        conversationId: 1,
        messageId: 'message-1',
      })
    })

    expect(queuedUpdater).toBeTruthy()
    expect(selectAndCenterCanvasItem).toHaveBeenCalledWith(expect.objectContaining({
      id: 'image-1',
      type: 'image_generator',
    }))
    expect(saveCanvasItems).not.toHaveBeenCalled()
  })

  it('applies agent canvas writes locally while stale without saving a stale snapshot', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = []
    const updateCanvasItems = vi.fn()
    const selectAndCenterCanvasItem = vi.fn()
    const saveCanvasItems = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: [],
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem,
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'image-stale',
        type: 'image_generator',
        url: '',
        name: 'stale image',
        conversationId: 1,
        messageId: 'message-1',
      })
    })

    expect(updateCanvasItems).toHaveBeenCalled()
    const firstUpdate = updateCanvasItems.mock.calls[0][0] as CanvasItem[]
    latestCanvasItems = firstUpdate
    expect(latestCanvasItems).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'image-stale',
        type: 'image_generator',
        status: undefined,
      }),
    ]))
    expect(saveCanvasItems).not.toHaveBeenCalled()
    expect(selectAndCenterCanvasItem).toHaveBeenCalled()
  })

  it('syncs backend agent patch revisions without saving a canvas snapshot', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null = null
    const updateCanvasItems = vi.fn()
    const saveCanvasItems = vi.fn()
    const syncCanvasRevisionFromAgentPatch = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: [],
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        syncCanvasRevisionFromAgentPatch,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('sync_canvas_revision', {}, { canvasRevision: 17 })
    })

    expect(syncCanvasRevisionFromAgentPatch).toHaveBeenCalledWith(17, { resolveStale: true })
    expect(updateCanvasItems).not.toHaveBeenCalled()
    expect(saveCanvasItems).not.toHaveBeenCalled()
  })

  it('syncs canvas revision from agent media write payloads before applying them', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null = null
    const calls: string[] = []
    let latestCanvasItems: CanvasItem[] = [{
      id: 'image-completed',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 512,
      height: 512,
      task_id: 'task-completed',
      status: 'generating',
      agent_media_key: 'image-completed',
    }]
    const syncCanvasRevisionFromAgentPatch = vi.fn(() => {
      calls.push('sync')
    })
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
      calls.push('update')
    })

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        syncCanvasRevisionFromAgentPatch,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('update', {
        id: 'image-completed',
        type: 'image',
        url: '/api/v1/uploads/canvas/1/completed.png',
        status: 'completed',
        task_id: 'task-completed',
        canvas_revision: 31,
        canvas_item_deleted: false,
      })
    })

    expect(syncCanvasRevisionFromAgentPatch).toHaveBeenCalledWith(31, { resolveStale: true })
    expect(latestCanvasItems[0]).toMatchObject({
      id: 'image-completed',
      type: 'image',
      status: 'completed',
      url: '/api/v1/uploads/canvas/1/completed.png',
    })
    expect(updateCanvasItems).toHaveBeenCalled()
    expect(calls).toEqual(['sync', 'update'])
  })

  it('routes backend-persisted agent patches through the agent-only canvas updater', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = [{
      id: 'image-completed',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 512,
      height: 512,
      task_id: 'task-completed',
      status: 'generating',
      agent_media_key: 'image-completed',
    }]
    const updateCanvasItems = vi.fn()
    const applyAgentCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        applyAgentCanvasItems,
        syncCanvasRevisionFromAgentPatch: vi.fn(),
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('update', {
        id: 'image-completed',
        type: 'image',
        url: '/api/v1/uploads/canvas/1/completed.png',
        status: 'completed',
        task_id: 'task-completed',
        canvas_revision: 31,
      })
    })

    expect(applyAgentCanvasItems).toHaveBeenCalledTimes(1)
    expect(updateCanvasItems).not.toHaveBeenCalled()
    expect(latestCanvasItems[0]).toMatchObject({
      id: 'image-completed',
      type: 'image',
      status: 'completed',
      url: '/api/v1/uploads/canvas/1/completed.png',
    })
  })

  it('does not resolve stale from deleted backend agent patch revision events', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null = null
    const syncCanvasRevisionFromAgentPatch = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: [],
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems: vi.fn(),
        syncCanvasRevisionFromAgentPatch,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('sync_canvas_revision', {}, {
        canvasRevision: 19,
        canvasItemDeleted: true,
      })
    })

    expect(syncCanvasRevisionFromAgentPatch).toHaveBeenCalledWith(19, { resolveStale: false })
  })

  it.each([
    ['image_generator', 'image-1'],
    ['video_generator', 'video-1'],
  ] as const)('projects agent placeholder items immediately while backend owns persistence for %s', (type, id) => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = []
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const saveCanvasItems = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add', {
        id,
        type,
        url: '',
        name: `agent ${type}`,
        artifact_ref: 'artifact_ref:placeholder-1',
        status: 'generating',
        progress: 0,
        conversationId: 12,
        messageId: 'message-12',
      })
    })

    expect(latestCanvasItems).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id,
        type,
        status: 'generating',
        progress: 0,
        artifact_ref: 'artifact_ref:placeholder-1',
        agent_conversation_id: 12,
        agent_message_id: 'message-12',
      }),
    ]))
    expect(saveCanvasItems).not.toHaveBeenCalled()
  })

  it('uses model dimension tables for newly inserted agent image placeholders', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = []
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const saveCanvasItems = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'builtin',
        videoProvider: 'test-provider',
        imageModel: 'gpt-image-2',
        availableImageModels: [
          {
            value: 'gpt-image-2',
            provider: 'builtin',
            config: {
              dimension_table: {
                '4K': {
                  '1:1': { width: 2880, height: 2880 },
                  '16:9': { width: 3840, height: 2160 },
                },
              },
            },
          },
        ],
        imageRes: '4K',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add', {
        id: 'agent-gpt-image-2-placeholder',
        type: 'image_generator',
        url: '',
        name: 'agent image',
        status: 'generating',
        model_name: 'gpt-image-2',
        provider_code: 'builtin',
        resolution: '4K',
        aspect_ratio: '1:1',
        conversationId: 12,
        messageId: 'message-12',
      })
    })

    expect(latestCanvasItems).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'agent-gpt-image-2-placeholder',
        width: 2880,
        height: 2880,
        media_display_size_source: 'placeholder',
      }),
    ]))
    expect(saveCanvasItems).not.toHaveBeenCalled()
  })

  it('moves a newly created agent group as a whole when the natural grid overlaps existing canvas items', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = [
      {
        id: 'blocking-image',
        type: 'image',
        url: '/blocking.png',
        x: 1180,
        y: 0,
        width: 500,
        height: 500,
      },
    ]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: -512, y: -512 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'agent-image-1',
        type: 'image',
        url: '',
        name: 'agent image 1',
        conversationId: 1,
        messageId: 'message-1',
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'agent-image-2',
        type: 'image',
        url: '',
        name: 'agent image 2',
        conversationId: 1,
        messageId: 'message-1',
      })
    })

    const group = latestCanvasItems.find((item) => item.type === 'group')
    const first = latestCanvasItems.find((item) => item.id === 'agent-image-1')
    const second = latestCanvasItems.find((item) => item.id === 'agent-image-2')

    expect(group).toMatchObject({
      group_layout_mode: 'agent_grid',
      x: 1730,
      y: 0,
    })
    expect(first).toMatchObject({ groupId: group?.id, x: 1810, y: 80 })
    expect(second).toMatchObject({ groupId: group?.id, x: 2854, y: 80 })
  })

  it('groups URL media synchronously and preserves the group when image loads finish in reverse order', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, unknown>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = []
    const pendingImages: Array<{
      onload: null | (() => void)
      onerror: null | (() => void)
      naturalWidth: number
      naturalHeight: number
    }> = []
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const originalImage = globalThis.Image
    const MockImage = class {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      naturalWidth = 0
      naturalHeight = 0

      constructor() {
        pendingImages.push(this)
      }

      set src(value: string) {
        void value
      }
    } as unknown as typeof Image
    vi.stubGlobal('Image', MockImage)

    const { rerender } = renderHook(
      ({ canvasItems }: { canvasItems: CanvasItem[] }) => {
        const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

        useCanvasAgentUpdates({
          canvasItems,
          imageRatio: '1:1',
          videoAspect: '16:9',
          imageProvider: 'test-provider',
          videoProvider: 'test-provider',
          imageRes: '1024x1024',
          videoQuality: '720p',
          zoomRef: { current: 100 },
          offsetRef: { current: { x: 0, y: 0 } },
          setOnCanvasUpdate: (callback) => {
            onCanvasUpdate = callback
          },
          updateCanvasItems,
          selectAndCenterCanvasItem: vi.fn(),
          agentGeneratedMediaRef,
          deletedAgentMediaKeys: [],
        })
      },
      { initialProps: { canvasItems: latestCanvasItems } },
    )

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'agent-image-1',
        type: 'image',
        url: '/generated/image-1.png',
        name: 'agent image 1',
        conversationId: 1,
        messageId: 'message-1',
        groupId: 'backend-group-1',
      })
      onCanvasUpdate?.('add_generated_media', {
        id: 'agent-image-2',
        type: 'image',
        url: '/generated/image-2.png',
        name: 'agent image 2',
        conversationId: 1,
        messageId: 'message-1',
        groupId: 'backend-group-1',
      })
    })

    expect(pendingImages).toHaveLength(2)
    expect(latestCanvasItems.filter((item) => item.type === 'group')).toEqual([
      expect.objectContaining({ id: 'backend-group-1', group_layout_mode: 'agent_grid' }),
    ])
    expect(latestCanvasItems.find((item) => item.id === 'agent-image-1')).toMatchObject({
      groupId: 'backend-group-1',
      width: 1024,
      height: 1024,
      agent_group_order: 0,
      media_display_size_source: 'placeholder',
    })
    expect(latestCanvasItems.find((item) => item.id === 'agent-image-2')).toMatchObject({
      groupId: 'backend-group-1',
      width: 1024,
      height: 1024,
      agent_group_order: 1,
      media_display_size_source: 'placeholder',
    })

    rerender({ canvasItems: latestCanvasItems })
    const beforeDecodeError = latestCanvasItems
    act(() => {
      pendingImages[0].onerror?.()
    })
    expect(latestCanvasItems).toBe(beforeDecodeError)

    pendingImages[0].naturalWidth = 640
    pendingImages[0].naturalHeight = 480
    pendingImages[1].naturalWidth = 800
    pendingImages[1].naturalHeight = 600

    act(() => {
      pendingImages[1].onload?.()
    })
    expect(latestCanvasItems.find((item) => item.id === 'agent-image-1')?.groupId).toBe('backend-group-1')
    expect(latestCanvasItems.find((item) => item.id === 'agent-image-2')).toMatchObject({
      groupId: 'backend-group-1',
      width: 800,
      height: 600,
    })

    act(() => {
      pendingImages[0].onload?.()
    })

    expect(latestCanvasItems.filter((item) => item.type === 'group')).toHaveLength(1)
    expect(latestCanvasItems.find((item) => item.id === 'agent-image-1')).toMatchObject({
      groupId: 'backend-group-1',
      width: 640,
      height: 480,
      agent_group_order: 0,
      media_display_size_source: 'intrinsic',
    })
    expect(latestCanvasItems.find((item) => item.id === 'agent-image-2')).toMatchObject({
      groupId: 'backend-group-1',
      width: 800,
      height: 600,
      agent_group_order: 1,
      media_display_size_source: 'intrinsic',
    })

    vi.stubGlobal('Image', originalImage)
  })

  it('repositions an existing agent group when a completed media item grows into an obstacle', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = [
      {
        id: 'group-1',
        type: 'group',
        url: '',
        x: -80,
        y: -80,
        width: 1180,
        height: 660,
        group_layout_mode: 'agent_grid',
        agent_message_id: 'message-1',
        agent_conversation_id: 1,
      },
      {
        id: 'agent-image-1',
        type: 'image',
        url: '/1.png',
        x: 0,
        y: 0,
        width: 500,
        height: 500,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
        agent_conversation_id: 1,
        agent_group_order: 0,
        agent_media_key: 'agent-image-1',
      },
      {
        id: 'agent-image-2',
        type: 'image_generator',
        url: '',
        x: 520,
        y: 0,
        width: 500,
        height: 500,
        groupId: 'group-1',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
        agent_conversation_id: 1,
        agent_group_order: 1,
        agent_media_key: 'agent-image-2',
        media_display_size_source: 'placeholder',
      },
      {
        id: 'blocking-image',
        type: 'image',
        url: '/blocking.png',
        x: 1180,
        y: 0,
        width: 500,
        height: 500,
      },
    ]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const originalImage = globalThis.Image
    const MockImage = class {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      naturalWidth = 1024
      naturalHeight = 1024

      set src(_value: string) {
        this.onload?.()
      }
    } as unknown as typeof Image
    vi.stubGlobal('Image', MockImage)

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'agent-image-2',
        agentMediaKey: 'agent-image-2',
        type: 'image',
        url: '/generated/image-2.png',
        conversationId: 1,
        messageId: 'message-1',
      })
    })

    const group = latestCanvasItems.find((item) => item.id === 'group-1')
    const first = latestCanvasItems.find((item) => item.id === 'agent-image-1')
    const second = latestCanvasItems.find((item) => item.id === 'agent-image-2')

    expect(group).toMatchObject({ x: 1730, y: -80 })
    expect(first).toMatchObject({ x: 1810, y: 0 })
    expect(second).toMatchObject({ x: 2330, y: 0, width: 1024, height: 1024 })
    vi.stubGlobal('Image', originalImage)
  })

  it('updates an untouched placeholder video to intrinsic dimensions when agent media completes', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = [
      {
        id: 'video-1',
        type: 'video_generator',
        url: '',
        x: 100,
        y: 80,
        width: 400,
        height: 200,
        media_display_size_source: 'placeholder',
        agent_message_id: 'message-1',
        agent_conversation_id: 7,
        agent_media_key: 'video-1',
      },
    ]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const saveCanvasItems = vi.fn()

    const originalCreateElement = document.createElement.bind(document)
    const mockVideo = {
      onloadedmetadata: null as null | (() => void),
      onerror: null as null | (() => void),
      videoWidth: 1920,
      videoHeight: 1080,
      set src(_value: string) {
        this.onloadedmetadata?.()
      },
    }
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'video') {
        return mockVideo as any
      }
      return originalCreateElement(tagName)
    }) as typeof document.createElement)

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'video-1',
        agentMediaKey: 'video-1',
        type: 'video',
        url: '/generated/video.mp4',
        conversationId: 7,
        messageId: 'message-1',
      })
    })

    expect(latestCanvasItems[0]).toMatchObject({
      width: 1920,
      height: 1080,
      x: 100,
      y: 80,
      media_display_size_source: 'intrinsic',
    })
    expect(saveCanvasItems).not.toHaveBeenCalled()
  })

  it('keeps a user-resized placeholder size when agent media completes', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = [
      {
        id: 'image-1',
        type: 'image_generator',
        url: '',
        x: 100,
        y: 80,
        width: 400,
        height: 200,
        media_display_size_source: 'user',
        agent_message_id: 'message-1',
        agent_conversation_id: 7,
        agent_media_key: 'image-1',
      },
    ]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const saveCanvasItems = vi.fn()
    const originalImage = globalThis.Image
    const MockImage = class {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      naturalWidth = 2880
      naturalHeight = 2880

      set src(_value: string) {
        this.onload?.()
      }
    } as unknown as typeof Image
    vi.stubGlobal('Image', MockImage)

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'image-1',
        agentMediaKey: 'image-1',
        type: 'image',
        url: '/generated/image.png',
        conversationId: 7,
        messageId: 'message-1',
      })
    })

    expect(latestCanvasItems[0]).toMatchObject({
      width: 400,
      height: 200,
      x: 100,
      y: 80,
      media_display_size_source: 'user',
    })
    expect(saveCanvasItems).not.toHaveBeenCalled()
    vi.stubGlobal('Image', originalImage)
  })

  it('repairs historical agent media items whose intrinsic size was initialized from configured dimensions', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = [
      {
        id: 'image-historical',
        type: 'image',
        url: '/generated/old-image.png',
        x: 100,
        y: 80,
        width: 2880,
        height: 2880,
        media_display_size_source: 'intrinsic',
        asset_origin: 'ai_generated',
        agent_message_id: 'message-1',
        agent_conversation_id: 7,
        agent_media_key: 'image-historical',
      },
    ]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const originalImage = globalThis.Image
    const MockImage = class {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      naturalWidth = 1663
      naturalHeight = 945

      set src(_value: string) {
        this.onload?.()
      }
    } as unknown as typeof Image
    vi.stubGlobal('Image', MockImage)

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'image-historical',
        agentMediaKey: 'image-historical',
        type: 'image',
        url: '/generated/old-image.png',
        conversationId: 7,
        messageId: 'message-1',
      })
    })

    expect(latestCanvasItems[0]).toMatchObject({
      width: 1663,
      height: 945,
      x: 100,
      y: 80,
      media_display_size_source: 'intrinsic',
    })
    vi.stubGlobal('Image', originalImage)
  })

  it('stores agent media refs without binding the backend host', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    let latestCanvasItems: CanvasItem[] = []
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const originalImage = globalThis.Image
    const MockImage = class {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      naturalWidth = 1024
      naturalHeight = 1024

      set src(_value: string) {
        this.onload?.()
      }
    } as unknown as typeof Image
    vi.stubGlobal('Image', MockImage)

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem: vi.fn(),
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('add_generated_media', {
        id: 'image-1',
        agentMediaKey: 'image-1',
        type: 'image',
        url: 'assets/references/generated_image_001/original.png',
        conversationId: 'conv-1',
        messageId: 'message-1',
      })
    })

    expect(latestCanvasItems).toEqual(expect.arrayContaining([
      expect.objectContaining({
        id: 'image-1',
        url: '/api/v1/agent/harness/conversations/conv-1/files/references%2Fgenerated%2Fgenerated_image_001%2Foriginal.png',
      }),
    ]))

    vi.stubGlobal('Image', originalImage)
  })

  it('updates an existing generated media placeholder by task id', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    const selectAndCenterCanvasItem = vi.fn()
    const placeholder = {
      id: 'agent-generated-artifact_ref-image-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 512,
      height: 512,
      task_id: 'task-1',
      artifact_ref: 'artifact_ref:image-1',
      status: 'generating',
      progress: 0,
      agent_media_key: 'agent-generated-artifact_ref-image-1',
    } satisfies CanvasItem
    let latestCanvasItems: CanvasItem[] = [placeholder]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const saveCanvasItems = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem,
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('update', {
        type: 'image_generator',
        task_id: 'task-1',
        status: 'completed',
        progress: 100,
        url: '/api/v1/uploads/canvas/1/final.png',
        agentMediaKey: 'agent-generated-artifact_ref-image-1',
      })
    })

    expect(latestCanvasItems[0]).toMatchObject({
      id: 'agent-generated-artifact_ref-image-1',
      status: 'completed',
      progress: 100,
      url: '/api/v1/uploads/canvas/1/final.png',
    })
    expect(updateCanvasItems).toHaveBeenCalled()
    expect(selectAndCenterCanvasItem).not.toHaveBeenCalled()
    expect(saveCanvasItems).not.toHaveBeenCalled()
  })

  it('updates an existing generated media placeholder while stale without saving', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    const selectAndCenterCanvasItem = vi.fn()
    let latestCanvasItems: CanvasItem[] = [{
      id: 'agent-generated-artifact_ref-image-stale',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 512,
      height: 512,
      task_id: 'task-stale',
      artifact_ref: 'artifact_ref:image-stale',
      status: 'generating',
      progress: 0,
      agent_media_key: 'agent-generated-artifact_ref-image-stale',
      groupId: 'group-stale',
    }]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })
    const saveCanvasItems = vi.fn()

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem,
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('update', {
        type: 'image',
        task_id: 'task-stale',
        status: 'completed',
        progress: 100,
        url: '/api/v1/uploads/canvas/1/final-stale.png',
        agentMediaKey: 'agent-generated-artifact_ref-image-stale',
      })
    })

    expect(latestCanvasItems[0]).toMatchObject({
      id: 'agent-generated-artifact_ref-image-stale',
      type: 'image',
      status: 'completed',
      progress: 100,
      url: '/api/v1/uploads/canvas/1/final-stale.png',
      x: 20,
      y: 30,
      width: 512,
      height: 512,
      groupId: 'group-stale',
    })
    expect(updateCanvasItems).toHaveBeenCalled()
    expect(saveCanvasItems).not.toHaveBeenCalled()
    expect(selectAndCenterCanvasItem).not.toHaveBeenCalled()
  })

  it('does not refocus the canvas while polling updates an existing generating placeholder', () => {
    let onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null = null
    const selectAndCenterCanvasItem = vi.fn()
    let latestCanvasItems: CanvasItem[] = [{
      id: 'agent-generated-artifact_ref-image-2',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 512,
      height: 512,
      task_id: 'task-2',
      artifact_ref: 'artifact_ref:image-2',
      status: 'generating',
      progress: 0,
      agent_media_key: 'agent-generated-artifact_ref-image-2',
    }]
    const updateCanvasItems = vi.fn((updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => {
      latestCanvasItems = typeof updater === 'function' ? updater(latestCanvasItems) : updater
    })

    renderHook(() => {
      const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

      useCanvasAgentUpdates({
        canvasItems: latestCanvasItems,
        imageRatio: '1:1',
        videoAspect: '16:9',
        imageProvider: 'test-provider',
        videoProvider: 'test-provider',
        imageRes: '1024x1024',
        videoQuality: '720p',
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        setOnCanvasUpdate: (callback) => {
          onCanvasUpdate = callback
        },
        updateCanvasItems,
        selectAndCenterCanvasItem,
        agentGeneratedMediaRef,
        deletedAgentMediaKeys: [],
      })
    })

    act(() => {
      onCanvasUpdate?.('update', {
        type: 'image_generator',
        task_id: 'task-2',
        artifact_ref: 'artifact_ref:image-2',
        status: 'generating',
        progress: 50,
        agentMediaKey: 'agent-generated-artifact_ref-image-2',
        agent_group_key: 'ecommerce_white_background',
      })
    })

    expect(latestCanvasItems[0]).toMatchObject({
      id: 'agent-generated-artifact_ref-image-2',
      status: 'generating',
      progress: 50,
      agent_group_key: 'ecommerce_white_background',
    })
    expect(selectAndCenterCanvasItem).not.toHaveBeenCalled()
  })
})
