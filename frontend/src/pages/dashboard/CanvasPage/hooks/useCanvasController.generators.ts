/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment, react-hooks/exhaustive-deps */
// @ts-nocheck
import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { agentApi } from '@/api/endpoints/agent'
import { apiClient } from '@/api/client'
import { extractApiErrorMessage, toastApiError } from '@/api/errorHandling'
import { generationApi } from '@/api/endpoints/generation'
import { ensureBalanceOrNotify, isBalanceRequiredForProvider } from '@/utils/balanceGuard'
import { validateUploadFileSize } from '@/utils/uploadLimits'

import {
  getAvailableVideoResolutions,
  getTailFrameConstraintState,
  getVideoImageInputMode,
  shouldDisableVideoAspectRatio,
} from '../generatorCapabilities'
import {
  getImageCapabilityFromConfig,
  getResolvedImageModelCapability,
  resolveImageModelSelection,
} from '../imageModelConfig'
import {
  buildAnchoredVideoInputs,
  findNearbyVideoTaskPosition,
} from '../imageAnchoredVideo'
import {
  applyGeneratorAssetsToAnchoredImageDraft,
  applyGeneratorAssetsToAnchoredVideoDraft,
  applyGeneratorAssetsToCanvasItem,
} from '../generatorAssetLibrary'
import { buildImageEraseResultItem } from '../imageErase'
import { buildTextRedrawResultItem } from '../textRedraw'
import { findEmptyPosition } from '../canvasLayout'
import { GENERATION_TASK_STATUS_POLL_INTERVAL_MS, startSerialPolling } from '../generationPolling'
import { getNextCanvasStackZIndex } from '../imageActions'
import { normalizeCanvasAgentMediaRef } from '../canvasMediaUrl'
import { getGenerationFailureKind, getGenerationPollingStatus, isRetryableFailedGenerationItem } from '../generationFailure'
import { getClosestImageGenerationDefaults } from '../mediaDimensions'
import { fetchCanvasGenerationTaskSnapshot } from '../generationTaskSnapshot'
import {
  applyRecoveredGenerationTask,
  createGenerationClientRequestId,
  getGenerationRecoveryLookupKey,
  getPendingGenerationBindingItems,
  isGenerationTaskPendingStatus,
  shouldExpireBindingTask,
} from '../generationTaskBinding'

