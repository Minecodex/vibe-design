import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import enUS from '@/i18n/locales/en-US.json'
import zhCN from '@/i18n/locales/zh-CN.json'

const currentDir = dirname(fileURLToPath(import.meta.url))
const toolDefinitionsSource = readFileSync(resolve(currentDir, 'canvasToolDefinitions.tsx'), 'utf8')
const workspaceSource = readFileSync(resolve(currentDir, 'components', 'CanvasWorkspace.tsx'), 'utf8')

describe('canvas text tool i18n', () => {
  it('provides readable English locale strings for the text toolbar', () => {
    expect(enUS.canvas.tools.text).toBe('Text')
    expect(enUS.canvas.text_toolbar.fill).toBe('Fill')
    expect(enUS.canvas.text_toolbar.stroke).toBe('Stroke')
    expect(enUS.canvas.text_toolbar.font).toBe('Font')
    expect(enUS.canvas.text_toolbar.variant).toBe('Style')
    expect(enUS.canvas.text_toolbar.size).toBe('Size')
    expect(enUS.canvas.text_toolbar.align).toBe('Align')
    expect(enUS.canvas.text_toolbar.more).toBe('More')
    expect(enUS.canvas.text_toolbar.vertical).toBe('Vertical')
  })

  it('provides readable Chinese locale strings for the text toolbar', () => {
    expect(zhCN.canvas.tools.text).toBe('文字')
    expect(zhCN.canvas.text_toolbar.fill).toBe('填充')
    expect(zhCN.canvas.text_toolbar.stroke).toBe('描边')
    expect(zhCN.canvas.text_toolbar.font).toBe('字体')
    expect(zhCN.canvas.text_toolbar.variant).toBe('字重')
    expect(zhCN.canvas.text_toolbar.size).toBe('字号')
    expect(zhCN.canvas.text_toolbar.align).toBe('对齐')
    expect(zhCN.canvas.text_toolbar.more).toBe('更多')
    expect(zhCN.canvas.text_toolbar.vertical).toBe('竖排')
  })

  it('keeps readable fallback copy in source for the new text controls', () => {
    expect(toolDefinitionsSource).toContain("t('canvas.tools.text', '文字')")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.fill'")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.stroke'")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.font'")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.variant'")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.size'")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.align'")
    expect(workspaceSource).toContain("t('canvas.text_toolbar.more'")
  })
})
