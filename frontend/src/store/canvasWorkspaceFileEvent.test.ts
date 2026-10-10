import { beforeEach, describe, expect, it } from 'vitest'
import type { AgentEvent } from '@/api/endpoints/agent'
import { useChatStore } from './canvasAgentStore'
import { handleAgentEventV2 } from './canvasAgentEventHandler'

function receive(data: AgentEvent['data'], type: 'file_created' | 'file_updated' = 'file_created') {
  handleAgentEventV2({ type, data }, useChatStore.setState, useChatStore.getState)
}

describe('workspace file stream events', () => {
  beforeEach(() => useChatStore.getState().reset())

  it('updates the same file in global chat without creating duplicate entries', () => {
    receive({ file_path: 'draft/report.html', type: 'html', size: 10 })
    receive({ file_path: 'draft/report.html', type: 'html', size: 20 }, 'file_updated')
    expect(useChatStore.getState().workspaceFiles).toEqual([
      expect.objectContaining({ name: 'report.html', path: 'draft/report.html', type: 'html', size: 20 }),
    ])
  })

  it('ignores malformed file paths while keeping the stream able to accept the next event', () => {
    receive({ file_path: { name: 'invalid' }, type: 'html', size: 10 })
    receive({ file_path: null })
    expect(useChatStore.getState().workspaceFiles).toEqual([])
    receive({ file_path: 'next.txt', type: {}, size: 'not a number' })
    expect(useChatStore.getState().workspaceFiles).toEqual([
      expect.objectContaining({ path: 'next.txt', type: 'other', size: 0 }),
    ])
  })

  it('projects file updates into the active conversation session', () => {
    useChatStore.setState({ conversationId: 'files-session' })
    receive({ file_path: 'scoped.txt', type: 'text', size: 3 })
    expect(useChatStore.getState().conversationSessions['files-session'].workspaceFiles).toEqual([
      expect.objectContaining({ path: 'scoped.txt', size: 3 }),
    ])
  })
})
