import { describe, it, expect } from 'vitest';
import { getBonds, getScore, getExplanation, getMarketSummary, getPortfolioTemplate, getPortfolioImpact } from '../demo-api';
import { SCORE_STATUS_LABEL, SCORE_STATUS_DESC } from '../demo-config';

describe('demo-api', () => {
  describe('getBonds', () => {
    it('возвращает BCSE облигации', () => {
      const bonds = getBonds('BCSE');
      expect(bonds.length).toBeGreaterThan(0);
      expect(bonds[0].market).toBe('bcse');
    });

    it('возвращает MOEX облигации', () => {
      const bonds = getBonds('MOEX');
      expect(bonds.length).toBeGreaterThan(0);
      expect(bonds[0].market).toBe('moex');
    });

    it('возвращает пустой массив для неизвестного рынка', () => {
      const bonds = getBonds('UNKNOWN');
      expect(bonds).toEqual([]);
    });
  });

  describe('getScore', () => {
    it('возвращает Score для demo-bond-001', () => {
      const score = getScore('demo-bond-001');
      expect(score).toBeDefined();
      expect(score!.score).toBe(61.44);
      expect(score!.status).toBe('neutral');
    });

    it('возвращает undefined для неизвестного ID', () => {
      const score = getScore('nonexistent');
      expect(score).toBeUndefined();
    });
  });

  describe('getExplanation', () => {
    it('возвращает факторы для demo-bond-001', () => {
      const exp = getExplanation('demo-bond-001');
      expect(exp).toBeDefined();
      expect(exp!.factors.length).toBeGreaterThan(0);
      expect(exp!.factors[0].direction).toBe('positive');
    });
  });

  describe('getMarketSummary', () => {
    it('содержит оба рынка', () => {
      const summary = getMarketSummary();
      expect(summary.markets.bcse).toBeDefined();
      expect(summary.markets.moex).toBeDefined();
      expect(summary.global.data_status).toBe('ok');
    });
  });

  describe('getPortfolioTemplate', () => {
    it('возвращает moderate_byn шаблон', () => {
      const tpl = getPortfolioTemplate('moderate_byn');
      expect(tpl.id).toBe('moderate_byn');
      expect(tpl.total_value_byn).toBeGreaterThan(0);
      expect(tpl.positions.length).toBeGreaterThan(0);
    });
  });

  describe('getPortfolioImpact', () => {
    it('возвращает положительный эффект для attractive облигации', () => {
      const impact = getPortfolioImpact({
        portfolio_template: 'moderate_byn',
        bond_id: 'demo-bond-001',
        allocation_pct: 10,
      });
      expect(impact.before.expected_yield_pct).toBeGreaterThan(0);
      expect(impact.after.expected_yield_pct).toBeGreaterThan(impact.before.expected_yield_pct);
      expect(impact.summary).toBeTruthy();
    });

    it('содержит constraint checks', () => {
      const impact = getPortfolioImpact({
        portfolio_template: 'moderate_byn',
        bond_id: 'demo-bond-001',
        allocation_pct: 5,
      });
      expect(impact.constraints.length).toBeGreaterThan(0);
      impact.constraints.forEach((c) => {
        expect(['ok', 'warning', 'breach']).toContain(c.status);
      });
    });
  });
});

describe('demo-config', () => {
  it('SCORE_STATUS_LABEL содержит все статусы', () => {
    expect(SCORE_STATUS_LABEL).toHaveProperty('attractive');
    expect(SCORE_STATUS_LABEL).toHaveProperty('neutral');
    expect(SCORE_STATUS_LABEL).toHaveProperty('review');
    expect(SCORE_STATUS_LABEL).toHaveProperty('high_risk');
    expect(SCORE_STATUS_LABEL).toHaveProperty('no_data');
  });

  it('SCORE_STATUS_DESC не содержит запрещённых формулировок', () => {
    Object.values(SCORE_STATUS_DESC).forEach((desc) => {
      expect(desc).not.toMatch(/купить|продать|гарантирован|обязательно/i);
    });
  });

  it('SCORE_STATUS_LABEL не содержит buy/sell', () => {
    Object.values(SCORE_STATUS_LABEL).forEach((label) => {
      expect(label).not.toMatch(/покупать|продавать|buy|sell/i);
    });
  });
});
