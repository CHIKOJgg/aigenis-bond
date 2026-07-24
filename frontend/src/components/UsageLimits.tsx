import { AlertTriangle, TrendingUp } from 'lucide-react';
import { usePaywall } from '../lib/PaywallContext';
import { tierLimits } from '../lib/tiers';

interface UsageLimitsProps {
  tier: string;
  bondsUsed: number;
  currenciesUsed: number;
}

export default function UsageLimits({ tier, bondsUsed, currenciesUsed }: UsageLimitsProps) {
  const { openPaywall } = usePaywall();
  const limits = tierLimits(tier);

  if (tier !== 'free') return null;

  const bondsLimit = limits.maxBonds;
  const currenciesLimit = limits.maxCurrencies;
  const bondsPct = bondsLimit > 0 ? Math.min((bondsUsed / bondsLimit) * 100, 100) : 0;
  const currenciesPct = currenciesLimit > 0 ? Math.min((currenciesUsed / currenciesLimit) * 100, 100) : 0;

  return (
    <div className="rounded-xl bg-amber-900/20 border border-amber-500/20 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <AlertTriangle size={16} className="text-amber-400" />
        <span className="text-sm font-medium text-amber-300">Лимиты Free-аккаунта</span>
      </div>

      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-slate-400">Облигации</span>
          <span className="text-amber-300">{bondsUsed} / {bondsLimit}</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${bondsPct >= 100 ? 'bg-red-500' : bondsPct >= 80 ? 'bg-amber-500' : 'bg-emerald-500/60'}`}
            style={{ width: `${bondsPct}%` }} />
        </div>
      </div>

      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-slate-400">Валюты</span>
          <span className="text-amber-300">{currenciesUsed} / {currenciesLimit}</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${currenciesPct >= 100 ? 'bg-red-500' : currenciesPct >= 80 ? 'bg-amber-500' : 'bg-emerald-500/60'}`}
            style={{ width: `${currenciesPct}%` }} />
        </div>
      </div>

      <button onClick={() => openPaywall('default')}
        className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium transition-colors">
        <TrendingUp size={14} /> Обновить до Pro — безлимит
      </button>
    </div>
  );
}
