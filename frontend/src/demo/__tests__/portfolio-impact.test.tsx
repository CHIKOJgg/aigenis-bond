import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PortfolioImpactCard from '../components/PortfolioImpactCard';
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

describe('PortfolioImpactCard', () => {
  it('оценивает эффект по фактической доходности для обычной бумаги', () => {
    render(<PortfolioImpactCard bondId="live-001" allocationPct={10} bond={makeBond({ yield_to_maturity: 9.5 })} />);
    expect(screen.getByText(/После добавления 10% позиции/)).toBeInTheDocument();
    expect(screen.queryByText(/Дистрибуция/)).not.toBeInTheDocument();
  });

  it('не засчитывает недостижимый YTM дистрибуции и показывает предупреждение', () => {
    render(
      <PortfolioImpactCard
        bondId="live-001"
        allocationPct={10}
        bond={makeBond({ distressed: true })}
      />,
    );
    expect(screen.getByText(/Дистрибуция: цена ниже 80%/)).toBeInTheDocument();
    expect(screen.getByText(/консервативной доходности 20%/)).toBeInTheDocument();
  });
});
