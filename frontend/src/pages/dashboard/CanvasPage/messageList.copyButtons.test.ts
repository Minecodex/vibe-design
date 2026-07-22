import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'MessageList.tsx'), 'utf8')

describe('MessageList copy buttons', () => {
  it('keeps a copy button on top-level message content', () => {
    expect(source).toContain('<CopyButton text={message.content} isDark={isDark} isUser={isUser} />')
  })

  it('adds copy buttons to assistant text blocks and analysis text blocks', () => {
    expect(source).toContain("<div className=\"group relative\" style={{ maxWidth: '85%' }}>")
    expect(source).toContain('<CopyButton text={text} isDark={isDark} isUser={false} />')
    expect(source).toContain('<CopyButton text={streamingText} isDark={isDark} isUser={false} />')
    expect(source).toContain('<CopyButton text={analysisResult} isDark={isDark} isUser={false} />')
  })
})
