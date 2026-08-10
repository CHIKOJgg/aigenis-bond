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
