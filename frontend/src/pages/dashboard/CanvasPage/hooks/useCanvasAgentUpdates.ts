type AgentCanvasUpdateItem = Partial<CanvasItem> & Record<string, unknown> & {
  conversationId?: string | number | null
  messageId?: string | number | null
  agentMediaKey?: string | null
  agentGroupKey?: string | null
  canvasItemDeleted?: boolean
  suppressCompletionToast?: boolean
  _agentLabel?: string
}

import { useEffect, useRef } from 'react'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  createInitialAgentGeneratedMediaState,
  DEFAULT_AGENT_GROUP_LAYOUT,
  findExistingAgentGeneratedMedia,
  hasDeletedAgentMediaKey,
  hydrateAgentGeneratedMediaState,
  layoutAgentGridMembers,
  planAgentGeneratedMediaInsertion,
} from '../agentGeneratedMedia'
import { normalizeCanvasAgentMediaRef, resolveCanvasAgentMediaUrl } from '../canvasMediaUrl'
import { findEmptyPosition, findEmptyRectPosition } from '../canvasLayout'
import { getMediaDimensions } from '../mediaDimensions'
import { getMediaDisplayInitializationUpdate } from '../mediaSelectionResize'

export { layoutAgentGridMembers as layoutAgentGroupMembers } from '../agentGeneratedMedia'

function normalizeAgentConversationId(value: string | number | null | undefined): string | number | null {
  if (typeof value === 'number') {
    return value
  }

  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || null
  }

  return null
}

function normalizeAgentMessageId(value: string | number | null | undefined): string | null {
  if (typeof value === 'number') {
    return String(value)
  }

  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || null
  }

  return null
}

