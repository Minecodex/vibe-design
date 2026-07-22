import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import zhCN from './locales/zh-CN.json'

describe('canvas image Chinese labels', () => {
  it('keeps the image generation labels readable in zh-CN and source fallbacks', () => {
    const currentDir = dirname(fileURLToPath(import.meta.url))
    const canvasWorkspaceSource = readFileSync(
      resolve(currentDir, '../pages/dashboard/CanvasPage/components/CanvasWorkspace.tsx'),
      'utf8',
    )
    const messageListSource = readFileSync(
      resolve(currentDir, '../pages/dashboard/CanvasPage/MessageList.tsx'),
      'utf8',
    )

    expect(zhCN.canvas.chat.tool_tips.gen_image).toBe('生成图片')
    expect(zhCN.canvas.chat.tool_labels.generate_image).toBe('生成图片')
    expect(canvasWorkspaceSource).toContain("t('canvas.chat.tool_tips.gen_image', '生成图片')")
    expect(messageListSource).toContain("t('canvas.chat.tool_labels.generate_image', '生成图片')")
  })
})
