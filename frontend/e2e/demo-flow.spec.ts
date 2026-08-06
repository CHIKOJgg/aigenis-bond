import { test, expect, type Page } from '@playwright/test';

const SIDE_EFFECT_URL = /\/api\/|\/auth\/|\/orders|\/billing\/|\/webhook|\/payment|yookassa/i;

async function trackSideEffects(page: Page): Promise<string[]> {
  const offenders: string[] = [];
  page.on('request', (req) => {
    if (SIDE_EFFECT_URL.test(req.url())) {
      offenders.push(`${req.method()} ${req.url()}`);
    }
  });
  return offenders;
}

test.describe('demo smoke flow (6.3)', () => {
  test('Торги → Аналитика → фильтр → карточка → portfolio impact без side effects', async ({ page }) => {
    const offenders = await trackSideEffects(page);

    await page.goto('/demo/trading');
    await expect(page.getByRole('heading', { name: /Торги/ })).toBeVisible();

    await page.getByRole('main').getByRole('button', { name: /MOEX/ }).click();
    await page.goto('/demo/analytics?market=BCSE');

    await expect(page.getByRole('heading', { name: 'Аналитика облигаций' })).toBeVisible();

    const rowsBefore = await page.getByRole('row').count();
    expect(rowsBefore).toBeGreaterThan(1);

    await page.getByLabel('Статус').selectOption('attractive');
    const rowsAfter = await page.getByRole('row').count();
    expect(rowsAfter).toBeLessThan(rowsBefore);
    expect(rowsAfter).toBeGreaterThan(1);

    await page.getByRole('button', { name: 'Открыть' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/Эмитент:/)).toBeVisible();
    await expect(dialog.getByText(/Почему бумага в фокусе/)).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();

    await page.getByRole('button', { name: 'Открыть' }).first().click();
    await dialog.getByRole('button', { name: 'Влияние на портфель' }).click();

    await expect(page).toHaveURL(/\/demo\/portfolio-impact\//);
    await expect(page.getByRole('heading', { name: /Влияние на портфель/ })).toBeVisible();

    await page.getByRole('button', { name: /10%/ }).click();
    await expect(page.getByText(/Изменение допустимо/)).toBeVisible();

    await expect(page.getByText(/Концепт пилотной интеграции/)).toBeVisible();
    expect(offenders).toEqual([]);
  });

  test('демо-страницы не делают сетевых запросов к API', async ({ page }) => {
    const offenders = await trackSideEffects(page);
    for (const path of ['/demo/trading', '/demo/analytics?market=BCSE', '/demo/analytics?market=MOEX']) {
      await page.goto(path);
      await expect(page.locator('body')).not.toHaveText('502 Bad Gateway');
    }
    expect(offenders).toEqual([]);
  });

  test('market selection сохраняется в URL при навигации', async ({ page }) => {
    await page.goto('/demo/trading');
    await page.getByRole('main').getByRole('button', { name: /MOEX/ }).click();
    await expect(page).toHaveURL(/market=MOEX/);
  });
});
