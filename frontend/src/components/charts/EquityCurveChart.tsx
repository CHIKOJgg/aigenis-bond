import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';

interface Props {
  data: { date: string; value: number }[];
  benchmark?: { date: string; value: number }[];
}

export default function EquityCurveChart({ data, benchmark }: Props) {
  const merged = data.map((d, i) => ({
    date: d.date,
    strategy: d.value,
    benchmark: benchmark?.[i]?.value ?? null,
  }));

  if (merged.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных для отображения</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={merged} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <defs>
          <linearGradient id="colorStrategy" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="colorBenchmark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6b7280" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#6b7280" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#9ca3af', fontSize: 10 }}
          tickFormatter={(v) => new Date(v).toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' })}
        />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} width={60} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
          labelFormatter={(v) => new Date(v).toLocaleDateString('ru-RU')}
          formatter={(value: number, name: string) => [`${value.toFixed(2)}`, name === 'strategy' ? 'Стратегия' : 'Benchmark']}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area
          type="monotone"
          dataKey="strategy"
          stroke="#34d399"
          fillOpacity={1}
          fill="url(#colorStrategy)"
          strokeWidth={2}
          name="Стратегия"
        />
        {benchmark && (
          <Area
            type="monotone"
            dataKey="benchmark"
            stroke="#6b7280"
            fillOpacity={1}
            fill="url(#colorBenchmark)"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            name="Benchmark"
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}
