import type { ChatMessage, MessageBlock } from '@/store/canvasAgentStore'

export interface ForwardSelectableEntry {
  id: string
  messageId: string | number
  blockId?: string
  text: string
  source: 'message_content' | 'block'
}

function extractStreamPanelText(block: MessageBlock): string {
  const toolName = String(block.payload?.tool_name || block.payload?.name || '')

  if (toolName === 'analyze_image') {
    return ''
  }

  return String(block.payload?.stream_text || block.payload?.text || '').trim()
}

function compactTextParts(parts: Array<string | null | undefined>): string {
  return parts
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .join('\n')
    .trim()
}

function getBlockText(block: MessageBlock): string {
  if (block.visible === false) {
    return ''
  }

  const toolName = String(block.payload?.tool_name || block.payload?.name || '')

  if (toolName === 'analyze_image') {
    return ''
  }

  if (block.uiKind === 'assistant_text' || block.uiKind === 'assistant_final_answer' || block.uiKind === 'text') {
    return String(block.payload?.text || '').trim()
  }

  if (block.uiKind === 'choice_prompt') {
    const question = String(block.payload?.question || '').trim()
    const options = Array.isArray(block.payload?.options)
      ? block.payload.options
        .map((option: any) => String(option?.label || option?.value || '').trim())
        .filter(Boolean)
      : []

    return compactTextParts([question, options.length > 0 ? options.join(' / ') : ''])
  }

  if (block.uiKind === 'stream_panel') {
    return extractStreamPanelText(block)
  }

  if (block.uiKind === 'plan_artifact') {
    const steps = Array.isArray(block.payload?.steps)
      ? block.payload.steps.map((step: any) => compactTextParts([
        `${String(step?.order || '').trim()}. ${String(step?.title || '').trim()}`.trim(),
        String(step?.description || '').trim(),
      ])).filter(Boolean)
      : []

    return compactTextParts([
      String(block.payload?.title || '').trim(),
      String(block.payload?.summary || '').trim(),
      steps.join('\n'),
    ])
  }

  if (block.uiKind === 'friendly_status' || block.uiKind === 'friendly_issue') {
    return compactTextParts([
      String(block.payload?.title || '').trim(),
      String(block.payload?.text || block.payload?.message || block.payload?.description || '').trim(),
    ])
  }

  return ''
}

export function getForwardSelectableEntries(
  message: Pick<ChatMessage, 'id' | 'role' | 'content' | 'blocks'>,
): ForwardSelectableEntry[] {
  if (message.role !== 'assistant') {
    return []
  }

  const entries: ForwardSelectableEntry[] = []
  const directContent = String(message.content || '').trim()

  if (directContent) {
    entries.push({
      id: `message:${String(message.id)}:content`,
      messageId: message.id,
      text: directContent,
      source: 'message_content',
    })
  }

  ;(message.blocks || []).forEach((block) => {
    const text = getBlockText(block)
    if (!text) {
      return
    }
    entries.push({
      id: `message:${String(message.id)}:block:${block.id}`,
      messageId: message.id,
      blockId: block.id,
      text,
      source: 'block',
    })
  })

  return entries
}

export function getForwardSelectableMessageText(message: Pick<ChatMessage, 'id' | 'role' | 'content' | 'blocks'>): string | null {
  const text = getForwardSelectableEntries(message)
    .map((entry) => entry.text)
    .join('\n\n')
    .trim()

  return text || null
}

export function isForwardSelectableMessage(message: Pick<ChatMessage, 'id' | 'role' | 'content' | 'blocks'>): boolean {
  return getForwardSelectableEntries(message).length > 0
}

export function buildForwardSelectionText(
  messages: Array<Pick<ChatMessage, 'id' | 'role' | 'content' | 'blocks'>>,
  selectedIds: ReadonlySet<string>,
): string {
  return messages
    .flatMap((message) => getForwardSelectableEntries(message))
    .filter((entry) => selectedIds.has(entry.id))
    .map((entry) => entry.text)
    .join('\n\n')
}
