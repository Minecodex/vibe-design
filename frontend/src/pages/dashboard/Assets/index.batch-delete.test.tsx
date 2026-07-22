import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, test } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')

describe('AssetsPage batch delete flow', () => {
  test('opens a confirmation dialog before executing batch delete', () => {
    expect(source).toContain("setIsBatchDeleteDialogOpen(true)")
    expect(source).toContain("<DeleteAssetsConfirmDialog")
    expect(source).toContain("variant=\"batch\"")
    expect(source).toContain("onConfirm={() => void handleBatchAction('delete')}")
  })
})
