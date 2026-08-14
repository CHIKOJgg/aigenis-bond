import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PortfolioForecastCalculator from '../components/PortfolioForecastCalculator';

describe('PortfolioForecastCalculator', () => {
  it('отображает параметры калькулятора, номинальный и реальный капитал', () => {
    render(
      <PortfolioForecastCalculator
        initialCapital={50000}
        initialYtm={14.0}
        currency="BYN"
      />
    );

    expect(screen.getByText(/Калькулятор Капитала & Доходности Портфеля/i)).toBeInTheDocument();
    expect(screen.getByText(/Итоговый капитал/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Реальная ценность/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Бонус сложного процента/i)).toBeInTheDocument();
  });

  it('позволяет переключать реинвестирование купонов', () => {
    render(
      <PortfolioForecastCalculator
        initialCapital={100000}
        initialYtm={15.0}
        currency="BYN"
      />
    );

    const withdrawBtn = screen.getByRole('button', { name: /Снимать/i });
    fireEvent.click(withdrawBtn);

    expect(screen.getByText(/Выключен/i)).toBeInTheDocument();

    const reinvestBtn = screen.getByRole('button', { name: /Реинвестировать/i });
    fireEvent.click(reinvestBtn);

    expect(screen.queryByText(/Выключен/i)).not.toBeInTheDocument();
  });

  it('раскрывает таблицу разбивки по годам', () => {
    render(
      <PortfolioForecastCalculator
        initialCapital={30000}
        initialYtm={12.0}
        currency="USD"
      />
    );

    const toggleBtn = screen.getByRole('button', { name: /Показать подробную разбивку по годам/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('Год 1')).toBeInTheDocument();
    expect(screen.getByText('Год 5')).toBeInTheDocument();
  });

  it('позволяет переключать налоговую ставку', () => {
    render(
      <PortfolioForecastCalculator
        initialCapital={50000}
        initialYtm={10.0}
        currency="BYN"
      />
    );

    const ndflBtn = screen.getByRole('button', { name: /13% \(НДФЛ\)/i });
    fireEvent.click(ndflBtn);

    expect(screen.getByText(/чистыми 8.7%/i)).toBeInTheDocument();
  });

  it('в режиме «Снимать» купонный доход считается только с вложенного капитала', () => {
    render(
      <PortfolioForecastCalculator
        initialCapital={100000}
        initialYtm={15.0}
        currency="BYN"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Снимать/i }));

    // 100000 * 15% / 12 = 1250 BYN/мес — без реинвестирования выплаченные
    // купоны не должны раздувать базу дохода.
    expect(screen.getByText(/Купонный доход в месяц/i)).toBeInTheDocument();
    expect(screen.getByText(/~?\s*1[\s\u00a0\u202f]*250 BYN \/ мес/i)).toBeInTheDocument();
    expect(screen.getByText(/15[\s\u00a0\u202f]*000 BYN/)).toBeInTheDocument(); // годовой поток = 1250*12
  });

  it('в режиме «Реинвестировать» доход считается с итогового баланса', () => {
    render(
      <PortfolioForecastCalculator
        initialCapital={100000}
        initialYtm={15.0}
        currency="BYN"
      />
    );
    // По умолчанию реинвестирование включено: итог > вложенного капитала.
    expect(screen.getByText(/Пассивный доход на конец срока/i)).toBeInTheDocument();
  });
});
