import { createTranslationFixture } from '@/store/testing/translationFixture'
import { describe, expect, it } from 'vitest'

import {
  getHomeToolActionLabel,
  isHomeReadonlyTool,
  summarizeToolArgs,
} from './homeToolDisplay'

const t = createTranslationFixture({})

describe('summarizeToolArgs', () => {
  it('summarizes file tools as their (relative) path', () => {
    expect(summarizeToolArgs('write_file', { path: 'report.md' })).toBe('report.md')
    expect(summarizeToolArgs('edit_file', { file_path: './src/a.ts' })).toBe('src/a.ts')
    expect(summarizeToolArgs('list_files', { path: 'src/' })).toBe('src/')
  })

  it('appends a line range for read_file when offset/limit are present', () => {
    expect(summarizeToolArgs('read_file', { path: 'a.ts' })).toBe('a.ts')
    expect(summarizeToolArgs('read_file', { path: 'a.ts', offset: 10, limit: 5 })).toBe('a.ts · 10-14')
  })

  it('formats glob/grep as pattern, optionally with path', () => {
    expect(summarizeToolArgs('grep_files', { pattern: 'TODO' })).toBe('pattern: "TODO"')
    expect(summarizeToolArgs('glob_files', { pattern: '**/*.ts', path: 'src' })).toBe(
      'pattern: "**/*.ts", path: "src"',
    )
  })

  it('truncates bash commands to 2 lines / 160 chars with an ellipsis', () => {
    expect(summarizeToolArgs('exec_command', { command: 'pytest -q' })).toBe('pytest -q')

    const multiline = summarizeToolArgs('exec_command', { command: 'a\nb\nc\nd' })
    expect(multiline).toBe('a\nb…')

    const long = 'x'.repeat(200)
    const truncated = summarizeToolArgs('bash', { command: long })
    expect(truncated.endsWith('…')).toBe(true)
    expect(truncated.length).toBeLessThanOrEqual(161)
  })

  it('returns the url for fetch_webpage and empty for unknown tools', () => {
    expect(summarizeToolArgs('fetch_webpage', { url: 'https://example.com' })).toBe('https://example.com')
    expect(summarizeToolArgs('some_other_tool', { foo: 'bar' })).toBe('')
  })
})

describe('isHomeReadonlyTool', () => {
  it('treats read/search/fetch tools as readonly and write/exec as not', () => {
    expect(isHomeReadonlyTool('read_file')).toBe(true)
    expect(isHomeReadonlyTool('grep_files')).toBe(true)
    expect(isHomeReadonlyTool('lc_fetch_webpage')).toBe(true)
    expect(isHomeReadonlyTool('write_file')).toBe(false)
    expect(isHomeReadonlyTool('exec_command')).toBe(false)
  })
})

describe('getHomeToolActionLabel', () => {
  it('maps known tools to localized action verbs', () => {
    expect(getHomeToolActionLabel('read_file', t)).toBe('读取')
    expect(getHomeToolActionLabel('exec_command', t)).toBe('执行命令')
    expect(getHomeToolActionLabel('Bash', t)).toBe('执行命令')
  })
})
