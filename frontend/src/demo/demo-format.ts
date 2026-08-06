export function formatYtm(ytm: number | null | undefined): string {
  return ytm != null ? `${ytm}%` : '—';
}

export function formatDurationYears(days: number | null | undefined): string {
  return days != null ? `${(days / 365.25).toFixed(1)} г.` : '—';
}

export function formatPrice(
  price: number | null | undefined,
  currency?: string,
): string {
  if (price == null) return '—';
  return currency ? `${price} ${currency}` : `${price}`;
}
