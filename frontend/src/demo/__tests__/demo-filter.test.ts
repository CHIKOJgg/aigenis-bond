import { describe, it, expect } from 'vitest';
import { filterAndSortBonds, termMatches } from '../demo-filter';
import type { DemoBond } from '../types';

function bond(id: string, overrides: Partial<DemoBond> = {}): DemoBond {
  return {
    internal_id: id,
    isin: null,
    name: id,
    issuer: 'Тест',
    issuer_logo: null,
    currency: 'BYN',
    nominal: null,
    coupon_rate: null,
    coupon_frequency: null,
    maturity_date: null,
    price: null,
    yield_to_maturity: null,
    amortization: null,
    market: 'bcse',
    status: 'active',
    is_government: false,
    in_stock: null,
    guarantor: null,
    maturity_term_text: null,
    coupon_description: null,
    fetched_at: null,
    term_days: null,
    ...overrides,
  };
}

const bonds: DemoBond[] = [
  bond('a', { currency: 'BYN', yield_to_maturity: 10, term_days: 300 }),
  bond('b', { currency: 'BYN', yield_to_maturity: 12, term_days: 800 }),
  bond('c', { currency: 'USD', yield_to_maturity: 5, term_days: 2000 }),
];

const scoreLookup = (id: string) => {
  const scores: Record<string, { score: number; status: 'attractive' | 'neutral' | 'review' | 'high_risk' | 'no_data' }> = {
    a: { score: 70, status: 'attractive' },
    b: { score: 40, status: 'neutral' },
    c: { score: 20, status: 'review' },
  };
  return scores[id];
};

const defaults = { currency: 'ALL', term: 'all' as const, status: 'all' as const, sortKey: 'score' as const, sortDir: 'desc' as const };

describe('termMatches', () => {
  it('все сроки — всегда true', () => {
    expect(termMatches(null, 'all')).toBe(true);
    expect(termMatches(10000, 'all')).toBe(true);
  });

  it('up_to_1 — до 365 дней включительно', () => {
    expect(termMatches(365, 'up_to_1')).toBe(true);
    expect(termMatches(366, 'up_to_1')).toBe(false);
  });

  it('1_3 — между 366 и 1095 днями', () => {
    expect(termMatches(365, '1_3')).toBe(false);
    expect(termMatches(1000, '1_3')).toBe(true);
    expect(termMatches(1095, '1_3')).toBe(true);
    expect(termMatches(1096, '1_3')).toBe(false);
  });

  it('3_5 — между 1096 и 1825 днями', () => {
    expect(termMatches(1800, '3_5')).toBe(true);
    expect(termMatches(1825, '3_5')).toBe(true);
    expect(termMatches(1826, '3_5')).toBe(false);
  });

  it('5_plus — больше 1825 дней', () => {
    expect(termMatches(1826, '5_plus')).toBe(true);
    expect(termMatches(1000, '5_plus')).toBe(false);
  });

  it('без срока (null) — только all', () => {
    expect(termMatches(null, 'up_to_1')).toBe(false);
  });
});

describe('filterAndSortBonds', () => {
  it('не меняет порядок без фильтров (по умолчанию score desc)', () => {
    const result = filterAndSortBonds(bonds, defaults, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['a', 'b', 'c']);
  });

  it('сортирует по YTM desc', () => {
    const result = filterAndSortBonds(bonds, { ...defaults, sortKey: 'ytm' }, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['b', 'a', 'c']);
  });

  it('сортирует по YTM asc', () => {
    const result = filterAndSortBonds(bonds, { ...defaults, sortKey: 'ytm', sortDir: 'asc' }, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['c', 'a', 'b']);
  });

  it('сортирует по score asc', () => {
    const result = filterAndSortBonds(bonds, { ...defaults, sortDir: 'asc' }, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['c', 'b', 'a']);
  });

  it('фильтрует по валюте', () => {
    const result = filterAndSortBonds(bonds, { ...defaults, currency: 'USD' }, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['c']);
  });

  it('фильтрует по сроку 1_3', () => {
    const result = filterAndSortBonds(bonds, { ...defaults, term: '1_3' }, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['b']);
  });

  it('фильтрует по статусу', () => {
    const result = filterAndSortBonds(bonds, { ...defaults, status: 'neutral' }, scoreLookup);
    expect(result.map((b) => b.internal_id)).toEqual(['b']);
  });

  it('бумага без Score не попадает в фильтр по статусу', () => {
    const extra = filterAndSortBonds(
      [...bonds, bond('noscore')],
      { ...defaults, status: 'attractive' },
      scoreLookup,
    );
    expect(extra.map((b) => b.internal_id)).toEqual(['a']);
  });

  it('бумага без Score сортируется как 0', () => {
    const result = filterAndSortBonds([...bonds, bond('noscore')], defaults, scoreLookup);
    expect(result[result.length - 1].internal_id).toBe('noscore');
  });
});
