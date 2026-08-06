import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import BondDetailDrawer from '../components/BondDetailDrawer';

function renderDrawer(onClose = vi.fn()) {
  return render(
    <BondDetailDrawer
      bondId="demo-bond-001"
      onClose={onClose}
      onPortfolioImpact={() => {}}
      onAlert={() => {}}
      onOrder={() => {}}
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

  it('показывает недоступность действия — кнопка алерта без сайд-эффекта', () => {
    const onAlert = vi.fn();
    render(
      <BondDetailDrawer
        bondId="demo-bond-001"
        onClose={() => {}}
        onPortfolioImpact={() => {}}
        onAlert={onAlert}
        onOrder={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Создать алерт/ }));
    expect(onAlert).toHaveBeenCalledTimes(1);
  });
});
