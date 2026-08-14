export function formatYtm(ytm: number | null | undefined): string {
  if (ytm == null) return '—';
  const val = Number(ytm.toFixed(2));
  return `${val}%`;
}

export function formatDurationYears(val: number | null | undefined): string {
  if (val == null) return '—';
  const years = val > 30 ? val / 365.25 : val;
  return `${years.toFixed(1)} г.`;
}

export function formatYears(years: number | null | undefined): string {
  return years != null ? `${years.toFixed(1)} г.` : '—';
}

export function formatPrice(
  price: number | null | undefined,
  currency?: string,
  nominal?: number | null,
  accruedInterest?: number | null,
): string {
  if (price == null) return '—';
  const pricePct = Number(price.toFixed(2));
  if (!nominal || nominal <= 0) {
    return `${pricePct}%`;
  }
  const cur = currency || 'BYN';
  const moneyVal = (pricePct / 100) * nominal;
  const dirtyVal = accruedInterest ? moneyVal + accruedInterest : moneyVal;
  
  if (nominal <= 100) {
    const formattedMoney = dirtyVal.toFixed(2);
    return `${pricePct}% (${formattedMoney} ${cur})`;
  }
  
  const formattedMoney = Math.round(dirtyVal).toLocaleString('ru-RU').replace(/\s/g, ' ');
  return `${pricePct}% (${formattedMoney} ${cur})`;
}

export function formatPoints(points: number | null | undefined): string {
  if (points == null) return '—';
  const v = Number(points.toFixed(1));
  if (v > 0) return `+${v}`;
  return `${v}`;
}

export function formatBondDisplayName(
  name: string | null | undefined,
  internalId: string | null | undefined,
  isin?: string | null,
): string {
  if (!name) return isin || internalId || 'Облигация';
  const cleanName = name.trim();

  // Очищаем технические префиксы вида MF-LB-USD-0355 -> ВГДО 355
  const humanized = cleanName
    .replace(/MF-LB-USD-0?(\d+)/gi, 'ВГДО $1 (USD)')
    .replace(/MF-LB-BYN-0?(\d+)/gi, 'ВГДО $1 (BYN)')
    .replace(/demo-bond-minfin-usd-0?(\d+)/gi, 'ВГДО $1 (USD)');

  // Если это generic-заголовок "Министерство финансов" без номера выпуска
  if (/^министерство финансов( республики беларусь)?$/i.test(humanized) || humanized.toLowerCase() === 'минфин') {
    const rawCode = internalId ? internalId.replace(/^(demo-bond-)?(BCSE|MOEX|MF-LB-BYN|MF-LB-USD)-?/i, '') : (isin ?? '');
    if (rawCode) {
      return `Минфин РБ (выпуск ${rawCode})`;
    }
    return `Минфин РБ`;
  }

  return humanized;
}
