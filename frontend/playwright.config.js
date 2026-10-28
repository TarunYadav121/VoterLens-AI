import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 5'] } },
  ],
  webServer: [
    {
      command: './venv/bin/python -m flask --app app run --host 127.0.0.1 --port 5053 --no-debugger --no-reload',
      cwd: '../backend',
      url: 'http://127.0.0.1:5053/api/health',
      reuseExistingServer: false,
      timeout: 30_000,
      env: { ALLOWED_ORIGINS: 'http://127.0.0.1:4173' },
    },
    {
      command: 'VITE_API_BASE_URL=http://127.0.0.1:5053 npm run dev -- --host 127.0.0.1 --port 4173',
      cwd: '.',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
