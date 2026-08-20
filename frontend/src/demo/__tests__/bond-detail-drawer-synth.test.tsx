import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import BondDetailDrawer from '../components/BondDetailDrawer';

const bond = {
  internal_id: 'live-synth',
  isin: null,
  name: 'live-synth',
  issuer: null,
  issuer_logo: null,
  currency: 'BYN',
  nominal: 100,
  coupon_rate: null,
  coupon_frequency: null,
  maturity_date: null,
  price: null,
  yield_to_maturity: null,
  amortization: null,
  market: 'bcse',
  status: 'active',
  is_government: false,
  in_stock: null,
  guarantor: null,
  maturity_term_text: null,
  coupon_description: null,
  fetched_at: null,
  term_days: null,
} as any;

const score = {
  score: 42,
  status: 'review',
  breakdown: {
    yield_component: 12,
    coupon_component: 2,
    currency_component: 1,
    inflation_component: 4,
    liquidity_component: 3,
    duration_component: -2,
    credit_risk_component: -8,
    volatility_component: 1,
    historical_volatility_component: 0,
    peer_relative_component: 5,
    metal_component: 0,
  },
} as any;

describe('BondDetailDrawer: синтез объяснения', () => {
  it('рендерит синтезированное объяснение при отсутствии explanation', () => {
    render(
      <BondDetailDrawer
        bondId="live-synth"
        bond={bond}
        score={score}
        onClose={() => {}}
        onPortfolioImpact={() => {}}
      />,
    );
    // ScoreExplanation рендерится только если factors.length > 0 (т.е. синтез сработал)
    expect(screen.getByText('Почему такой рейтинг')).toBeInTheDocument();
    expect(
      screen.getAllByText(/улучшает рейтинг на 12\.0 п\./).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/ухудшает рейтинг на 8\.0 п\./).length,
    ).toBeGreaterThan(0);
  });
});
