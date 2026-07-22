type RenderOnlyBlockLike = {
  uiKind?: string | null
  children?: RenderOnlyBlockLike[] | null
}

const STANDALONE_RENDER_ONLY_CARD_KINDS = new Set([
  'generation_card',
  'media_card',
  'web_search_card',
])

export function shouldReplayRenderOnlyMessageStandalone(blocks: readonly RenderOnlyBlockLike[]): boolean {
  return blocks.some((block) => {
    if (!block) {
      return false
    }
    if (STANDALONE_RENDER_ONLY_CARD_KINDS.has(String(block.uiKind || ''))) {
      return true
    }
    return Array.isArray(block.children) && shouldReplayRenderOnlyMessageStandalone(block.children)
  })
}
