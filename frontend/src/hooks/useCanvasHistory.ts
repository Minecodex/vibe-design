import { useState, useCallback, useRef } from 'react'
import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'

interface CanvasSnapshot {
  canvasItems: CanvasItem[]
  marks: CanvasMark[]
}

interface UseCanvasHistoryOptions {
  maxHistory?: number
}

export function useCanvasHistory({ maxHistory = 50 }: UseCanvasHistoryOptions = {}) {
  const [canvasItems, setCanvasItemsInternal] = useState<CanvasItem[]>([])
  const [marks, setMarksInternal] = useState<CanvasMark[]>([])

  const undoStackRef = useRef<CanvasSnapshot[]>([])
  const redoStackRef = useRef<CanvasSnapshot[]>([])

  // Refs to track latest values for snapshot capture (avoids stale closures)
  const canvasItemsRef = useRef(canvasItems)
  canvasItemsRef.current = canvasItems
  const marksRef = useRef(marks)
  marksRef.current = marks

  // Transaction state for drag/resize batching
  const transactionRef = useRef<{
    active: boolean
    preSnapshot: CanvasSnapshot | null
  }>({ active: false, preSnapshot: null })

  // Force re-render to update canUndo/canRedo
  const [, forceUpdate] = useState(0)

  const pushToUndoStack = useCallback((snapshot: CanvasSnapshot) => {
    undoStackRef.current = [
      ...undoStackRef.current.slice(-(maxHistory - 1)),
      snapshot,
    ]
    redoStackRef.current = []
    forceUpdate(n => n + 1)
  }, [maxHistory])

  const updateCanvasItems = useCallback((
    updater: CanvasItem[] | ((prev: CanvasItem[]) => CanvasItem[]),
    options?: { skipHistory?: boolean },
  ) => {
    if (!options?.skipHistory && !transactionRef.current.active) {
      pushToUndoStack({
        canvasItems: canvasItemsRef.current,
        marks: marksRef.current,
      })
    }
    setCanvasItemsInternal(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      canvasItemsRef.current = next
      return next
    })
  }, [pushToUndoStack])

  const updateMarks = useCallback((
    updater: CanvasMark[] | ((prev: CanvasMark[]) => CanvasMark[]),
    options?: { skipHistory?: boolean },
  ) => {
    if (!options?.skipHistory && !transactionRef.current.active) {
      pushToUndoStack({
        canvasItems: canvasItemsRef.current,
        marks: marksRef.current,
      })
    }
    setMarksInternal(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      marksRef.current = next
      return next
    })
  }, [pushToUndoStack])

  const beginTransaction = useCallback(() => {
    transactionRef.current = {
      active: true,
      preSnapshot: {
        canvasItems: canvasItemsRef.current,
        marks: marksRef.current,
      },
    }
  }, [])

  const commitTransaction = useCallback(() => {
    const tx = transactionRef.current
    if (!tx.active || !tx.preSnapshot) return
    // Only push if state actually changed
    if (
      tx.preSnapshot.canvasItems !== canvasItemsRef.current ||
      tx.preSnapshot.marks !== marksRef.current
    ) {
      pushToUndoStack(tx.preSnapshot)
    }
    transactionRef.current = { active: false, preSnapshot: null }
  }, [pushToUndoStack])

  const rollbackTransaction = useCallback(() => {
    const tx = transactionRef.current
    if (!tx.active || !tx.preSnapshot) return
    const snapshot = tx.preSnapshot
    setCanvasItemsInternal(snapshot.canvasItems)
    canvasItemsRef.current = snapshot.canvasItems
    setMarksInternal(snapshot.marks)
    marksRef.current = snapshot.marks
    transactionRef.current = { active: false, preSnapshot: null }
  }, [])

  const undo = useCallback(() => {
    const stack = undoStackRef.current
    if (stack.length === 0) return
    const snapshot = stack[stack.length - 1]
    undoStackRef.current = stack.slice(0, -1)
    // Push current state to redo
    redoStackRef.current = [
      ...redoStackRef.current,
      { canvasItems: canvasItemsRef.current, marks: marksRef.current },
    ]
    setCanvasItemsInternal(snapshot.canvasItems)
    canvasItemsRef.current = snapshot.canvasItems
    setMarksInternal(snapshot.marks)
    marksRef.current = snapshot.marks
    forceUpdate(n => n + 1)
  }, [])

  const redo = useCallback(() => {
    const stack = redoStackRef.current
    if (stack.length === 0) return
    const snapshot = stack[stack.length - 1]
    redoStackRef.current = stack.slice(0, -1)
    // Push current state to undo
    undoStackRef.current = [
      ...undoStackRef.current,
      { canvasItems: canvasItemsRef.current, marks: marksRef.current },
    ]
    setCanvasItemsInternal(snapshot.canvasItems)
    canvasItemsRef.current = snapshot.canvasItems
    setMarksInternal(snapshot.marks)
    marksRef.current = snapshot.marks
    forceUpdate(n => n + 1)
  }, [])

  const initializeState = useCallback((items: CanvasItem[], newMarks: CanvasMark[]) => {
    setCanvasItemsInternal(items)
    canvasItemsRef.current = items
    setMarksInternal(newMarks)
    marksRef.current = newMarks
    undoStackRef.current = []
    redoStackRef.current = []
    forceUpdate(n => n + 1)
  }, [])

  return {
    canvasItems,
    marks,
    updateCanvasItems,
    updateMarks,
    beginTransaction,
    commitTransaction,
    rollbackTransaction,
    undo,
    redo,
    canUndo: undoStackRef.current.length > 0,
    canRedo: redoStackRef.current.length > 0,
    initializeState,
  }
}
