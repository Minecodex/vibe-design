import { resolveCanvasAgentMediaUrl } from '../canvasMediaUrl'

export const ensureFullUrl = (
  url: string | null | undefined,
  conversationId?: string | number | null,
) => resolveCanvasAgentMediaUrl(url, conversationId)
