import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DemoSearchPage from '../pages/DemoSearchPage';
import GlobalBondDrawer from '../components/GlobalBondDrawer';

vi.mock('../live-demo-api', () => ({
  fetchLiveSearch: vi.fn(async (q = '') => {
    if (q.toLowerCase().includes('газпром')) {
      return [
        {
          internal_id: 'gazprom-01',
          name: 'Газпром Капитал БО-002P-01',
          market: 'moex',
          currency: 'RUB',
          yield_to_maturity: 15.5,
          price: 99.2,
          tier: 'A',
          score: 82.0,
          score_status: 'ok',
          distressed: false,
        },
      ];
    }
    return [
      {
        internal_id: 'bcse-01',
        name: 'Минфин Выпуск 320',
        market: 'bcse',
        currency: 'USD',
        yield_to_maturity: 6.8,
        price: 100.0,
        tier: 'S',
        score: 88.5,
        score_status: 'ok',
        distressed: false,
      },
    ];
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DemoSearchPage />
      <GlobalBondDrawer />
    </MemoryRouter>
  );
}

describe('DemoSearchPage', () => {
  it('выполняет поиск и отображает карточки найденных облигаций', async () => {
    renderPage();
    expect(screen.getByPlaceholderText(/Введите название, эмитента, ISIN или код…/i)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/Введите название, эмитента, ISIN или код…/i);
    fireEvent.change(input, { target: { value: 'Газпром' } });

    await waitFor(() => {
      expect(screen.getByText('Газпром Капитал БО-002P-01')).toBeInTheDocument();
    });
  });
});
