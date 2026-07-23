import { useState } from 'react';
import TransactionLog from './TransactionLog';
import PnLDashboard from './PnLDashboard';
import BacktestPanel from './BacktestPanel';

const TABS = [
  { id: 'pnl', label: 'P&L Дашборд' },
  { id: 'transactions', label: 'Транзакции' },
  { id: 'backtest', label: 'Бэктест' },
] as const;

type Tab = (typeof TABS)[number]['id'];

export default function PortfolioAdvancedPage() {
  const [tab, setTab] = useState<Tab>('pnl');

  return (
    <div className="space-y-6">
      <div className="flex gap-1 border-b border-slate-700/50">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'pnl' && <PnLDashboard />}
      {tab === 'transactions' && <TransactionLog />}
      {tab === 'backtest' && <BacktestPanel />}
    </div>
  );
}
