import { useState } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';

interface CurvePoint {
  tenor: string;
  years: number;
  rate_pct: number;
}

interface CurrencyCurve {
  currency: string;
  points: CurvePoint[];
}

interface Props {
  currencies: CurrencyCurve[];
  width?: number;
  height?: number;
}

const COLORS = ['#34d399', '#60a5fa', '#f59e0b', '#f87171', '#a78bfa', '#2dd4bf'];

export default function YieldCurveChart({ currencies, height = 240 }: Props) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  if (currencies.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных для отображения</p>;
  }

  const allYears = new Set<number>();
  currencies.forEach((c) => c.points.forEach((p) => { if (p.years > 0 && p.rate_pct != null) allYears.add(p.years); }));
  const sortedYears = [...allYears].sort((a, b) => a - b);

  const data = sortedYears.map((year) => {
    const row: Record<string, number | string> = { year: Number(year.toFixed(2)) };
    currencies.forEach((c) => {
      const pt = c.points.find((p) => p.years === year);
      if (pt) row[c.currency] = pt.rate_pct;
    });
    return row;
  });

  const toggle = (currency: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(currency)) next.delete(currency);
      else next.add(currency);
      return next;
    });
  };

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="year" tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={(v) => `${v}y`} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={(v) => `${v}%`} width={50} />
          <Tooltip
            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
            labelFormatter={(v) => `${v} лет`}
            formatter={(value: number, name: string) => [`${value.toFixed(2)}%`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} onClick={(e) => e.value && toggle(String(e.value))} />
          {currencies.map((c, i) => (
            !hidden.has(c.currency) && (
              <Line
                key={c.currency}
                type="monotone"
                dataKey={c.currency}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3, fill: COLORS[i % COLORS.length] }}
                connectNulls
              />
            )
          ))}
          <ReferenceLine y={12} stroke="#6b7280" strokeDasharray="4 4" label={{ value: 'Key Rate', fill: '#6b7280', fontSize: 10 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
