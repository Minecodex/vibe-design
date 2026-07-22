import { beforeEach, describe, expect, it, vi } from 'vitest'

const { queryTaskMock, getHarnessGenerationTaskMock } = vi.hoisted(() => ({
  queryTaskMock: vi.fn(),
  getHarnessGenerationTaskMock: vi.fn(),
}))

vi.mock('@/api/endpoints/generation', () => ({
  generationApi: {
    queryTask: queryTaskMock,
  },
}))

vi.mock('@/api/endpoints/agent', () => ({
  agentApi: {
    getHarnessGenerationTask: getHarnessGenerationTaskMock,
  },
}))

import { fetchCanvasGenerationTaskSnapshot } from './generationTaskSnapshot'

describe('fetchCanvasGenerationTaskSnapshot', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses harness task status when a canvas item carries an agent conversation id', async () => {
    getHarnessGenerationTaskMock.mockResolvedValue({
      data: {
        task_id: '2076c19dd0e84b74b06f6d6810709331',
        status: 'processing',
      },
    })

    const response = await fetchCanvasGenerationTaskSnapshot({
      taskId: '2076c19dd0e84b74b06f6d6810709331',
      conversationId: '1778489817514_57f18c',
    })

    expect(getHarnessGenerationTaskMock).toHaveBeenCalledWith(
      '1778489817514_57f18c',
      '2076c19dd0e84b74b06f6d6810709331',
    )
    expect(queryTaskMock).not.toHaveBeenCalled()
    expect(response.data.status).toBe('processing')
  })

  it('falls back to the project generation endpoint for regular canvas tasks', async () => {
    queryTaskMock.mockResolvedValue({
      data: {
        id: 123,
        status: 'completed',
      },
    })

    const response = await fetchCanvasGenerationTaskSnapshot({
      taskId: 123,
      conversationId: null,
    })

    expect(queryTaskMock).toHaveBeenCalledWith(123)
    expect(getHarnessGenerationTaskMock).not.toHaveBeenCalled()
    expect(response.data.status).toBe('completed')
  })
})
