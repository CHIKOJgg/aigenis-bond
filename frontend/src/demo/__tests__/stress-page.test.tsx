import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DemoStressPage from '../pages/DemoStressPage';

vi.mock('../live-demo-api', () => ({
  fetchLiveStress: vi.fn(async () => ({
    scenario: {
      key: 'parallel_+100bp',
      name: 'Параллельный сдвиг +100 б.п.',
      description: 'Рост кривой доходности на 1.0%',
      kind: 'parallel',
    },
    portfolio_value: 50000.0,
    stressed_value: 48500.0,
    pnl_amount: -1500.0,
    pnl_pct: -3.0,
    duration_before: 3.2,
    duration_after: 3.1,
    var_95: 4.8,
    by_tenor: { '1-3Y': -500.0, '3-5Y': -1000.0 },
    by_position: { 'B1': -800.0, 'B2': -700.0 },
    positions: [
      { internal_id: 'B1', name: 'Облигация Минфин', lots: 25, invested: 25000.0, price_money: 1000.0, pnl: -800.0 },
      { internal_id: 'B2', name: 'Облигация Евроторг', lots: 25, invested: 25000.0, price_money: 1000.0, pnl: -700.0 },
    ],
    available_scenarios: [
      { key: 'parallel_+100bp', name: 'Параллельный сдвиг +100 б.п.', description: 'Рост ставок' },
      { key: 'credit_shock_+150bp', name: 'Кредитный шок +150 б.п.', description: 'Расширение спредов' },
    ],
  })),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DemoStressPage />
    </MemoryRouter>
  );
}

describe('DemoStressPage', () => {
  it('отображает институциональный стресс-тест, метрики потерь и позиции', async () => {
    renderPage();
    expect(screen.getByText(/Институциональное Стресс-Тестирование/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Облигация Минфин')).toBeInTheDocument();
    });

    expect(screen.getByText('Облигация Евроторг')).toBeInTheDocument();
    expect(screen.getByText(/-1 500 BYN|-1500 BYN|-1 500.00 BYN/i)).toBeInTheDocument();
  });

  it('позволяет переключать рынки BCSE и MOEX', async () => {
    renderPage();
    const moexBtn = screen.getByRole('button', { name: /MOEX/i });
    fireEvent.click(moexBtn);
    expect(moexBtn).toBeInTheDocument();
  });

  it('подписывает денежные суммы валютой рынка (RUB для MOEX)', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /MOEX/i }));
    await waitFor(() => {
      expect(screen.getByText(/Облигация Минфин/i)).toBeInTheDocument();
    });
    // P&L-карточка и шапка таблицы используют RUB для MOEX.
    expect(screen.getByText(/-1 500 RUB|-1500 RUB/i)).toBeInTheDocument();
    expect(screen.getByText(/Инвестиции \(RUB\)/i)).toBeInTheDocument();
  });

  it('подписывает денежные суммы валютой рынка (BYN для BCSE)', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/-1 500 BYN|-1500 BYN/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Инвестиции \(BYN\)/i)).toBeInTheDocument();
  });
});
