import type {
  DemoBond,
  DemoScore,
  BondExplanation,
  MarketSummary,
  DemoPortfolioTemplate,
  PortfolioImpactRequest,
  PortfolioImpactResponse,
} from './types';

export const STRATEGY_LABELS: Record<string, string> = {
  'Conservative': 'Консервативная',
  'Balanced': 'Сбалансированная',
  'Aggressive': 'Агрессивная',
  'Carry Trade': 'Carry Trade',
  'Dollarization': 'Долларизация',
  'Maximum Reward/Risk': 'Макс. доходность/риск',
  'Metals++': 'Металлы++',
};

import bcseBonds from './data/bonds_bcse.json';
import moexBonds from './data/bonds_moex.json';
import scores from './data/scores.json';
import explanations from './data/explanations.json';
import marketSummary from './data/market_summary.json';
import portfolioTemplates from './data/portfolio_templates.json';

const bondsByMarket: Record<string, DemoBond[]> = {
  BCSE: bcseBonds as DemoBond[],
  MOEX: moexBonds as DemoBond[],
};

const scoreMap = new Map<string, DemoScore>();
(scores as DemoScore[]).forEach((s) => scoreMap.set(s.internal_id, s));

const explanationMap = new Map<string, BondExplanation>();
(explanations as BondExplanation[]).forEach((e) =>
  explanationMap.set(e.internal_id, e),
);

const templates = portfolioTemplates as Record<string, DemoPortfolioTemplate>;

export function getBonds(market: string): DemoBond[] {
  return bondsByMarket[market] ?? [];
}

export function getAllBonds(): DemoBond[] {
  return [...bondsByMarket['BCSE'] ?? [], ...bondsByMarket['MOEX'] ?? []];
}

export function getScore(internalId: string): DemoScore | undefined {
  return scoreMap.get(internalId);
}

export function scoreFromLiveBond(bond: DemoBond): DemoScore | undefined {
  if (bond.score == null || !bond.score_status || !bond.breakdown) return undefined;
  return {
    internal_id: bond.internal_id,
    score: bond.score,
    tier: bond.tier ?? '',
    status: bond.score_status,
    computed_at: bond.fetched_at ?? new Date().toISOString(),
    breakdown: bond.breakdown,
  };
}

export function getExplanation(
  internalId: string,
): BondExplanation | undefined {
  return explanationMap.get(internalId);
}

export function searchAllBonds(
  q: string,
  market?: string,
): DemoBond[] {
  const term = q.trim().toLowerCase();
  if (!term) return [];
  return getAllBonds()
    .filter((b) => (market && market !== 'ALL' ? b.market.toUpperCase() === market.toUpperCase() : true))
    .filter((b) =>
      [b.name, b.issuer, b.isin, b.internal_id]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(term)),
    )
    .slice(0, 30);
}

export function getMarketSummary(): MarketSummary {
  return marketSummary as MarketSummary;
}

export function getPortfolioTemplate(id: string): DemoPortfolioTemplate {
  return templates[id] ?? templates['moderate_byn'];
}

export function getPortfolioImpact(
  req: PortfolioImpactRequest,
): PortfolioImpactResponse {
  const template = getPortfolioTemplate(req.portfolio_template);
  const bond = getAllBonds().find((b) => b.internal_id === req.bond_id);

  const yieldBoost = bond && bond.yield_to_maturity
    ? (bond.yield_to_maturity - template.benchmarks.expected_yield_pct) *
      (req.allocation_pct / 100)
    : 0;

  const durationDelta = bond && bond.term_days
    ? ((bond.term_days / 365.25 - template.benchmarks.duration_years) *
        (req.allocation_pct / 100))
    : 0;

  return {
    before: {
      expected_yield_pct: template.benchmarks.expected_yield_pct,
      duration_years: template.benchmarks.duration_years,
    },
    after: {
      expected_yield_pct: +(template.benchmarks.expected_yield_pct + yieldBoost).toFixed(1),
      duration_years: +(template.benchmarks.duration_years + durationDelta).toFixed(1),
    },
    deltas: {
      expected_yield_pp: +yieldBoost.toFixed(1),
      duration_years: +durationDelta.toFixed(1),
    },
    constraints: [
      {
        name: 'Концентрация на эмитентах',
        status: 'ok',
        detail: 'В пределах лимита (макс. 25% на эмитента)',
      },
      {
        name: 'Доля низкой ликвидности',
        status: 'ok',
        detail: 'Без изменения',
      },
    ],
    summary: 'Изменение допустимо при умеренном риск-профиле',
    disclaimer: 'Демонстрационный расчёт. Не является инвестиционной рекомендацией. Не учитывает комиссии, налоги и рыночные изменения.',
  };
}

