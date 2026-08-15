export function formatYtm(ytm: number | null | undefined): string {
  if (ytm == null) return '—';
  const val = Number(ytm.toFixed(2));
  return `${val}%`;
}

export function formatDurationYears(val: number | null | undefined): string {
  if (val == null) return '—';
  // Входное значение может быть выражено и в днях (term_days), и в годах:
  // значения больше 30 интерпретируются как дни. Для однозначности срока
  // используйте formatTermDays.
  const years = val > 30 ? val / 365.25 : val;
  return `${years.toFixed(1)} г.`;
}

export function formatTermDays(days: number | null | undefined): string {
  if (days == null) return '—';
  return formatYears(days / 365.25);
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
  const cleanVal = (pricePct / 100) * nominal;
  const aciVal = accruedInterest && accruedInterest > 0 ? accruedInterest : 0;
  const totalVal = cleanVal + aciVal;

  const fmt = (v: number): string => {
    if (nominal <= 100) return v.toFixed(2);
    return Math.round(v).toLocaleString('ru-RU').replace(/\s/g, ' ');
  };

  const total = `${fmt(totalVal)} ${cur}`;
  if (aciVal > 0) {
    // Общая цена (чистая цена + НКД) и в скобках цена самой облигации плюс НКД.
    return `${pricePct}% · ${total} (${fmt(cleanVal)} + ${fmt(aciVal)} ${cur} НКД)`;
  }
  return `${pricePct}% · ${total}`;
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
