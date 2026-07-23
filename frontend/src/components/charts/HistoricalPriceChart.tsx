import { useState, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';

interface Props {
  bondId: string;
  metric: 'price' | 'ytm';
  data: { date: string; value: number }[];
}

const PERIODS = [
  { label: '1M', months: 1 },
  { label: '3M', months: 3 },
  { label: '6M', months: 6 },
  { label: '1Y', months: 12 },
  { label: 'ALL', months: 999 },
] as const;

export default function HistoricalPriceChart({ metric, data }: Props) {
  const [period, setPeriod] = useState<number>(12);

  const filtered = useMemo(() => {
    if (period >= 999) return data;
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - period);
    return data.filter((d) => new Date(d.date) >= cutoff);
  }, [data, period]);

  const currentValue = filtered.length > 0 ? filtered[filtered.length - 1].value : null;

  if (filtered.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных за выбранный период</p>;
  }

  return (
    <div>
      <div className="flex gap-1 mb-3">
        {PERIODS.map((p) => (
          <button
            key={p.label}
            onClick={() => setPeriod(p.months)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              period === p.months
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={filtered} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
          <defs>
            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            tickFormatter={(v) => new Date(v).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            tickFormatter={(v) => metric === 'ytm' ? `${v}%` : String(v)}
            width={50}
          />
          <Tooltip
            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
            labelFormatter={(v) => new Date(v).toLocaleDateString('ru-RU')}
            formatter={(value: number) => [metric === 'ytm' ? `${value.toFixed(2)}%` : value.toFixed(2), metric === 'ytm' ? 'YTM' : 'Цена']}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#34d399"
            fillOpacity={1}
            fill="url(#colorValue)"
            strokeWidth={2}
          />
          {currentValue != null && (
            <ReferenceLine y={currentValue} stroke="#6b7280" strokeDasharray="4 4" />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
