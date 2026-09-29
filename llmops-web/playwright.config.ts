import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  workers: 4,
  use: {
    baseURL: 'http://127.0.0.1:5179',
    headless: true,
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm build && pnpm preview --host 127.0.0.1 --port 5179 --strictPort',
    url: 'http://127.0.0.1:5179',
    reuseExistingServer: false,
    timeout: 120000,
  },
  reporter: 'list',
  timeout: 30000,
})
