import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BondsTable, fmtDate, type SortDir } from '../components/BondsTable';
import type { Bond } from '../../../lib/api';

const bonds: Bond[] = [
  { internal_id: 'demo-bond-001', name: 'Облигация 1', issuer: 'Эмитент А', currency: 'BYN', yield_to_maturity: 12.3456, price: 99.5, coupon_rate: 8.5, coupon_frequency: 4, maturity_date: '2030-01-15', status: 'active', issuer_logo: null, fetched_at: '2026-01-01T00:00:00Z' },
  { internal_id: 'demo-bond-002', name: 'Облигация 2', issuer: null, currency: 'RUB', yield_to_maturity: 5.1, price: 101.25, coupon_rate: 4.2, coupon_frequency: 2, maturity_date: null, status: 'inactive', issuer_logo: null, fetched_at: null },
];

const baseProps = {
  loading: false,
  bonds,
  scoreMap: { 'demo-bond-001': 85.4, 'demo-bond-002': 30 },
  favorites: new Set<string>(),
  sortKey: 'score',
  sortDir: 'desc' as SortDir,
  onSort: vi.fn(),
  onToggleFav: vi.fn(),
  onExportCsv: vi.fn(),
};

describe('BondsTable', () => {
  it('рендерит строки с данными и тир-бейджами', () => {
    render(<BondsTable {...baseProps} />);
    expect(screen.getByText('Облигация 1')).toBeTruthy();
    expect(screen.getByText('Эмитент А')).toBeTruthy();
    expect(screen.getByText('12.35%')).toBeTruthy();
    expect(screen.getByText('85.4')).toBeTruthy();
    expect(screen.getByText('A')).toBeTruthy();
    expect(screen.getByText('D')).toBeTruthy();
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('показывает статус active отдельно от inactive', () => {
    render(<BondsTable {...baseProps} />);
    expect(screen.getAllByText('active')).toHaveLength(1);
    expect(screen.getAllByText('inactive')).toHaveLength(1);
  });

  it('сортировка по клику на заголовок', () => {
    render(<BondsTable {...baseProps} />);
    fireEvent.click(screen.getByText('Доходность'));
    expect(baseProps.onSort).toHaveBeenCalledWith('yield_to_maturity');
  });

  it('клик по звёздочке переключает избранное', () => {
    render(<BondsTable {...baseProps} />);
    fireEvent.click(screen.getByLabelText('В избранное: Облигация 1'));
    expect(baseProps.onToggleFav).toHaveBeenCalledWith('demo-bond-001');
  });

  it('экспорт CSV по клику', () => {
    render(<BondsTable {...baseProps} />);
    fireEvent.click(screen.getByText('Экспорт CSV'));
    expect(baseProps.onExportCsv).toHaveBeenCalledTimes(1);
  });

  it('loading state без таблицы', () => {
    render(<BondsTable {...baseProps} loading={true} />);
    expect(screen.getByText('Загрузка данных…')).toBeTruthy();
    expect(screen.queryByText('Экспорт CSV')).toBeNull();
  });

  it('пустое состояние', () => {
    render(<BondsTable {...baseProps} bonds={[]} />);
    expect(screen.getByText('Ничего не найдено. Попробуйте изменить фильтры.')).toBeTruthy();
  });

  it('длинные названия не ломают рендер (нет выброса)', () => {
    const longBond = { ...bonds[0], name: 'Длинное название '.repeat(20).trim() };
    render(<BondsTable {...baseProps} bonds={[longBond]} />);
    expect(screen.getByText(longBond.name)).toBeTruthy();
  });
});

describe('fmtDate', () => {
  it('пустая дата → тире', () => {
    expect(fmtDate(null)).toBe('—');
    expect(fmtDate(undefined)).toBe('—');
  });
});
