import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../lib/api';

interface BacktestResult {
  strategy: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  annual_return_pct: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  equity_curve: Array<{ date: string; value: number }>;
  positions_history: Array<{
    date: string;
    holdings: Record<string, number>;
    capital: number;
  }>;
}

const STRATEGIES = [
  'Balanced',
  'Conservative',
  'Aggressive',
  'Carry Trade',
  'Dollarization',
  'Maximum Reward/Risk',
];

export default function BacktestPanel() {
  const [strategy, setStrategy] = useState('Balanced');
  const [initialCapital, setInitialCapital] = useState('10000');
  const [topN, setTopN] = useState('5');
  const [rebalanceDays, setRebalanceDays] = useState('30');
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);

  async function runBacktest() {
    setLoading(true);
    try {
      const data = await api.request('/api/v1/backtest', {
        method: 'POST',
        body: JSON.stringify({
          strategy,
          initial_capital: parseFloat(initialCapital),
          top_n: parseInt(topN),
          rebalance_days: parseInt(rebalanceDays),
        }),
      });
      setResult(data);
    } catch {
      console.error('Failed to run backtest');
    }
    setLoading(false);
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-white">Бэктест стратегии</h2>

      <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-4 space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Стратегия</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white"
            >
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Начальный капитал</label>
            <input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(e.target.value)}
              className="w-full rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Топ N облигаций</label>
            <input
              type="number"
              value={topN}
              onChange={(e) => setTopN(e.target.value)}
              className="w-full rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Ребалансировка (дни)</label>
            <input
              type="number"
              value={rebalanceDays}
              onChange={(e) => setRebalanceDays(e.target.value)}
              className="w-full rounded-lg bg-slate-700 border border-slate-600 px-3 py-2 text-sm text-white"
            />
          </div>
        </div>
        <button
          onClick={runBacktest}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
        >
          {loading ? 'Выполнение...' : 'Запустить бэктест'}
        </button>
      </div>

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-3">
              <div className="text-xs text-slate-400">Итого</div>
              <div className={`text-lg font-bold font-mono ${result.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {result.total_return_pct >= 0 ? '+' : ''}{result.total_return_pct.toFixed(2)}%
              </div>
            </div>
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-3">
              <div className="text-xs text-slate-400">Годовая</div>
              <div className="text-lg font-bold font-mono text-white">
                {result.annual_return_pct !== null ? `${result.annual_return_pct.toFixed(2)}%` : '—'}
              </div>
            </div>
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-3">
              <div className="text-xs text-slate-400">Sharpe</div>
              <div className="text-lg font-bold font-mono text-white">
                {result.sharpe_ratio !== null ? result.sharpe_ratio.toFixed(3) : '—'}
              </div>
            </div>
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-3">
              <div className="text-xs text-slate-400">Max Drawdown</div>
              <div className="text-lg font-bold font-mono text-red-400">
                {result.max_drawdown_pct !== null ? `${result.max_drawdown_pct.toFixed(2)}%` : '—'}
              </div>
            </div>
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-3">
              <div className="text-xs text-slate-400">Финал</div>
              <div className="text-lg font-bold font-mono text-white">
                {result.final_value.toLocaleString('ru-RU', { maximumFractionDigits: 0 })}
              </div>
            </div>
          </div>

          {result.equity_curve.length > 0 && (
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-4">
              <h3 className="text-sm font-medium text-slate-300 mb-3">Equity Curve</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={result.equity_curve}>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={(v: string) => v.slice(5)}
                  />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: 8 }}
                    labelStyle={{ color: '#94a3b8' }}
                    formatter={(value: number) => [value.toLocaleString('ru-RU'), 'Капитал']}
                  />
                  <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {result.positions_history.length > 0 && (
            <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-4">
              <h3 className="text-sm font-medium text-slate-300 mb-3">
                История ребалансировок ({result.positions_history.length})
              </h3>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {result.positions_history.map((p, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-slate-700/50 last:border-0">
                    <span className="text-xs text-slate-400">{p.date}</span>
                    <span className="text-xs text-white">
                      {Object.keys(p.holdings).length} позиций
                    </span>
                    <span className="text-xs text-white font-mono">
                      {p.capital.toFixed(2)} cash
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
