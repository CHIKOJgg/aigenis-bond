import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const bcseBonds = JSON.parse(readFileSync(join(process.cwd(), 'src/demo/data/bonds_bcse.json'), 'utf8')) as Array<Record<string, unknown>>;
const moexBonds = JSON.parse(readFileSync(join(process.cwd(), 'src/demo/data/bonds_moex.json'), 'utf8')) as Array<Record<string, unknown>>;
const scores = JSON.parse(readFileSync(join(process.cwd(), 'src/demo/data/scores.json'), 'utf8')) as Array<Record<string, any>>;

const scoreById = new Map(scores.map((score) => [score.internal_id, score]));

function liveBonds(market: string) {
  const bonds = market === 'moex' ? moexBonds : bcseBonds;
  return bonds.map((bond) => {
    const score = scoreById.get(bond.internal_id);
    return {
      ...bond,
      score: score?.score ?? null,
      tier: score?.tier ?? null,
      score_status: score?.status ?? null,
      breakdown: score?.breakdown ?? null,
      explanation: null,
    };
  });
}

export async function mockLiveDemoApi(page: Page) {
  await page.route('**/api/v1/demo/**', async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split('/').filter(Boolean);
    const endpoint = parts[parts.length - 1];
    const market = url.searchParams.get('market') ?? 'bcse';

    if (endpoint === 'market-data') {
      const bonds = liveBonds(market);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          source: 'Test live source',
          market,
          currency: null,
          as_of: '2026-08-10T15:07:49.000Z',
          count: bonds.length,
          bonds,
          disclaimer: 'Test live data',
        }),
      });
      return;
    }

    if (parts.includes('bond')) {
      const id = decodeURIComponent(endpoint);
      const bond = [...liveBonds('bcse'), ...liveBonds('moex')].find((item) => item.internal_id === id);
      if (!bond) {
        await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...bond, history: [], coupon_schedule: null }),
      });
      return;
    }

    if (endpoint === 'search') {
      const q = (url.searchParams.get('q') ?? '').toLowerCase();
      const bonds = [...liveBonds('bcse'), ...liveBonds('moex')].filter((bond) =>
        [bond.name, bond.issuer, bond.isin, bond.internal_id].some((value) =>
          String(value ?? '').toLowerCase().includes(q),
        ),
      );
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ query: q, market: null, count: bonds.length, bonds, disclaimer: 'Test live data' }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
  });
}
