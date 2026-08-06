import type { DemoBond, ScoreStatus, TermFilter } from './types';

export interface FilterState {
  currency: string;
  term: TermFilter;
  status: ScoreStatus | 'all';
  sortKey: 'score' | 'ytm';
  sortDir: 'asc' | 'desc';
}

export interface ScoreLookup {
  (id: string): { score: number; status: ScoreStatus } | undefined;
}

export function termMatches(
  days: number | null | undefined,
  term: TermFilter,
): boolean {
  if (term === 'all') return true;
  if (days == null) return false;
  if (term === 'up_to_1') return days <= 365;
  if (term === '1_3') return days > 365 && days <= 1095;
  if (term === '3_5') return days > 1095 && days <= 1825;
  if (term === '5_plus') return days > 1825;
  return true;
}

export function filterAndSortBonds(
  bonds: DemoBond[],
  filters: FilterState,
  getScore: ScoreLookup,
): DemoBond[] {
  const rows = bonds.filter((b) => {
    if (filters.currency !== 'ALL' && b.currency !== filters.currency) return false;
    if (!termMatches(b.term_days, filters.term)) return false;
    if (filters.status !== 'all' && getScore(b.internal_id)?.status !== filters.status) return false;
    return true;
  });

  const dir = filters.sortDir === 'asc' ? 1 : -1;
  rows.sort((a, b) => {
    const diff =
      filters.sortKey === 'score'
        ? (getScore(a.internal_id)?.score ?? 0) - (getScore(b.internal_id)?.score ?? 0)
        : (a.yield_to_maturity ?? 0) - (b.yield_to_maturity ?? 0);
    return diff * dir;
  });

  return rows;
}
