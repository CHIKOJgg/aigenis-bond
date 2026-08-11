import { test, expect, type Page } from '@playwright/test';
import { mockLiveDemoApi } from './live-demo';

const SIDE_EFFECT_URL = /\/api\/(?!v1\/demo\/)|\/auth\/|\/orders|\/billing\/|\/webhook|\/payment|yookassa/i;

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
    await mockLiveDemoApi(page);
    const offenders = await trackSideEffects(page);

    await page.goto('/demo/trading');
    await expect(page.getByRole('heading', { name: /Торги/ })).toBeVisible();

    await page.getByRole('main').getByRole('button', { name: /MOEX/ }).click();
    await page.goto('/demo/analytics?market=BCSE');

    await expect(page.getByRole('heading', { name: 'Аналитика облигаций' })).toBeVisible();

    const rowsBefore = await page.getByRole('row').count();
    expect(rowsBefore).toBeGreaterThan(1);

    // Интерактивная карта возможностей: кружочки кликабельны, zoom-кнопки работают
    const chart = page.getByText('Карта возможностей рынка');
    await expect(chart).toBeVisible();
    const zoomInBtn = page.getByRole('button', { name: 'Увеличить' });
    const zoomOutBtn = page.getByRole('button', { name: 'Уменьшить' });
    await expect(zoomInBtn).toBeVisible();
    await zoomInBtn.click();
    await zoomOutBtn.click();

    const dots = page.locator('svg circle[role="button"]');
    const dotCount = await dots.count();
    expect(dotCount).toBeGreaterThan(0);
    await dots.first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/Эмитент:/)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();

    await page.getByRole('button', { name: 'Открыть' }).first().click();
    await dialog.getByRole('button', { name: 'Влияние на портфель' }).click();

    await expect(page).toHaveURL(/\/demo\/portfolio-impact\//);
    await expect(page.getByRole('heading', { name: /Влияние на портфель/ })).toBeVisible();
    await expect(page.getByText(/После добавления 10% позиции/)).toBeVisible();
    await expect(page.getByText(/5\s*000 BYN из портфеля 50\s*000 BYN/)).toBeVisible();
    await expect(page.getByText(/500\s*000 BYN/)).not.toBeVisible();

    const bondSearch = page.getByRole('combobox', { name: 'Поиск облигации' });
    await bondSearch.fill('Минфин');
    await expect(page.getByRole('listbox')).toBeVisible();
    await page.getByRole('option').first().click();

    await page.getByRole('button', { name: /^10% \(/ }).click();
    await expect(page.getByText(/Изменение допустимо/)).toBeVisible();
    await page.getByRole('button', { name: 'Купить 10% позиции' }).click();
    await expect(page.getByRole('dialog', { name: 'Подготовка заявки на покупку' })).toBeVisible();
    await expect(page.getByText(/заявка не отправляется/)).toBeVisible();

    await expect(page.getByText(/Концепт пилотной интеграции/)).toBeVisible();
    expect(offenders).toEqual([]);
  });

  test('демо-страницы используют только read-only live demo API', async ({ page }) => {
    await mockLiveDemoApi(page);
    const offenders = await trackSideEffects(page);
    for (const path of ['/demo/trading', '/demo/analytics?market=BCSE', '/demo/analytics?market=MOEX', '/demo/search?q=Минфин']) {
      await page.goto(path);
      await expect(page.locator('body')).not.toHaveText('502 Bad Gateway');
    }
    expect(offenders).toEqual([]);
  });

  test('market selection сохраняется в URL при навигации', async ({ page }) => {
    await mockLiveDemoApi(page);
    await page.goto('/demo/trading');
    await page.getByRole('main').getByRole('button', { name: /MOEX/ }).click();
    await expect(page).toHaveURL(/market=MOEX/);
  });
});
