import { describe, it, expect } from 'vitest';
import { formatYtm, formatDurationYears, formatPrice, formatPoints, formatBondDisplayName } from '../demo-format';

describe('formatYtm', () => {
  it('форматирует число с процентом', () => {
    expect(formatYtm(14.2)).toBe('14.2%');
    expect(formatYtm(25.1135)).toBe('25.11%');
  });

  it('форматирует ноль', () => {
    expect(formatYtm(0)).toBe('0%');
  });

  it('возвращает прочерк для null/undefined', () => {
    expect(formatYtm(null)).toBe('—');
    expect(formatYtm(undefined)).toBe('—');
  });
});

describe('formatDurationYears', () => {
  it('переводит дни в годы с одним знаком', () => {
    expect(formatDurationYears(365)).toBe('1.0 г.');
    expect(formatDurationYears(1095)).toBe('3.0 г.');
    expect(formatDurationYears(456.5625)).toBe('1.3 г.');
  });

  it('возвращает прочерк для null/undefined', () => {
    expect(formatDurationYears(null)).toBe('—');
    expect(formatDurationYears(undefined)).toBe('—');
  });
});

describe('formatPrice', () => {
  it('форматирует цену как % от номинала', () => {
    expect(formatPrice(98.5, 'BYN')).toBe('98.5%');
  });

  it('округляет до двух знаков и отбрасывает пустые нули', () => {
    expect(formatPrice(100.187, 'BYN')).toBe('100.19%');
    expect(formatPrice(92, 'USD')).toBe('92%');
  });

  it('рассчитывает цену в валюте от реального номинала', () => {
    expect(formatPrice(100.71, 'BYN', 200)).toBe('100.71% (201 BYN)');
    expect(formatPrice(100.09, 'BYN', 100)).toBe('100.09% (100.09 BYN)');
    expect(formatPrice(104.38, 'BYN', 1000)).toBe('104.38% (1 044 BYN)');
  });

  it('добавляет НКД к стоимости лота', () => {
    expect(formatPrice(100.0, 'BYN', 1000, 25.5)).toBe('100% (1 026 BYN)');
    expect(formatPrice(100.0, 'BYN', 100, 2.5)).toBe('100% (102.50 BYN)');
  });

  it('возвращает прочерк для null/undefined', () => {
    expect(formatPrice(null)).toBe('—');
    expect(formatPrice(undefined, 'USD')).toBe('—');
  });
});

describe('formatPoints', () => {
  it('показывает знак для не нуля', () => {
    expect(formatPoints(18.5)).toBe('+18.5');
    expect(formatPoints(-3)).toBe('-3');
    expect(formatPoints(0)).toBe('0');
    expect(formatPoints(null)).toBe('—');
  });
});

describe('formatBondDisplayName', () => {
  it('различает выпуски Минфина по internal_id', () => {
    expect(formatBondDisplayName('Министерство финансов Республики Беларусь', '004405')).toBe('Минфин РБ (выпуск 004405)');
    expect(formatBondDisplayName('Министерство финансов Республики Беларусь', 'MF-LB-BYN-0405')).toBe('Минфин РБ (выпуск 0405)');
  });

  it('сохраняет обычные названия эмитентов', () => {
    expect(formatBondDisplayName('АВАНГАРД ЛИЗИНГ Оп64', 'BCSE-0064')).toBe('АВАНГАРД ЛИЗИНГ Оп64');
  });
});