export function useCanvasControllerGenerators(args: any) {
  const {
    t,
    id,
    user,
    canvasItems,
    offsetRef,
    zoomRef,
    setOffset,
    setSelectedItems,
    updateCanvasItems,
    saveCanvasItems,
    updateItem,
    getItemDims,
    getItemReferenceImages,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    getResolvedImageCapability,
    withReferenceImages,
    availableImageModels,
    availableVideoModels,
    imageModel,
    imageProvider,
    videoModel,
    videoProvider,
    imageRes,
    imageRatio,
    videoAspect,
    videoDuration,
    videoQuality,
    setImageAnchoredImageDraft,
    imageAnchoredImageDraft,
    setImageAnchoredVideoDraft,
    imageAnchoredVideoDraft,
    spatialAngleSession,
    setSpatialAngleSession,
    setActiveDropdown,
    selectAndCenterCanvasItem,
    loadIntrinsicImageSize,
    notifiedTasksRef,
  } = args

  // Use refs so the polling closure always sees the latest values
  // without triggering useEffect re-runs (same pattern as MessageList.tsx)
  const canvasItemsRef = useRef(canvasItems)
  canvasItemsRef.current = canvasItems
  const updateCanvasItemsRef = useRef(updateCanvasItems)
  updateCanvasItemsRef.current = updateCanvasItems
  const saveCanvasItemsRef = useRef(saveCanvasItems)
  saveCanvasItemsRef.current = saveCanvasItems
  const loadIntrinsicImageSizeRef = useRef(loadIntrinsicImageSize)
  loadIntrinsicImageSizeRef.current = loadIntrinsicImageSize
  const retryingTaskIdsRef = useRef(new Set<string>())
  const submittingGenerationItemIdsRef = useRef(new Set<string>())
  const anchoredImageSubmittingRef = useRef(false)
  const anchoredVideoSubmittingRef = useRef(false)
  const bindingTaskKey = canvasItems
    .filter((item: any) => item.status === 'binding_task' && !item.task_id && item.client_request_id)
    .map((item: any) => `${item.id}:${item.client_request_id}`)
    .join(',')

  const ensureProviderPaidActionAllowed = useCallback((providerCode?: string | null) => {
    const requiresBalance = isBalanceRequiredForProvider(providerCode)
    if (requiresBalance && !ensureBalanceOrNotify(user?.balance_cents, t)) return false
    if (requiresBalance && (user?.balance_cents ?? 0) <= 0) {
      toast.error(t('billing.insufficient', '余额不足，无法发起新对话'))
      return false
    }
    return true
  }, [t, user?.balance_cents])

  useEffect(() => {
    if (!id || !bindingTaskKey) return

    return startSerialPolling(async () => {
      const pendingBindings = getPendingGenerationBindingItems(canvasItemsRef.current)
      if (pendingBindings.length === 0) {
        return null
      }

      try {
        const response = await generationApi.recoverTasks(Number(id), {
          items: pendingBindings.map(({ client_request_id, task_type }) => ({
            client_request_id,
            task_type,
          })),
        })
        const recoveredTasks = response.data.tasks || {}
        let hasCriticalUpdate = false

        updateCanvasItemsRef.current((prev: any[]) => {
          const next = prev.map((item: any) => {
            if (
              item.status !== 'binding_task'
              || item.task_id != null
              || !item.client_request_id
            ) {
              return item
            }

            const taskType = item.type === 'image_generator'
              ? 'text2image'
              : ((item.reference_images?.length || item.first_frame_image || item.tail_frame_image) ? 'image2video' : 'text2video')
            const lookupKey = getGenerationRecoveryLookupKey(taskType, item.client_request_id)
            const recoveredTask = recoveredTasks[lookupKey]

            if (recoveredTask) {
              hasCriticalUpdate = true
              const nextItem = applyRecoveredGenerationTask(item, recoveredTask)
              return {
                ...nextItem,
                failure_kind: nextItem.status === 'failed'
                  ? getGenerationFailureKind({ status: 'failed', task_id: nextItem.task_id })
                  : undefined,
              }
            }

            if (shouldExpireBindingTask(item)) {
              hasCriticalUpdate = true
              return {
                ...item,
                status: 'failed',
                error_message: item.error_message || t('canvas.generator.task_binding_failed', '任务创建超时，请重试'),
                failure_kind: 'task_binding_failed',
              }
            }

            return item
          })

          if (hasCriticalUpdate) {
            saveCanvasItemsRef.current(next)
          }
          return next
        }, { skipHistory: true })
      } catch (error) {
        console.error('Failed to recover generation task bindings:', error)
      }

      return 3000
    })
  }, [bindingTaskKey, id, t])

  // Stable key: only changes when the set of generating task IDs changes
  const generatingTaskKey = canvasItems
    .filter((item: any) => item.status === 'generating' && item.task_id)
    .map((item: any) => item.task_id)
    .join(',')

  useEffect(() => {
    if (!generatingTaskKey) return

    const checkStatus = async () => {
      const currentItems = canvasItemsRef.current
      const generatingTasks = currentItems
        .filter((item: any) => item.status === 'generating' && item.task_id)
        .map((item: any) => ({
          id: item.id,
          task_id: item.task_id,
          conversationId: item.agent_conversation_id ?? null,
        }))

      if (generatingTasks.length === 0) return
      const updates: any[] = []

      for (const task of generatingTasks) {
        try {
          const statusRes = await fetchCanvasGenerationTaskSnapshot({
            taskId: task.task_id,
            conversationId: task.conversationId,
          })
          const status = getGenerationPollingStatus(statusRes.data)
          const effectiveTaskId = statusRes.data.task_id ?? statusRes.data.id ?? task.task_id

          if (status === 'failed' && retryingTaskIdsRef.current.has(task.id)) {
            const currentItem = currentItems.find((item: any) => item.id === task.id)
            updates.push({ id: task.id, status: 'generating', task_id: effectiveTaskId, progress: currentItem?.progress ?? 0 })
            continue
          }

          if (status === 'completed' || status === 'failed') {
            const currentItem = currentItems.find((item: any) => item.id === task.id)
            const fallbackSize = {
              width: Math.max(1, Math.round(currentItem?.width || 0)),
              height: Math.max(1, Math.round(currentItem?.height || 0)),
            }

            if (!notifiedTasksRef.current.has(task.id)) {
              if (status === 'completed') {
                if (!currentItem?.suppressCompletionToast) {
                  toast.success(currentItem?.type.includes('image') ? t('canvas.generator.completed_image') : t('canvas.generator.completed_video'))
                }
              } else {
                toast.error(statusRes.data.error_message || (currentItem?.type.includes('image') ? t('canvas.generator.failed_image') : t('canvas.generator.failed_video')))
              }
              notifiedTasksRef.current.add(task.id)
            }

            let resultSize

            if (
              status === 'completed' &&
              (currentItem?.generation_kind === 'text_redraw' || currentItem?.generation_kind === 'image_erase') &&
              statusRes.data.result_url
            ) {
              resultSize = await loadIntrinsicImageSizeRef.current(statusRes.data.result_url, fallbackSize)
            }

            updates.push({
              id: task.id,
              status,
              task_id: effectiveTaskId,
              url: statusRes.data.result_url,
              urls: statusRes.data.result_urls,
              artifact_ref: statusRes.data.artifact_ref,
              prompt: statusRes.data.prompt,
              model_label: statusRes.data.model_label,
              created_at: statusRes.data.created_at,
              creator_name: user?.nickname || user?.username,
              creator_avatar: user?.avatar_url,
              resultSize,
              progress: status === 'completed' ? 100 : undefined,
              error: statusRes.data.error_message,
            })
          } else {
            updates.push({ id: task.id, status: 'generating', task_id: effectiveTaskId, progress: statusRes.data.progress })
          }
        } catch (error) {
          console.error(`Failed to query task status for ${task.task_id}:`, error)
        }
      }

      if (updates.length === 0) return

      updateCanvasItemsRef.current((prev: any[]) => {
        let hasCriticalUpdate = false
        let next = prev

        for (const update of updates) {
          const currentItem = next.find((item: any) => item.id === update.id)
          if (!currentItem) continue

          if (
            currentItem.generation_kind === 'text_redraw' &&
            update.status === 'completed' &&
            update.url
          ) {
            const resultItem = buildTextRedrawResultItem({
              taskItem: currentItem,
              resultUrl: update.url,
              resultSize: update.resultSize,
            })
            next = next.map((item: any) => item.id === currentItem.id ? resultItem : item)
            hasCriticalUpdate = true
            continue
          }

          if (
            currentItem.generation_kind === 'image_erase' &&
            update.status === 'completed' &&
            update.url
          ) {
            const resultItem = buildImageEraseResultItem({
              taskItem: currentItem,
              resultUrl: update.url,
              resultSize: update.resultSize,
            })
            next = next.map((item: any) => item.id === currentItem.id ? resultItem : item)
            hasCriticalUpdate = true
            continue
          }

          if (
            currentItem.status === update.status &&
            currentItem.progress === update.progress &&
            currentItem.task_id === update.task_id &&
            currentItem.url === update.url
          ) {
            continue
          }

          let newType = currentItem.type
          if (update.status === 'completed') {
            if (currentItem.type === 'image_generator') newType = 'image'
            else if (currentItem.type === 'video_generator') newType = 'video'
            hasCriticalUpdate = true
          } else if (update.status === 'failed') {
            hasCriticalUpdate = true
          }

          next = next.map((item: any) => item.id === currentItem.id ? {
            ...item,
            type: newType,
            status: update.status,
            task_id: update.task_id ?? item.task_id,
            url: update.url || item.url,
            prompt: update.prompt ?? item.prompt,
            model_label: update.model_label ?? item.model_label,
            created_at: update.created_at ?? item.created_at,
            creator_name: update.creator_name ?? item.creator_name,
            creator_avatar: update.creator_avatar ?? item.creator_avatar,
            progress: update.progress ?? item.progress,
            artifact_ref: update.artifact_ref ?? item.artifact_ref,
            error_message: update.error ?? item.error_message,
            failure_kind: update.status === 'failed'
              ? getGenerationFailureKind({ status: update.status, task_id: update.task_id ?? currentItem.task_id })
              : undefined,
            asset_origin: update.status === 'completed' ? 'ai_generated' : item.asset_origin,
          } : item)
        }

        if (hasCriticalUpdate) {
          saveCanvasItemsRef.current(next)
        }

        return next
      }, { skipHistory: true })
    }

    return startSerialPolling(async () => {
      await checkStatus()
      return GENERATION_TASK_STATUS_POLL_INTERVAL_MS
    })
  }, [generatingTaskKey, t])

  const addNewGenerator = useCallback((type: 'image_generator' | 'video_generator') => {
    const viewportCenterX = -offsetRef.current.x / (zoomRef.current / 100)
    const viewportCenterY = -offsetRef.current.y / (zoomRef.current / 100)

    const isImage = type === 'image_generator'
    const resolvedImageModel = isImage
      ? availableImageModels.find((model: any) => model.value === imageModel && model.provider === imageProvider)
      : null
    const imageSelection = isImage
      ? resolveImageModelSelection({
        config: resolvedImageModel?.config,
        currentResolution: imageRes,
        currentAspectRatio: imageRatio,
      })
      : null
    const configuredItem = {
      id: '',
      type,
      url: '',
      x: 0,
      y: 0,
      prompt: '',
      model_name: isImage ? imageModel : videoModel,
      provider_code: isImage ? imageProvider : videoProvider,
      aspect_ratio: isImage ? imageSelection?.aspect_ratio : videoAspect,
      reference_images: [],
      status: 'completed',
      resolution: isImage ? imageSelection?.resolution : videoQuality,
      duration: isImage ? undefined : videoDuration,
    }
    const dims = getItemDims(configuredItem)
    const pos = findEmptyPosition(viewportCenterX, viewportCenterY, dims.width, dims.height, canvasItems)
    const newItem: any = {
      id: Date.now().toString() + Math.random().toString().slice(2, 6),
      type,
      url: '',
      x: pos.x,
      y: pos.y,
      width: dims.width,
      height: dims.height,
      z_index: getNextCanvasStackZIndex(canvasItems),
      prompt: '',
      model_name: configuredItem.model_name,
      provider_code: configuredItem.provider_code,
      aspect_ratio: configuredItem.aspect_ratio,
      resolution: configuredItem.resolution,
      reference_images: [],
      status: 'completed',
    }
    if (!isImage) {
      newItem.duration = videoDuration
    }
    const nextItems = [...canvasItems, newItem]
    updateCanvasItems(nextItems)
    selectAndCenterCanvasItem(newItem)
    saveCanvasItems(nextItems)
    toast.success(t('canvas.generator_added_success', { type: isImage ? t('canvas.generator.image_title') : t('canvas.generator.video_title') }))
  }, [availableImageModels, canvasItems, getItemDims, imageModel, imageProvider, imageRatio, imageRes, saveCanvasItems, selectAndCenterCanvasItem, t, videoAspect, videoDuration, videoModel, videoProvider, videoQuality, updateCanvasItems])

  const resolveAnchoredImageModel = useCallback(() => {
    const supportedImageModel = availableImageModels.find((model: any) =>
      getImageCapabilityFromConfig(model.config, model.value).supportsReferenceImages,
    )
    if (supportedImageModel) {
      return supportedImageModel
    }

    if (imageModel) {
      return {
        value: imageModel,
        provider: imageProvider,
        config: undefined,
      }
    }

    return null
  }, [availableImageModels, imageModel, imageProvider])

  const uploadImageFiles = useCallback(async (files: File[]) => {
    return Promise.all(files.map(async (file) => {
      if (!validateUploadFileSize(file, 'canvas_image_max_bytes', t)) {
        throw new Error('canvas_image_upload_too_large')
      }
      const formData = new FormData()
      formData.append('file', file)
      const res = await apiClient.post(`/projects/${id}/upload/image`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data.url as string
    }))
  }, [id, t])

  const getResolvedVideoModelConfig = useCallback((item: any) => {
    return availableVideoModels.find((model: any) =>
      model.value === (item.model_name || videoModel) &&
      model.provider === (item.provider_code || videoProvider),
    )?.config
  }, [availableVideoModels, videoModel, videoProvider])

  const getAllowedResolutionOptionsForItem = useCallback((item: any, capability: any) => {
    const modelConfig = getResolvedVideoModelConfig(item)
    const baseResolutions = modelConfig?.allowed_sizes?.length
      ? modelConfig.allowed_sizes
      : [videoQuality]
    return getAvailableVideoResolutions(capability, item, baseResolutions)
  }, [getResolvedVideoModelConfig, videoQuality])

  const getTailFrameConstraintMessage = useCallback((reason: string | null | undefined) => {
    if (reason === 'requires_first_frame') {
      return t('canvas.generator.tail_frame_requires_first_frame', '尾帧图需要先设置首帧图')
    }
    if (reason === 'requires_pro_resolution') {
      return t('canvas.generator.tail_frame_requires_pro_resolution', '当前模型的尾帧图仅支持指定高质量分辨率')
    }
    if (reason === 'audio_conflict') {
      return t('canvas.generator.tail_frame_audio_conflict', '尾帧图与音频模式不能同时使用')
    }
    return t('canvas.generator.tail_frame')
  }, [t])

  const handleGenerateImage = useCallback(async (itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item) return
    if (isGenerationTaskPendingStatus(item.status) || submittingGenerationItemIdsRef.current.has(itemId)) return
    const prompt = item.prompt || ''
    if (!prompt.trim()) return toast.warning(t('canvas.generator.prompt_required'))
    const referenceImages = getItemReferenceImages(item)
    const resolvedModel = availableImageModels.find((model: any) =>
      model.value === (item.model_name || imageModel) &&
      model.provider === (item.provider_code || imageProvider),
    )
    const resolvedSelection = resolveImageModelSelection({
      config: resolvedModel?.config,
      currentResolution: item.resolution || imageRes,
      currentAspectRatio: item.aspect_ratio || imageRatio,
    })
    const resolvedDims = getItemDims({ ...item, ...resolvedSelection })

    if (!ensureProviderPaidActionAllowed(item.provider_code || imageProvider)) return
    submittingGenerationItemIdsRef.current.add(itemId)
    const clientRequestId = createGenerationClientRequestId()
    const bindingStartedAt = new Date().toISOString()

    try {
      updateItem(itemId, {
        status: 'binding_task',
        task_id: undefined,
        client_request_id: clientRequestId,
        binding_started_at: bindingStartedAt,
        resolution: resolvedSelection.resolution,
        aspect_ratio: resolvedSelection.aspect_ratio,
        width: resolvedDims.width,
        height: resolvedDims.height,
        progress: 0,
        error_message: null,
        failure_kind: undefined,
      })
      if (
        resolvedSelection.resolution !== (item.resolution || imageRes) ||
        resolvedSelection.aspect_ratio !== (item.aspect_ratio || imageRatio)
      ) {
        updateItem(itemId, { ...resolvedSelection, width: resolvedDims.width, height: resolvedDims.height })
      }
      const res = await generationApi.generateImage(Number(id), {
        prompt,
        model_name: item.model_name || imageModel,
        provider_code: item.provider_code || imageProvider,
        aspect_ratio: resolvedSelection.aspect_ratio,
        resolution: resolvedSelection.resolution,
        image_urls: referenceImages.length > 0 ? referenceImages : undefined,
        client_request_id: clientRequestId,
      })
      const nextItem = applyRecoveredGenerationTask({
        ...item,
        type: 'image_generator',
        resolution: resolvedSelection.resolution,
        aspect_ratio: resolvedSelection.aspect_ratio,
        width: resolvedDims.width,
        height: resolvedDims.height,
        client_request_id: clientRequestId,
        binding_started_at: bindingStartedAt,
      }, res.data)
      if (res.data.status === 'failed') {
        updateItem(itemId, {
          ...nextItem,
          error_message: res.data.error_message || t('canvas.generator.failed_image'),
          failure_kind: getGenerationFailureKind({ status: 'failed', task_id: nextItem.task_id }),
        })
        toast.error(res.data.error_message || t('canvas.generator.failed_image'))
      } else {
        updateItem(itemId, { ...nextItem, failure_kind: undefined })
        toast.success(t('canvas.generator.submit_success'))
      }
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_image'))
      updateItem(itemId, {
        status: 'failed',
        error_message: errorMessage,
        failure_kind: 'internal_failed',
      })
      toastApiError(error, t('canvas.generator.failed_image'))
    } finally {
      submittingGenerationItemIdsRef.current.delete(itemId)
    }
  }, [availableImageModels, canvasItems, ensureProviderPaidActionAllowed, getItemDims, getItemReferenceImages, id, imageModel, imageProvider, imageRatio, imageRes, t, updateItem])

  const cancelImageAnchoredImageDraft = useCallback((clearSelection = true) => {
    setImageAnchoredImageDraft(null)
    setActiveDropdown(null)
    if (clearSelection) {
      setSelectedItems([])
    }
  }, [setActiveDropdown, setImageAnchoredImageDraft, setSelectedItems])

  const updateImageAnchoredImageDraft = useCallback((updates: any) => {
    setImageAnchoredImageDraft((current: any) => {
      if (!current) return null
      return { ...current, ...updates }
    })
  }, [setImageAnchoredImageDraft])

  const openImageAnchoredImageDraft = useCallback((itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || !item.url) return

    const resolvedModel = resolveAnchoredImageModel()
    if (!resolvedModel) {
      toast.warning(t('canvas.generator.reference_model_required', '当前没有可用的参考图图片模型'))
      return
    }

    const capability = getResolvedImageModelCapability(
      availableImageModels,
      resolvedModel.value,
      resolvedModel.provider || imageProvider,
    )
    if (!capability.supportsReferenceImages) {
      toast.warning(t('canvas.generator.reference_model_required', '当前没有可用的参考图图片模型'))
      return
    }

    const allowedResolutions = resolvedModel.config?.allowed_sizes?.length
      ? resolvedModel.config.allowed_sizes
      : [imageRes]
    const autoDefaults = getClosestImageGenerationDefaults({
      sourceWidth: item.width,
      sourceHeight: item.height,
      providerCode: resolvedModel.provider || imageProvider,
      allowedRatios: resolvedModel.config?.allowed_aspect_ratios?.length
        ? resolvedModel.config.allowed_aspect_ratios
        : [imageRatio],
      allowedResolutions,
    })
    const draftSelection = resolveImageModelSelection({
      config: resolvedModel.config,
      currentResolution: autoDefaults.resolution,
      currentAspectRatio: autoDefaults.aspect_ratio,
    })

    setImageAnchoredImageDraft({
      sourceImageItemId: item.id,
      sourceImageUrl: normalizeCanvasAgentMediaRef(item.url, item.agent_conversation_id ?? null),
      prompt: '',
      model_name: resolvedModel.value,
      provider_code: resolvedModel.provider || imageProvider,
      aspect_ratio: draftSelection.aspect_ratio,
      resolution: draftSelection.resolution,
      reference_images: [],
    })
    setActiveDropdown(null)
    setSelectedItems([item.id])
  }, [canvasItems, imageProvider, imageRatio, imageRes, resolveAnchoredImageModel, setActiveDropdown, setImageAnchoredImageDraft, setSelectedItems, t])

  const buildImageAnchoredImageDraftItem = useCallback((draft: any) => {
    if (!draft) return null

    const effectiveReferenceImages = [draft.sourceImageUrl, ...(draft.reference_images || [])].filter(Boolean)

    return {
      id: draft.sourceImageItemId,
      type: 'image_generator',
      url: '',
      x: 0,
      y: 0,
      width: 0,
      height: 0,
      prompt: draft.prompt,
      model_name: draft.model_name,
      provider_code: draft.provider_code,
      aspect_ratio: draft.aspect_ratio,
      resolution: draft.resolution,
      reference_images: effectiveReferenceImages,
      reference_image: effectiveReferenceImages[0] || '',
      status: 'completed',
    }
  }, [])

  const imageAnchoredImageDraftItem = buildImageAnchoredImageDraftItem(imageAnchoredImageDraft)
  const imageAnchoredImageSourceItem = imageAnchoredImageDraft
    ? canvasItems.find((item: any) => item.id === imageAnchoredImageDraft.sourceImageItemId) || null
    : null

  const handleUploadAnchoredImageReference = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0 || !imageAnchoredImageDraft) return
    const capability = getResolvedImageModelCapability(
      availableImageModels,
      imageAnchoredImageDraft.model_name,
      imageAnchoredImageDraft.provider_code,
    )

    const currentReferenceCount = imageAnchoredImageDraft.reference_images.length + 1
    if (capability.maxReferenceImages > 0 && currentReferenceCount >= capability.maxReferenceImages) {
      toast.warning(t('canvas.generator.reference_limit_reached', '参考图已达上限'))
      e.target.value = ''
      return
    }

    const remainingSlots = capability.maxReferenceImages > 0
      ? Math.max(0, capability.maxReferenceImages - currentReferenceCount)
      : files.length
    const acceptedFiles = capability.maxReferenceImages > 0 ? files.slice(0, remainingSlots) : files
    if (acceptedFiles.length === 0) {
      e.target.value = ''
      return
    }

    try {
      const uploadUrls = await uploadImageFiles(acceptedFiles)
      updateImageAnchoredImageDraft({
        reference_images: [...imageAnchoredImageDraft.reference_images, ...uploadUrls],
      })
      if (acceptedFiles.length < files.length) {
        toast.warning(t('canvas.generator.reference_limit_reached', '参考图已达上限'))
      }
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [availableImageModels, imageAnchoredImageDraft, t, updateImageAnchoredImageDraft, uploadImageFiles])

  const handleGenerateAnchoredImage = useCallback(async () => {
    if (!imageAnchoredImageDraft || !imageAnchoredImageSourceItem) return
    if (anchoredImageSubmittingRef.current) return
    const prompt = imageAnchoredImageDraft.prompt || ''
    if (!prompt.trim()) return toast.warning(t('canvas.generator.prompt_required'))

    if (!ensureProviderPaidActionAllowed(imageAnchoredImageDraft.provider_code || imageProvider)) return
    anchoredImageSubmittingRef.current = true

    const effectiveReferenceImages = [
      imageAnchoredImageDraft.sourceImageUrl,
      ...imageAnchoredImageDraft.reference_images,
    ].filter(Boolean)
    const resolvedDraftModel = availableImageModels.find((model: any) =>
      model.value === (imageAnchoredImageDraft.model_name || imageModel) &&
      model.provider === (imageAnchoredImageDraft.provider_code || imageProvider),
    )
    const draftSelection = resolveImageModelSelection({
      config: resolvedDraftModel?.config,
      currentResolution: imageAnchoredImageDraft.resolution || imageRes,
      currentAspectRatio: imageAnchoredImageDraft.aspect_ratio || imageRatio,
    })
    const draftItem = buildImageAnchoredImageDraftItem(imageAnchoredImageDraft)
    if (!draftItem) return

    const taskDims = getItemDims({
      ...draftItem,
      width: undefined,
      height: undefined,
    })
    const taskPosition = findNearbyVideoTaskPosition({
      sourceItem: imageAnchoredImageSourceItem,
      canvasItems,
      taskSize: { width: taskDims.width, height: taskDims.height },
    })

    const taskItemId = Date.now().toString() + Math.random().toString().slice(2, 6)
    const taskItem: any = {
      id: taskItemId,
      type: 'image_generator',
      generator_origin: 'image_action',
      url: '',
      x: taskPosition.x,
      y: taskPosition.y,
      width: taskDims.width,
      height: taskDims.height,
      prompt,
      model_name: imageAnchoredImageDraft.model_name || imageModel,
      provider_code: imageAnchoredImageDraft.provider_code || imageProvider,
      aspect_ratio: draftSelection.aspect_ratio,
      resolution: draftSelection.resolution,
      reference_images: effectiveReferenceImages,
      reference_image: effectiveReferenceImages[0] || '',
      status: 'binding_task',
      client_request_id: createGenerationClientRequestId(),
      binding_started_at: new Date().toISOString(),
    }

    const nextItems = [...canvasItems, taskItem]
    updateCanvasItems(nextItems, { skipHistory: true })
    saveCanvasItems(nextItems)
    selectAndCenterCanvasItem(taskItem)
    cancelImageAnchoredImageDraft(false)

    try {
      const res = await generationApi.generateImage(Number(id), {
        prompt,
        model_name: taskItem.model_name,
        provider_code: taskItem.provider_code,
        aspect_ratio: taskItem.aspect_ratio,
        resolution: taskItem.resolution,
        image_urls: effectiveReferenceImages.length > 0 ? effectiveReferenceImages : undefined,
        client_request_id: taskItem.client_request_id,
      })
      const nextItem = applyRecoveredGenerationTask(taskItem, res.data)
      updateItem(taskItemId, {
        ...nextItem,
        failure_kind: nextItem.status === 'failed'
          ? getGenerationFailureKind({ status: 'failed', task_id: nextItem.task_id })
          : undefined,
      })
      toast.success(t('canvas.generator.submit_success'))
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_image'))
      updateItem(taskItemId, {
        status: 'failed',
        error_message: errorMessage,
        failure_kind: 'internal_failed',
      })
      toastApiError(error, t('canvas.generator.failed_image'))
    } finally {
      anchoredImageSubmittingRef.current = false
    }
  }, [
    availableImageModels,
    buildImageAnchoredImageDraftItem,
    cancelImageAnchoredImageDraft,
    canvasItems,
    getItemDims,
    id,
    imageAnchoredImageDraft,
    imageAnchoredImageSourceItem,
    imageModel,
    imageProvider,
    imageRatio,
    imageRes,
    saveCanvasItems,
    selectAndCenterCanvasItem,
    t,
    updateCanvasItems,
    updateItem,
    ensureProviderPaidActionAllowed,
  ])

  const handleGenerateVideo = useCallback(async (itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item) return
    if (isGenerationTaskPendingStatus(item.status) || submittingGenerationItemIdsRef.current.has(itemId)) return
    const prompt = item.prompt || ''
    if (!prompt.trim()) return toast.warning(t('canvas.generator.prompt_required'))
    const capability = getResolvedVideoCapability(item)
    const videoImageMode = getVideoImageInputMode(capability, item)
    const referenceImages = getItemReferenceImages(item)
    const allowedResolutions = getAllowedResolutionOptionsForItem(item, capability)
    const resolvedResolution = allowedResolutions.includes(item.resolution || videoQuality)
      ? (item.resolution || videoQuality)
      : (allowedResolutions[0] || item.resolution || videoQuality)
    const tailFrameConstraint = getTailFrameConstraintState(capability, item, resolvedResolution)
    if (item.tail_frame_image && !tailFrameConstraint.enabled) {
      return toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
    }
    const allowedDurations = getResolvedVideoDurations(item)
    const resolvedDuration = allowedDurations.includes(item.duration || videoDuration)
      ? (item.duration || videoDuration)
      : (allowedDurations[0] || item.duration || videoDuration)

    if (!ensureProviderPaidActionAllowed(item.provider_code || videoProvider)) return
    submittingGenerationItemIdsRef.current.add(itemId)
    const clientRequestId = createGenerationClientRequestId()
    const bindingStartedAt = new Date().toISOString()

    try {
      updateItem(itemId, {
        status: 'binding_task',
        task_id: undefined,
        client_request_id: clientRequestId,
        binding_started_at: bindingStartedAt,
        progress: 0,
        error_message: null,
        failure_kind: undefined,
      })
      const payload: any = {
        prompt,
        model_name: item.model_name || videoModel,
        provider_code: item.provider_code || videoProvider,
        duration: parseInt(resolvedDuration),
        quality: resolvedResolution,
        resolution: resolvedResolution,
        audio: resolvedResolution.toLowerCase().endsWith('_audio'),
        image_urls: videoImageMode === 'reference' && referenceImages.length > 0 ? referenceImages : undefined,
        first_frame_image: videoImageMode === 'frames' ? item.first_frame_image || undefined : undefined,
        tail_frame_image: videoImageMode === 'frames' ? item.tail_frame_image || undefined : undefined,
        client_request_id: clientRequestId,
      }
      if (!shouldDisableVideoAspectRatio(capability, item)) {
        payload.aspect_ratio = item.aspect_ratio || videoAspect
      }
      const res = await generationApi.generateVideo(Number(id), payload)
      const nextItem = applyRecoveredGenerationTask({
        ...item,
        type: 'video_generator',
        duration: resolvedDuration,
        client_request_id: clientRequestId,
        binding_started_at: bindingStartedAt,
      }, res.data)
      if (res.data.status === 'failed') {
        updateItem(itemId, {
          ...nextItem,
          duration: resolvedDuration,
          error_message: res.data.error_message || t('canvas.generator.failed_video'),
          failure_kind: getGenerationFailureKind({ status: 'failed', task_id: nextItem.task_id }),
        })
        toast.error(res.data.error_message || t('canvas.generator.failed_video'))
      } else {
        updateItem(itemId, { ...nextItem, duration: resolvedDuration, failure_kind: undefined })
        toast.success(t('canvas.generator.submit_success'))
      }
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_video'))
      updateItem(itemId, {
        status: 'failed',
        error_message: errorMessage,
        failure_kind: 'internal_failed',
      })
      toastApiError(error, t('canvas.generator.failed_video'))
    } finally {
      submittingGenerationItemIdsRef.current.delete(itemId)
    }
  }, [canvasItems, ensureProviderPaidActionAllowed, getAllowedResolutionOptionsForItem, getItemReferenceImages, getResolvedVideoCapability, getResolvedVideoDurations, getTailFrameConstraintMessage, id, t, updateItem, videoAspect, videoDuration, videoModel, videoProvider, videoQuality])

  const cancelImageAnchoredVideoDraft = useCallback((clearSelection = true) => {
    setImageAnchoredVideoDraft(null)
    setActiveDropdown(null)
    if (clearSelection) {
      setSelectedItems([])
    }
  }, [setActiveDropdown, setImageAnchoredVideoDraft, setSelectedItems])

  const updateImageAnchoredVideoDraft = useCallback((updates: any) => {
    setImageAnchoredVideoDraft((current: any) => {
      if (!current) return null
      return { ...current, ...updates }
    })
  }, [setImageAnchoredVideoDraft])

  const openImageAnchoredVideoDraft = useCallback((itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || !item.url) return

    setImageAnchoredVideoDraft({
      sourceImageItemId: item.id,
      sourceImageUrl: normalizeCanvasAgentMediaRef(item.url, item.agent_conversation_id ?? null),
      prompt: '',
      model_name: videoModel,
      provider_code: videoProvider,
      aspect_ratio: videoAspect,
      duration: videoDuration,
      resolution: videoQuality,
      sourcePlacement: 'reference',
      reference_images: [],
      first_frame_image: '',
      tail_frame_image: '',
    })
    setActiveDropdown(null)
    setSelectedItems([item.id])
  }, [canvasItems, setActiveDropdown, setImageAnchoredVideoDraft, setSelectedItems, videoAspect, videoDuration, videoModel, videoProvider, videoQuality])

  const buildImageAnchoredVideoDraftItem = useCallback((draft: any) => {
    if (!draft) return null

    const effectiveInputs = buildAnchoredVideoInputs({
      sourceImageUrl: draft.sourceImageUrl,
      sourcePlacement: draft.sourcePlacement,
      referenceImages: draft.reference_images,
      firstFrameImage: draft.first_frame_image,
      tailFrameImage: draft.tail_frame_image,
    })

    return {
      id: draft.sourceImageItemId,
      type: 'video_generator',
      url: '',
      x: 0,
      y: 0,
      width: 0,
      height: 0,
      prompt: draft.prompt,
      model_name: draft.model_name,
      provider_code: draft.provider_code,
      aspect_ratio: draft.aspect_ratio,
      duration: draft.duration,
      resolution: draft.resolution,
      reference_images: effectiveInputs.referenceImages,
      reference_image: effectiveInputs.referenceImages[0] || '',
      first_frame_image: effectiveInputs.firstFrameImage,
      tail_frame_image: effectiveInputs.tailFrameImage,
      status: 'completed',
    }
  }, [])

  const imageAnchoredVideoDraftItem = buildImageAnchoredVideoDraftItem(imageAnchoredVideoDraft)
  const imageAnchoredVideoSourceItem = imageAnchoredVideoDraft
    ? canvasItems.find((item: any) => item.id === imageAnchoredVideoDraft.sourceImageItemId) || null
    : null
  const imageAnchoredVideoCapability = imageAnchoredVideoDraftItem
    ? getResolvedVideoCapability(imageAnchoredVideoDraftItem)
    : null
  const imageAnchoredVideoAllowedDurations = imageAnchoredVideoDraftItem
    ? getResolvedVideoDurations(
      imageAnchoredVideoDraftItem,
      {},
      imageAnchoredVideoDraftItem.model_name,
      undefined,
    )
    : []

  const handleMoveAnchoredVideoSourcePlacement = useCallback((placement: any) => {
    setImageAnchoredVideoDraft((current: any) => {
      if (!current) return null
      const nextDraft = {
        ...current,
        sourcePlacement: placement,
      }
      const draftItem = buildImageAnchoredVideoDraftItem(nextDraft)
      if (!draftItem) return current
      const capability = getResolvedVideoCapability(draftItem)

      if (placement === 'reference' && !capability.supportsReferenceImages) return current
      if (placement === 'first_frame' && !capability.supportsFirstFrame) return current
      if (placement === 'tail_frame' && !capability.supportsTailFrame) return current
      if (placement === 'tail_frame') {
        const tailFrameConstraint = getTailFrameConstraintState(
          capability,
          draftItem,
          nextDraft.resolution || videoQuality,
        )
        if (!tailFrameConstraint.enabled) {
          toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
          return current
        }
      }
      if (placement === 'first_frame' && current.first_frame_image) {
        toast.warning(t('canvas.generator.first_frame'))
        return current
      }
      if (placement === 'tail_frame' && current.tail_frame_image) {
        toast.warning(t('canvas.generator.tail_frame'))
        return current
      }

      if (capability.imageModesConflict) {
        if (placement === 'reference') {
          nextDraft.first_frame_image = ''
          nextDraft.tail_frame_image = ''
        } else {
          nextDraft.reference_images = []
        }
      }

      return nextDraft
    })
  }, [buildImageAnchoredVideoDraftItem, getResolvedVideoCapability, getTailFrameConstraintMessage, setImageAnchoredVideoDraft, t, videoQuality])

  const handleUploadAnchoredReferenceImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0 || !imageAnchoredVideoDraft) return
    const draftItem = buildImageAnchoredVideoDraftItem(imageAnchoredVideoDraft)
    if (!draftItem) return
    const capability = getResolvedVideoCapability(draftItem)

    if (capability.imageModesConflict && imageAnchoredVideoDraft.sourcePlacement !== 'reference') {
      toast.warning(t('canvas.generator.reference_image'))
      e.target.value = ''
      return
    }

    const currentReferenceCount = imageAnchoredVideoDraft.reference_images.length + (imageAnchoredVideoDraft.sourcePlacement === 'reference' ? 1 : 0)
    if (capability.maxReferenceImages > 0 && currentReferenceCount >= capability.maxReferenceImages) {
      toast.warning(t('canvas.generator.reference_limit_reached', '参考图已达上限'))
      e.target.value = ''
      return
    }

    const remainingSlots = capability.maxReferenceImages > 0
      ? Math.max(0, capability.maxReferenceImages - currentReferenceCount)
      : files.length
    const acceptedFiles = capability.maxReferenceImages > 0 ? files.slice(0, remainingSlots) : files
    if (acceptedFiles.length === 0) {
      e.target.value = ''
      return
    }

    try {
      const uploadUrls = await uploadImageFiles(acceptedFiles)
      updateImageAnchoredVideoDraft({
        reference_images: [...imageAnchoredVideoDraft.reference_images, ...uploadUrls],
      })
      if (acceptedFiles.length < files.length) {
        toast.warning(t('canvas.generator.reference_limit_reached', '参考图已达上限'))
      }
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [buildImageAnchoredVideoDraftItem, getResolvedVideoCapability, imageAnchoredVideoDraft, t, updateImageAnchoredVideoDraft, uploadImageFiles])

  const handleUploadAnchoredFirstFrameImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !imageAnchoredVideoDraft) return
    const draftItem = buildImageAnchoredVideoDraftItem(imageAnchoredVideoDraft)
    if (!draftItem) return
    const capability = getResolvedVideoCapability(draftItem)

    if (imageAnchoredVideoDraft.sourcePlacement === 'first_frame') {
      toast.warning(t('canvas.generator.first_frame'))
      e.target.value = ''
      return
    }
    if (capability.imageModesConflict && imageAnchoredVideoDraft.sourcePlacement === 'reference') {
      toast.warning(t('canvas.generator.reference_image'))
      e.target.value = ''
      return
    }

    try {
      const [uploadUrl] = await uploadImageFiles([file])
      const updates: any = { first_frame_image: uploadUrl }
      if (capability.imageModesConflict) {
        updates.reference_images = []
      }
      updateImageAnchoredVideoDraft(updates)
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [buildImageAnchoredVideoDraftItem, getResolvedVideoCapability, imageAnchoredVideoDraft, t, updateImageAnchoredVideoDraft, uploadImageFiles])

  const handleUploadAnchoredTailFrameImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !imageAnchoredVideoDraft) return
    const draftItem = buildImageAnchoredVideoDraftItem(imageAnchoredVideoDraft)
    if (!draftItem) return
    const capability = getResolvedVideoCapability(draftItem)

    if (imageAnchoredVideoDraft.sourcePlacement === 'tail_frame') {
      toast.warning(t('canvas.generator.tail_frame'))
      e.target.value = ''
      return
    }
    if (capability.imageModesConflict && imageAnchoredVideoDraft.sourcePlacement === 'reference') {
      toast.warning(t('canvas.generator.reference_image'))
      e.target.value = ''
      return
    }
    const nextDraftItem = buildImageAnchoredVideoDraftItem({
      ...imageAnchoredVideoDraft,
      tail_frame_image: '__pending_tail_frame__',
    })
    if (!nextDraftItem) {
      e.target.value = ''
      return
    }
    const tailFrameConstraint = getTailFrameConstraintState(
      capability,
      nextDraftItem,
      imageAnchoredVideoDraft.resolution || videoQuality,
    )
    if (!tailFrameConstraint.enabled) {
      toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
      e.target.value = ''
      return
    }

    try {
      const [uploadUrl] = await uploadImageFiles([file])
      const updates: any = { tail_frame_image: uploadUrl }
      if (capability.imageModesConflict) {
        updates.reference_images = []
      }
      updateImageAnchoredVideoDraft(updates)
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [buildImageAnchoredVideoDraftItem, getResolvedVideoCapability, getTailFrameConstraintMessage, imageAnchoredVideoDraft, t, updateImageAnchoredVideoDraft, uploadImageFiles, videoQuality])

  const handleGenerateAnchoredVideo = useCallback(async () => {
    if (!imageAnchoredVideoDraft || !imageAnchoredVideoSourceItem) return
    if (anchoredVideoSubmittingRef.current) return
    const prompt = imageAnchoredVideoDraft.prompt || ''
    if (!prompt.trim()) return toast.warning(t('canvas.generator.prompt_required'))

    if (!ensureProviderPaidActionAllowed(imageAnchoredVideoDraft.provider_code || videoProvider)) return
    anchoredVideoSubmittingRef.current = true

    const effectiveInputs = buildAnchoredVideoInputs({
      sourceImageUrl: imageAnchoredVideoDraft.sourceImageUrl,
      sourcePlacement: imageAnchoredVideoDraft.sourcePlacement,
      referenceImages: imageAnchoredVideoDraft.reference_images,
      firstFrameImage: imageAnchoredVideoDraft.first_frame_image,
      tailFrameImage: imageAnchoredVideoDraft.tail_frame_image,
    })

    const draftItem = buildImageAnchoredVideoDraftItem(imageAnchoredVideoDraft)
    if (!draftItem) return
    const capability = getResolvedVideoCapability(draftItem)
    const effectiveVideoItem = {
      ...draftItem,
      reference_images: effectiveInputs.referenceImages,
      reference_image: effectiveInputs.referenceImages[0] || '',
      first_frame_image: effectiveInputs.firstFrameImage,
      tail_frame_image: effectiveInputs.tailFrameImage,
    }
    const allowedResolutions = getAllowedResolutionOptionsForItem(effectiveVideoItem, capability)
    const resolvedResolution = allowedResolutions.includes(effectiveVideoItem.resolution || videoQuality)
      ? (effectiveVideoItem.resolution || videoQuality)
      : (allowedResolutions[0] || effectiveVideoItem.resolution || videoQuality)
    const tailFrameConstraint = getTailFrameConstraintState(capability, effectiveVideoItem, resolvedResolution)
    if (effectiveVideoItem.tail_frame_image && !tailFrameConstraint.enabled) {
      return toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
    }
    const videoImageMode = getVideoImageInputMode(capability, effectiveVideoItem)
    const taskDims = getItemDims({
      ...effectiveVideoItem,
      resolution: resolvedResolution,
      width: undefined,
      height: undefined,
    })
    const taskPosition = findNearbyVideoTaskPosition({
      sourceItem: imageAnchoredVideoSourceItem,
      canvasItems,
      taskSize: { width: taskDims.width, height: taskDims.height },
    })

    const taskItemId = Date.now().toString() + Math.random().toString().slice(2, 6)
    const taskItem: any = {
      id: taskItemId,
      type: 'video_generator',
      generator_origin: 'image_action',
      url: '',
      x: taskPosition.x,
      y: taskPosition.y,
      width: taskDims.width,
      height: taskDims.height,
      prompt,
      model_name: imageAnchoredVideoDraft.model_name || videoModel,
      provider_code: imageAnchoredVideoDraft.provider_code || videoProvider,
      aspect_ratio: imageAnchoredVideoDraft.aspect_ratio || videoAspect,
      duration: imageAnchoredVideoDraft.duration || videoDuration,
      resolution: resolvedResolution,
      reference_images: effectiveInputs.referenceImages,
      reference_image: effectiveInputs.referenceImages[0] || '',
      first_frame_image: effectiveInputs.firstFrameImage,
      tail_frame_image: effectiveInputs.tailFrameImage,
      status: 'binding_task',
      client_request_id: createGenerationClientRequestId(),
      binding_started_at: new Date().toISOString(),
    }
    const draftAllowedDurations = getResolvedVideoDurations(taskItem)
    const resolvedDraftDuration = draftAllowedDurations.includes(taskItem.duration || videoDuration)
      ? (taskItem.duration || videoDuration)
      : (draftAllowedDurations[0] || taskItem.duration || videoDuration)
    taskItem.duration = resolvedDraftDuration

    const nextItems = [...canvasItems, taskItem]
    updateCanvasItems(nextItems, { skipHistory: true })
    saveCanvasItems(nextItems)
    selectAndCenterCanvasItem(taskItem)
    cancelImageAnchoredVideoDraft(true)

    try {
      const payload: any = {
        prompt,
        model_name: taskItem.model_name,
        provider_code: taskItem.provider_code,
        duration: parseInt(resolvedDraftDuration),
        quality: resolvedResolution,
        resolution: resolvedResolution,
        audio: resolvedResolution.toLowerCase().endsWith('_audio'),
        image_urls: videoImageMode === 'reference' && effectiveInputs.referenceImages.length > 0
          ? effectiveInputs.referenceImages
          : undefined,
        first_frame_image: videoImageMode === 'frames'
          ? effectiveInputs.firstFrameImage || undefined
          : undefined,
        tail_frame_image: videoImageMode === 'frames'
          ? effectiveInputs.tailFrameImage || undefined
          : undefined,
        client_request_id: taskItem.client_request_id,
      }
      if (!shouldDisableVideoAspectRatio(capability, effectiveVideoItem)) {
        payload.aspect_ratio = taskItem.aspect_ratio || videoAspect
      }
      const res = await generationApi.generateVideo(Number(id), payload)
      const nextItem = applyRecoveredGenerationTask(taskItem, res.data)
      updateItem(taskItemId, {
        ...nextItem,
        failure_kind: nextItem.status === 'failed'
          ? getGenerationFailureKind({ status: 'failed', task_id: nextItem.task_id })
          : undefined,
      })
      toast.success(t('canvas.generator.submit_success'))
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_video'))
      updateItem(taskItemId, {
        status: 'failed',
        error_message: errorMessage,
        failure_kind: 'internal_failed',
      })
      toastApiError(error, t('canvas.generator.failed_video'))
    } finally {
      anchoredVideoSubmittingRef.current = false
    }
  }, [
    buildImageAnchoredVideoDraftItem,
    cancelImageAnchoredVideoDraft,
    canvasItems,
    getItemDims,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    id,
    imageAnchoredVideoDraft,
    imageAnchoredVideoSourceItem,
    saveCanvasItems,
    selectAndCenterCanvasItem,
    t,
    updateCanvasItems,
    updateItem,
    ensureProviderPaidActionAllowed,
    videoAspect,
    videoDuration,
    videoModel,
    videoProvider,
    videoQuality,
    getAllowedResolutionOptionsForItem,
    getTailFrameConstraintMessage,
  ])

  const handleUploadReferenceImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>, itemId: string) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item) return
    const isImageGenerator = item.type === 'image_generator'
    const imageCapability = isImageGenerator ? getResolvedImageCapability(item) : null
    const videoCapability = !isImageGenerator ? getResolvedVideoCapability(item) : null
    const currentReferenceImages = getItemReferenceImages(item)
    const maxReferenceImages = isImageGenerator
      ? imageCapability?.maxReferenceImages || 0
      : videoCapability?.maxReferenceImages || 0

    if (maxReferenceImages > 0 && currentReferenceImages.length >= maxReferenceImages) {
      toast.warning(t('canvas.generator.reference_limit_reached', '参考图已达上限'))
      e.target.value = ''
      return
    }

    const remainingSlots = maxReferenceImages > 0
      ? Math.max(0, maxReferenceImages - currentReferenceImages.length)
      : files.length
    const acceptedFiles = maxReferenceImages > 0 ? files.slice(0, remainingSlots) : files
    if (acceptedFiles.length === 0) {
      e.target.value = ''
      return
    }

    try {
      const uploadUrls = await uploadImageFiles(acceptedFiles)
      const nextReferenceImages = [...currentReferenceImages, ...uploadUrls]
      const updates: any = withReferenceImages(nextReferenceImages)
      if (videoCapability?.imageModesConflict && (item.first_frame_image || item.tail_frame_image)) {
        updates.first_frame_image = ''
        updates.tail_frame_image = ''
      }
      updateItem(itemId, updates)
      if (acceptedFiles.length < files.length) {
        toast.warning(t('canvas.generator.reference_limit_reached', '参考图已达上限'))
      }
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [canvasItems, getItemReferenceImages, getResolvedImageCapability, getResolvedVideoCapability, t, updateItem, uploadImageFiles, withReferenceImages])

  const handleUploadFirstFrameImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>, itemId: string) => {
    const file = e.target.files?.[0]
    if (!file) return
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item) return
    try {
      const [uploadUrl] = await uploadImageFiles([file])
      const capability = getResolvedVideoCapability(item)
      const updates: any = { first_frame_image: uploadUrl }
      if (capability.imageModesConflict && getItemReferenceImages(item).length > 0) {
        Object.assign(updates, withReferenceImages([]))
      }
      updateItem(itemId, updates)
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [canvasItems, getItemReferenceImages, getResolvedVideoCapability, t, updateItem, uploadImageFiles, withReferenceImages])

  const handleUploadTailFrameImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>, itemId: string) => {
    const file = e.target.files?.[0]
    if (!file) return
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item) return
    const capability = getResolvedVideoCapability(item)
    const nextItem = { ...item, tail_frame_image: '__pending_tail_frame__' }
    const allowedResolutions = getAllowedResolutionOptionsForItem(nextItem, capability)
    const resolvedResolution = allowedResolutions.includes(item.resolution || videoQuality)
      ? (item.resolution || videoQuality)
      : (allowedResolutions[0] || item.resolution || videoQuality)
    const tailFrameConstraint = getTailFrameConstraintState(capability, nextItem, resolvedResolution)
    if (!tailFrameConstraint.enabled) {
      toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
      e.target.value = ''
      return
    }
    try {
      const [uploadUrl] = await uploadImageFiles([file])
      const updates: any = { tail_frame_image: uploadUrl }
      if (capability.imageModesConflict && getItemReferenceImages(item).length > 0) {
        Object.assign(updates, withReferenceImages([]))
      }
      updateItem(itemId, updates)
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [canvasItems, getAllowedResolutionOptionsForItem, getItemReferenceImages, getResolvedVideoCapability, getTailFrameConstraintMessage, t, updateItem, uploadImageFiles, videoQuality, withReferenceImages])

  const applyAssetLibraryToCanvasItem = useCallback((itemId: string, target: 'reference' | 'first_frame' | 'tail_frame', assets: any[]) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item) return
    const isImageGenerator = item.type === 'image_generator'
    const imageCapability = isImageGenerator ? getResolvedImageCapability(item) : null
    const videoCapability = !isImageGenerator ? getResolvedVideoCapability(item) : null
    const maxSelection = isImageGenerator
      ? imageCapability?.maxReferenceImages || 0
      : target === 'reference'
        ? videoCapability?.maxReferenceImages || 0
        : 1
    const tailFrameConstraint = !isImageGenerator && target === 'tail_frame'
      ? getTailFrameConstraintState(
          videoCapability,
          { ...item, tail_frame_image: '__pending_tail_frame__' },
          item.resolution || videoQuality,
        )
      : null
    if (target === 'tail_frame' && tailFrameConstraint && !tailFrameConstraint.enabled) {
      toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
      return
    }

    const nextItem = applyGeneratorAssetsToCanvasItem({
      item,
      target,
      assets,
      maxSelection,
      imageModesConflict: Boolean(videoCapability?.imageModesConflict),
      allowTailFrame: tailFrameConstraint?.enabled ?? true,
    })
    updateItem(itemId, nextItem)
  }, [canvasItems, getResolvedImageCapability, getResolvedVideoCapability, getTailFrameConstraintMessage, updateItem, videoQuality])

  const applyAssetLibraryToAnchoredImageDraft = useCallback((assets: any[]) => {
    if (!imageAnchoredImageDraft) return
    const capability = getResolvedImageModelCapability(
      availableImageModels,
      imageAnchoredImageDraft.model_name,
      imageAnchoredImageDraft.provider_code,
    )
    updateImageAnchoredImageDraft(
      applyGeneratorAssetsToAnchoredImageDraft({
        draft: imageAnchoredImageDraft,
        assets,
        maxSelection: capability.maxReferenceImages > 0 ? Math.max(0, capability.maxReferenceImages - 1) : 0,
      }),
    )
  }, [availableImageModels, imageAnchoredImageDraft, updateImageAnchoredImageDraft])

  const applyAssetLibraryToAnchoredVideoDraft = useCallback((target: 'reference' | 'first_frame' | 'tail_frame', assets: any[]) => {
    if (!imageAnchoredVideoDraft || !imageAnchoredVideoCapability) return
    const maxSelection = target === 'reference'
      ? (imageAnchoredVideoCapability.maxReferenceImages > 0
        ? Math.max(0, imageAnchoredVideoCapability.maxReferenceImages - (imageAnchoredVideoDraft.sourcePlacement === 'reference' ? 1 : 0))
        : 0)
      : 1

    const allowTailFrame = target === 'tail_frame'
      ? getTailFrameConstraintState(
          imageAnchoredVideoCapability,
          { ...imageAnchoredVideoDraftItem, tail_frame_image: '__pending_tail_frame__' },
          imageAnchoredVideoDraft.resolution || videoQuality,
        ).enabled
      : true
    if (target === 'tail_frame' && !allowTailFrame) {
      const tailFrameConstraint = getTailFrameConstraintState(
        imageAnchoredVideoCapability,
        { ...imageAnchoredVideoDraftItem, tail_frame_image: '__pending_tail_frame__' },
        imageAnchoredVideoDraft.resolution || videoQuality,
      )
      toast.warning(getTailFrameConstraintMessage(tailFrameConstraint.reason))
      return
    }

    const nextDraft = applyGeneratorAssetsToAnchoredVideoDraft({
      draft: imageAnchoredVideoDraft,
      target,
      assets,
      maxSelection,
      imageModesConflict: imageAnchoredVideoCapability.imageModesConflict,
      allowTailFrame,
    })
    if (nextDraft !== imageAnchoredVideoDraft) {
      updateImageAnchoredVideoDraft(nextDraft)
    }
  }, [getTailFrameConstraintMessage, imageAnchoredVideoCapability, imageAnchoredVideoDraft, imageAnchoredVideoDraftItem, updateImageAnchoredVideoDraft, videoQuality])



  const handleOpenSpatialAngle = useCallback((itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || !item.url) return

    setSpatialAngleSession({
      itemId: item.id,
      imageUrl: item.url,
      x: 0,
      y: 0,
      scale: 'normal',
      isSubmitting: false,
    })
    setActiveDropdown(null)
    setSelectedItems([item.id])
  }, [canvasItems, setActiveDropdown, setSpatialAngleSession, setSelectedItems])

  const handleCancelSpatialAngle = useCallback((clearSelection = true) => {
    setSpatialAngleSession(null)
    setActiveDropdown(null)
    if (clearSelection) {
      setSelectedItems([])
    }
  }, [setActiveDropdown, setSpatialAngleSession, setSelectedItems])

  const handleSubmitSpatialAngle = useCallback(async ({ x, y, scale }: { x: number, y: number, scale: string }) => {
    if (!spatialAngleSession) return
    const sourceItem = canvasItems.find((item: any) => item.id === spatialAngleSession.itemId)
    if (!sourceItem) return

    if (!ensureBalanceOrNotify(user?.balance_cents, t)) return

    if ((user?.balance_cents ?? 0) <= 0) {
      return toast.error(t('billing.insufficient', '余额不足，无法发起新对话'))
    }

    setSpatialAngleSession((prev: any) => prev ? { ...prev, isSubmitting: true } : null)

    const prompt = `camera position: center x=0 y=0; up y positive, down y negative (range -30 to 60); left x negative, right x positive (range -90 to 90); scale: close-up, normal, wide-angle; x=${x}, y=${y}, scale=${scale}`

    const taskDims = getItemDims({
      ...sourceItem,
      type: 'image_generator',
      width: undefined,
      height: undefined,
    })

    const taskWidth = sourceItem.width || taskDims.width
    const taskHeight = sourceItem.height || taskDims.height

    const taskPosition = findNearbyVideoTaskPosition({
      sourceItem,
      canvasItems,
      taskSize: { width: taskWidth, height: taskHeight }
    })

    const taskItemId = Date.now().toString() + Math.random().toString().slice(2, 6)
    const taskItem: any = {
      id: taskItemId,
      type: 'image_generator',
      generator_origin: 'image_action',
      url: '',
      x: taskPosition.x,
      y: taskPosition.y,
      width: taskWidth,
      height: taskHeight,
      prompt,
      model_name: 'nanobanana2',
      provider_code: 'mizu', 
      aspect_ratio: sourceItem.aspect_ratio || imageRatio,
      resolution: sourceItem.resolution || imageRes,
      status: 'generating',
    }

    const nextItems = [...canvasItems, taskItem]
    updateCanvasItems(nextItems, { skipHistory: true })
    saveCanvasItems(nextItems)
    selectAndCenterCanvasItem(taskItem)
    handleCancelSpatialAngle(true)

    try {
      const payload = {
        source_image_url: sourceItem.url,
        source_width: sourceItem.width,
        source_height: sourceItem.height,
        x,
        y,
        scale,
      }
      const res = await generationApi.generateSpatialAngle(Number(id), payload)
      updateItem(taskItemId, { task_id: res.data.id, failure_kind: undefined })
      toast.success(t('canvas.generator.submit_success'))
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_image'))
      updateItem(taskItemId, {
        status: 'failed',
        error_message: errorMessage,
        failure_kind: 'internal_failed',
      })
      toastApiError(error, t('canvas.generator.failed_image'))
    }
  }, [canvasItems, getItemDims, handleCancelSpatialAngle, id, imageRatio, imageRes, saveCanvasItems, selectAndCenterCanvasItem, spatialAngleSession, t, updateCanvasItems, updateItem, user, offsetRef, zoomRef])

  const handleRetryFailedGeneration = useCallback(async (itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!isRetryableFailedGenerationItem(item)) return
    if (isGenerationTaskPendingStatus(item?.status) || retryingTaskIdsRef.current.has(itemId) || submittingGenerationItemIdsRef.current.has(itemId)) return
    const retrySourceTaskId = item.task_id
    const shouldUseHarnessRetry = Boolean(
      item.agent_conversation_id != null
      && String(item.agent_conversation_id).trim() !== ''
      && item.artifact_ref,
    )

    const retryProviderCode = item.type === 'video_generator'
      ? (item.provider_code || videoProvider)
      : (item.provider_code || imageProvider)
    if (!ensureProviderPaidActionAllowed(retryProviderCode)) return

    updateItem(itemId, {
      status: 'generating',
      task_id: retrySourceTaskId,
      progress: 0,
      error_message: null,
      failure_kind: undefined,
    })
    retryingTaskIdsRef.current.add(itemId)

    try {
      if (shouldUseHarnessRetry) {
        const conversationId = String(item.agent_conversation_id)
        const res = await agentApi.retryHarnessGenerationArtifact(conversationId, item.artifact_ref)
        if (res.data.status === 'failed') {
          updateItem(itemId, {
            status: 'failed',
            task_id: res.data.task_id || retrySourceTaskId,
            artifact_ref: res.data.artifact_ref || item.artifact_ref,
            error_message: res.data.error_message || (item.type === 'video_generator' ? t('canvas.generator.failed_video') : t('canvas.generator.failed_image')),
            failure_kind: 'task_failed',
          })
          toast.error(res.data.error_message || (item.type === 'video_generator' ? t('canvas.generator.failed_video') : t('canvas.generator.failed_image')))
        } else {
          updateItem(itemId, {
            status: 'generating',
            task_id: res.data.task_id,
            artifact_ref: res.data.artifact_ref || item.artifact_ref,
            progress: 0,
            failure_kind: undefined,
          })
          toast.success(t('canvas.generator.submit_success'))
        }
      } else if (item.type === 'image_generator') {
        const resolvedModel = availableImageModels.find((model: any) =>
          model.value === (item.model_name || imageModel) &&
          model.provider === (item.provider_code || imageProvider),
        )
        const resolvedSelection = resolveImageModelSelection({
          config: resolvedModel?.config,
          currentResolution: item.resolution || imageRes,
          currentAspectRatio: item.aspect_ratio || imageRatio,
        })
        const referenceImages = getItemReferenceImages(item)
        const res = await generationApi.retryTask(retrySourceTaskId, {
          prompt: item.prompt || '',
          model_name: item.model_name || imageModel,
          provider_code: item.provider_code || imageProvider,
          aspect_ratio: resolvedSelection.aspect_ratio,
          resolution: resolvedSelection.resolution,
          image_urls: referenceImages.length > 0 ? referenceImages : undefined,
        })
        updateItem(itemId, { status: 'generating', task_id: res.data.id, progress: 0, failure_kind: undefined })
      } else if (item.type === 'video_generator') {
        const capability = getResolvedVideoCapability(item)
        const videoImageMode = getVideoImageInputMode(capability, item)
        const referenceImages = getItemReferenceImages(item)
        const allowedDurations = getResolvedVideoDurations(item)
        const resolvedDuration = allowedDurations.includes(item.duration || videoDuration)
          ? (item.duration || videoDuration)
          : (allowedDurations[0] || item.duration || videoDuration)
        const resolvedResolution = item.resolution || videoQuality
        const payload: any = {
          prompt: item.prompt || '',
          model_name: item.model_name || videoModel,
          provider_code: item.provider_code || videoProvider,
          duration: parseInt(resolvedDuration),
          quality: resolvedResolution,
          resolution: resolvedResolution,
          audio: resolvedResolution.toLowerCase().endsWith('_audio'),
          image_urls: videoImageMode === 'reference' && referenceImages.length > 0 ? referenceImages : undefined,
          first_frame_image: videoImageMode === 'frames' ? item.first_frame_image || undefined : undefined,
          tail_frame_image: videoImageMode === 'frames' ? item.tail_frame_image || undefined : undefined,
        }
        if (!shouldDisableVideoAspectRatio(capability, item)) {
          payload.aspect_ratio = item.aspect_ratio || videoAspect
        }
        const res = await generationApi.retryTask(retrySourceTaskId, payload)
        updateItem(itemId, { status: 'generating', task_id: res.data.id, duration: resolvedDuration, progress: 0, failure_kind: undefined })
      }
      retryingTaskIdsRef.current.delete(itemId)
      if (!shouldUseHarnessRetry) {
        toast.success(t('canvas.generator.submit_success'))
      }
    } catch (error: any) {
      retryingTaskIdsRef.current.delete(itemId)
      const errorMessage = extractApiErrorMessage(
        error,
        item.type === 'video_generator' ? t('canvas.generator.failed_video') : t('canvas.generator.failed_image'),
      )
      updateItem(itemId, {
        status: 'failed',
        task_id: retrySourceTaskId,
        error_message: errorMessage,
        failure_kind: 'task_failed',
      })
      toastApiError(
        error,
        item.type === 'video_generator' ? t('canvas.generator.failed_video') : t('canvas.generator.failed_image'),
      )
    }
  }, [
    availableImageModels,
    canvasItems,
    getItemReferenceImages,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    ensureProviderPaidActionAllowed,
    imageModel,
    imageProvider,
    imageRatio,
    imageRes,
    t,
    updateItem,
    videoAspect,
    videoDuration,
    videoModel,
    videoProvider,
    videoQuality,
  ])

  return {
    addNewGenerator,
    handleGenerateImage,
    handleGenerateVideo,
    handleRetryFailedGeneration,
    cancelImageAnchoredImageDraft,
    updateImageAnchoredImageDraft,
    openImageAnchoredImageDraft,
    handleUploadAnchoredImageReference,
    handleGenerateAnchoredImage,
    imageAnchoredImageDraftItem,
    imageAnchoredImageSourceItem,
    cancelImageAnchoredVideoDraft,
    updateImageAnchoredVideoDraft,
    openImageAnchoredVideoDraft,
    handleMoveAnchoredVideoSourcePlacement,
    handleUploadAnchoredReferenceImage,
    handleUploadAnchoredFirstFrameImage,
    handleUploadAnchoredTailFrameImage,
    handleGenerateAnchoredVideo,
    handleUploadReferenceImage,
    handleUploadFirstFrameImage,
    handleUploadTailFrameImage,
    applyAssetLibraryToCanvasItem,
    applyAssetLibraryToAnchoredImageDraft,
    applyAssetLibraryToAnchoredVideoDraft,
    imageAnchoredVideoDraftItem,
    imageAnchoredVideoSourceItem,
    imageAnchoredVideoCapability,
    imageAnchoredVideoAllowedDurations,
    spatialAngleSession,
    handleOpenSpatialAngle,
    handleCancelSpatialAngle,
    handleSubmitSpatialAngle,
  }
}


