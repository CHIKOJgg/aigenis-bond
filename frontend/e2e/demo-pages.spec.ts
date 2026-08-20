import { test, expect, type Page } from '@playwright/test';
import { mockLiveDemoApi } from './live-demo';

const SIDE_EFFECT_URL =
  /\/api\/(?!v1\/demo\/)|\/auth\/|\/orders|\/billing\/|\/webhook|\/payment|yookassa/i;

test.describe('demo per-page smoke (8 страниц, read-only)', () => {
  const pages: Array<{ path: string; heading: RegExp }> = [
    { path: '/demo/trading', heading: /Торги/ },
    { path: '/demo/analytics?market=BCSE', heading: /Аналитика облигаций/ },
    { path: '/demo/desk?market=BCSE', heading: /Desk & Relative Value/ },
    { path: '/demo/stress', heading: /стресс-тест/i },
    { path: '/demo/optimizer', heading: /Оптимизатор/ },
    { path: '/demo/search?q=Минфин', heading: /Поиск/ },
    { path: '/demo/portfolio-lab', heading: /Лаборатория Портфелей/i },
    { path: '/demo/portfolio-impact/demo-bond-001?market=ALL', heading: /Влияние на портфель/ },
  ];

  for (const p of pages) {
    test(`${p.path} рендерится без side-effect и без 502`, async ({ page }: { page: Page }) => {
      await mockLiveDemoApi(page);
      const offenders: string[] = [];
      page.on('request', (req) => {
        if (SIDE_EFFECT_URL.test(req.url())) offenders.push(`${req.method()} ${req.url()}`);
      });

      await page.goto(p.path);
      await expect(page.getByRole('heading', { name: p.heading })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.locator('body')).not.toHaveText('502 Bad Gateway');
      expect(offenders).toEqual([]);
    });
  }
});
