import { useCallback, useLayoutEffect, useRef, type UIEvent } from 'react'

const TOP_LOAD_THRESHOLD_PX = 80
const BOTTOM_FOLLOW_THRESHOLD_PX = 80

type ScrollContainer = Pick<HTMLElement, 'clientHeight' | 'scrollHeight' | 'scrollTop' | 'scrollTo'>

export function isHomeChatNearTop(container: ScrollContainer): boolean {
  return container.scrollTop <= TOP_LOAD_THRESHOLD_PX
}

export function isHomeChatNearBottom(container: ScrollContainer): boolean {
  return container.scrollHeight - container.scrollTop - container.clientHeight <= BOTTOM_FOLLOW_THRESHOLD_PX
}

export function scrollHomeChatToBottom(container: ScrollContainer, behavior: ScrollBehavior): void {
  if (typeof container.scrollTo === 'function') {
    container.scrollTo({
      top: container.scrollHeight,
      behavior,
    })
    return
  }
  container.scrollTop = container.scrollHeight
}

export function restoreHomeChatScrollAnchor(
  container: ScrollContainer,
  previousScrollHeight: number,
  previousScrollTop: number,
): void {
  container.scrollTop = Math.max(0, previousScrollTop + container.scrollHeight - previousScrollHeight)
}

interface UseHomeChatMessageScrollOptions {
  conversationId: number | string | null
  messageCount: number
  streamingBlockCount: number
  olderMessagesHasMore: boolean
  olderMessagesLoading: boolean
  loadOlderMessages: () => Promise<void>
}

export function useHomeChatMessageScroll({
  conversationId,
  messageCount,
  streamingBlockCount,
  olderMessagesHasMore,
  olderMessagesLoading,
  loadOlderMessages,
}: UseHomeChatMessageScrollOptions) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const activeConversationKeyRef = useRef('')
  const lastMessageCountRef = useRef(0)
  const isFollowingBottomRef = useRef(true)
  const isLoadingOlderRef = useRef(false)
  const isRestoringHistoryRef = useRef(false)

  const loadOlderMessagesWithAnchor = useCallback(async () => {
    const container = scrollContainerRef.current
    if (!container || !olderMessagesHasMore || olderMessagesLoading || isLoadingOlderRef.current) {
      return
    }

    const conversationKey = String(conversationId ?? '')
    const previousScrollHeight = container.scrollHeight
    const previousScrollTop = container.scrollTop
    isLoadingOlderRef.current = true
    isRestoringHistoryRef.current = true

    try {
      await loadOlderMessages()
      window.requestAnimationFrame(() => {
        const currentContainer = scrollContainerRef.current
        if (currentContainer && activeConversationKeyRef.current === conversationKey) {
          restoreHomeChatScrollAnchor(currentContainer, previousScrollHeight, previousScrollTop)
          isFollowingBottomRef.current = isHomeChatNearBottom(currentContainer)
        }
        isRestoringHistoryRef.current = false
        isLoadingOlderRef.current = false
      })
    } catch (error) {
      isRestoringHistoryRef.current = false
      isLoadingOlderRef.current = false
      throw error
    }
  }, [conversationId, loadOlderMessages, olderMessagesHasMore, olderMessagesLoading])

  const handleMessageScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    const container = event.currentTarget
    isFollowingBottomRef.current = isHomeChatNearBottom(container)
    if (isHomeChatNearTop(container)) {
      void loadOlderMessagesWithAnchor()
    }
  }, [loadOlderMessagesWithAnchor])

  useLayoutEffect(() => {
    const container = scrollContainerRef.current
    if (!container) {
      return
    }

    const conversationKey = String(conversationId ?? '')
    const previousMessageCount = lastMessageCountRef.current
    const conversationChanged = activeConversationKeyRef.current !== conversationKey
    activeConversationKeyRef.current = conversationKey
    lastMessageCountRef.current = messageCount

    if (isRestoringHistoryRef.current) {
      return
    }
    if (conversationChanged || (previousMessageCount === 0 && messageCount > 0)) {
      scrollHomeChatToBottom(container, 'auto')
      isFollowingBottomRef.current = true
      return
    }
    if (isFollowingBottomRef.current) {
      scrollHomeChatToBottom(container, streamingBlockCount > 0 ? 'auto' : 'smooth')
    }
  }, [conversationId, messageCount, streamingBlockCount])

  return {
    handleMessageScroll,
    loadOlderMessagesWithAnchor,
    scrollContainerRef,
  }
}
