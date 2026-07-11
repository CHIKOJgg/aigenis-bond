// Per-tier usage limits, used by the paywall to gate UI features client-side.
// Keep in sync with api/access_control.py FEATURE_FLAGS.
export interface TierLimits {
  maxCurrencies: number; // how many "exchanges"/currencies a user can track
  maxBonds: number; // -1 == unlimited
  apiRateLimit: number;
}

export const TIER_LIMITS: Record<string, TierLimits> = {
  free: { maxCurrencies: 1, maxBonds: 20, apiRateLimit: 10 },
  pro: { maxCurrencies: 99, maxBonds: 1000, apiRateLimit: 60 },
  enterprise: { maxCurrencies: 99, maxBonds: -1, apiRateLimit: 300 },
};

export function tierLimits(tier: string | undefined | null): TierLimits {
  return TIER_LIMITS[tier ?? 'free'] ?? TIER_LIMITS.free;
}

export function isPremium(tier: string | undefined | null): boolean {
  return tier === 'pro' || tier === 'enterprise';
}
