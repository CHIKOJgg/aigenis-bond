import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import DemoAnalyticsPage from '../pages/DemoAnalyticsPage';
import GlobalBondDrawer from '../components/GlobalBondDrawer';
import { getBonds } from '../demo-api';

vi.mock('../live-demo-api', () => ({
  fetchLiveMarket: vi.fn(async (market = 'bcse') => {
    const { getBonds } = await import('../demo-api');
    const bonds = getBonds(market.toUpperCase());
    return {
      source: 'test live source',
      market,
      currency: null,
      as_of: '2026-08-10T15:07:49.000Z',
      count: bonds.length,
      bonds,
      disclaimer: 'test live data',
    };
  }),
  fetchLiveBond: vi.fn(async (internalId: string) => {
    const { getAllBonds, getScore } = await import('../demo-api');
    const bond = getAllBonds().find((item) => item.internal_id === internalId);
    if (!bond) throw new Error('not found');
    const score = getScore(internalId);
    return {
      ...bond,
      score: score?.score ?? null,
      tier: score?.tier ?? null,
      score_status: score?.status ?? null,
      breakdown: score?.breakdown ?? null,
      history: [],
      coupon_schedule: null,
    };
  }),
}));

function UrlProbe() {
  const location = useLocation();
  return <div data-testid="url-probe">{location.search}</div>;
}

function renderPage(initialEntries: string[] = ['/demo/analytics?market=BCSE']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <DemoAnalyticsPage />
      <GlobalBondDrawer />
      <UrlProbe />
    </MemoryRouter>,
  );
}

describe('DemoAnalyticsPage', () => {
  it('показывает BCSE облигации по умолчанию', async () => {
    renderPage();
    const bcse = getBonds('BCSE');
    expect(bcse.length).toBeGreaterThan(0);
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByText(bcse[0].name)).toBeInTheDocument();
  });

  it('сохраняет выбранный рынок из query-параметра (?market=MOEX)', async () => {
    renderPage(['/demo/analytics?market=MOEX']);
    const moex = getBonds('MOEX');
    expect(moex.length).toBeGreaterThan(0);
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByText(moex[0].name)).toBeInTheDocument();
    const bcse = getBonds('BCSE');
    expect(screen.queryByText(bcse[0].name)).not.toBeInTheDocument();
  });

  it('переключение рынка обновляет URL (market selection persistence)', async () => {
    renderPage();
    expect(await screen.findByRole('table')).toBeInTheDocument();
    const marketSelect = screen.getByLabelText('Рынок');
    fireEvent.change(marketSelect, { target: { value: 'MOEX' } });
    expect(screen.getByTestId('url-probe')).toHaveTextContent('market=MOEX');
    const moex = getBonds('MOEX');
    expect(await screen.findByText(moex[0].name)).toBeInTheDocument();
  });

  it('фильтр по статусу работает через UI', async () => {
    renderPage();
    expect(await screen.findByRole('table')).toBeInTheDocument();
    const bcse = getBonds('BCSE');
    fireEvent.change(screen.getByLabelText('Статус'), { target: { value: 'high_risk' } });
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(bcse.length);
  });

  it('не ломается на длинных названиях бумаг', async () => {
    renderPage();
    const rows = await screen.findAllByRole('row');
    expect(rows.length).toBeGreaterThan(1);
    rows.forEach((row) => {
      const nameCell = within(row).getAllByText(/./).length;
      expect(nameCell).toBeGreaterThan(0);
    });
  });

  it('показывает пустое состояние при несовместимых фильтрах', async () => {
    renderPage();
    expect(await screen.findByRole('table')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Валюта'), { target: { value: 'EUR' } });
    expect(screen.getByText('Нет бумаг, соответствующих фильтрам')).toBeInTheDocument();
  });

  it('открывает drawer по клику на строку', async () => {
    renderPage();
    const bcse = getBonds('BCSE');
    expect(await screen.findByRole('table')).toBeInTheDocument();
    fireEvent.click(screen.getByText(bcse[0].name));
    const dialog = await screen.findByRole('dialog', { name: bcse[0].name });
    expect(dialog).toBeInTheDocument();
    expect((await screen.findAllByText('Score', { exact: false })).length).toBeGreaterThan(0);
  });

  it('KPI-лента отображает данные рынка', async () => {
    renderPage();
    expect(screen.getByText('Аналитика облигаций')).toBeInTheDocument();
    expect(await screen.findByText(/обновлено/i)).toBeInTheDocument();
  });

  it('market=ALL объединяет оба рынка в одну таблицу', async () => {
    renderPage(['/demo/analytics?market=ALL']);
    expect(await screen.findByRole('table')).toBeInTheDocument();
    const bcse = getBonds('BCSE');
    const moex = getBonds('MOEX');
    // Оба рынка представлены (названия могут повторяться между рынками).
    expect(screen.getAllByText(bcse[0].name).length).toBeGreaterThan(0);
    expect(screen.getAllByText(moex[0].name).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Рынок')).toHaveValue('ALL');
  });

  it('рынок ALL доступен в селекторе и переключается в URL', async () => {
    renderPage();
    expect(await screen.findByRole('table')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Рынок'), { target: { value: 'ALL' } });
    expect(screen.getByTestId('url-probe')).toHaveTextContent('market=ALL');
    const bcse = getBonds('BCSE');
    const moex = getBonds('MOEX');
    expect((await screen.findAllByText(moex[0].name)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(bcse[0].name).length).toBeGreaterThan(0);
  });
});
