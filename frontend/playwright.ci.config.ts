import { defineConfig, devices } from '@playwright/test'

const profile = process.env.VIBE_E2E_PROFILE ?? 'pr'
if (!['pr', 'release'].includes(profile)) throw new Error(`Unknown browser E2E profile: ${profile}`)

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: profile === 'release' ? ['core.spec.ts', 'release.spec.ts'] : 'core.spec.ts',
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 60_000,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'zh-CN',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: process.env.VIBE_CI_PRODUCTION === 'true'
      ? 'npm run preview -- --host 127.0.0.1 --port 5173'
      : 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
