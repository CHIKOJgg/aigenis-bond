import { useEffect, useRef, type ReactNode } from 'react';

interface ModalProps {
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
  className?: string;
  initialFocus?: boolean;
}

/**
 * Accessible modal: backdrop-click closes, Escape closes, focus is moved into
 * the dialog on open and focus is trapped while open. Renders an overlay with
 * `role="dialog"` and `aria-modal="true"`.
 */
export function Modal({ onClose, children, labelledBy, className = '', initialFocus = true }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);

    const previouslyFocused = document.activeElement as HTMLElement | null;
    if (initialFocus) {
      const target = panelRef.current?.querySelector<HTMLElement>(
        'input, button, select, textarea, [tabindex]',
      );
      (target ?? panelRef.current)?.focus();
    }

    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus?.();
    };
  }, [onClose, initialFocus]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    const panel = panelRef.current;
    panel?.addEventListener('keydown', onKeyDown);
    return () => panel?.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={`bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl outline-none ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
