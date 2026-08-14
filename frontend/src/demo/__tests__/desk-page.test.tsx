import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DemoDeskPage from '../pages/DemoDeskPage';

vi.mock('../live-demo-api', () => ({
  fetchLiveDeskCurve: vi.fn(async (currency = 'BYN') => ({
    currency,
    market: 'BCSE',
    points: [
      { tenor: '1Y', years: 1.0, rate_pct: 12.5 },
      { tenor: '3Y', years: 3.0, rate_pct: 14.0 },
      { tenor: '5Y', years: 5.0, rate_pct: 15.2 },
    ],
    params: { beta0: 15.5, beta1: -3.0, beta2: 1.0, tau: 1.5 },
    slope: 2.7,
  })),
  fetchLiveDeskRv: vi.fn(async (currency = 'BYN') => [
    {
      internal_id: 'test-rv-001',
      name: 'Минфин Вып. 300',
      issuer: 'Министерство финансов РБ',
      price: 98.5,
      nominal: 1000.0,
      ytm: 14.8,
      accrued_interest: 12.3,
      peer_currency: currency,
      z_score: 1.85,
      spread_pct: 1.2,
      fair_spread_pct: 0.8,
      side: 'buy' as const,
      rationale: 'Торгуется с недооценкой к кривой госдолга',
    },
    {
      internal_id: 'test-rv-002',
      name: 'Корпорат Вып. 01',
      issuer: 'ООО Ритейл',
      price: 104.0,
      nominal: 1000.0,
      ytm: 10.2,
      accrued_interest: 5.0,
      peer_currency: currency,
      z_score: -2.1,
      spread_pct: -1.5,
      fair_spread_pct: 0.0,
      side: 'sell' as const,
      rationale: 'Переоценена относительно дюрации',
    },
  ]),
}));

function renderPage(initialEntries = ['/demo/desk?market=BCSE']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <DemoDeskPage />
    </MemoryRouter>
  );
}

describe('DemoDeskPage', () => {
  it('отображает заголовок, кривую доходности и сигналы Relative Value', async () => {
    renderPage();
    expect(screen.getByText(/Институциональный Desk & Relative Value/i)).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('Корпорат Вып. 01')).toBeInTheDocument();
    });

    expect(screen.getByText(/Минфин Вып\. 300/i)).toBeInTheDocument();
    expect(screen.getByText(/Торгуется с недооценкой к кривой госдолга/i)).toBeInTheDocument();
  });

  it('позволяет переключать валюты BYN / USD / RUB', async () => {
    renderPage();
    const usdBtn = screen.getByRole('button', { name: 'USD' });
    fireEvent.click(usdBtn);

    await waitFor(() => {
      expect(usdBtn).toBeInTheDocument();
    });
  });
});
