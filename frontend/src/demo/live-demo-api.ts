import type { DemoBond, LiveBondDetail, LiveSearchResult } from './types';

export interface LiveMarketSnapshot {
  source: string;
  market: string;
  currency: string | null;
  as_of: string | null;
  count: number;
  bonds: DemoBond[];
  disclaimer: string;
}

export async function fetchLiveMarket(
  market = 'bcse',
  currency?: string,
): Promise<LiveMarketSnapshot> {
  const params = new URLSearchParams({ market, limit: '2000' });
  if (currency && currency !== 'ALL') params.set('currency', currency);
  const response = await fetch(`/api/v1/demo/market-data?${params.toString()}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`live market request failed: ${response.status}`);
  return response.json() as Promise<LiveMarketSnapshot>;
}

export async function fetchLiveSearch(
  q: string,
  market?: string,
): Promise<LiveSearchResult> {
  const params = new URLSearchParams({ q, limit: '50' });
  if (market && market !== 'ALL') params.set('market', market.toLowerCase());
  const response = await fetch(`/api/v1/demo/search?${params.toString()}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`live search request failed: ${response.status}`);
  return response.json() as Promise<LiveSearchResult>;
}

export async function fetchLiveBond(
  internalId: string,
  signal?: AbortSignal,
): Promise<LiveBondDetail> {
  const response = await fetch(`/api/v1/demo/bond/${encodeURIComponent(internalId)}`, {
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok) throw new Error(`live bond request failed: ${response.status}`);
  return response.json() as Promise<LiveBondDetail>;
}

export async function fetchLiveDeskCurve(
  currency = 'BYN',
  market = 'bcse',
): Promise<{ currency: string; market: string; points: any[]; params: any; slope: number }> {
  const params = new URLSearchParams({ currency, market: market.toLowerCase() });
  const response = await fetch(`/api/v1/demo/desk/curve?${params.toString()}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`live desk curve request failed: ${response.status}`);
  return response.json();
}

export async function fetchLiveDeskRv(
  currency = 'BYN',
  market = 'bcse',
): Promise<any[]> {
  const params = new URLSearchParams({ currency, market: market.toLowerCase() });
  const response = await fetch(`/api/v1/demo/desk/rv?${params.toString()}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`live desk rv request failed: ${response.status}`);
  return response.json();
}

export interface LiveOptimizeRequest {
  capital: number;
  strategy: string;
  currency: string;
  top_n: number;
  market?: string;
}

export interface LiveOptimizeResponse {
  strategy: string;
  capital: number;
  currency: string;
  metrics: {
    expected_return: number;
    volatility: number;
    sharpe: number;
    sortino: number;
    calmar: number;
    max_drawdown: number;
    var_95: number;
  };
  allocations: Array<{
    internal_id: string;
    name: string;
    issuer: string;
    isin: string;
    amount: number;
    currency?: string;
    weight_pct: number;
    lots: number;
    ytm: number | null;
  }>;
  order_tickets: Array<{
    action: string;
    internal_id: string;
    name: string;
    lots: number;
    est_cost: number;
    currency?: string;
    rationale: string;
  }>;
  available_strategies: string[];
  warning?: string | null;
}

export async function fetchLiveOptimize(
  params: LiveOptimizeRequest,
): Promise<LiveOptimizeResponse> {
  const response = await fetch('/api/v1/demo/portfolio/optimize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`live optimize request failed: ${response.status}`);
  return response.json() as Promise<LiveOptimizeResponse>;
}

export interface LiveStressRequest {
  scenario: string;
  market: string;
  capital: number;
}

export interface LiveStressPosition {
  internal_id: string;
  name: string;
  lots: number;
  invested: number;
  price_money: number;
  pnl: number;
}

export interface LiveStressResponse {
  scenario: {
    key: string;
    name: string;
    description: string;
    kind: string;
  };
  pnl_amount: number;
  pnl_pct: number;
  duration_before: number;
  duration_after: number;
  by_tenor: Record<string, number>;
  by_position: Record<string, number>;
  positions?: LiveStressPosition[];
  var_95?: number;
  available_scenarios: Array<{
    key: string;
    name: string;
    description: string;
  }>;
}

export async function fetchLiveStress(
  params: LiveStressRequest,
): Promise<LiveStressResponse> {
  const response = await fetch('/api/v1/demo/desk/stress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`live stress request failed: ${response.status}`);
  return response.json() as Promise<LiveStressResponse>;
}
