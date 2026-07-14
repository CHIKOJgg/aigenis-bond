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
    title: 'paywall.title.default',
    description: 'paywall.desc.default',
    icon: 'lock',
  },
  currencies: {
    key: 'currencies',
    title: 'paywall.title.currencies',
    description: 'paywall.desc.currencies',
    icon: 'currencies',
  },
  desk: {
    key: 'desk',
    title: 'paywall.title.desk',
    description: 'paywall.desc.desk',
    icon: 'desk',
  },
  portfolio: {
    key: 'portfolio',
    title: 'paywall.title.portfolio',
    description: 'paywall.desc.portfolio',
    icon: 'lock',
  },
  forecast: {
    key: 'forecast',
    title: 'paywall.title.forecast',
    description: 'paywall.desc.forecast',
    icon: 'lock',
  },
  ml: {
    key: 'ml',
    title: 'paywall.title.ml',
    description: 'paywall.desc.ml',
    icon: 'ml',
  },
  alerts: {
    key: 'alerts',
    title: 'paywall.title.alerts',
    description: 'paywall.desc.alerts',
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
