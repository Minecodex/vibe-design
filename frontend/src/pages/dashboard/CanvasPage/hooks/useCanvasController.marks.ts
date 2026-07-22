/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useCallback } from 'react'

import { agentApi } from '@/api/endpoints/agent'
import { extractApiErrorMessage, isBillingInsufficientMessage } from '@/api/errorHandling'
import { useChatStore } from '@/store/canvasAgentStore'

export function useCanvasControllerMarks(args: any) {
  const {
    t,
    updateMarks,
    isChatSidebarOpen,
    setIsChatSidebarOpen,
    markIdCounter,
  } = args
  const modelPreferences = useChatStore(state => state.modelPreferences)

  const analyzeMarkElement = useCallback(async (mark: any, imageItem: any) => {
    try {
      const res = await agentApi.analyzeElement({
        image_url: imageItem.url,
        relative_x: mark.relativeX,
        relative_y: mark.relativeY,
        language: 'zh',
        model_name: modelPreferences.multimodal_model,
        provider_code: modelPreferences.multimodal_provider,
      })
      const labels = res.data.labels
      updateMarks((prev: any[]) => prev.map((item) =>
        item.id === mark.id
          ? { ...item, isAnalyzing: false, aiLabels: labels, selectedLabel: labels[0] || null }
          : item
      ), { skipHistory: true })
    } catch (error) {
      console.error('Element analysis failed:', error)
      const message = extractApiErrorMessage(error, '')
      const markPatch = isBillingInsufficientMessage(message)
        ? { isAnalyzing: false }
        : { isAnalyzing: false, aiLabels: [t('common.unknown', '未识别')], selectedLabel: t('common.unknown', '未识别') }
      updateMarks((prev: any[]) => prev.map((item) =>
        item.id === mark.id
          ? { ...item, ...markPatch }
          : item
      ), { skipHistory: true })
    }
  }, [modelPreferences.multimodal_model, modelPreferences.multimodal_provider, t, updateMarks])

  const addMark = useCallback((imageItem: any, clickEvent: React.MouseEvent) => {
    const imgEl = document.querySelector(`#item-${imageItem.id} img`) as HTMLImageElement
    if (!imgEl) return

    const imgRect = imgEl.getBoundingClientRect()
    const rx = Math.max(0, Math.min(1, (clickEvent.clientX - imgRect.left) / imgRect.width))
    const ry = Math.max(0, Math.min(1, (clickEvent.clientY - imgRect.top) / imgRect.height))

    markIdCounter.current += 1
    const newMark = {
      id: `mark-${Date.now()}-${markIdCounter.current}`,
      imageItemId: imageItem.id,
      imageUrl: imageItem.url,
      relativeX: rx,
      relativeY: ry,
      number: 0,
      aiLabels: [],
      selectedLabel: null,
      customLabel: null,
      isAnalyzing: true,
    }

    updateMarks((prev: any[]) => {
      const updated = [...prev, newMark]
      return updated.map((item, index) => ({ ...item, number: index + 1 }))
    })

    if (!isChatSidebarOpen) setIsChatSidebarOpen(true)
    analyzeMarkElement(newMark, imageItem)
  }, [analyzeMarkElement, isChatSidebarOpen, markIdCounter, setIsChatSidebarOpen, updateMarks])

  const removeMark = useCallback((markId: string) => {
    updateMarks((prev: any[]) => {
      const filtered = prev.filter((item) => item.id !== markId)
      return filtered.map((item, index) => ({ ...item, number: index + 1 }))
    })
  }, [updateMarks])

  const updateMarkLabel = useCallback((markId: string, label: string | null, isCustom: boolean) => {
    updateMarks((prev: any[]) => prev.map((item) =>
      item.id === markId
        ? { ...item, selectedLabel: isCustom ? null : label, customLabel: isCustom ? label : null }
        : item
    ))
  }, [updateMarks])

  const clearMarks = useCallback(() => {
    updateMarks([])
    markIdCounter.current = 0
  }, [markIdCounter, updateMarks])

  return {
    addMark,
    removeMark,
    updateMarkLabel,
    clearMarks,
  }
}
