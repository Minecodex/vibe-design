import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const localesDir = resolve(currentDir, '..', '..', '..', 'i18n', 'locales')

const zhCN = JSON.parse(readFileSync(resolve(localesDir, 'zh-CN.json'), 'utf8'))
const enUS = JSON.parse(readFileSync(resolve(localesDir, 'en-US.json'), 'utf8'))

describe('Canvas text redraw i18n resources', () => {
  it('defines localized copy for text redraw status and panel labels', () => {
    expect(zhCN.canvas?.text_redraw).toEqual({
      extracting: '提取文字中',
      detect_result: '识别结果',
      no_text_found: '未检测到可编辑文字',
      segment_label: '文字',
      submit: '确认重绘',
    })

    expect(enUS.canvas?.text_redraw).toEqual({
      extracting: 'Extracting text',
      detect_result: 'Detected text',
      no_text_found: 'No editable text detected',
      segment_label: 'Text',
      submit: 'Apply redraw',
    })
  })
})
