import { defineConfig, devices } from '@playwright/test';

const viewports = [
  { name: 'desktop-1366', width: 1366, height: 768 },
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'desktop-1024', width: 1024, height: 768 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'mobile-390', width: 390, height: 844 },
];

const browsers = [
  { suffix: '', browser: 'chromium' as const, device: 'Desktop Chrome' },
  { suffix: '-firefox', browser: 'firefox' as const, device: 'Desktop Firefox' },
  { suffix: '-webkit', browser: 'webkit' as const, device: 'Desktop Safari' },
];

export default defineConfig({
  testDir: './e2e',
  testMatch: /\.visual\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
    },
  },
  use: {
    baseURL: 'http://127.0.0.1:4173',
  },
  projects: viewports.flatMap((v) =>
    browsers.map((b) => ({
      name: `${v.name}${b.suffix}`,
      use: {
        ...devices[b.device],
        viewport: { width: v.width, height: v.height },
        browserName: b.browser,
      },
    })),
  ),
  webServer: {
    command: 'npm run build && npm run preview -- --port 4173 --strictPort --host 127.0.0.1',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
