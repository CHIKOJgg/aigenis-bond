export type ScoreTier = 'A' | 'B' | 'C' | 'D';

export function scoreTier(score: number | undefined | null): ScoreTier {
  const s = score ?? 0;
  if (s >= 80) return 'A';
  if (s >= 60) return 'B';
  if (s >= 40) return 'C';
  return 'D';
}

export function tierBadgeClass(tier: ScoreTier): string {
  switch (tier) {
    case 'A': return 'bg-aigenis-400 text-white';
    case 'B': return 'bg-aigenis-300 text-aigenis-900';
    case 'C': return 'bg-aigenis-warning-500 text-white';
    case 'D': return 'bg-aigenis-error-600 text-white';
  }
}
