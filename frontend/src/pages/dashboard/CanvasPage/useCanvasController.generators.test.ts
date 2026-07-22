import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasController.generators.ts'),
  'utf8',
)

describe('useCanvasController generators binding flow', () => {
  it('persists a dedicated binding_task state before task ids exist', () => {
    expect(source).toContain("status: 'binding_task'")
    expect(source).toContain('binding_started_at')
  })

  it('recovers unresolved placeholders by client_request_id after reload', () => {
    expect(source).toContain('generationApi.recoverTasks')
    expect(source).toContain('client_request_id')
  })

  it('guards generator handlers against repeated clicks while a submission is already in flight', () => {
    expect(source).toContain('isGenerationTaskPendingStatus(item.status)')
    expect(source).toContain('anchoredImageSubmittingRef.current')
    expect(source).toContain('anchoredVideoSubmittingRef.current')
  })

  it('skips balance guards for Ollama image and video generator providers', () => {
    expect(source).toContain("import { ensureBalanceOrNotify, isBalanceRequiredForProvider } from '@/utils/balanceGuard'")
    expect(source).toContain('const requiresBalance = isBalanceRequiredForProvider(providerCode)')
    expect(source).toContain('if (requiresBalance && !ensureBalanceOrNotify(user?.balance_cents, t)) return false')
    expect(source).toContain('if (!ensureProviderPaidActionAllowed(item.provider_code || imageProvider)) return')
    expect(source).toContain('if (!ensureProviderPaidActionAllowed(imageAnchoredImageDraft.provider_code || imageProvider)) return')
    expect(source).toContain('if (!ensureProviderPaidActionAllowed(item.provider_code || videoProvider)) return')
    expect(source).toContain('if (!ensureProviderPaidActionAllowed(imageAnchoredVideoDraft.provider_code || videoProvider)) return')
    expect(source).toContain('if (!ensureProviderPaidActionAllowed(retryProviderCode)) return')
  })
})
