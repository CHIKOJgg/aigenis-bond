import { scoreTier, tierBadgeClass } from '../lib/tiers';

export function BondIcon({ name, size = 36 }: { name?: string | null; size?: number }) {
  const letter = (name ?? '?').charAt(0).toUpperCase();
  return (
    <div
      className="flex items-center justify-center rounded-[8px] bg-aigenis-500 text-white font-aigenis-heading font-bold shrink-0"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      aria-hidden="true"
    >
      {letter}
    </div>
  );
}

export function ScoreTierBadge({ score }: { score: number | undefined | null }) {
  const tier = scoreTier(score);
  return (
    <span
      className={`inline-flex items-center justify-center min-w-[22px] h-5 rounded-[6px] text-[11px] font-bold font-aigenis-heading ${tierBadgeClass(tier)}`}
    >
      {tier}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const active = status === 'active';
  return (
    <span
      className={`text-[11px] font-medium px-2.5 py-0.5 rounded-[6px] ${
        active ? 'bg-aigenis-success-50 text-aigenis-success-600' : 'bg-aigenis-surface-subtle text-aigenis-text-muted'
      }`}
    >
      {status ?? '—'}
    </span>
  );
}

export function CurrencyBadge({ currency }: { currency: string | null | undefined }) {
  return (
    <span className="px-2 py-0.5 rounded-[6px] text-[11px] font-semibold bg-aigenis-surface-subtle text-aigenis-text-secondary">
      {currency ?? '—'}
    </span>
  );
}
