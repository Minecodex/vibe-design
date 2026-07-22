import type { ChatMessage, MessageBlock, ToolCallInfo } from './canvasAgentTypes'

function textPayload(block: MessageBlock): string {
  return String(
    block.payload?.text
    ?? block.payload?.content
    ?? block.payload?.stream_text
    ?? block.payload?.message
    ?? block.payload?.summary
    ?? block.payload?.analysis
    ?? '',
  ).trim()
}

function isNonEmptyValue(value: unknown): boolean {
  if (value == null) {
    return false
  }
  if (typeof value === 'string') {
    return value.trim().length > 0
  }
  if (Array.isArray(value)) {
    return value.length > 0
  }
  if (typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>).length > 0
  }
  return true
}

function hasToolIdentity(block: MessageBlock): boolean {
  return [
    block.payload?.tool,
    block.payload?.tool_name,
    block.payload?.toolName,
    block.payload?.call_id,
    block.payload?.callId,
  ].some((value) => String(value || '').trim())
}

function hasRenderableInteraction(block: MessageBlock): boolean {
  const requestId = String(
    block.payload?.request_id
    ?? block.payload?.requestId
    ?? block.payload?.tool_call_id
    ?? block.payload?.toolCallId
    ?? '',
  ).trim()
  if (!requestId) {
    return false
  }

  const schema = block.payload?.schema
  if (schema && typeof schema === 'object') {
    const source = schema as Record<string, unknown>
    const title = String(source.title || '').trim()
    const questions = Array.isArray(source.questions) ? source.questions : []
    const fields = Array.isArray(source.fields) ? source.fields : []
    if (title || questions.length > 0 || fields.length > 0) {
      return true
    }
  }

  return Boolean(String(block.payload?.question || block.payload?.content || '').trim())
}

function hasRenderableMedia(block: MessageBlock): boolean {
  const mediaType = String(block.payload?.media_type ?? block.payload?.mediaType ?? '').trim()
  if (mediaType === 'image_analysis') {
    return Boolean(
      textPayload(block)
      || hasToolIdentity(block)
      || isNonEmptyValue(block.payload?.result)
      || isNonEmptyValue(block.payload?.analysis)
    )
  }

  const result = block.payload?.result && typeof block.payload.result === 'object'
    ? block.payload.result as Record<string, unknown>
    : null

  return [
    mediaType,
    block.payload?.result_url,
    block.payload?.resultUrl,
    result?.result_url,
    result?.resultUrl,
    block.payload?.artifact_ref,
    block.payload?.artifactRef,
    result?.artifact_ref,
    result?.artifactRef,
    block.payload?.task_id,
    block.payload?.taskId,
    result?.task_id,
    result?.taskId,
    block.payload?.prompt,
    result?.prompt,
    block.payload?.canvas_item,
    block.payload?.canvasItem,
    result?.canvas_item,
    result?.canvasItem,
    block.payload?.result,
  ].some(isNonEmptyValue)
}

function hasRenderableWebSearch(block: MessageBlock): boolean {
  const result = block.payload?.result && typeof block.payload.result === 'object'
    ? block.payload.result as Record<string, unknown>
    : null

  return [
    block.payload?.query,
    block.payload?.message,
    block.payload?.summary,
    block.payload?.search_type,
    block.payload?.searchType,
    block.payload?.results,
    block.payload?.ui_results,
    result?.query,
    result?.message,
    result?.summary,
    result?.search_type,
    result?.searchType,
    result?.results,
    result?.ui_results,
  ].some(isNonEmptyValue)
}

export function hasRenderableMessageBlock(block: MessageBlock): boolean {
  if (!block || block.visible === false || block.uiKind === 'hidden_tool') {
    return false
  }

  if (block.children?.some(hasRenderableMessageBlock)) {
    return true
  }

  const uiKind = String(block.uiKind || '')
  if (uiKind === 'text' || uiKind === 'assistant_text' || uiKind === 'assistant_final_answer' || block.kind === 'text') {
    return Boolean(textPayload(block))
  }

  if (uiKind === 'choice_prompt' || uiKind === 'interaction_form' || block.kind === 'interaction') {
    return hasRenderableInteraction(block)
  }

  if (uiKind === 'media_card' || uiKind === 'generation_task') {
    return hasRenderableMedia(block)
  }

  if (uiKind === 'web_search_card') {
    return hasRenderableWebSearch(block)
  }

  if (uiKind === 'stream_panel') {
    return Boolean(textPayload(block)) || hasToolIdentity(block)
  }

  if (uiKind === 'progress_update') {
    // The progress renderer only displays payload.text, so a text-less progress block is
    // not actually renderable. Keep this in sync with the renderer's empty-text guard so a
    // message whose only block is an empty progress update is dropped (no blank bubble).
    return Boolean(String(block.payload?.text || '').trim())
  }

  if (
    uiKind === 'compact_tool'
    || uiKind === 'tool_call'
    || uiKind === 'tool_result'
    || block.kind === 'tool'
  ) {
    return hasToolIdentity(block) || Boolean(textPayload(block))
  }

  if (uiKind === 'plan_artifact' || uiKind === 'user_plan_card') {
    return Boolean(
      String(block.payload?.title || block.payload?.summary || block.payload?.status || '').trim()
      || Array.isArray(block.payload?.steps)
      || Array.isArray(block.payload?.items),
    )
  }

  if (uiKind === 'subagent_card' || uiKind === 'error_card') {
    return Object.keys(block.payload || {}).length > 0
  }

  return Object.keys(block.payload || {}).length > 0
}

function hasRenderableToolCall(toolCall: ToolCallInfo): boolean {
  return Boolean(
    String(toolCall.name || '').trim()
    || String(toolCall.streamingText || '').trim()
    || Object.keys(toolCall.result || {}).length > 0
    || Object.keys(toolCall.args || {}).length > 0
    || String(toolCall.error || '').trim(),
  )
}

export function hasRenderableChatMessage(message: ChatMessage): boolean {
  if (String(message.content || '').trim()) {
    return true
  }
  if (message.attachments?.length) {
    return true
  }
  if (message.toolCalls?.some(hasRenderableToolCall)) {
    return true
  }
  return Boolean(message.blocks?.some(hasRenderableMessageBlock))
}
