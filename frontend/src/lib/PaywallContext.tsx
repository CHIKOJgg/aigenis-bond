import { createContext, useContext, useState, type ReactNode } from 'react';

export interface PaywallFeature {
  key: string;
  title: string;
  description: string;
  icon: 'lock' | 'currencies' | 'desk' | 'ml';
}

export const PAYWALL_FEATURES: Record<string, PaywallFeature> = {
  default: {
    key: 'default',
    title: 'Функция Pro / Enterprise',
    description:
      'Эта возможность доступна по подписке. Оформите её — и доступ откроется здесь и в Telegram-боте одновременно.',
    icon: 'lock',
  },
  currencies: {
    key: 'currencies',
    title: 'Трекер валют (бирж)',
    description:
      'Бесплатный тариф позволяет отслеживать только 1 валюту. Оформите Pro, чтобы следить за всеми биржами и валютами сразу.',
    icon: 'currencies',
  },
  desk: {
    key: 'desk',
    title: 'Fixed Income Desk',
    description:
      'Кривая доходности, Relative Value, Carry, РЕПО и стресс-тесты доступны по подписке Pro / Enterprise.',
    icon: 'desk',
  },
  portfolio: {
    key: 'portfolio',
    title: 'Портфель и оптимизация',
    description: 'Метрики портфеля, прогноз капитала и оптимизация — функции тарифа Pro / Enterprise.',
    icon: 'lock',
  },
  forecast: {
    key: 'forecast',
    title: 'Прогноз капитала',
    description: 'Прогноз капитала по горизонтам доступен по подписке Pro / Enterprise.',
    icon: 'lock',
  },
  ml: {
    key: 'ml',
    title: 'ML-рекомендации',
    description: 'Объяснимые рекомендации buy/hold/wait/avoid доступны по подписке Pro / Enterprise.',
    icon: 'ml',
  },
  alerts: {
    key: 'alerts',
    title: 'Алерты',
    description: 'Уведомления о событиях рынка доступны по подписке Pro / Enterprise.',
    icon: 'lock',
  },
};

export interface PaywallState {
  open: boolean;
  feature: PaywallFeature;
}

interface PaywallContextValue {
  state: PaywallState;
  openPaywall: (featureKey?: string) => void;
  closePaywall: () => void;
}

const PaywallContext = createContext<PaywallContextValue | null>(null);

export function PaywallProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PaywallState>({
    open: false,
    feature: PAYWALL_FEATURES.default,
  });

  const openPaywall = (featureKey = 'default') => {
    setState({
      open: true,
      feature: PAYWALL_FEATURES[featureKey] ?? PAYWALL_FEATURES.default,
    });
  };

  const closePaywall = () => setState((s) => ({ ...s, open: false }));

  return (
    <PaywallContext.Provider value={{ state, openPaywall, closePaywall }}>
      {children}
    </PaywallContext.Provider>
  );
}

export function usePaywall() {
  const ctx = useContext(PaywallContext);
  if (!ctx) throw new Error('usePaywall must be used within PaywallProvider');
  return ctx;
}
