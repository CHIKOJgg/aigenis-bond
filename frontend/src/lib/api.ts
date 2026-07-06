const BASE = '';

function getToken(): string | null {
  return localStorage.getItem('access_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
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
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
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
  is_active: boolean;
  is_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
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
  },

  scores: (params?: { limit?: number; offset?: number; min_score?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    if (params?.min_score) q.set('min_score', String(params.min_score));
    return get<BondScore[]>(`/api/v1/scores?${q}`);
  },

  stats: () => get<Stats>('/api/v1/stats'),

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
