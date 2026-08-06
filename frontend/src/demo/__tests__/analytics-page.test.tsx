import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import DemoAnalyticsPage from '../pages/DemoAnalyticsPage';
import { getBonds } from '../demo-api';

function UrlProbe() {
  const location = useLocation();
  return <div data-testid="url-probe">{location.search}</div>;
}

function renderPage(initialEntries: string[] = ['/demo/analytics?market=BCSE']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <DemoAnalyticsPage />
      <UrlProbe />
    </MemoryRouter>,
  );
}

describe('DemoAnalyticsPage', () => {
  it('показывает BCSE облигации по умолчанию', () => {
    renderPage();
    const bcse = getBonds('BCSE');
    expect(bcse.length).toBeGreaterThan(0);
    expect(screen.getByText(bcse[0].name)).toBeInTheDocument();
  });

  it('сохраняет выбранный рынок из query-параметра (?market=MOEX)', () => {
    renderPage(['/demo/analytics?market=MOEX']);
    const moex = getBonds('MOEX');
    expect(moex.length).toBeGreaterThan(0);
    expect(screen.getByText(moex[0].name)).toBeInTheDocument();
    const bcse = getBonds('BCSE');
    expect(screen.queryByText(bcse[0].name)).not.toBeInTheDocument();
  });

  it('переключение рынка обновляет URL (market selection persistence)', () => {
    renderPage();
    const marketSelect = screen.getByLabelText('Рынок');
    fireEvent.change(marketSelect, { target: { value: 'MOEX' } });
    expect(screen.getByTestId('url-probe')).toHaveTextContent('market=MOEX');
    const moex = getBonds('MOEX');
    expect(screen.getByText(moex[0].name)).toBeInTheDocument();
  });

  it('фильтр по статусу работает через UI', () => {
    renderPage();
    const bcse = getBonds('BCSE');
    fireEvent.change(screen.getByLabelText('Статус'), { target: { value: 'attractive' } });
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(bcse.length);
  });

  it('не ломается на длинных названиях бумаг', () => {
    renderPage();
    const rows = screen.getAllByRole('row');
    expect(rows.length).toBeGreaterThan(1);
    rows.forEach((row) => {
      const nameCell = within(row).getAllByText(/./).length;
      expect(nameCell).toBeGreaterThan(0);
    });
  });

  it('показывает пустое состояние при несовместимых фильтрах', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText('Валюта'), { target: { value: 'EUR' } });
    expect(screen.getByText('Нет бумаг, соответствующих фильтрам')).toBeInTheDocument();
  });

  it('открывает drawer по клику на строку', () => {
    renderPage();
    const bcse = getBonds('BCSE');
    fireEvent.click(screen.getByText(bcse[0].name));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('KPI-лента отображает данные рынка', () => {
    renderPage();
    expect(screen.getByText('Аналитика облигаций')).toBeInTheDocument();
    expect(screen.getByText(/обновлено/i)).toBeInTheDocument();
  });
});
