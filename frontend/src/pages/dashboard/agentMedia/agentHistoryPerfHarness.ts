import {
  getAgentRenderWeightSnapshot,
  shouldVirtualizeAgentItems,
} from './agentRenderWeight'

type PerfHarnessMessage = {
  id: string
  content: string
  attachments?: Array<Record<string, unknown>>
  blocks: Array<{ id: string; uiKind: string; status: string; payload: Record<string, unknown> }>
}

export interface AgentHistoryPerfHarnessResult {
  messageCount: number
  estimatedImageNodesWithoutOptimization: number
  estimatedMountedRowsWithVirtualization: number
  renderWeight: number
  shouldVirtualize: boolean
}

export function createAgentHistoryPerfHarnessMessages(messageCount: number): PerfHarnessMessage[] {
  return Array.from({ length: messageCount }, (_, index) => {
    const blocks: PerfHarnessMessage['blocks'] = []
    const attachments: PerfHarnessMessage['attachments'] = []
    let content = `Message ${index}`
    if (index % 5 === 0) {
      content += `\n![sample](references/generated/generated_image_${index}/original.png)`
      attachments.push({ type: 'image', url: `references/inputs/upload_${index}/source.png` })
    }
    if (index % 20 === 0) {
      blocks.push({
        id: `generation-${index}`,
        uiKind: 'generation_task',
        status: 'completed',
        payload: {
          status: 'completed',
          media_type: 'image',
          result_url: `references/generated/generated_image_${index}/original.png`,
        },
      })
    }
    if (index % 50 === 0) {
      blocks.push({
        id: `video-${index}`,
        uiKind: 'media_card',
        status: 'completed',
        payload: {
          status: 'completed',
          media_type: 'video',
          result_url: `references/generated/generated_video_${index}/original.mp4`,
        },
      })
    }
    return {
      id: `message-${index}`,
      content,
      attachments,
      blocks,
    }
  })
}

export function runAgentHistoryPerfHarness(messageCount: number): AgentHistoryPerfHarnessResult {
  const messages = createAgentHistoryPerfHarnessMessages(messageCount)
  const snapshot = getAgentRenderWeightSnapshot(messages)
  const estimatedImageNodesWithoutOptimization = messages.reduce((sum, message) => (
    sum
    + (message.content.includes('![') ? 1 : 0)
    + (message.attachments?.length || 0)
    + message.blocks.filter((block) => String(block.payload?.media_type || '') === 'image').length
  ), 0)
  return {
    messageCount,
    estimatedImageNodesWithoutOptimization,
    estimatedMountedRowsWithVirtualization: Math.min(messageCount, 18),
    renderWeight: snapshot.totalWeight,
    shouldVirtualize: shouldVirtualizeAgentItems(snapshot, {
      itemThreshold: 30,
      weightThreshold: 40,
    }),
  }
}
