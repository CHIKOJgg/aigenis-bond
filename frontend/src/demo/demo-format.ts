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
  return formatYears(years);
}

export function formatTermDays(days: number | null | undefined): string {
  if (days == null) return '—';
  return formatYears(days / 365.25);
}

export function formatYears(years: number | null | undefined): string {
  if (years == null) return '—';
  // Короткие бумаги (дюрация меньше ~36 дней) не должны превращаться в
  // обманчивое «0.0 г.»: показываем 2 знака, иначе 0.04 г. выглядит как
  // нулевой срок. От 0.1 года и выше одного знака достаточно.
  const precision = Math.abs(years) < 0.1 ? 2 : 1;
  return `${years.toFixed(precision)} г.`;
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
  // НКД показываем только когда он реально ощутим (>0.005), чтобы не выводить
  // обманчивое «+ 0 НКД» для бескупонных/индексируемых бумаг. Когда НКД есть,
  // выводим общую цену и в скобках цену самой облигации плюс накопленный купон.
  if (aciVal > 0.005) {
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
  const humanized = cleanName.replace(
    /MF-(LB|SB)-(BYN|USD|RUB)-0?(\d+)/gi,
    (_match, _kind: string, cur: string, num: string) => `ВГДО ${num} (${cur})`,
  ).replace(/demo-bond-minfin-usd-0?(\d+)/gi, 'ВГДО $1 (USD)');

  // Если это generic-заголовок "Министерство финансов" без номера выпуска
  if (/^министерство финансов( республики беларусь)?$/i.test(humanized) || humanized.toLowerCase() === 'минфин') {
    const rawCode = internalId ? internalId.replace(/^(demo-bond-)?(BCSE|MOEX|MF-(?:LB|SB)-(?:BYN|USD|RUB))-?/i, '') : (isin ?? '');
    if (rawCode) {
      return `Минфин РБ (выпуск ${rawCode})`;
    }
    return `Минфин РБ`;
  }

  return humanized;
}
