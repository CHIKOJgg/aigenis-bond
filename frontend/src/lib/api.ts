const BASE = '';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get<{ status: string; db: string; uptime_seconds: number; version: string }>('/health'),
  bonds: {
    list: (params?: { currency?: string; limit?: number; offset?: number }) => {
      const q = new URLSearchParams();
      if (params?.currency) q.set('currency', params.currency);
      if (params?.limit) q.set('limit', String(params.limit));
      if (params?.offset) q.set('offset', String(params.offset));
      return get<any[]>(`/api/v1/bonds?${q}`);
    },
    get: (id: string) => get<any>(`/api/v1/bonds/${id}`),
  },
  scores: (params?: { limit?: number; offset?: number; min_score?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    if (params?.min_score) q.set('min_score', String(params.min_score));
    return get<any[]>(`/api/v1/scores?${q}`);
  },
  stats: () => get<{ total_bonds: number; active_bonds: number; by_currency: Record<string, number> }>('/api/v1/stats'),
};
