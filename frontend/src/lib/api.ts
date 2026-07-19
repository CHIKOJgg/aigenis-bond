const BASE = '';

export class ApiError extends Error {
  status: number;
  upgradeRequired: boolean;
  constructor(message: string, status: number, upgradeRequired = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.upgradeRequired = upgradeRequired;
  }
}

function getToken(): string | null {
  return localStorage.getItem('access_token');
}

async function request<T>(path: string, options: RequestInit = {}, _isRetry = false): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401 && !_isRetry) {
    const refreshToken = localStorage.getItem('refresh_token');
    if (refreshToken) {
      try {
        const refreshRes = await fetch(`${BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          return request<T>(path, options, true);
        }
      } catch { /* refresh failed, fall through */ }
    }
    // Refresh failed — clear tokens so AuthContext logs user out
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // 402 == subscription required (see api.access_control.RequireFeature)
    throw new ApiError(body.detail || `HTTP ${res.status}`, res.status, res.status === 402);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export interface Bond {
  internal_id: string;
  name: string;
  currency: string;
  price: number | null;
  yield_to_maturity: number | null;
  coupon_rate: number | null;
  coupon_frequency: number | null;
  maturity_date: string | null;
  status: string;
  issuer: string | null;
  issuer_logo: string | null;
  fetched_at: string | null;
}

export interface BondScore {
  internal_id: string;
  score: number;
  tier: string | null;
}

export interface Stats {
  total_bonds: number;
  active_bonds: number;
  by_currency: Record<string, number>;
}

export interface Health {
  status: string;
  db: string;
  uptime_seconds: number;
  version: string;
}

export interface CurvePoint {
  tenor: string;
  years: number;
  rate_pct: number;
}

export interface YieldCurve {
  currency: string;
  observed_at: string;
  points: CurvePoint[];
  ns_params: { beta0: number; beta1: number; beta2: number; tau: number } | null;
}

export interface RVSignal {
  internal_id: string;
  z_score: number;
  spread_pct: number;
  fair_spread_pct: number;
  side: string;
  rationale: string;
}

export interface DurationReport {
  internal_id: string | null;
  modified_duration: number;
  macaulay_duration: number;
  convexity: number;
  dv01: number;
  key_rate_durations: Record<string, number>;
  asof_date: string;
}

export interface CarryTrade {
  internal_id: string;
  coupon_pct: number;
  rolldown_bps: number;
  expected_pnl_pct: number;
  breakeven_bps: number;
}

export interface RepoDeal {
  internal_id: string;
  notional: number;
  haircut_pct: number;
  repo_rate_pct: number;
  tenor_days: number;
  cash_lent: number;
  collateral_value: number;
  accrued_interest: number;
}

export interface StressRun {
  scenario_name: string;
  scenario_kind: string;
  pnl: number;
  pnl_pct: number;
  portfolio_value: number;
  stressed_value: number;
}

export interface Alert {
  id: number;
  kind: string;
  title: string;
  message: string;
  created_at: string;
}

export interface MLModel {
  version: string;
  kind: string;
  metrics: Record<string, number>;
  trained_at: string;
  train_rows: number;
}

export interface Prediction {
  internal_id: string;
  decision: string;
  confidence: number;
  predicted_ytm: number | null;
  predicted_return_pct: number | null;
  explanation: string[];
}

export interface User {
  id: number;
  email: string;
  name: string;
  role: string;
  subscription_tier: string;
  trial_end: string | null;
  is_active: boolean;
  is_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface StarPlan {
  tier: string;
  name: string;
  stars: number;
  duration_days: number;
  blurb: string;
}

export interface SubscribeInfo {
  provider: string;
  yookassa_configured: boolean;
  yookassa_plans: YooKassaPlan[];
  bot_username: string | null;
  deep_link: string | null;
  plans: StarPlan[];
}

export interface YooKassaPlan {
  tier: string;
  name: string;
  price: string;
  currency: string;
  interval: string;
}

export interface AnalyticsCurve {
  currency: string;
  slope: number;
  beta0: number;
  beta1: number;
  beta2: number;
  points: { tenor: string; years: number; rate_pct: number }[];
}

export interface AnalyticsRV {
  internal_id: string;
  side: string;
  z_score: number | null;
  spread_pct: number | null;
}

export interface AnalyticsCarry {
  internal_id: string;
  coupon_pct: number;
  rolldown_bps: number;
  expected_pnl_pct: number;
}

export interface AnalyticsStress {
  scenario: string;
  kind: string;
  pnl_pct: number;
  pnl: number;
}

export interface AnalyticsRepo {
  internal_id: string;
  collateral_value: number;
  haircut_pct: number;
  cash_lent: number;
  repo_rate_pct: number;
  tenor_days: number;
  accrued_interest: number;
}

export interface AnalyticsPortfolio {
  strategy: string;
  expected_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  var_95: number;
  forecast: {
    horizon_years: number;
    expected_capital: number;
    pessimistic_capital: number;
    optimistic_capital: number;
  }[];
}

export interface AnalyticsForecast {
  horizon_years: number;
  expected_capital: number;
  pessimistic_capital: number;
  optimistic_capital: number;
}

export interface AnalyticsRecommendation {
  rank: number;
  internal_id: string;
  name: string;
  issuer: string | null;
  decision: string;
  confidence: number;
  score: number | null;
  predicted_return_pct: number | null;
  reasons: string[];
  risks: string[];
}

export interface CompanySummary {
  issuer: string;
  name: string;
  sector: string | null;
  description: string | null;
  why_important: string | null;
  logo_url: string | null;
  bond_count: number;
  avg_yield_to_maturity: number | null;
  top_tier: string | null;
  currencies: string[];
}

export interface CompanyBond {
  internal_id: string;
  name: string;
  currency: string;
  yield_to_maturity: number | null;
  maturity_date: string | null;
  price: number | null;
  issuer: string | null;
  score: number | null;
  tier: string | null;
}

export interface CompanyRecommendation {
  decision: string;
  confidence: number;
  score: number | null;
  predicted_return_pct: number | null;
  reasons: string[];
  risks: string[];
}

export interface CompanyDetail {
  issuer: string;
  name: string;
  sector: string | null;
  description: string | null;
  why_important: string | null;
  website: string | null;
  logo_url: string | null;
  bond_count: number;
  bonds: CompanyBond[];
  recommendation: CompanyRecommendation | null;
}

export interface SearchResult {
  query: string;
  bonds: {
    internal_id: string;
    name: string;
    currency: string;
    yield_to_maturity: number | null;
    issuer: string | null;
  }[];
  companies: {
    issuer: string;
    name: string;
    sector: string | null;
  }[];
}

export interface AnalyticsAlert {
  title: string;
  message: string;
}

export interface WatchlistItem {
  internal_id: string;
  name: string;
  score: number | null;
}

export interface Position {
  internal_id: string;
  amount: number;
  name: string | null;
  currency: string | null;
  yield_to_maturity: number | null;
  price: number | null;
}

export interface PortfolioIncome {
  mode: string;
  total_invested: number;
  annual_income: number;
  yield_on_cost: number;
  next_payment: string | null;
  monthly_calendar: unknown[];
  per_bond: unknown[];
}

export interface MLPredictionResult {
  decision: string;
  confidence: number;
  predicted_ytm: number | null;
  predicted_return_pct: number | null;
  explanation: string[];
}

export interface BondAnalysisResult {
  bond: Bond;
  analysis: { verdict: string; score: number; breakdown: unknown[]; reasons: unknown[] };
  relative_value: { side: string; z_score: number | null; spread_pct: number | null } | null;
  ml_prediction: MLPredictionResult | null;
  disclaimer: string;
}

export interface Cashflow {
  bond: Bond;
  amount_invested: number;
  annual_income: number;
  yield_on_cost: number;
  total_coupons: number;
  cashflows: { date: string; amount: number; kind: string }[];
}

export interface AlertRule {
  id: number;
  internal_id: string;
  metric: 'price' | 'ytm';
  direction: 'above' | 'below';
  threshold: number;
  note?: string | null;
  active: boolean;
  last_value: number | null;
  triggered_at: string | null;
}

export interface AlertFeedItem {
  id: number;
  internal_id: string;
  metric: string;
  message: string;
  value: number | null;
  delivered: boolean;
  created_at: string | null;
}

export const api = {
  health: () => get<Health>('/health'),

  bonds: {
    list: (params?: { currency?: string; limit?: number; offset?: number }) => {
      const q = new URLSearchParams();
      if (params?.currency) q.set('currency', params.currency);
      if (params?.limit) q.set('limit', String(params.limit));
      if (params?.offset) q.set('offset', String(params.offset));
      return get<Bond[]>(`/api/v1/bonds?${q}`);
    },
    get: (id: string) => get<Bond>(`/api/v1/bonds/${id}`),
    watchlist: () => get<WatchlistItem[]>('/api/v1/watchlist'),
    addToWatchlist: (id: string) =>
      post<{ watchlist: string[] }>(`/api/v1/watchlist?internal_id=${encodeURIComponent(id)}`, undefined),
    removeFromWatchlist: (id: string) =>
      request<{ watchlist: string[] }>(`/api/v1/watchlist/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  },

  scores: (params?: { limit?: number; offset?: number; min_score?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    if (params?.min_score) q.set('min_score', String(params.min_score));
    return get<BondScore[]>(`/api/v1/scores?${q}`);
  },

  stats: () => get<Stats>('/api/v1/stats'),

  subscribeInfo: () => get<SubscribeInfo>('/api/v1/subscribe-info'),

  // Analytics endpoints — mirror the Telegram bot 1:1. Pro/Enterprise endpoints
  // return 402 (ApiError.upgradeRequired) for free users.
  analytics: {
    curve: () => get<AnalyticsCurve[]>('/api/v1/desk/curve'),
    rv: () => get<AnalyticsRV[]>('/api/v1/desk/rv'),
    carry: (funding = 5.0) => get<AnalyticsCarry[]>(`/api/v1/desk/carry?funding=${funding}`),
    stress: () => get<AnalyticsStress[]>('/api/v1/desk/stress'),
    repo: (body: { bond_id: string; notional?: number; tenor_days?: number; repo_rate_pct?: number }) =>
      post<AnalyticsRepo>('/api/v1/desk/repo', body),
    portfolio: () => get<AnalyticsPortfolio>('/api/v1/portfolio'),
    forecast: () => get<AnalyticsForecast[]>('/api/v1/forecast'),
    recommendations: (topK = 5) => get<AnalyticsRecommendation[]>(`/api/v1/recommendations?top_k=${topK}`),
    companies: (params?: { sector?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.sector) q.set('sector', params.sector);
      if (params?.limit) q.set('limit', String(params.limit));
      return get<CompanySummary[]>(`/api/v1/companies?${q}`);
    },
    company: (issuer: string) => get<CompanyDetail>(`/api/v1/companies/${encodeURIComponent(issuer)}`),
    search: (q: string) => get<SearchResult>(`/api/v1/search?q=${encodeURIComponent(q)}`),
    alerts: (limit = 10) => get<AnalyticsAlert[]>(`/api/v1/alerts?limit=${limit}`),
  },

  billing: {
    plans: () => get<{ id: string; name: string; price: number; currency: string; features: string[] }[]>('/billing/plans'),
    createPayment: (plan: string, success_url: string, cancel_url: string) =>
      post<{ payment_id: string; confirmation_url: string | null }>('/billing/create-payment', { plan, success_url, cancel_url }),
    subscription: () => get<{ plan: string; status: string; current_period_end: string | null; cancel_at_period_end: boolean }>('/billing/subscription'),
  },

  // Real user positions / portfolio income / bond deep-dive (Pro endpoints,
  // return 402 ApiError.upgradeRequired for free users).
  portfolio: {
    positions: () =>
      get<{ positions: Position[]; total_invested: number }>('/api/v1/positions'),
    addPosition: (internal_id: string, amount: number) =>
      post<{ status: string; internal_id: string; amount: number }>('/api/v1/positions', { internal_id, amount }),
    removePosition: (internal_id: string) =>
      request<{ status: string; internal_id: string }>(`/api/v1/positions/${encodeURIComponent(internal_id)}`, { method: 'DELETE' }),
    income: () =>
      get<PortfolioIncome>('/api/v1/portfolio/income'),
    analysis: (internal_id: string) =>
      get<BondAnalysisResult>(`/api/v1/bond/${encodeURIComponent(internal_id)}/analysis`),
    cashflow: (internal_id: string, amount: number) =>
      get<Cashflow>(`/api/v1/bond/${encodeURIComponent(internal_id)}/cashflow?amount=${amount}`),
    mlPredict: (internal_id: string) =>
      get<MLPredictionResult>(`/api/v1/ml/predict/${encodeURIComponent(internal_id)}`),
  },

  // Real user alert rules + feed (Pro endpoints, 402 for free users).
  userAlerts: {
    rules: () =>
      get<AlertRule[]>('/api/v1/alerts/rules'),
    createRule: (body: { internal_id: string; metric: 'price' | 'ytm'; direction: 'above' | 'below'; threshold: number; note?: string }) =>
      post<AlertRule>('/api/v1/alerts/rules', body),
    deleteRule: (id: number) =>
      request<{ status: string; id: number }>(`/api/v1/alerts/rules/${id}`, { method: 'DELETE' }),
    feed: (limit = 50) =>
      get<AlertFeedItem[]>(`/api/v1/alerts/feed?limit=${limit}`),
  },

  auth: {
    register: (email: string, password: string, name: string) =>
      post<TokenResponse>('/auth/register', { email, password, name }),
    login: (email: string, password: string) =>
      post<TokenResponse>('/auth/login', { email, password }),
    refresh: (refresh_token: string) =>
      post<TokenResponse>('/auth/refresh', { refresh_token }),
    google: (id_token: string, name?: string) =>
      post<TokenResponse>('/auth/google', { id_token, name }),
    me: () => get<User>('/auth/me'),
  },
};

export function exportCsv(filename: string, headers: string[], rows: (string | number | null)[][]) {
  const escape = (v: string | number | null) => {
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [headers.map(escape).join(','), ...rows.map((r) => r.map(escape).join(','))];
  const blob = new Blob(['\uFEFF', lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
