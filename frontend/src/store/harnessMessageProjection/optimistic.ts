import type { PresentationOpEvent } from './types'

interface OptimisticInteractionSubmissionArgs {
  requestId: string
  answer: unknown
  answers?: Record<string, unknown> | null
  displayLabel?: string | null
  approved?: boolean | null
  kind?: string | null
}

export function optimisticInteractionSubmissionOps(
  args: OptimisticInteractionSubmissionArgs,
): PresentationOpEvent[] {
  const requestId = String(args.requestId || '').trim()
  if (!requestId) {
    return []
  }
  const submittedLabel = String(args.displayLabel ?? args.answer ?? '').trim()
  const submittedAnswer = String(args.answer ?? '').trim()
  const bubbleContent = submittedLabel || submittedAnswer
  const tempMessageKey = `temp-${Date.now()}`
  const opNonce = `${tempMessageKey}:${Math.random().toString(36).slice(2)}`
  const submissionMetadata = {
    request_id: requestId,
    kind: args.kind || null,
    answer: args.answer,
    display_label: submittedLabel || null,
    approved: args.approved ?? null,
    answers: args.answers || {},
    source: 'optimistic_interaction_submitted',
  }

  return [
    {
      type: 'presentation.block.patch',
      source_sequence: 0,
      op_id: `optimistic:interaction-submitted:${requestId}:${opNonce}`,
      data: {
        message_key: `interaction:${requestId}`,
        block_key: `interaction-form:${requestId}`,
        status: 'submitted',
        requires_existing_message: true,
        revision: 0,
        payload: {
          status: 'submitted',
          payload: {
            status: 'submitted',
            answers: args.answers || null,
            submitted_label: submittedLabel || undefined,
            submittedLabel: submittedLabel || undefined,
            submitted_answer: submittedAnswer || undefined,
            submittedAnswer: submittedAnswer || undefined,
          },
        },
      },
    },
    {
      type: 'presentation.message.upsert',
      source_sequence: 0,
      op_id: `optimistic:user-message:${requestId}:${opNonce}`,
      data: {
        message_key: tempMessageKey,
        block_key: `message:${tempMessageKey}`,
        role: 'user',
        status: 'completed',
        content: bubbleContent,
        revision: 0,
        payload: {
          content: bubbleContent,
          blocks: [],
          attachments: [],
          metadata: submissionMetadata,
        },
      },
    },
  ]
}
