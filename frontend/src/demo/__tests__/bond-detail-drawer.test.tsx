import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import BondDetailDrawer from '../components/BondDetailDrawer';

function renderDrawer(onClose = vi.fn()) {
  return render(
    <BondDetailDrawer
      bondId="demo-bond-001"
      onClose={onClose}
      onPortfolioImpact={() => {}}
    />,
  );
}

describe('BondDetailDrawer', () => {
  it('рендерит dialog с aria-modal и названием', () => {
    renderDrawer();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName();
  });

  it('кнопка закрытия имеет aria-label', () => {
    renderDrawer();
    expect(screen.getByRole('button', { name: 'Закрыть' })).toBeInTheDocument();
  });

  it('Escape вызывает onClose', () => {
    const onClose = vi.fn();
    renderDrawer(onClose);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('клик по оверлею вызывает onClose', () => {
    const onClose = vi.fn();
    const { container } = renderDrawer(onClose);
    const overlay = container.querySelector('[aria-hidden="true"]');
    expect(overlay).not.toBeNull();
    fireEvent.click(overlay!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('перемещает фокус внутрь панели при открытии', () => {
    renderDrawer();
    expect(screen.getByRole('button', { name: 'Закрыть' })).toHaveFocus();
  });

  it('Tab с последнего элемента циклически возвращает на первый', () => {
    renderDrawer();
    const buttons = screen.getAllByRole('button');
    const last = buttons[buttons.length - 1];
    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByRole('button', { name: 'Закрыть' })).toHaveFocus();
  });

  it('Shift+Tab с первого элемента переходит на последний', () => {
    renderDrawer();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    const buttons = screen.getAllByRole('button');
    expect(buttons[buttons.length - 1]).toHaveFocus();
  });

  it('показывает Score, вердикт и плюсы/минусы из фикстурного объяснения', () => {
    renderDrawer();
    expect(screen.getByText('69')).toBeInTheDocument();
    expect(screen.getByText(/Нейтральна/)).toBeInTheDocument();
    expect(screen.getByText(/Умеренно интересна/)).toBeInTheDocument();
    expect(screen.getByText('Плюсы и минусы')).toBeInTheDocument();
    expect(screen.getAllByText(/доходность к погашению 13\.4%/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Государственный эмитент — минимальный кредитный риск/).length).toBeGreaterThan(0);
  });

  it('показывает состав оценки с компонентами breakdown', () => {
    renderDrawer();
    expect(screen.getByText('Состав оценки')).toBeInTheDocument();
    expect(screen.getAllByText('Доходность').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Кредитный риск').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Ликвидность').length).toBeGreaterThan(0);
    expect(screen.getByText('Эффективность доходность/риск')).toBeInTheDocument();
  });

  it('показывает ключевые показатели', () => {
    renderDrawer();
    expect(screen.getByText('Ключевые показатели')).toBeInTheDocument();
    expect(screen.getByText('13.38%')).toBeInTheDocument();
    expect(screen.getByText('12.5%')).toBeInTheDocument();
  });

  it('кнопка "Влияние на портфель" вызывается при клике', () => {
    const onPI = vi.fn();
    render(
      <BondDetailDrawer
        bondId="demo-bond-001"
        onClose={() => {}}
        onPortfolioImpact={onPI}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Влияние на портфель/ }));
    expect(onPI).toHaveBeenCalledTimes(1);
  });

  it('рендерит купонный график: даты слева, суммы купонов справа', () => {
    renderDrawer();
    expect(screen.getByText('Купонные выплаты')).toBeInTheDocument();
    // demo-bond-001: {"2026-12-15": ["6.25 BYN"], ..., "2028-06-15": ["106.25 BYN"]}
    expect(screen.getByText('15.12.2026')).toBeInTheDocument();
    expect(screen.getAllByText('6.25 BYN').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('106.25 BYN')).toBeInTheDocument();
  });

  it('купонный график из live-детали имеет приоритет над фикстурой', () => {
    render(
      <BondDetailDrawer
        bondId="demo-bond-001"
        onClose={() => {}}
        onPortfolioImpact={() => {}}
        detail={{
          internal_id: 'demo-bond-001',
          isin: null,
          name: 'demo-bond-001',
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
          history: [],
          coupon_schedule: { '2031-01-01': ['99.99 BYN'] },
        }}
      />,
    );
    expect(screen.getByText('01.01.2031')).toBeInTheDocument();
    expect(screen.getByText('99.99 BYN')).toBeInTheDocument();
  });

  it('показывает заглушку, когда график купонов не предоставлен', () => {
    render(
      <BondDetailDrawer
        bondId="live-custom"
        onClose={() => {}}
        onPortfolioImpact={() => {}}
        bond={{
          internal_id: 'live-custom',
          isin: null,
          name: 'live-custom',
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
        }}
        detail={{
          internal_id: 'live-custom',
          isin: null,
          name: 'live-custom',
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
          history: [],
          coupon_schedule: {},
        }}
      />,
    );
    expect(screen.getByText('График не предоставлен')).toBeInTheDocument();
  });
});
