import { describe, it, expect } from 'vitest';
import { synthesizeExplanation } from '../demo-explanation';
import type { ScoreBreakdown } from '../types';

const breakdown = {
  yield_component: 12,
  coupon_component: 2,
  currency_component: 1,
  inflation_component: 4,
  liquidity_component: 3,
  duration_component: -2,
  credit_risk_component: -8,
  volatility_component: 1,
  historical_volatility_component: 0,
  peer_relative_component: 5,
  metal_component: 0,
} as unknown as ScoreBreakdown;

describe('synthesizeExplanation', () => {
  it('строит факторы из числового breakdown с направлением и значимостью', () => {
    const e = synthesizeExplanation(breakdown, 'review', 42);
    expect(e).toBeDefined();
    expect(e!.factors.length).toBe(9); // historical_volatility и metal равны 0 → исключены
    const yieldF = e!.factors.find((f) => f.label === 'Доходность к погашению');
    expect(yieldF).toMatchObject({
      label: 'Доходность к погашению',
      impact: 'positive',
      points: 12,
    });
    const creditF = e!.factors.find((f) => f.label === 'Кредитный риск');
    expect(creditF!.impact).toBe('negative');
  });

  it('возвращает summary, вердикт и метаданные синтеза', () => {
    const e = synthesizeExplanation(breakdown, 'review', 42);
    expect(e!.source).toContain('синтезировано');
    expect(e!.summary).toMatch(/Итоговый балл 42/);
    expect(e!.metadata?.generated_by).toMatch(/Aigenis/);
  });

  it('возвращает undefined при отсутствии breakdown', () => {
    expect(synthesizeExplanation(undefined, 'review', 42)).toBeUndefined();
    expect(synthesizeExplanation(null, 'review', 42)).toBeUndefined();
  });
});
