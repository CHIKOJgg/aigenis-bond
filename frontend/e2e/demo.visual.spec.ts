import { test, expect } from '@playwright/test';

test.describe('demo visual regression (6.4)', () => {
  test('Торги', async ({ page }, testInfo) => {
    await page.goto('/demo/trading');
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveScreenshot(`trading-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Аналитика облигаций', async ({ page }, testInfo) => {
    await page.goto('/demo/analytics?market=BCSE');
    await expect(page.getByRole('heading', { name: 'Аналитика облигаций' })).toBeVisible();
    await expect(page).toHaveScreenshot(`analytics-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Drawer облигации', async ({ page }, testInfo) => {
    await page.goto('/demo/analytics?market=BCSE');
    await page.getByRole('button', { name: 'Открыть' }).first().click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page).toHaveScreenshot(`drawer-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Влияние на портфель', async ({ page }, testInfo) => {
    await page.goto('/demo/portfolio-impact/demo-bond-001?market=BCSE');
    await expect(page.getByRole('heading', { name: /Влияние на портфель/ })).toBeVisible();
    await expect(page).toHaveScreenshot(`impact-${testInfo.project.name}.png`, { fullPage: true });
  });
});
