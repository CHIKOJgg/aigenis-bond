export function formatYtm(ytm: number | null | undefined): string {
  return ytm != null ? `${ytm}%` : '—';
}

export function formatDurationYears(days: number | null | undefined): string {
  return days != null ? `${(days / 365.25).toFixed(1)} г.` : '—';
}

export function formatYears(years: number | null | undefined): string {
  return years != null ? `${years.toFixed(1)} г.` : '—';
}

export function formatPrice(
  price: number | null | undefined,
  _currency?: string,
): string {
  if (price == null) return '—';
  return `${Number(price.toFixed(2))}%`;
}

export function formatPoints(points: number | null | undefined): string {
  if (points == null) return '—';
  const v = Number(points.toFixed(1));
  if (v > 0) return `+${v}`;
  return `${v}`;
}
