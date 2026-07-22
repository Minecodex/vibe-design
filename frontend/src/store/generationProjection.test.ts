import { describe, expect, it } from 'vitest'

import {
  applyGenerationProjectionUpdate,
  buildGenerationProjectionUpdateFromTaskSnapshot,
  createGenerationProjectionState,
} from './generationProjection'

describe('generationProjection', () => {
  it('does not let stale polling regress a newer completed event', () => {
    const completed = applyGenerationProjectionUpdate(createGenerationProjectionState(), {
      taskId: 42,
      status: 'completed',
      sourceSequence: 8,
      resultUrl: '/result.png',
      artifactId: 'artifact-1',
    }).state

    const stale = applyGenerationProjectionUpdate(completed, {
      taskId: 42,
      status: 'processing',
      sourceSequence: 4,
      progress: 40,
    }).state

    expect(stale.tasks['42'].status).toBe('completed')
    expect(stale.tasks['42'].resultUrl).toBe('/result.png')
  })

  it('emits a canvas insertion command at most once per task artifact', () => {
    const first = applyGenerationProjectionUpdate(createGenerationProjectionState(), {
      taskId: 'task-1',
      status: 'completed',
      sourceSequence: 2,
      resultUrl: '/result.png',
      artifactId: 'artifact-1',
    })
    const duplicate = applyGenerationProjectionUpdate(first.state, {
      taskId: 'task-1',
      status: 'completed',
      sourceSequence: 3,
      resultUrl: '/result.png',
      artifactId: 'artifact-1',
    })

    expect(first.canvasInsertion).toEqual({
      taskId: 'task-1',
      artifactId: 'artifact-1',
      resultUrl: '/result.png',
    })
    expect(duplicate.canvasInsertion).toBeUndefined()
  })

  it('normalizes polling task snapshots through the shared projection contract', () => {
    const update = buildGenerationProjectionUpdateFromTaskSnapshot({
      id: 77,
      status: 'running',
      progress: 41.7,
      result_url: '/generated/preview.png',
      artifact_ref: 'artifact_ref:77',
      error_message: null,
    })

    expect(update).toEqual({
      taskId: 77,
      status: 'running',
      sourceSequence: null,
      progress: 41.7,
      resultUrl: '/generated/preview.png',
      artifactId: 'artifact_ref:77',
      artifactRef: 'artifact_ref:77',
      errorMessage: null,
      source: 'poll',
    })

    const projected = applyGenerationProjectionUpdate(createGenerationProjectionState(), update!)

    expect(projected.state.tasks['77'].status).toBe('processing')
    expect(projected.state.tasks['77'].progress).toBe(42)
    expect(projected.state.tasks['77'].resultUrl).toBe('/generated/preview.png')
  })

  it('uses polling snapshots to fill missed terminal state without regressing newer events', () => {
    const missed = applyGenerationProjectionUpdate(
      createGenerationProjectionState(),
      buildGenerationProjectionUpdateFromTaskSnapshot({
        task_id: 'task-9',
        status: 'completed',
        progress: 100,
        artifact: {
          relative_path: 'generated/final.png',
          base_dir: 'FILES_DIR',
        },
        canvas_item: { id: 'canvas-asset-9' },
      })!,
    )

    expect(missed.state.tasks['task-9'].status).toBe('completed')
    expect(missed.state.tasks['task-9'].resultUrl).toBe('generated/final.png')
    expect(missed.canvasInsertion).toEqual({
      taskId: 'task-9',
      artifactId: 'canvas-asset-9',
      resultUrl: 'generated/final.png',
    })

    const stalePoll = applyGenerationProjectionUpdate(missed.state, {
      taskId: 'task-9',
      status: 'processing',
      source: 'poll',
      sourceSequence: null,
      progress: 20,
    })

    expect(stalePoll.state.tasks['task-9'].status).toBe('completed')
    expect(stalePoll.state.tasks['task-9'].resultUrl).toBe('generated/final.png')
  })
})
