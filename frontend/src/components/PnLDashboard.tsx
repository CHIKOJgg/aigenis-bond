import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../lib/api';

interface PnLData {
  total_invested: number;
  total_value: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  total_coupon_income: number;
  total_pnl: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  per_bond: Array<{
    internal_id: string;
    realized_pnl: number;
    unrealized_pnl: number;
    coupon_income: number;
    total_pnl: number;
    current_value: number;
    cost_basis: number;
    weight: number;
  }>;
  daily_returns: Array<{
    date: string;
    return_pct: number;
  }>;
}

function StatCard({ label, value, icon, color }: { label: string; value: string; icon: React.ReactNode; color: string }) {
  return (
    <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${color}`}>
          {icon}
        </div>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
      <div className="text-lg font-bold text-white font-mono">{value}</div>
    </div>
  );
}

export default function PnLDashboard() {
  const [data, setData] = useState<PnLData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPnL();
  }, []);

  async function loadPnL() {
    setLoading(true);
    try {
      const result = await api.request('/api/v1/pnl');
      setData(result);
    } catch {
      console.error('Failed to load P&L');
    }
    setLoading(false);
  }

  if (loading) {
    return <div className="text-slate-400 text-sm py-8 text-center">Загрузка P&L...</div>;
  }

  if (!data) {
    return <div className="text-slate-400 text-sm py-8 text-center">Нет данных P&L</div>;
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-white">P&L Дашборд</h2>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Инвестировано"
          value={data.total_invested.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}
          icon={<DollarSign size={16} className="text-blue-400" />}
          color="bg-blue-500/20"
        />
        <StatCard
          label="Текущая стоимость"
          value={data.total_value.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}
          icon={<Activity size={16} className="text-purple-400" />}
          color="bg-purple-500/20"
        />
        <StatCard
          label="Общий P&L"
          value={`${data.total_pnl >= 0 ? '+' : ''}${data.total_pnl.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}`}
          icon={data.total_pnl >= 0 ? <TrendingUp size={16} className="text-green-400" /> : <TrendingDown size={16} className="text-red-400" />}
          color={data.total_pnl >= 0 ? 'bg-green-500/20' : 'bg-red-500/20'}
        />
        <StatCard
          label="Доходность"
          value={`${data.total_return_pct >= 0 ? '+' : ''}${data.total_return_pct.toFixed(2)}%`}
          icon={data.total_return_pct >= 0 ? <TrendingUp size={16} className="text-green-400" /> : <TrendingDown size={16} className="text-red-400" />}
          color={data.total_return_pct >= 0 ? 'bg-green-500/20' : 'bg-red-500/20'}
        />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Реализованный P&L"
          value={`${data.total_realized_pnl >= 0 ? '+' : ''}${data.total_realized_pnl.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}`}
          icon={<TrendingUp size={16} className="text-emerald-400" />}
          color="bg-emerald-500/20"
        />
        <StatCard
          label="Нереализованный P&L"
          value={`${data.total_unrealized_pnl >= 0 ? '+' : ''}${data.total_unrealized_pnl.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}`}
          icon={<Activity size={16} className="text-amber-400" />}
          color="bg-amber-500/20"
        />
        <StatCard
          label="Купонный доход"
          value={data.total_coupon_income.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}
          icon={<DollarSign size={16} className="text-cyan-400" />}
          color="bg-cyan-500/20"
        />
        <StatCard
          label="Sharpe / Max DD"
          value={`${data.sharpe_ratio.toFixed(2)} / ${data.max_drawdown_pct.toFixed(1)}%`}
          icon={<Activity size={16} className="text-slate-400" />}
          color="bg-slate-500/20"
        />
      </div>

      {data.daily_returns.length > 0 && (
        <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-4">
          <h3 className="text-sm font-medium text-slate-300 mb-3">Кривая доходности</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.daily_returns}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: 8 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(value: number) => [`${value.toFixed(4)}%`, 'Return']}
              />
              <Line type="monotone" dataKey="return_pct" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.per_bond.length > 0 && (
        <div className="rounded-xl bg-slate-800/60 border border-slate-600/30 p-4">
          <h3 className="text-sm font-medium text-slate-300 mb-3">P&L по облигациям</h3>
          <div className="space-y-2">
            {data.per_bond.map((b) => (
              <div key={b.internal_id} className="flex items-center justify-between py-2 border-b border-slate-700/50 last:border-0">
                <div className="flex-1">
                  <span className="text-sm text-white font-medium">{b.internal_id}</span>
                  <span className="text-xs text-slate-500 ml-2">{(b.weight * 100).toFixed(1)}%</span>
                </div>
                <div className="flex gap-4 text-xs">
                  <span className={b.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    Реал: {b.realized_pnl >= 0 ? '+' : ''}{b.realized_pnl.toFixed(2)}
                  </span>
                  <span className={b.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    Нереал: {b.unrealized_pnl >= 0 ? '+' : ''}{b.unrealized_pnl.toFixed(2)}
                  </span>
                  <span className={b.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    Итого: {b.total_pnl >= 0 ? '+' : ''}{b.total_pnl.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
