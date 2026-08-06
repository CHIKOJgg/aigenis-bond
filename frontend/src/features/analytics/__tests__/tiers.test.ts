import { describe, expect, it } from 'vitest';
import { scoreTier, tierBadgeClass } from '../lib/tiers';

describe('scoreTier', () => {
  it('маппит границы тиров', () => {
    expect(scoreTier(100)).toBe('A');
    expect(scoreTier(80)).toBe('A');
    expect(scoreTier(79.9)).toBe('B');
    expect(scoreTier(60)).toBe('B');
    expect(scoreTier(59.9)).toBe('C');
    expect(scoreTier(40)).toBe('C');
    expect(scoreTier(39.9)).toBe('D');
    expect(scoreTier(0)).toBe('D');
  });

  it('обрабатывает undefined/null как D (недостаточно данных)', () => {
    expect(scoreTier(undefined)).toBe('D');
    expect(scoreTier(null)).toBe('D');
  });

  it('возвращает токены классов для каждого тира', () => {
    expect(tierBadgeClass('A')).toContain('bg-aigenis-400');
    expect(tierBadgeClass('B')).toContain('bg-aigenis-300');
    expect(tierBadgeClass('C')).toContain('bg-aigenis-warning-500');
    expect(tierBadgeClass('D')).toContain('bg-aigenis-error-600');
  });
});
