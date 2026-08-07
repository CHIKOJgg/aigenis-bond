import type { DemoBond } from './types';

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
  const params = new URLSearchParams({ market, limit: '100' });
  if (currency && currency !== 'ALL') params.set('currency', currency);
  const response = await fetch(`/api/v1/demo/market-data?${params.toString()}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`live market request failed: ${response.status}`);
  return response.json() as Promise<LiveMarketSnapshot>;
}
