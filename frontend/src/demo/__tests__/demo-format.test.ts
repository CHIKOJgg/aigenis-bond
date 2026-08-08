import { describe, it, expect } from 'vitest';
import { formatYtm, formatDurationYears, formatPrice, formatPoints } from '../demo-format';

describe('formatYtm', () => {
  it('форматирует число с процентом', () => {
    expect(formatYtm(14.2)).toBe('14.2%');
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
