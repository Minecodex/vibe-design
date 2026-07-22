// @vitest-environment node

import { describe, expect, it } from 'vitest'

import {
  getPromptExtractorPackagingPlan,
  getPromptExtractorRuntimeIntro,
  getPromptExtractorRuntimeDefine,
  resolvePromptExtractorDefaultServer,
} from '../scripts/package-extension'

describe('prompt extractor packaging', () => {
  it('publishes a versioned zip into the frontend static downloads directory', () => {
    const plan = getPromptExtractorPackagingPlan('D:/workspace/py/ai-code/.worktrees/harness/prompt-extractor-extension/frontend')

    expect(plan.zipFileName).toBe('提取插件.zip')
    expect(plan.versionedReleaseDir.replace(/\\/g, '/')).toContain('/public/downloads/prompt-extractor/v1.0.2')
    expect(plan.latestReleaseDir.replace(/\\/g, '/')).toContain('/public/downloads/prompt-extractor/latest')
    expect(plan.versionedZipPath.replace(/\\/g, '/')).toContain('/public/downloads/prompt-extractor/v1.0.2/')
    expect(plan.latestZipPath.replace(/\\/g, '/')).toContain('/public/downloads/prompt-extractor/latest/')
  })

  it('forces browser-safe production defines for packaged runtime bundles', () => {
    const define = getPromptExtractorRuntimeDefine('https://example.com')

    expect(define.__PROMPT_EXTRACTOR_DEFAULT_SERVER__).toBe(JSON.stringify('https://example.com'))
    expect(define['process.env.NODE_ENV']).toBe(JSON.stringify('production'))
  })

  it('injects a production process shim for browser extension pages', () => {
    expect(getPromptExtractorRuntimeIntro()).toContain('process')
    expect(getPromptExtractorRuntimeIntro()).toContain("NODE_ENV: 'production'")
  })

  it('uses APP_API_BASE_URL as the packaged default server origin when a plugin-specific server is not set', () => {
    expect(resolvePromptExtractorDefaultServer({
      APP_API_BASE_URL: 'http://localhost:8000/api/v1',
    })).toBe('http://localhost:8000')
    expect(resolvePromptExtractorDefaultServer({
      APP_API_BASE_URL: 'http://localhost:8000',
    })).toBe('http://localhost:8000')
  })
})
