import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import BondScoreBadge from '../components/BondScoreBadge';
import ScoreExplanation from '../components/ScoreExplanation';
import type { DemoScore, ExplanationFactor } from '../types';

function makeScore(overrides: Partial<DemoScore> = {}): DemoScore {
  return {
    internal_id: 'test-1',
    score: 84,
    tier: 'A',
    status: 'attractive',
    computed_at: '2026-08-06T09:42:00+03:00',
    breakdown: {
      yield_component: 18.5,
      currency_component: 10.0,
      duration_component: 12.0,
      liquidity_component: 9.0,
      metal_component: 0.0,
      credit_risk_component: 12.0,
      inflation_component: 8.0,
      coupon_component: 7.5,
      volatility_component: 2.0,
      historical_volatility_component: 3.0,
      peer_relative_component: 2.0,
      reward_subtotal: 56.0,
      risk_subtotal: 5.0,
      efficiency_ratio: 9.33,
    },
    ...overrides,
  };
}

describe('BondScoreBadge', () => {
  it('отображает числовой Score для attractive', () => {
    render(<BondScoreBadge score={makeScore()} />);
    expect(screen.getByText('84')).toBeInTheDocument();
    expect(screen.getByText('/ 100')).toBeInTheDocument();
  });

  it('отображает прочерк для отсутствующего Score', () => {
    render(<BondScoreBadge score={undefined} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('отображает 0 для score=0', () => {
    render(<BondScoreBadge score={makeScore({ score: 0 })} />);
    expect(screen.getByText('0')).toBeInTheDocument();
  });
});

describe('ScoreExplanation', () => {
  const factors: ExplanationFactor[] = [
    { label: 'Доходность', direction: 'positive', plainText: 'YTM выше среднего', importance: 'high' },
    { label: 'Кредитный риск', direction: 'negative', plainText: 'Необходимо учитывать', importance: 'medium' },
    { label: 'Дюрация', direction: 'neutral', plainText: 'Средний горизонт', importance: 'low' },
  ];

  it('отображает все факторы', () => {
    render(<ScoreExplanation factors={factors} />);
    expect(screen.getByText('Доходность')).toBeInTheDocument();
    expect(screen.getByText('Кредитный риск')).toBeInTheDocument();
    expect(screen.getByText('Дюрация')).toBeInTheDocument();
  });

  it('отображает заголовок', () => {
    render(<ScoreExplanation factors={factors} />);
    expect(screen.getByText('Почему бумага в фокусе')).toBeInTheDocument();
  });

  it('отображает метку для высокозначимых факторов', () => {
    render(<ScoreExplanation factors={factors} />);
    expect(screen.getByText('значимый фактор')).toBeInTheDocument();
  });

  it('не ломается на пустом массиве', () => {
    const { container } = render(<ScoreExplanation factors={[]} />);
    expect(container.querySelector('div')).toBeInTheDocument();
  });
});
