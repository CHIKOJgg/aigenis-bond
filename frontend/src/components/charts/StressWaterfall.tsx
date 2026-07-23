import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';

interface ScenarioRun {
  scenario_name: string;
  pnl_pct: number;
}

interface Props {
  runs: ScenarioRun[];
}

export default function StressWaterfall({ runs }: Props) {
  if (runs.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных для отображения</p>;
  }

  const totalPnl = runs.reduce((s, r) => s + r.pnl_pct, 0);
  const data = [
    ...runs.map((r) => ({
      name: r.scenario_name.replace(/_/g, ' '),
      value: r.pnl_pct,
      isTotal: false,
    })),
    { name: 'Итого', value: totalPnl, isTotal: true },
  ];

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 36)}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, bottom: 5, left: 80 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
        <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} width={80} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
          formatter={(value: number) => [`${value >= 0 ? '+' : ''}${value.toFixed(2)}%`, 'P&L']}
        />
        <ReferenceLine x={0} stroke="#6b7280" />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.isTotal
                ? (entry.value >= 0 ? '#3b82f6' : '#ef4444')
                : (entry.value >= 0 ? '#22c55e' : '#ef4444')
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
