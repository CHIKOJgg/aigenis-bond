import { test, expect } from '@playwright/test';
import { mockLiveDemoApi } from './live-demo';

test.describe('demo visual regression (6.4)', () => {
  test('Торги', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/trading');
    await expect(page.getByText('Источник:')).toBeVisible();
    await expect(page).toHaveScreenshot(`trading-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Аналитика облигаций', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/analytics?market=BCSE');
    await expect(page.getByRole('heading', { name: 'Аналитика облигаций' })).toBeVisible();
    await expect(page).toHaveScreenshot(`analytics-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Drawer облигации', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/analytics?market=BCSE');
    await page.locator('table').getByRole('button', { name: 'Открыть' }).first().click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page).toHaveScreenshot(`drawer-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Влияние на портфель', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/portfolio-impact/demo-bond-001?market=BCSE');
    await expect(page.getByRole('heading', { name: /Влияние на портфель/ })).toBeVisible();
    await expect(page).toHaveScreenshot(`impact-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Институциональный Desk', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/desk?market=BCSE');
    await expect(page.getByRole('heading', { name: /Институциональный Desk/ })).toBeVisible();
    await expect(page.getByText('Кривая доходности BYN')).toBeVisible();
    await expect(page).toHaveScreenshot(`desk-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Стресс-тестирование', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/stress?market=BCSE');
    await expect(page.getByRole('heading', { name: /Стресс-Тестирование/ })).toBeVisible();
    await expect(page.getByText('Загрузка данных...')).toBeHidden();
    await expect(page.getByText('Активный сценарий:')).toBeVisible();
    await expect(page).toHaveScreenshot(`stress-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Оптимизатор портфеля', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/optimizer?market=BCSE');
    await expect(page.getByRole('heading', { name: /Оптимизатор Портфеля/ })).toBeVisible();
    await expect(page.getByText('Загрузка данных...')).toBeHidden();
    await expect(page).toHaveScreenshot(`optimizer-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Поиск облигаций', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/search?q=Минфин');
    await expect(page.getByRole('heading', { name: 'Поиск облигаций' })).toBeVisible();
    await expect(page.getByText(/Найдено бумаг:/)).toBeVisible();
    await expect(page).toHaveScreenshot(`search-${testInfo.project.name}.png`, { fullPage: true });
  });

  test('Portfolio Lab', async ({ page }, testInfo) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/portfolio-lab?market=BCSE');
    await expect(page.getByRole('heading', { name: /Лаборатория Портфелей/ })).toBeVisible();
    await expect(page.getByText('Мой портфель (демо-пользователь)')).toBeVisible();
    await expect(page.getByText('Загрузка портфеля пользователя...')).toBeHidden();
    await expect(page).toHaveScreenshot(`portfolio-lab-${testInfo.project.name}.png`, { fullPage: true });
  });
});
