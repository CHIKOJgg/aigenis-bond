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
});
