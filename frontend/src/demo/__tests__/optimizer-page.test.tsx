import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DemoOptimizerPage from '../pages/DemoOptimizerPage';

vi.mock('../live-demo-api', () => ({
  fetchLiveOptimize: vi.fn(async () => ({
    strategy: 'Balanced',
    capital: 50000.0,
    currency: 'BYN',
    metrics: {
      expected_return: 13.5,
      volatility: 2.1,
      sharpe: 4.8,
      sortino: 6.2,
      max_drawdown_pct: 3.1,
      var_95: 3.45,
    },
    allocations: [
      { internal_id: 'B1', name: 'Облигация Минфин', weight_pct: 50.0, amount: 25000.0, price_pct: 100.0, ytm: 14.0 },
      { internal_id: 'B2', name: 'Облигация Ритейл', weight_pct: 50.0, amount: 25000.0, price_pct: 98.0, ytm: 13.0 },
    ],
    order_tickets: [
      { action: 'BUY', internal_id: 'B1', name: 'Облигация Минфин', lots: 25, price_pct: 100.0, total_nominal: 25000.0 },
    ],
    available_strategies: ['Conservative', 'Balanced', 'Aggressive'],
  })),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DemoOptimizerPage />
    </MemoryRouter>
  );
}

describe('DemoOptimizerPage', () => {
  it('отображает параметры стратегии, метрики риска и сгенерированные ордера', async () => {
    renderPage();
    expect(screen.getByText(/Институциональный Оптимизатор Портфеля/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/13.5% годовых/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText('Облигация Минфин').length).toBeGreaterThanOrEqual(1);
  });

  it('позволяет переключать стратегии и валюты', async () => {
    renderPage();
    const usdBtn = screen.getByRole('button', { name: /USD/i });
    fireEvent.click(usdBtn);
    expect(usdBtn).toBeInTheDocument();
  });

  it('открывает drawer с аналитикой при клике на строку облигации в аллокации', async () => {
    const { bondDrawerStore } = await import('../drawer-store');
    const openSpy = vi.spyOn(bondDrawerStore, 'open');

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/13.5% годовых/i)).toBeInTheDocument();
    });

    const bondCells = screen.getAllByText('Облигация Минфин');
    fireEvent.click(bondCells[0]);

    expect(openSpy).toHaveBeenCalledWith('B1');
  });
});

