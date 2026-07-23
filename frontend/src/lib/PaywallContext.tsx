import { createContext, useContext, useState, type ReactNode } from 'react';

export interface PaywallFeature {
  key: string;
  title: string;
  description: string;
  icon: 'lock' | 'currencies' | 'desk' | 'ml';
  benefit?: string;
  stat?: string;
}

export const PAYWALL_FEATURES: Record<string, PaywallFeature> = {
  default: {
    key: 'default',
    title: 'paywall.title.default',
    description: 'paywall.desc.default',
    icon: 'lock',
  },
  currencies: {
    key: 'currencies',
    title: 'paywall.title.currencies',
    description: 'paywall.desc.currencies',
    icon: 'currencies',
    benefit: 'Следите за всеми биржами и валютами одновременно — BYN, USD, EUR, RUB',
    stat: 'Pro-пользователи отслеживают в среднем 3 валюты одновременно',
  },
  desk: {
    key: 'desk',
    title: 'paywall.title.desk',
    description: 'paywall.desc.desk',
    icon: 'desk',
    benefit: 'Оценивайте справедливую стоимость облигаций с точностью институционального инвестора',
    stat: 'Пользователи Pro улучшают доходность портфеля в среднем на 2.3%',
  },
  portfolio: {
    key: 'portfolio',
    title: 'paywall.title.portfolio',
    description: 'paywall.desc.portfolio',
    icon: 'lock',
    benefit: 'Mean-variance оптимизация с учётом корреляций и VaR',
    stat: 'Оптимизированный портфель снижает просадки на 30%',
  },
  forecast: {
    key: 'forecast',
    title: 'paywall.title.forecast',
    description: 'paywall.desc.forecast',
    icon: 'lock',
    benefit: 'Прогнозируйте рост капитала методом Монте-Карло на 1-3 года',
    stat: 'Точность прогноза на 6 месяцев: ±4.5%',
  },
  ml: {
    key: 'ml',
    title: 'paywall.title.ml',
    description: 'paywall.desc.ml',
    icon: 'ml',
    benefit: 'Объяснимые рекомендации buy/hold/wait/avoid от ML на исторических данных',
    stat: 'ML-модели обучаются на 500+ исторических точках',
  },
  alerts: {
    key: 'alerts',
    title: 'paywall.title.alerts',
    description: 'paywall.desc.alerts',
    icon: 'lock',
    benefit: 'Мгновенные уведомления об изменении цен, доходностей и качества данных в Telegram',
    stat: 'Среднее время доставки алерта: 45 секунд',
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