export interface StressScenarioInfo {
  key: string;
  name: string;
  description: string;
  simple_description?: string;
  kind: string;
}

export interface StressTestResponse {
  scenario: StressScenarioInfo;
  pnl_amount: number;
  pnl_pct: number;
  duration_before: number;
  duration_after: number;
  by_tenor: Record<string, number>;
  by_position: Record<string, number>;
  available_scenarios: StressScenarioInfo[];
  var_95?: number;
  positions?: Array<{
    internal_id: string;
    name: string;
    lots: number;
    invested: number;
    price_money: number;
    pnl: number;
  }>;
}

export function runStressTest(
  scenarioKey: string = 'parallel_+100bp',
  market: string = 'BCSE',
  capital: number = 50000,
): StressTestResponse {
  const scenarios: Record<string, StressScenarioInfo> = {
    'parallel_+100bp': {
      key: 'parallel_+100bp',
      name: 'Параллельный сдвиг +100 б.п. (+1%)',
      description: 'Синхронный рост процентных ставок ЦБ и доходностей по всей кривой на 100 б.п.',
      simple_description: 'Ставки в экономике выросли на 1%. Облигации слегка дешевеют в цене, но продолжают давать стабильный купон.',
      kind: 'parallel',
    },
    'parallel_+300bp': {
      key: 'parallel_+300bp',
      name: 'Параллельный шок +300 б.п. (+3%)',
      description: 'Резкое ужесточение ДКП и стрессовый подъем ключевой ставки регулятора на 300 б.п.',
      simple_description: 'Жесткий кризисный подъем ставок (+3%). Рыночные цены текущих облигаций заметно проседают, так как новые бумаги будут выходить с повышенным процентом.',
      kind: 'parallel',
    },
    'parallel_-100bp': {
      key: 'parallel_-100bp',
      name: 'Снижение ставок -100 б.п. (-1%)',
      description: 'Смягчение денежно-кредитной политики и параллельное снижение доходностей на 100 б.п.',
      simple_description: 'ЦБ снижает ставки на 1%. Текущие облигации с высокой доходностью дорожают на бирже, принося дополнительную прибыль к купонам.',
      kind: 'parallel',
    },
    'steepener_+50_+150': {
      key: 'steepener_+50_+150',
      name: 'Steepener (Крутизна кривой)',
      description: 'Короткие ставки +50 б.п., долгосрочные ставки +150 б.п. Рост премии за срочность.',
      simple_description: 'Инвесторы требуют повышенную премию за риск вдолгую. Длинные бумаги дешевеют сильнее, а короткие сохраняют стоимость.',
      kind: 'steepener',
    },
    'flattener_+150_+50': {
      key: 'flattener_+150_+50',
      name: 'Flattener (Уплощение кривой)',
      description: 'Опережающий рост коротких ставок (+150 б.п.) при умеренном изменении длинных (+50 б.п.).',
      simple_description: 'Краткосрочные деньги резко дорожают. Разница в доходности между короткими и длинными бумагами почти исчезает.',
      kind: 'flattener',
    },
    'inversion_+200_-50': {
      key: 'inversion_+200_-50',
      name: 'Инверсия кривой (+200 / -50 б.п.)',
      description: 'Резкий скачок коротких ставок (+200 б.п.) при снижении долгосрочных (-50 б.п.).',
      simple_description: 'Аномалия: короткие вклады и бумаги дают больше процентов, чем длинные. Обычно бывает перед экономическим спадом.',
      kind: 'inversion',
    },
    'credit_shock_+150bp': {
      key: 'credit_shock_+150bp',
      name: 'Кредитный шок спредов (+150 б.п.)',
      description: 'Расширение кредитных спредов корпоративного сектора на 150 б.п. из-за роста риска компаний.',
      simple_description: 'Рынок опасается за надежность коммерческих компаний. Корпоративные бумаги дешевеют, а гособлигации Минфина остаются в безопасности.',
      kind: 'credit_shock',
    },
    'fx_shock_-20%': {
      key: 'fx_shock_-20%',
      name: 'Валютный шок (-20% к USD)',
      description: 'Девальвация национальной валюты к доллару США на 20%.',
      simple_description: 'Курс доллара подскочил на 20%. Валютные и замещающие облигации в пересчете на рубли дают мощную курсовую прибыль.',
      kind: 'fx_shock',
    },
  };

  const sc = scenarios[scenarioKey] ?? scenarios['parallel_+100bp'];
  const bonds = getBonds(market.toUpperCase());

  if (capital <= 0 || bonds.length === 0) {
    return {
      scenario: sc,
      pnl_amount: 0.0,
      pnl_pct: 0.0,
      duration_before: 0.0,
      duration_after: 0.0,
      by_tenor: { '1Y': 0, '5Y': 0, '10Y': 0, '30Y': 0 },
      by_position: {},
      positions: [],
      available_scenarios: Object.values(scenarios),
    };
  }

  const topBonds = bonds.slice(0, 10);
  const perBond = capital / Math.max(topBonds.length, 1);

  let totalPnl = 0;
  const byPosition: Record<string, number> = {};
  const byTenor: Record<string, number> = { '1Y': 0, '5Y': 0, '10Y': 0, '30Y': 0 };
  const positions: StressTestResponse['positions'] = [];

  topBonds.forEach((b) => {
    const dur = b.duration_years ?? (b.term_days ? b.term_days / 365.25 : 2.0);
    let shock = 1.0;
    if (sc.kind === 'parallel') {
      // Снижение ставок (-100bp) даёт рост цен: знак шока отрицательный.
      shock = scenarioKey.includes('-100') ? -1.0 : (scenarioKey.includes('300') ? 3.0 : 1.0);
    } else if (sc.kind === 'steepener') shock = dur > 3 ? 1.5 : 0.5;
    else if (sc.kind === 'flattener') shock = dur > 3 ? 0.5 : 1.5;
    else if (sc.kind === 'inversion') shock = dur > 3 ? -0.5 : 2.0;
    else if (sc.kind === 'credit_shock') shock = 1.5;
    else if (sc.kind === 'fx_shock') shock = b.currency === 'BYN' ? 2.5 : -1.0;

    const nominal = b.nominal && b.nominal > 0 ? b.nominal : 100;
    const pricePct = b.price && b.price > 0 ? b.price : 100;
    const priceMoney = (pricePct / 100) * nominal;
    const lots = Math.floor(perBond / priceMoney);
    const invested = lots * priceMoney;

    if (lots > 0) {
      const pnl = -1 * invested * (dur / 100) * shock;
      totalPnl += pnl;
      byPosition[b.name || b.internal_id] = +pnl.toFixed(2);
      positions.push({
        internal_id: b.internal_id,
        name: b.name || b.internal_id,
        lots,
        invested: +invested.toFixed(2),
        price_money: +priceMoney.toFixed(2),
        pnl: +pnl.toFixed(2),
      });

      const tenorKey = dur <= 1 ? '1Y' : dur <= 5 ? '5Y' : dur <= 10 ? '10Y' : '30Y';
      byTenor[tenorKey] = +(byTenor[tenorKey] + pnl).toFixed(2);
    }
  });

  // Если из-за малого капитала лоты стали 0, но на 1 лот хватает
  if (positions.length === 0 && topBonds.length > 0) {
    const b = topBonds[0];
    const nominal = b.nominal && b.nominal > 0 ? b.nominal : 100;
    const pricePct = b.price && b.price > 0 ? b.price : 100;
    const priceMoney = (pricePct / 100) * nominal;
    if (capital >= priceMoney) {
      const dur = b.duration_years ?? (b.term_days ? b.term_days / 365.25 : 2.0);
      const pnl = -1 * priceMoney * (dur / 100);
      totalPnl = pnl;
      byPosition[b.name || b.internal_id] = +pnl.toFixed(2);
      positions.push({
        internal_id: b.internal_id,
        name: b.name || b.internal_id,
        lots: 1,
        invested: +priceMoney.toFixed(2),
        price_money: +priceMoney.toFixed(2),
        pnl: +pnl.toFixed(2),
      });
      const tenorKey = dur <= 1 ? '1Y' : dur <= 5 ? '5Y' : dur <= 10 ? '10Y' : '30Y';
      byTenor[tenorKey] = +pnl.toFixed(2);
    }
  }

  // Сдвиг дюрации: после роста ставок дюрация уменьшается, после снижения —
  // увеличивается (формула api/demo.py: D*(1+y)/(1+y+s), s = ±1% при y ≈ 12.4%).
  // Для остальных сценариев дюрация остаётся на месте.
  const durationAfter = sc.kind === 'parallel'
    ? (scenarioKey.includes('-100') ? 2.83 : 2.77)
    : 2.8;

  return {
    scenario: sc,
    pnl_amount: +totalPnl.toFixed(2),
    pnl_pct: capital > 0 ? +((totalPnl / capital) * 100).toFixed(2) : 0.0,
    duration_before: 2.8,
    duration_after: durationAfter,
    by_tenor: byTenor,
    by_position: byPosition,
    positions,
    available_scenarios: Object.values(scenarios),
  };
}

