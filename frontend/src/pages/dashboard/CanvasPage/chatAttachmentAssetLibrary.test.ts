import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')

describe('CanvasPage chat attachment asset library wiring', () => {
  it('uses multi-select when opening the asset library for chat attachments', () => {
    expect(source).toContain("onOpenAttachmentLibrary={() => openGeneratorAssetLibrary({ type: 'chat-attachment' })}")
    expect(source).toContain("if (generatorAssetLibraryContext.type === 'chat-attachment') {\r\n      return { selectionMode: 'multiple' as const }\r\n    }")
  })
})
