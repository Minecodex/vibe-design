import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { findExistingAgentGeneratedMedia } from './agentGeneratedMedia'

describe('findExistingAgentGeneratedMedia', () => {
  it('matches an existing placeholder by stable agent media key', () => {
    const existing: CanvasItem[] = [
      {
        id: 'placeholder-1',
        type: 'image_generator',
        url: '',
        x: 10,
        y: 20,
        agent_media_key: 'media-key-1',
      },
    ]

    const match = findExistingAgentGeneratedMedia(existing, {
      id: 'completed-1',
      task_id: 88,
      agentMediaKey: 'media-key-1',
    })

    expect(match?.id).toBe('placeholder-1')
  })

  it('falls back to task id matching when the media key is absent', () => {
    const existing: CanvasItem[] = [
      {
        id: 'placeholder-2',
        type: 'video_generator',
        url: '',
        x: 10,
        y: 20,
        task_id: 99,
      },
    ]

    const match = findExistingAgentGeneratedMedia(existing, {
      id: 'completed-2',
      task_id: 99,
    })

    expect(match?.id).toBe('placeholder-2')
  })

  it('matches string task ids from harness generation placeholders', () => {
    const existing: CanvasItem[] = [
      {
        id: 'placeholder-string-task',
        type: 'image_generator',
        url: '',
        x: 10,
        y: 20,
        task_id: 'image-task-1',
      },
    ]

    const match = findExistingAgentGeneratedMedia(existing, {
      id: 'completed-string-task',
      task_id: 'image-task-1',
    })

    expect(match?.id).toBe('placeholder-string-task')
  })

  it('matches by artifact ref when ids differ between started and completed events', () => {
    const existing: CanvasItem[] = [
      {
        id: 'agent-generated-artifact_ref-image-1',
        type: 'image_generator',
        url: '',
        x: 10,
        y: 20,
        artifact_ref: 'artifact_ref:image-1',
      },
    ]

    const match = findExistingAgentGeneratedMedia(existing, {
      id: 'artifact_ref:image-1',
      artifact_ref: 'artifact_ref:image-1',
    })

    expect(match?.id).toBe('agent-generated-artifact_ref-image-1')
  })

  it('returns no match when neither key nor task id identifies an existing media item', () => {
    const existing: CanvasItem[] = [
      {
        id: 'placeholder-3',
        type: 'image_generator',
        url: '',
        x: 10,
        y: 20,
        agent_media_key: 'media-key-3',
        task_id: 100,
      },
    ]

    const match = findExistingAgentGeneratedMedia(existing, {
      id: 'completed-3',
      task_id: 101,
      agentMediaKey: 'media-key-other',
    })

    expect(match).toBeUndefined()
  })
})