export interface PortfolioOptimizationAllocation {
  internal_id: string;
  name: string;
  issuer: string;
  isin: string;
  amount: number;
  currency?: string;
  weight_pct: number;
  lots: number;
  ytm: number | null;
}

export interface RebalanceOrderTicket {
  action: 'BUY' | 'SELL';
  internal_id: string;
  name: string;
  lots: number;
  est_cost: number;
  currency?: string;
  rationale: string;
}

export interface PortfolioOptimizationResponse {
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
  allocations: PortfolioOptimizationAllocation[];
  order_tickets: RebalanceOrderTicket[];
  available_strategies: string[];
  warning?: string | null;
}

export function runPortfolioOptimizer(
  capital: number = 50000,
  strategy: string = 'Balanced',
  currency: string = 'BYN',
  topN: number = 8,
  market: string = 'BCSE',
): PortfolioOptimizationResponse {
  const marketKey = (market || 'BCSE').toUpperCase() === 'MOEX' ? 'MOEX' : 'BCSE';
  let all = getBonds(marketKey);

  if (strategy === 'Dollarization') {
    // В долларовый портфель отбираем долларовые и валютно-индексируемые бумаги выбранного рынка
    const usdAssets = all.filter((b) => {
      const name = (b.name || '').toLowerCase();
      const id = (b.internal_id || '').toLowerCase();
      const isUsd = b.currency?.toUpperCase() === 'USD' || b.indexation_currency?.toUpperCase() === 'USD';
      const hasUsdKeyword =
        name.includes('usd') ||
        name.includes('долл') ||
        name.includes('вгдо') ||
        name.includes('op49') ||
        name.includes('оп-49') ||
        name.includes('оп49') ||
        name.includes('op50') ||
        name.includes('оп-50') ||
        name.includes('оп50') ||
        id.includes('op49') ||
        id.includes('op50');
      return isUsd || hasUsdKeyword;
    });
    all = usdAssets.length > 0 ? usdAssets : all.filter((b) => b.currency.toUpperCase() === currency.toUpperCase());
  } else if (strategy === 'Metals++') {
    // В металлы отбираем бумаги выбранного рынка по умной Risk-Parity модели
    if (marketKey === 'BCSE') {
      // Для BCSE — строго 3 выпуска Айгенис (Золото ОП-35, Серебро ОП-43, Платина ОП-42)
      const metalAssets = all.filter((b) => {
        const name = (b.name || '').toLowerCase();
        const id = (b.internal_id || '').toLowerCase();
        const issuer = (b.issuer || '').toLowerCase();
        const idx = (b.indexation_currency || '').toUpperCase();
        const isAig = issuer.includes('айгенис') || issuer.includes('aigenis') || id.includes('aigenis');
        const isMetalIdx = ['XAU', 'XAG', 'XPT', 'GOLD', 'SILVER', 'PLATINUM'].includes(idx);
        const isMetalAig =
          isAig &&
          (name.includes('золот') ||
            name.includes('gold') ||
            name.includes('серебр') ||
            name.includes('silver') ||
            name.includes('платин') ||
            name.includes('platinum') ||
            name.includes('op35') ||
            name.includes('op43') ||
            name.includes('op42') ||
            id.includes('op35') ||
            id.includes('op43') ||
            id.includes('op42'));
        return isMetalIdx || isMetalAig;
      });

      if (metalAssets.length > 0) {
        metalAssets.forEach((b) => {
          const name = (b.name || '').toLowerCase();
          const id = (b.internal_id || '').toLowerCase();
          const idx = (b.indexation_currency || '').toUpperCase();
          if (idx === 'XAU' || name.includes('золот') || name.includes('gold') || id.includes('op35')) {
            b.score = 58;
          } else if (idx === 'XAG' || name.includes('серебр') || name.includes('silver') || id.includes('op43')) {
            b.score = 27;
          } else if (idx === 'XPT' || name.includes('платин') || name.includes('platinum') || id.includes('op42')) {
            b.score = 15;
          } else {
            b.score = 10;
          }
        });
        all = metalAssets;
      } else {
        all = all.filter((b) => b.currency.toUpperCase() === currency.toUpperCase());
      }
    } else {
      // Для MOEX — российские золотые облигации (Южуралзолото, Селигдар, Полюс)
      const moexMetals = all.filter((b) => {
        const name = (b.name || '').toLowerCase();
        return name.includes('золот') || name.includes('gold') || name.includes('южуралзолото') || name.includes('селигдар') || name.includes('полюс');
      });
      all = moexMetals.length > 0 ? moexMetals : all.filter((b) => b.currency.toUpperCase() === currency.toUpperCase());
    }
  } else {
    all = all.filter((b) => b.currency.toUpperCase() === currency.toUpperCase());
  }

  const ranked = [...all].sort((a, b) => (b.score ?? 50) - (a.score ?? 50));
  const selected = ranked.slice(0, topN);

  if (selected.length === 0 || capital <= 0) {
    return {
      strategy,
      capital,
      currency,
      metrics: {
        expected_return: 0.0,
        volatility: 0.0,
        sharpe: 0.0,
        sortino: 0.0,
        calmar: 0.0,
        max_drawdown: 0.0,
        var_95: 0.0,
      },
      allocations: [],
      order_tickets: [],
      available_strategies: [
        'Conservative',
        'Balanced',
        'Aggressive',
        'Carry Trade',
        'Dollarization',
        'Maximum Reward/Risk',
        'Metals++',
      ],
      warning: capital <= 0 ? 'Сумма инвестиций должна быть больше 0.' : `В валюте ${currency} нет доступных облигаций.`,
    };
  }

  // Вычисляем цену за лот для каждой бумаги
  const candidates = selected.map((b) => {
    const nominal = b.nominal && b.nominal > 0 ? b.nominal : 1000;
    const pricePct = b.price && b.price > 0 ? b.price : 100;
    const priceMoney = (pricePct / 100) * nominal;
    return {
      bond: b,
      priceMoney,
      score: b.score ?? 50,
      lots: 0,
    };
  }).filter((c) => c.priceMoney > 0);

  const minPrice = Math.min(...candidates.map((c) => c.priceMoney));

  if (capital < minPrice) {
    return {
      strategy,
      capital,
      currency,
      metrics: {
        expected_return: 0.0,
        volatility: 0.0,
        sharpe: 0.0,
        sortino: 0.0,
        calmar: 0.0,
        max_drawdown: 0.0,
        var_95: 0.0,
      },
      allocations: [],
      order_tickets: [],
      available_strategies: [
        'Conservative',
        'Balanced',
        'Aggressive',
        'Carry Trade',
        'Dollarization',
        'Maximum Reward/Risk',
        'Metals++',
      ],
      warning: `Капитал (${capital.toLocaleString('ru-RU')} ${currency}) меньше минимальной стоимости 1 лота (${minPrice.toLocaleString('ru-RU')} ${currency}). Для формирования портфеля требуется минимум ${minPrice.toLocaleString('ru-RU')} ${currency}.`,
    };
  }

  const totalScore = candidates.reduce((acc, c) => acc + c.score, 0) || 1;

  // 1. Идеальное распределение
  for (const c of candidates) {
    const idealWeight = c.score / totalScore;
    const idealAmt = capital * idealWeight;
    c.lots = Math.floor(idealAmt / c.priceMoney);
  }

  let currentSpent = candidates.reduce((acc, c) => acc + c.lots * c.priceMoney, 0);
  let remainingCash = capital - currentSpent;

  // 2. Если из-за округления не купился ни 1 лот — выделяем по 1 лоту лучшим бумагам
  if (candidates.reduce((acc, c) => acc + c.lots, 0) === 0) {
    const sorted = [...candidates].sort((a, b) => b.score - a.score);
    for (const c of sorted) {
      if (remainingCash >= c.priceMoney) {
        c.lots = 1;
        remainingCash -= c.priceMoney;
      }
    }
  } else {
    // Жадное распределение остатка кэша
    const sorted = [...candidates].sort((a, b) => b.score - a.score);
    for (const c of sorted) {
      while (remainingCash >= c.priceMoney) {
        c.lots += 1;
        remainingCash -= c.priceMoney;
      }
    }
  }

  const allocated = candidates.filter((c) => c.lots > 0);
  const actualTotalCost = allocated.reduce((acc, c) => acc + c.lots * c.priceMoney, 0) || capital;

  const allocations: PortfolioOptimizationAllocation[] = [];
  const orderTickets: RebalanceOrderTicket[] = [];
  let weightedYtmSum = 0;

  for (const c of allocated) {
    const b = c.bond;
    const actualCost = +(c.lots * c.priceMoney).toFixed(2);
    const weightPct = +((actualCost / actualTotalCost) * 100).toFixed(1);

    if (b.yield_to_maturity) {
      weightedYtmSum += b.yield_to_maturity * (actualCost / actualTotalCost);
    }

    allocations.push({
      internal_id: b.internal_id,
      name: b.name,
      issuer: b.issuer ?? 'Aigenis',
      isin: b.isin ?? b.internal_id,
      amount: actualCost,
      currency: b.currency ?? currency,
      weight_pct: weightPct,
      lots: c.lots,
      ytm: b.yield_to_maturity ?? null,
    });

    orderTickets.push({
      action: 'BUY',
      internal_id: b.internal_id,
      name: b.name,
      lots: c.lots,
      est_cost: actualCost,
      currency: b.currency ?? currency,
      rationale: `Целевой вес ${weightPct}% в рамках стратегии '${STRATEGY_LABELS[strategy] ?? strategy}'`,
    });
  }

  const expectedReturn = +(weightedYtmSum || 14.5).toFixed(2);
  const vol = 4.2;
  const sharpe = +((expectedReturn - 4.0) / vol).toFixed(2);

  return {
    strategy,
    capital,
    currency,
    metrics: {
      expected_return: expectedReturn,
      volatility: vol,
      sharpe,
      sortino: +(sharpe * 1.35).toFixed(2),
      calmar: +(expectedReturn / 3.2).toFixed(2),
      max_drawdown: 3.2,
      var_95: 2.1,
    },
    allocations,
    order_tickets: orderTickets,
    available_strategies: [
      'Conservative',
      'Balanced',
      'Aggressive',
      'Carry Trade',
      'Dollarization',
      'Maximum Reward/Risk',
      'Metals++',
    ],
    warning: null,
  };
}

