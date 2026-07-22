import { describe, expect, it } from 'vitest'

import {
  getAgentMessageRenderWeight,
  getAgentRenderWeightSnapshot,
  shouldVirtualizeAgentItems,
} from './agentRenderWeight'

describe('agentRenderWeight', () => {
  it('assigns low weight to plain text and higher weight to rich media history', () => {
    const plainWeight = getAgentMessageRenderWeight({ content: 'hello', blocks: [] })
    const richWeight = getAgentMessageRenderWeight({
      content: '![image](references/generated/item/original.png)',
      attachments: [{ type: 'image' }],
      blocks: [
        {
          uiKind: 'generation_task',
          payload: { media_type: 'image', text: '`generation-artifact:abc`' },
        },
      ],
    })

    expect(plainWeight).toBeLessThan(5)
    expect(richWeight).toBeGreaterThan(15)
  })

  it('virtualizes when render weight crosses the rich-media threshold', () => {
    const snapshot = getAgentRenderWeightSnapshot(Array.from({ length: 8 }, (_, index) => ({
      id: index,
      blocks: [{ uiKind: 'media_card', payload: { media_type: 'image' } }],
    })))

    expect(snapshot.totalWeight).toBeGreaterThanOrEqual(40)
    expect(shouldVirtualizeAgentItems(snapshot, { itemThreshold: 30, weightThreshold: 40 })).toBe(true)
  })
})
