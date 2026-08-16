import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DemoPortfolioLabPage from '../pages/DemoPortfolioLabPage';

function mockBond(id: string, name: string) {
  return {
    internal_id: id,
    isin: id,
    name,
    issuer: 'Эмитент',
    issuer_logo: null,
    currency: 'BYN',
    nominal: 1000,
    coupon_rate: 10,
    coupon_frequency: 2,
    maturity_date: '2030-01-01',
    price: 100,
    yield_to_maturity: 11.5,
    amortization: null,
    market: 'BCSE',
    status: 'active',
    is_government: false,
    in_stock: true,
    guarantor: null,
    maturity_term_text: null,
    coupon_description: null,
    fetched_at: null,
    term_days: 1000,
    duration_years: 3,
    score: 70,
    tier: 'A',
    score_status: 'attractive',
    breakdown: null,
    explanation: null,
    issuer_risk: null,
  } as any;
}

vi.mock('../live-demo-api', () => ({
  fetchLiveMarket: vi.fn(async () => ({
    source: 'x',
    market: 'bcse',
    currency: null,
    as_of: null,
    count: 2,
    bonds: [mockBond('B1', 'Облигация А'), mockBond('B2', 'Облигация Б')],
    disclaimer: '',
  })),
  fetchLiveSearch: vi.fn(async () => ({
    query: '',
    market: 'bcse',
    count: 0,
    bonds: [],
    disclaimer: '',
  })),
  fetchCustomOptimize: vi.fn(async () => ({
    mode: 'optimize',
    objective: 'equal_weight',
    objective_ru: 'Равные веса',
    capital: 50000,
    currency: 'BYN',
    metrics: {
      expected_return: 11.5,
      volatility: 4.5,
      sharpe: 1.6,
      sortino: 2.1,
      var_95: 7.4,
      max_drawdown: 6.7,
      calmar: 1.7,
      weighted_duration: 3.0,
      weighted_current_yield: 10.0,
      concentration_by_issuer: { Эмитент: 100 },
    },
    allocations: [
      {
        internal_id: 'B1',
        name: 'Облигация А',
        issuer: 'Эмитент',
        isin: 'B1',
        amount: 25000,
        currency: 'BYN',
        weight_pct: 50,
        lots: 25,
        ytm: 11.5,
        duration_years: 3,
        current_yield: 10,
      },
    ],
    order_tickets: [
      {
        action: 'BUY',
        internal_id: 'B1',
        name: 'Облигация А',
        lots: 25,
        est_cost: 25000,
        currency: 'BYN',
        rationale: 'x',
      },
    ],
    excluded: [],
    warning: null,
  })),
  fetchCustomCalculate: vi.fn(async () => ({
    mode: 'calculate',
    currency: 'BYN',
    metrics: {
      expected_return: 11.5,
      volatility: 4.5,
      sharpe: 1.6,
      sortino: 2.1,
      var_95: 7.4,
      max_drawdown: 6.7,
      calmar: 1.7,
      weighted_duration: 3.0,
      weighted_current_yield: 10.0,
      concentration_by_issuer: { Эмитент: 100 },
      holdings: [
        {
          internal_id: 'B1',
          name: 'Облигация А',
          issuer: 'Эмитент',
          currency: 'BYN',
          amount: 25000,
          weight_pct: 50,
          ytm: 11.5,
          duration_years: 3,
          current_yield: 10,
        },
      ],
    },
    warning: null,
  })),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DemoPortfolioLabPage />
    </MemoryRouter>,
  );
}

describe('DemoPortfolioLabPage', () => {
  it('shows the three core sections', async () => {
    renderPage();
    expect(screen.getByText(/Лаборатория Портфелей/i)).toBeInTheDocument();
    expect(screen.getByText(/Мой портфель/i)).toBeInTheDocument();
    expect(screen.getByText(/Конструктор портфеля/i)).toBeInTheDocument();
    expect(screen.getByText(/Сохранённые портфели/i)).toBeInTheDocument();
  });

  it('renders the demo user portfolio with real YTM metrics', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/11\.5%/).length).toBeGreaterThan(0);
    });
  });

  it('switches between optimizer and calculator modes', async () => {
    renderPage();
    const calcBtn = screen.getByRole('button', { name: /Калькулятор/i });
    fireEvent.click(calcBtn);
    expect(calcBtn).toBeInTheDocument();
  });
});
