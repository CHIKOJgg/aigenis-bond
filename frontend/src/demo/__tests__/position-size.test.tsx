import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PositionSizeControl from '../components/PositionSizeControl';
import type { DemoBond } from '../types';

function makeBond(overrides: Partial<DemoBond> = {}): DemoBond {
  return {
    internal_id: 'live-001',
    isin: 'XS0000000000',
    name: 'Тестовая облигация',
    issuer: 'Тест',
    issuer_logo: null,
    market: 'MOEX',
    currency: 'USD',
    price: 75.1,
    yield_to_maturity: 36.09,
    coupon_rate: 2.2,
    coupon_frequency: 2,
    nominal: 1000,
    maturity_date: '2027-05-23',
    status: 'active',
    is_government: false,
    in_stock: null,
    guarantor: null,
    maturity_term_text: null,
    coupon_description: null,
    amortization: null,
    fetched_at: null,
    term_days: null,
    ...overrides,
  };
}

describe('PositionSizeControl', () => {
  it('показывает пресеты процентов с суммой в BYN', () => {
    render(<PositionSizeControl bond={makeBond()} allocationPct={10} onChange={() => {}} />);
    expect(screen.getByText('10% (5 000 BYN)')).toBeInTheDocument();
    expect(screen.getByText('15% (7 500 BYN)')).toBeInTheDocument();
  });

  it('переводит сумму в BYN в процент портфеля', () => {
    const onChange = vi.fn();
    render(<PositionSizeControl bond={makeBond()} allocationPct={10} onChange={onChange} />);
    fireEvent.click(screen.getByText('Сумма (BYN)'));
    const input = screen.getByLabelText('Сумма позиции в BYN');
    fireEvent.change(input, { target: { value: '5000' } });
    expect(onChange).toHaveBeenLastCalledWith(10);
  });

  it('переводит количество бумаг в сумму и процент', () => {
    const onChange = vi.fn();
    render(<PositionSizeControl bond={makeBond()} allocationPct={10} onChange={onChange} />);
    fireEvent.click(screen.getByText('Кол-во (шт)'));
    const input = screen.getByLabelText('Количество облигаций');
    fireEvent.change(input, { target: { value: '10' } });
    // 10 шт x 1 000 номинал x 75.1% = 7 510 BYN = 15.02% портфеля
    expect(onChange).toHaveBeenLastCalledWith(15.02);
    expect(screen.getByText(/7 510 BYN/)).toBeInTheDocument();
  });

  it('блокирует количество без выбранной бумаги', () => {
    render(<PositionSizeControl bond={undefined} allocationPct={10} onChange={() => {}} />);
    fireEvent.click(screen.getByText('Кол-во (шт)'));
    expect(screen.getByLabelText('Количество облигаций')).toBeDisabled();
    expect(screen.getByText(/выберите облигацию/i)).toBeInTheDocument();
  });
});
