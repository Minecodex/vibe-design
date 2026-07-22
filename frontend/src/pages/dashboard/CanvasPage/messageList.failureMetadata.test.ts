import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'MessageList.tsx'), 'utf8')

describe('MessageList generation failure metadata', () => {
  it('prefers persisted task params over request args for display metadata', () => {
    expect(source).toContain('result?.params?.aspect_ratio')
    expect(source).toContain('result?.params?.resolution')
    expect(source).toContain('result?.provider_code')
  })

  it('hydrates terminal tasks from the generation status API so failed cards can show real metadata', () => {
    expect(source).toContain('status === \'completed\' || status === \'failed\'')
    expect(source).toContain('generationApi.queryTask(taskId)')
    expect(source).toContain('task_snapshot_loaded')
  })
})
