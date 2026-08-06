import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import BondDetailDrawer from '../components/BondDetailDrawer';

vi.mock('../demo-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../demo-api')>();
  return { ...actual, getScore: () => undefined };
});

describe('BondDetailDrawer без Score', () => {
  it('показывает предупреждение при отсутствии Score', () => {
    render(
      <BondDetailDrawer
        bondId="demo-bond-001"
        onClose={() => {}}
        onPortfolioImpact={() => {}}
        onAlert={() => {}}
        onOrder={() => {}}
      />,
    );
    expect(screen.getByText('Недостаточно данных для расчёта Score')).toBeInTheDocument();
    expect(screen.queryByText('Score')).not.toBeInTheDocument();
  });
});
