import { describe, it, expect } from 'vitest';
import { runStressTest, runPortfolioOptimizer, honestYtm, getBonds } from '../demo-api';

describe('runStressTest (fixture fallback)', () => {
  it('parallel_+100bp даёт убыток, параллельное -100bp — прибыль', () => {
    const up = runStressTest('parallel_+100bp', 'BCSE', 50000);
    const down = runStressTest('parallel_-100bp', 'BCSE', 50000);
    expect(up.pnl_amount).toBeLessThan(0);
    expect(down.pnl_amount).toBeGreaterThan(0);
    expect(up.pnl_pct).toBeLessThan(0);
    expect(down.pnl_pct).toBeGreaterThan(0);
  });

  it('дюрация после роста ставок уменьшается, после снижения — растёт', () => {
    const up = runStressTest('parallel_+100bp', 'BCSE', 50000);
    const down = runStressTest('parallel_-100bp', 'BCSE', 50000);
    expect(up.duration_after).toBeLessThan(up.duration_before);
    expect(down.duration_after).toBeGreaterThan(down.duration_before);
    // Для не-параллельных сценариев дюрация не меняется.
    const credit = runStressTest('credit_shock_+150bp', 'BCSE', 50000);
    expect(credit.duration_after).toBe(credit.duration_before);
  });

  it('неизвестный сценарий откатывается на parallel_+100bp', () => {
    const res = runStressTest('parallel_-500bp', 'BCSE', 50000);
    expect(res.scenario.key).toBe('parallel_+100bp');
    expect(res.pnl_amount).toBeLessThan(0);
  });

  it('MOEX-сценарий считает по рублёвым бумагам', () => {
    const res = runStressTest('parallel_+100bp', 'MOEX', 50000);
    expect(res.pnl_amount).toBeLessThan(0);
    expect(Object.keys(res.by_position).length).toBeGreaterThan(0);
  });

  it('капитал <= 0 даёт нулевой результат без позиций', () => {
    const res = runStressTest('parallel_+100bp', 'BCSE', 0);
    expect(res.pnl_amount).toBe(0);
    expect(res.pnl_pct).toBe(0);
    expect(res.duration_before).toBe(0);
    expect(res.duration_after).toBe(0);
    expect(res.positions).toEqual([]);
  });

  it('достаточно капитала для покупки хотя бы одного лота самой дешёвой бумаги', () => {
    // С маленьким капиталом, когда лотов не хватает, всё равно должна
    // появиться одна позиция на 1 лот.
    const res = runStressTest('parallel_+100bp', 'BCSE', 100);
    expect(res.positions?.length ?? 0).toBeGreaterThan(0);
    expect(res.positions?.[0].lots).toBe(1);
  });
});

describe('runPortfolioOptimizer (fixture fallback)', () => {
  it('аллокации несут валюту конкретной бумаги', () => {
    const res = runPortfolioOptimizer(50000, 'Dollarization', 'BYN', 8, 'BCSE');
    expect(res.allocations.length).toBeGreaterThan(0);
    for (const a of res.allocations) {
      expect(a.currency).toBeDefined();
      expect(['USD', 'BYN', 'RUB']).toContain(a.currency);
    }
  });

  it('ордер-тикеты несут валюту позиции', () => {
    const res = runPortfolioOptimizer(50000, 'Balanced', 'BYN', 8, 'BCSE');
    expect(res.order_tickets.length).toBeGreaterThan(0);
    for (const t of res.order_tickets) {
      expect(t.currency).toBeDefined();
    }
  });

  it('неизвестная стратегия не ломает расчёт (generic-путь)', () => {
    const res = runPortfolioOptimizer(50000, 'Magic', 'BYN', 8, 'BCSE');
    expect(res.available_strategies).toContain('Balanced');
    expect(Array.isArray(res.allocations)).toBe(true);
    expect(Array.isArray(res.order_tickets)).toBe(true);
  });

  it('неизвестный рынок нормализуется в BCSE', () => {
    const res = runPortfolioOptimizer(50000, 'Balanced', 'BYN', 8, 'UNKNOWN');
    expect(res.allocations.length).toBeGreaterThan(0);
    expect(res.warning).toBeNull();
  });

  it('маленький капитал отдаёт пустые аллокации с warning', () => {
    const res = runPortfolioOptimizer(50, 'Balanced', 'BYN', 8, 'BCSE');
    expect(res.allocations).toEqual([]);
    expect(res.warning).toBeTruthy();
  });

  it('бескупонные индексируемые металлы показывают честную доходность 0%', () => {
    const metals = getBonds('BCSE').filter((b) =>
      ['XAU', 'XAG', 'XPT', 'GOLD', 'SILVER', 'PLATINUM'].includes((b.indexation_currency || '').toUpperCase()),
    );
    expect(metals.length).toBeGreaterThan(0);
    for (const m of metals) {
      expect(honestYtm(m)).toBe(0);
    }
  });

  it('Metals++ не показывает фиктивные 12%: ожидаемая доходность = 0%', () => {
    const res = runPortfolioOptimizer(50000, 'Metals++', 'BYN', 8, 'BCSE');
    expect(res.allocations.length).toBeGreaterThan(0);
    expect(res.metrics.expected_return).toBe(0);
    expect(res.notes?.length ?? 0).toBeGreaterThan(0);
    for (const a of res.allocations) {
      expect(a.ytm).toBe(0);
    }
  });

  it('стратегии Balanced и Aggressive дают разное ранжирование', () => {
    const bal = runPortfolioOptimizer(50000, 'Balanced', 'BYN', 8, 'BCSE');
    const agg = runPortfolioOptimizer(50000, 'Aggressive', 'BYN', 8, 'BCSE');
    const balOrder = bal.allocations.map((a) => a.internal_id);
    const aggOrder = agg.allocations.map((a) => a.internal_id);
    expect(balOrder.length).toBeGreaterThan(0);
    expect(aggOrder.length).toBeGreaterThan(0);
    expect(balOrder).not.toEqual(aggOrder);
  });
});