interface UseCanvasAgentUpdatesArgs {
  canvasItems: CanvasItem[]
  imageRatio: string
  videoAspect: string
  imageProvider: string
  videoProvider: string
  imageModel?: string
  videoModel?: string
  availableImageModels?: {
    value?: string
    model_name?: string
    provider?: string
    config?: Record<string, unknown> | null
  }[]
  availableVideoModels?: {
    value?: string
    model_name?: string
    provider?: string
    config?: Record<string, unknown> | null
  }[]
  imageRes: string
  videoQuality: string
  zoomRef: React.MutableRefObject<number>
  offsetRef: React.MutableRefObject<{ x: number; y: number }>
  setOnCanvasUpdate: (callback: ((action: string, item: AgentCanvasUpdateItem, meta?: Record<string, unknown>) => void) | null) => void
  updateCanvasItems: (updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => void
  applyAgentCanvasItems?: (updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => void
  syncCanvasRevisionFromAgentPatch?: (revision: number, options?: { resolveStale?: boolean }) => void
  selectAndCenterCanvasItem: (item: CanvasItem) => void
  agentGeneratedMediaRef: React.MutableRefObject<ReturnType<typeof createInitialAgentGeneratedMediaState>>
  deletedAgentMediaKeys: string[]
}

export function resolveAgentGeneratedMediaFocusTarget(
  items: CanvasItem[],
  args: {
    insertedItemId: string
    groupId?: string
  },
) {
  if (args.groupId) {
    const groupItem = items.find((item) => item.id === args.groupId && item.type === 'group')
    if (groupItem) {
      return groupItem
    }
  }

  return items.find((item) => item.id === args.insertedItemId) ?? null
}

export function useCanvasAgentUpdates({
  canvasItems,
  imageRatio,
  videoAspect,
  imageProvider,
  videoProvider,
  imageModel = '',
  videoModel = '',
  availableImageModels = [],
  availableVideoModels = [],
  imageRes,
  videoQuality,
  zoomRef,
  offsetRef,
  setOnCanvasUpdate,
  updateCanvasItems,
  applyAgentCanvasItems,
  syncCanvasRevisionFromAgentPatch,
  selectAndCenterCanvasItem,
  agentGeneratedMediaRef,
  deletedAgentMediaKeys,
}: UseCanvasAgentUpdatesArgs) {
  const canvasItemsRef = useRef(canvasItems)
  canvasItemsRef.current = canvasItems

  useEffect(() => {
    agentGeneratedMediaRef.current = hydrateAgentGeneratedMediaState(canvasItems)
  }, [agentGeneratedMediaRef, canvasItems])

  useEffect(() => {
    const commitAgentCanvasItems = applyAgentCanvasItems || updateCanvasItems

    const syncCanvasRevisionFromPayload = (
      item: Record<string, unknown>,
      meta?: Record<string, unknown>,
    ) => {
      const revision = Number(meta?.canvasRevision ?? item.canvas_revision ?? item.canvasRevision)
      if (!Number.isFinite(revision) || revision < 0) {
        return
      }
      syncCanvasRevisionFromAgentPatch?.(Math.trunc(revision), {
        resolveStale: meta?.canvasItemDeleted !== true
          && item.canvas_item_deleted !== true
          && item.canvasItemDeleted !== true,
      })
    }

    const computeMediaDims = (item: AgentCanvasUpdateItem): { w: number; h: number } => {
      const dimensions = getMediaDimensions({
        type: item.type === 'video' || item.type === 'video_generator' ? item.type : 'image',
        aspect_ratio: item.aspect_ratio, provider_code: item.provider_code,
        resolution: item.resolution, model_name: item.model_name,
      }, {
        imageRatio,
        videoAspect,
        imageProvider,
        videoProvider,
        imageRes,
        videoResolution: videoQuality,
        imageModel,
        videoModel,
        imageModels: availableImageModels,
        videoModels: availableVideoModels,
      })
      return { w: dimensions.configured.width, h: dimensions.configured.height }
    }

    const applyAgentGridLayout = (
      items: CanvasItem[],
      groupId: string,
      conversationId: string | number | null,
      messageId: string | null,
      fallbackName: string,
    ) => {
      const groupItem = items.find((existingItem) => existingItem.id === groupId && existingItem.type === 'group')
      const members = items
        .filter((existingItem) => existingItem.groupId === groupId)
        .map((existingItem) => ({
          ...existingItem,
          agent_group_order: existingItem.agent_group_order ?? 0,
        }))

      if (members.length === 0) {
        return items
      }

      const layout = layoutAgentGridMembers(
        members,
        groupItem || {
          x: members[0].x - DEFAULT_AGENT_GROUP_LAYOUT.padding,
          y: members[0].y - DEFAULT_AGENT_GROUP_LAYOUT.padding,
          width: 0,
          height: 0,
        },
        DEFAULT_AGENT_GROUP_LAYOUT,
      )
      const updates = new Map<string, CanvasItem>()

      layout.members.forEach((member) => {
        updates.set(member.id, {
          ...member,
          groupId,
          agent_message_id: member.agent_message_id ?? messageId,
          agent_conversation_id: member.agent_conversation_id ?? conversationId,
        })
      })

      const nextGroup = groupItem
        ? {
            ...groupItem,
            ...layout.group,
            name: groupItem.name || fallbackName,
            group_layout_mode: 'agent_grid' as const,
            agent_message_id: messageId,
            agent_conversation_id: conversationId,
          }
        : {
            id: groupId,
            type: 'group' as const,
            url: '',
            name: fallbackName,
            ...layout.group,
            z_index: -999,
            background_color: 'rgba(22, 119, 255, 0.2)',
            group_layout_mode: 'agent_grid' as const,
            agent_message_id: messageId,
            agent_conversation_id: conversationId,
          }

      updates.set(groupId, nextGroup)

      const hasGroup = items.some((existingItem) => existingItem.id === groupId)
      const nextItems = items.map((existingItem) => updates.get(existingItem.id) || existingItem)
      return hasGroup ? nextItems : [...nextItems, nextGroup]
    }

    const avoidAgentGroupCollisions = (
      items: CanvasItem[],
      groupId: string,
    ) => {
      const groupItem = items.find((existingItem) => existingItem.id === groupId && existingItem.type === 'group')
      if (!groupItem) {
        return items
      }

      const memberIds = new Set(
        items
          .filter((existingItem) => existingItem.groupId === groupId)
          .map((existingItem) => existingItem.id),
      )
      const excludeIds = new Set([groupId, ...memberIds])
      const position = findEmptyRectPosition(
        {
          x: groupItem.x,
          y: groupItem.y,
          width: groupItem.width || 0,
          height: groupItem.height || 0,
        },
        items,
        { excludeIds },
      )
      const dx = position.x - groupItem.x
      const dy = position.y - groupItem.y
      if (dx === 0 && dy === 0) {
        return items
      }

      return items.map((existingItem) => (
        existingItem.id === groupId || memberIds.has(existingItem.id)
          ? {
              ...existingItem,
              x: existingItem.x + dx,
              y: existingItem.y + dy,
            }
          : existingItem
      ))
    }

    setOnCanvasUpdate((action, item, meta) => {
      if (action === 'sync_canvas_revision') {
        syncCanvasRevisionFromPayload(item, meta)
        return
      }

      const mediaType = item.type ?? 'image'
      const isPlaceholderAction =
        action === 'add'
        && (mediaType === 'image_generator' || mediaType === 'video_generator')
      const isGeneratedMediaUpdate =
        action === 'update'
        && (
          mediaType === 'image_generator'
          || mediaType === 'video_generator'
          || Boolean(item.task_id)
          || Boolean(item.agentMediaKey)
          || Boolean(item.agent_media_key)
        )
      if (action === 'add_generated_media' || isPlaceholderAction || isGeneratedMediaUpdate) {
        syncCanvasRevisionFromPayload(item, meta)
      }
      if (isGeneratedMediaUpdate) {
        const incomingKey = item.agentMediaKey || item.agent_media_key || item.id || null
        let didUpdate = false
        const nextItems = canvasItemsRef.current.map((existingItem) => {
          const matches =
            (item.id && existingItem.id === item.id)
            || (item.task_id != null && existingItem.task_id != null && String(existingItem.task_id) === String(item.task_id))
            || (incomingKey && (existingItem.agent_media_key === incomingKey || existingItem.id === incomingKey))
          if (!matches) {
            return existingItem
          }
          didUpdate = true
          const normalizedUrl = item.url
            ? normalizeCanvasAgentMediaRef(item.url, normalizeAgentConversationId(item.conversationId))
            : undefined
          return {
            ...existingItem,
            type: mediaType || existingItem.type,
            url: normalizedUrl ?? existingItem.url,
            status: item.status ?? existingItem.status,
            task_id: item.task_id ?? existingItem.task_id,
            artifact_ref: item.artifact_ref ?? existingItem.artifact_ref,
            progress: item.progress ?? existingItem.progress,
            error_message: item.error_message ?? existingItem.error_message,
            failure_kind: item.failure_kind ?? existingItem.failure_kind,
            agent_media_key: existingItem.agent_media_key || incomingKey || undefined,
            agent_group_key: item.agent_group_key ?? item.agentGroupKey ?? existingItem.agent_group_key,
            suppressCompletionToast: item.suppressCompletionToast ?? existingItem.suppressCompletionToast ?? true,
          } as CanvasItem
        })
        if (didUpdate) {
          canvasItemsRef.current = nextItems
          agentGeneratedMediaRef.current = hydrateAgentGeneratedMediaState(nextItems)
          commitAgentCanvasItems(nextItems)
        }
        return
      }
      if (action !== 'add_generated_media' && !isPlaceholderAction) return

      const currentZoom = zoomRef.current
      const currentOffset = offsetRef.current
      const scale = currentZoom / 100
      const viewportCenterX = -currentOffset.x / scale
      const viewportCenterY = -currentOffset.y / scale

      const dims = computeMediaDims(item)
      const incomingId = item.id || `agent-media-${Date.now()}`
      const incomingKey = item.agentMediaKey || incomingId
      const backendGroupId = typeof item.groupId === 'string' && item.groupId.trim()
        ? item.groupId.trim()
        : null

      if (hasDeletedAgentMediaKey(deletedAgentMediaKeys, incomingKey)) {
        return
      }

      const insertionPlan = planAgentGeneratedMediaInsertion({
        currentState: agentGeneratedMediaRef.current,
        conversationId: normalizeAgentConversationId(item.conversationId),
        messageId: item.messageId == null ? null : String(item.messageId),
        groupKey: item.agent_group_key ?? item.agentGroupKey ?? null,
        incomingId,
        incomingName: item.name || item._agentLabel || 'agent',
        fallbackGroupId: backendGroupId || `group-${Date.now()}`,
      })

      // Update ref immediately to prevent concurrent events from reading stale session state
      agentGeneratedMediaRef.current = insertionPlan.nextState
      const normalizedItemUrl = normalizeCanvasAgentMediaRef(
        item.url || '',
        normalizeAgentConversationId(item.conversationId),
      ) || ''

      const newItem: CanvasItem = {
        id: incomingId,
        type: mediaType,
        url: normalizedItemUrl,
        name: item.name || item._agentLabel || 'agent',
        x: 0,
        y: 0,
        width: dims.w,
        height: dims.h,
        z_index: Date.now(),
        status: item.status,
        task_id: item.task_id,
        artifact_ref: item.artifact_ref,
        progress: item.progress,
        error_message: item.error_message,
        failure_kind: item.failure_kind,
        aspect_ratio: item.aspect_ratio,
        provider_code: item.provider_code,
        resolution: item.resolution,
        duration: item.duration,
        model_name: item.model_name,
        model_label: item.model_label,
        groupId: insertionPlan.currentCount >= 2 ? insertionPlan.nextSession.groupId || undefined : undefined,
        asset_origin: 'ai_generated',
        agent_message_id: item.messageId ?? null,
        agent_conversation_id: normalizeAgentConversationId(item.conversationId),
        agent_media_key: incomingKey,
        agent_group_key: item.agent_group_key ?? item.agentGroupKey ?? undefined,
        agent_group_order: insertionPlan.nextOrder,
        media_display_size_source: 'placeholder',
        suppressCompletionToast: item.suppressCompletionToast ?? true,
      }

      const groupItem =
        insertionPlan.currentCount === 2 && insertionPlan.createdGroupId
          ? {
              id: insertionPlan.createdGroupId,
              type: 'group' as const,
              url: '',
              name: item.name || item._agentLabel || 'agent',
              x: 0,
              y: 0,
              width: 0,
              height: 0,
              z_index: -999,
              background_color: 'rgba(22, 119, 255, 0.2)',
              group_layout_mode: 'agent_grid' as const,
              agent_message_id: item.messageId ?? null,
              agent_conversation_id: normalizeAgentConversationId(item.conversationId),
            }
          : null

      const upsertMediaOnCanvas = () => {
        let focusTarget: CanvasItem | null = null
        let targetItemId: string | null = null
        const previous = canvasItemsRef.current
        const nextItems = (() => {
          const existingGeneratedItem = findExistingAgentGeneratedMedia(previous, {
            id: incomingId,
            task_id: item.task_id,
            artifact_ref: item.artifact_ref,
            agentMediaKey: incomingKey,
          })

          if (existingGeneratedItem) {
            targetItemId = existingGeneratedItem.id
            const updatedItems = previous.map((existingItem) =>
              existingItem.id === existingGeneratedItem.id
                ? ({
                    ...existingItem,
                    type: mediaType,
                    url: normalizedItemUrl || existingItem.url,
                    name: item.name || item._agentLabel || existingItem.name || 'agent',
                    width: existingItem.width ?? dims.w,
                    height: existingItem.height ?? dims.h,
                    media_display_size_source: existingItem.media_display_size_source ?? 'placeholder',
                    status: item.status ?? existingItem.status,
                    task_id: item.task_id ?? existingItem.task_id,
                    artifact_ref: item.artifact_ref ?? existingItem.artifact_ref,
                    progress: item.progress ?? existingItem.progress,
                    error_message: item.error_message ?? existingItem.error_message,
                    failure_kind: item.failure_kind ?? existingItem.failure_kind,
                    aspect_ratio: item.aspect_ratio ?? existingItem.aspect_ratio,
                    provider_code: item.provider_code ?? existingItem.provider_code,
                    resolution: item.resolution ?? existingItem.resolution,
                    duration: item.duration ?? existingItem.duration,
                    model_name: item.model_name ?? existingItem.model_name,
                    model_label: item.model_label ?? existingItem.model_label,
                    agent_message_id: item.messageId ?? existingItem.agent_message_id,
                    agent_conversation_id: normalizeAgentConversationId(item.conversationId)
                      ?? existingItem.agent_conversation_id
                      ?? null,
                    agent_media_key: existingItem.agent_media_key || incomingKey,
                    agent_group_key: item.agent_group_key ?? item.agentGroupKey ?? existingItem.agent_group_key,
                    agent_group_order: existingItem.agent_group_order ?? insertionPlan.nextOrder,
                    asset_origin: 'ai_generated',
                    suppressCompletionToast: item.suppressCompletionToast ?? existingItem.suppressCompletionToast ?? true,
                  } as CanvasItem)
                : existingItem,
            )
            agentGeneratedMediaRef.current = hydrateAgentGeneratedMediaState(updatedItems)
            return updatedItems
          }

          if (!insertionPlan.shouldInsert) {
            return previous
          }

          if (previous.some((existingItem) => existingItem.id === incomingId)) {
            return previous
          }

          let position = { x: 0, y: 0 }
          if (insertionPlan.currentCount === 1) {
            position = findEmptyPosition(
              viewportCenterX,
              viewportCenterY,
              dims.w,
              dims.h,
              previous,
            )
          } else {
            const firstItemId = insertionPlan.nextSession.items[0]?.id
            const firstItem = previous.find((existingItem) => existingItem.id === firstItemId)

            if (firstItem) {
              const col = (insertionPlan.currentCount - 1) % 5
              const row = Math.floor((insertionPlan.currentCount - 1) / 5)
              position = {
                x: firstItem.x + col * (dims.w + 20),
                y: firstItem.y + row * (dims.h + 20),
              }
            } else {
              position = findEmptyPosition(
                viewportCenterX,
                viewportCenterY,
                dims.w,
                dims.h,
                previous,
              )
            }
          }

          const finalItem = { ...newItem, x: position.x, y: position.y }
          targetItemId = finalItem.id

          if (insertionPlan.currentCount === 1) {
            const nextItems = [...previous, finalItem]
            focusTarget = resolveAgentGeneratedMediaFocusTarget(nextItems, {
              insertedItemId: finalItem.id,
              groupId: finalItem.groupId,
            })
            return nextItems
          }

          const groupId = insertionPlan.nextSession.groupId

          if (!groupId) {
            const nextItems = [...previous, finalItem]
            focusTarget = resolveAgentGeneratedMediaFocusTarget(nextItems, {
              insertedItemId: finalItem.id,
              groupId: finalItem.groupId,
            })
            return nextItems
          }

          const sessionItemIds = new Set(insertionPlan.nextSession.items.map((sessionItem) => sessionItem.id))
          const nextItems = previous.map((existingItem) => (
            sessionItemIds.has(existingItem.id)
              ? {
                  ...existingItem,
                  groupId,
                  agent_message_id: item.messageId ?? existingItem.agent_message_id ?? null,
                  agent_conversation_id: normalizeAgentConversationId(item.conversationId)
                    ?? existingItem.agent_conversation_id
                    ?? null,
                  agent_group_key: item.agent_group_key ?? item.agentGroupKey ?? existingItem.agent_group_key,
                }
              : existingItem
          ))

          const needsGroup = !nextItems.some((existingItem) => existingItem.id === groupId)
          const groupedItems = needsGroup && groupItem ? [...nextItems, groupItem, finalItem] : [...nextItems, finalItem]
          const laidOutItems = applyAgentGridLayout(
            groupedItems,
            groupId,
            normalizeAgentConversationId(item.conversationId),
            item.messageId == null ? null : String(item.messageId),
            item.name || item._agentLabel || 'agent',
          )
          const placedItems = avoidAgentGroupCollisions(laidOutItems, groupId)
          focusTarget = resolveAgentGeneratedMediaFocusTarget(placedItems, {
            insertedItemId: finalItem.id,
            groupId,
          })
          return placedItems
        })()

        canvasItemsRef.current = nextItems
        commitAgentCanvasItems(nextItems)

        if (focusTarget) {
          selectAndCenterCanvasItem(focusTarget)
        }

        return targetItemId
      }

      const updateIntrinsicMediaDimensions = (
        targetItemId: string,
        actualWidth: number,
        actualHeight: number,
      ) => {
        const previous = canvasItemsRef.current
        const existingGeneratedItem = previous.find((existingItem) => existingItem.id === targetItemId)
        if (!existingGeneratedItem) {
          return
        }

        const intrinsicSizeUpdate = getMediaDisplayInitializationUpdate({
          item: existingGeneratedItem,
          intrinsicWidth: actualWidth,
          intrinsicHeight: actualHeight,
        })
        if (!intrinsicSizeUpdate) {
          return
        }

        const updatedItems = previous.map((existingItem) =>
          existingItem.id === targetItemId
            ? ({
                ...existingItem,
                width: intrinsicSizeUpdate.width,
                height: intrinsicSizeUpdate.height,
                x: intrinsicSizeUpdate.x,
                y: intrinsicSizeUpdate.y,
                media_display_size_source: intrinsicSizeUpdate.media_display_size_source,
              } as CanvasItem)
            : existingItem,
        )
        const groupItem = existingGeneratedItem.groupId
          ? updatedItems.find((existingItem) => (
              existingItem.id === existingGeneratedItem.groupId
              && existingItem.type === 'group'
              && existingItem.group_layout_mode === 'agent_grid'
            ))
          : null
        const nextItems = groupItem && existingGeneratedItem.groupId
          ? avoidAgentGroupCollisions(
              applyAgentGridLayout(
                updatedItems,
                existingGeneratedItem.groupId,
                existingGeneratedItem.agent_conversation_id ?? null,
                normalizeAgentMessageId(existingGeneratedItem.agent_message_id),
                existingGeneratedItem.name || 'agent',
              ),
              existingGeneratedItem.groupId,
            )
          : updatedItems

        canvasItemsRef.current = nextItems
        commitAgentCanvasItems(nextItems)
      }

      const targetItemId = upsertMediaOnCanvas()
      const fullUrl = normalizedItemUrl
        ? resolveCanvasAgentMediaUrl(normalizedItemUrl, normalizeAgentConversationId(item.conversationId))
        : ''

      if (targetItemId && (mediaType === 'image' || mediaType === 'image_generator') && fullUrl) {
        const image = new Image()
        image.onload = () => updateIntrinsicMediaDimensions(
          targetItemId,
          image.naturalWidth || dims.w,
          image.naturalHeight || dims.h,
        )
        image.onerror = () => undefined
        image.src = fullUrl
        return
      }

      if (targetItemId && (mediaType === 'video' || mediaType === 'video_generator') && fullUrl) {
        const video = document.createElement('video')
        video.onloadedmetadata = () => updateIntrinsicMediaDimensions(
          targetItemId,
          video.videoWidth || dims.w,
          video.videoHeight || dims.h,
        )
        video.onerror = () => undefined
        video.src = fullUrl
      }
    })

    return () => setOnCanvasUpdate(null)
  }, [
    canvasItems,
    availableImageModels,
    availableVideoModels,
    imageModel,
    videoModel,
    imageProvider,
    imageRatio,
    imageRes,
    setOnCanvasUpdate,
    updateCanvasItems,
    applyAgentCanvasItems,
    syncCanvasRevisionFromAgentPatch,
    videoAspect,
    videoProvider,
    videoQuality,
    zoomRef,
    offsetRef,
    agentGeneratedMediaRef,
    deletedAgentMediaKeys,
    selectAndCenterCanvasItem,
  ])
}
