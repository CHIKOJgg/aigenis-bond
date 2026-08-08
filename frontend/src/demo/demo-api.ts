import type {
  DemoBond,
  DemoScore,
  BondExplanation,
  MarketSummary,
  DemoPortfolioTemplate,
  PortfolioImpactRequest,
  PortfolioImpactResponse,
} from './types';

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
