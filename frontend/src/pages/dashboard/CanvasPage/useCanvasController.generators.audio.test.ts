import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'hooks', 'useCanvasController.generators.ts'), 'utf8')

describe('useCanvasController.generators audio payload wiring', () => {
  it('marks kling audio resolutions as audio-enabled video requests', () => {
    expect(source).toContain("audio: resolvedResolution.toLowerCase().endsWith('_audio')")
  })
})
