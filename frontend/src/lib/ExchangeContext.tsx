import { createContext, useContext, useState, type ReactNode } from 'react';

export type Exchange = 'BCSE' | 'MOEX';

const ExchangeContext = createContext<{ exchange: Exchange; setExchange: (e: Exchange) => void }>({
  exchange: 'BCSE',
  setExchange: () => {},
});

export function useExchange() {
  return useContext(ExchangeContext);
}

export function ExchangeProvider({ children }: { children: ReactNode }) {
  const [exchange, setExchange] = useState<Exchange>('BCSE');
  return (
    <ExchangeContext.Provider value={{ exchange, setExchange }}>
      {children}
    </ExchangeContext.Provider>
  );
}
