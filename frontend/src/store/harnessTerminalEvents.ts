export type HarnessRunStatus = 'idle' | 'running' | 'waiting_input' | 'completed' | 'failed' | 'blocked' | 'cancelled'

export function resolveHarnessTerminalRunStatus(runStatus: HarnessRunStatus): HarnessRunStatus {
  if (
    runStatus === 'failed'
    || runStatus === 'blocked'
    || runStatus === 'cancelled'
    || runStatus === 'waiting_input'
  ) {
    return runStatus
  }
  return 'completed'
}

export function isHarnessConversationTerminalStatus(status: HarnessRunStatus | null | undefined): boolean {
  return status === 'completed'
    || status === 'failed'
    || status === 'blocked'
    || status === 'cancelled'
}

export function isHarnessConversationActiveStatus(status: HarnessRunStatus | null | undefined): boolean {
  return status === 'running'
}
