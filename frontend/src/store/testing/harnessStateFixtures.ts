import { AxiosHeaders, type AxiosResponse } from 'axios'
import { agentApi, type HarnessConversationDetailRead, type HarnessRuntimeStateRead, type WorkspaceFileRead } from '@/api/endpoints/agent'
import { createEmptyConversationSession, type ConversationSessionState } from '../canvasAgentSession'

export function httpResponse<T>(value: { data: T }): AxiosResponse<T, unknown> {
  return { status: 200, statusText: 'OK', headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() }, ...value }
}

export function conversationDetail(overrides: Partial<HarnessConversationDetailRead>): HarnessConversationDetailRead {
  return {
    id: 'fixture-conversation', title: 'Fixture', skill_id: null, phase: 'discovery', mode: 'fast',
    status: 'active', runtime_status: 'idle', engine_version: 'harness', run_id: null,
    started_at: null, finished_at: null, created_at: '2026-05-01T00:00:00.000Z',
    updated_at: '2026-05-01T00:00:00.000Z', messages: [], ...overrides,
  }
}

export function runtimeState(overrides: Partial<HarnessRuntimeStateRead>): HarnessRuntimeStateRead {
  return { conversation_id: '', phase: '', run_status: '', ...overrides }
}

export function conversationSession(overrides: Partial<ConversationSessionState>): ConversationSessionState {
  return { ...createEmptyConversationSession(), ...overrides }
}

type ArtifactTask = Awaited<ReturnType<typeof agentApi.getHarnessGenerationArtifactTask>>['data']
export function artifactTask(overrides: Partial<ArtifactTask>): ArtifactTask {
  return { task_id: 'fixture-task', status: 'processing', result_url: null, error_message: null, ...overrides }
}

export function workspaceFile(overrides: Partial<WorkspaceFileRead>): WorkspaceFileRead {
  return { file_id: 'fixture-file', name: 'Fixture', path: 'references/inputs/fixture/file.txt',
    type: 'file', size: 0, created_at: '2026-05-01T00:00:00.000Z', ...overrides }
}
