import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'MessageList.tsx'), 'utf8')

describe('MessageList replay guards', () => {
  it('waits for canvas meta to load before replaying completed generated media', () => {
    expect(source).toContain('canReplayCompletedMedia')
    expect(source).toContain('!canReplayCompletedMedia')
  })

  it('skips replaying completed generated media that the user deleted from the canvas', () => {
    expect(source).toContain('hasDeletedAgentMediaKey')
    expect(source).toContain('deletedAgentMediaKeys')
  })
})
