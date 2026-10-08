import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'hooks/useChatSidebar.ts'), 'utf8')
const modelHelpersSource = readFileSync(resolve(currentDir, 'chatSidebarModelHelpers.ts'), 'utf8')

describe('ChatSidebar billing guard wiring', () => {
  it('checks balance before sending paid-provider chat requests', () => {
    expect(source).toContain('isBalanceRequiredForMultimodalProvider(modelPreferences.multimodal_provider)')
    expect(source).toContain("if (requiresBalance && !ensureBalanceOrNotify(user?.balance_cents, t)) return")
    expect(source).toContain('if (requiresBalance && currentBalanceCents <= 0)')
    expect(source).toContain('await sendMessage(content, atts, { references })')
    expect(source).toContain('await sendMessage(content, atts)')
  })

  it('defaults the chat video model picker to kling-v3 when available', () => {
    expect(source).toContain('resolveCanvasModelPreferences(')
    expect(modelHelpersSource).toContain("catalogs.videoModels.find(model => model.value === 'kling-v3') || catalogs.videoModels[0]")
  })

  it('localizes builtin provider names through the shared brand helper', () => {
    expect(source).toContain('resolveLocalizedProviderName(')
    expect(source).toContain("provider.code === 'builtin'")
  })

  it('supports appending unique image mentions from the canvas into the end of the composer', () => {
    expect(source).toContain('appendMentionRequest')
    expect(source).toContain('appendMentionToEnd')
    expect(source).toContain('querySelector(`[data-mention-id="${ci.id}"]`)')
    expect(source).toContain('getAppendMentionInsertionPoint(editorEl)')
    expect(source).toContain('moveCursorAfterNode(lastInsertedNode)')
  })
})


