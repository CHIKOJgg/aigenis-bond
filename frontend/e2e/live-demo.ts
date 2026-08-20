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

function tenorYears(bond: Record<string, unknown>): number | null {
  if (typeof bond.term_days === 'number' && bond.term_days > 0) {
    return bond.term_days / 365;
  }
  if (typeof bond.maturity_date === 'string' && bond.maturity_date) {
    const years = (new Date(bond.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 3600 * 1000);
    if (Number.isFinite(years)) return Math.max(0, years);
  }
  return null;
}

function curvePoints(market: string) {
  const bonds = liveBonds(market).filter(
    (b) => typeof b.yield_to_maturity === 'number' && b.yield_to_maturity > 0 && tenorYears(b) != null,
  );
  const buckets = new Map<number, { sum: number; count: number }>();
  for (const b of bonds) {
    const years = Math.round(tenorYears(b) as number);
    if (years < 1 || years > 20) continue;
    const cur = buckets.get(years) ?? { sum: 0, count: 0 };
    cur.sum += b.yield_to_maturity as number;
    cur.count += 1;
    buckets.set(years, cur);
  }
  const points = [...buckets.entries()]
    .map(([years, { sum, count }]) => ({
      tenor: `${years}Y`,
      years,
      rate_pct: Math.round((sum / count) * 100) / 100,
    }))
    .sort((a, b) => a.years - b.years);
  if (points.length < 2) {
    return [1, 2, 3, 5, 7, 10, 15, 20].map((years) => ({
      tenor: `${years}Y`,
      years,
      rate_pct: 8 + years * 0.4,
    }));
  }
  return points;
}

function rvSignals(market: string) {
  const bonds = liveBonds(market).filter((b) => typeof b.yield_to_maturity === 'number');
  const hash = (s: string) => {
    let h = 0;
    for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) | 0;
    return h;
  };
  return bonds
    .map((b) => {
      const z = ((hash(b.internal_id) % 500) / 100) - 2.5;
      if (Math.abs(z) < 0.5) return null;
      return {
        internal_id: b.internal_id,
        name: b.name,
        issuer: b.issuer,
        isin: b.isin,
        price: b.price,
        nominal: b.nominal,
        accrued_interest: b.accrued_interest,
        peer_currency: b.currency,
        z_score: Math.round(z * 100) / 100,
        spread_pct: 4 + z * 1.2,
        fair_spread_pct: 4,
        side: z > 1 ? 'buy' : z < -1 ? 'sell' : 'hold',
        rationale:
          z > 1
            ? 'Доходность выше справедливой — бумага недооценена относительно аналогов'
            : z < -1
              ? 'Доходность ниже справедливой — бумага переоценена относительно аналогов'
              : 'Спред в пределах справедливого диапазона',
      };
    })
    .filter(Boolean)
    .slice(0, 7);
}

function customCalculate(holdings: Array<{ internal_id: string; amount: number }>, currency: string) {
  const byId = new Map([...liveBonds('bcse'), ...liveBonds('moex')].map((b) => [b.internal_id, b]));
  const rows = holdings
    .map((h) => {
      const b = byId.get(h.internal_id);
      if (!b || typeof b.yield_to_maturity !== 'number') return null;
      const years = tenorYears(b) ?? 3;
      return {
        internal_id: b.internal_id,
        name: b.name,
        issuer: b.issuer,
        currency: b.currency,
        amount: h.amount,
        ytm: b.yield_to_maturity as number,
        duration_years: Math.round(years * 100) / 100,
        current_yield: b.yield_to_maturity as number,
      };
    })
    .filter(Boolean) as Array<Record<string, unknown>>;
  const total = rows.reduce((acc, r) => acc + (r.amount as number), 0) || 1;
  const weighted = (fn: (r: Record<string, unknown>) => number) =>
    rows.reduce((acc, r) => acc + fn(r) * ((r.amount as number) / total), 0);
  const ytm = weighted((r) => r.ytm as number);
  const duration = weighted((r) => r.duration_years as number);
  const vol = Math.round((8 + Math.abs(ytm - 12) * 0.8) * 100) / 100;
  const sharpe = Math.round(((ytm - 4) / vol) * 100) / 100;
  const byIssuer = new Map<string, number>();
  for (const r of rows) {
    const key = (r.issuer as string | null) ?? 'Прочее';
    byIssuer.set(key, (byIssuer.get(key) ?? 0) + (r.amount as number));
  }
  const concentration = Object.fromEntries([...byIssuer.entries()].map(([k, v]) => [k, Math.round((v / total) * 1000) / 10]));
  return {
    mode: 'calculate',
    currency,
    metrics: {
      expected_return: Math.round(ytm * 100) / 100,
      volatility: vol,
      sharpe,
      sortino: Math.round(sharpe * 1.25 * 100) / 100,
      var_95: -Math.round(vol * 1.65 * 100) / 100,
      max_drawdown: -Math.round(vol * 2.2 * 100) / 100,
      calmar: Math.round((ytm / Math.max(vol * 2.2, 1)) * 100) / 100,
      weighted_duration: Math.round(duration * 100) / 100,
      weighted_current_yield: Math.round(ytm * 100) / 100,
      concentration_by_issuer: concentration,
      holdings: rows.map((r) => ({
        ...r,
        weight_pct: Math.round(((r.amount as number) / total) * 1000) / 10,
      })),
    },
    excluded: [],
    warning: null,
  };
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

    if (endpoint === 'curve') {
      const currency = url.searchParams.get('currency') ?? 'BYN';
      const points = curvePoints(market);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          currency,
          market,
          points,
          params: { a: 9, b: -3, c: 2, d: 6 },
          slope: -0.6,
        }),
      });
      return;
    }

    if (endpoint === 'rv') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rvSignals(market)),
      });
      return;
    }

    if (endpoint === 'calculate') {
      const body = route.request().postDataJSON() as { holdings?: Array<{ internal_id: string; amount: number }>; currency?: string };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(customCalculate(body?.holdings ?? [], body?.currency ?? 'BYN')),
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
