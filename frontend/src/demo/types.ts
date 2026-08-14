export interface DemoBond {
  internal_id: string;
  isin: string | null;
  name: string;
  issuer: string | null;
  issuer_logo: string | null;
  currency: string;
  nominal: number | null;
  coupon_rate: number | null;
  coupon_frequency: number | null;
  maturity_date: string | null;
  price: number | null;
  yield_to_maturity: number | null;
  amortization: string | null;
  market: string;
  status: string;
  is_government: boolean;
  in_stock: boolean | null;
  guarantor: string | null;
  maturity_term_text: string | null;
  coupon_description: string | null;
  fetched_at: string | null;
  term_days: number | null;
  duration_years?: number | null;
  computed_ytm?: boolean;
  distressed?: boolean;
  score?: number | null;
  tier?: string | null;
  score_status?: ScoreStatus | null;
  breakdown?: ScoreBreakdown | null;
  explanation?: LiveExplanation | null;
  issuer_risk?: IssuerRisk | null;
  accrued_interest?: number | null;
  indexation_currency?: string | null;
  exchange_rate_on_start?: number | null;
}

export interface IssuerRisk {
  score: number;
  level: string;
  basis: string;
  credit_component: number;
  method: string;
}

export interface BondHistoryPoint {
  date: string;
  price: number | null;
  yield: number | null;
}

export interface LiveBondDetail extends DemoBond {
  history: BondHistoryPoint[];
  coupon_schedule: Record<string, unknown> | null;
}

export interface LiveExplanationFactor {
  component: string;
  label: string;
  points: number;
  impact: 'positive' | 'negative' | 'neutral';
  detail: string;
}

export interface LiveExplanation {
  verdict: string;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  factors: LiveExplanationFactor[];
}

export interface LiveSearchResult {
  query: string;
  market: string | null;
  count: number;
  bonds: DemoBond[];
  disclaimer: string;
}

export interface DemoScore {
  internal_id: string;
  score: number;
  tier: string;
  status: ScoreStatus;
  computed_at: string;
  breakdown: ScoreBreakdown;
}

export type ScoreStatus =
  | 'attractive'
  | 'neutral'
  | 'review'
  | 'high_risk'
  | 'no_data';

export interface ScoreBreakdown {
  yield_component: number;
  currency_component: number;
  duration_component: number;
  liquidity_component: number;
  metal_component: number;
  credit_risk_component: number;
  inflation_component: number;
  coupon_component: number;
  volatility_component: number;
  historical_volatility_component: number;
  peer_relative_component: number;
  reward_subtotal: number;
  risk_subtotal: number;
  efficiency_ratio: number;
}

export interface ExplanationFactor {
  label: string;
  direction: 'positive' | 'negative' | 'neutral';
  plainText: string;
  importance: 'high' | 'medium' | 'low';
}

export interface BondExplanation {
  internal_id: string;
  status: ScoreStatus;
  verdict?: string;
  summary?: string;
  factors: ExplanationFactor[];
  strengths?: string[];
  weaknesses?: string[];
}

export interface LiveExplanationFactor {
  component: string;
  label: string;
  points: number;
  impact: 'positive' | 'negative' | 'neutral';
  detail: string;
}

export interface LiveExplanation {
  verdict: string;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  factors: LiveExplanationFactor[];
}

export interface DemoPortfolioTemplate {
  id: string;
  label: string;
  total_value_byn: number;
  description: string;
  positions: PortfolioPosition[];
  free_cash_byn: number;
  benchmarks: PortfolioBenchmark;
}

export interface PortfolioPosition {
  instrument_id: string;
  name: string;
  weight_pct: number;
  value_byn: number;
}

export interface PortfolioBenchmark {
  expected_yield_pct: number;
  duration_years: number;
  issuer_concentration_max_pct: number;
  low_liquidity_share_pct: number;
}

export interface PortfolioImpactRequest {
  portfolio_template: string;
  bond_id: string;
  allocation_pct: number;
}

export interface PortfolioImpactResponse {
  before: {
    expected_yield_pct: number;
    duration_years: number;
  };
  after: {
    expected_yield_pct: number;
    duration_years: number;
  };
  deltas: {
    expected_yield_pp: number;
    duration_years: number;
  };
  constraints: ConstraintCheck[];
  summary: string;
  disclaimer: string;
}

export interface ConstraintCheck {
  name: string;
  status: 'ok' | 'warning' | 'breach';
  detail: string;
}

export interface MarketSummary {
  as_of: string;
  markets: Record<string, MarketStats>;
  global: GlobalStats;
}

export interface MarketStats {
  total_bonds: number;
  attractive_ideas: number;
  needs_review: number;
  neutral: number;
  high_risk: number;
  best_yield_pct: number;
  best_yield_id: string;
}

export interface GlobalStats {
  attractive_ideas: number;
  needs_review: number;
  best_yield_pct: number;
  data_status: 'ok' | 'warning' | 'critical';
  updated_at: string;
}

export type DemoMarket = 'BCSE' | 'MOEX';

export type TermFilter = 'all' | 'up_to_1' | '1_3' | '3_5' | '5_plus';

export interface AnalyticsFilters {
  market: DemoMarket;
  currency: string;
  term: TermFilter;
  status: ScoreStatus | 'all';
  liquidity: 'all' | 'high' | 'medium' | 'low';
  sortKey: 'score' | 'ytm' | 'maturity' | 'duration';
  sortDir: 'asc' | 'desc';
}
