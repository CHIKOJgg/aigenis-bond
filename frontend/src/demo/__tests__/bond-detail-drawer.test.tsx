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
    expect(screen.getByText('61')).toBeInTheDocument();
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
});
