import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';

interface Trade {
  internal_id: string;
  expected_pnl_pct: number;
  coupon_pct: number;
}

interface Props {
  trades: Trade[];
}

export default function CarryBarChart({ trades }: Props) {
  if (trades.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных для отображения</p>;
  }

  const sorted = [...trades]
    .sort((a, b) => Math.abs(b.expected_pnl_pct) - Math.abs(a.expected_pnl_pct))
    .slice(0, 20);

  const data = sorted.map((t) => ({
    name: t.internal_id,
    coupon: t.coupon_pct,
    rolldown: Math.max(0, t.expected_pnl_pct - t.coupon_pct),
    total: t.expected_pnl_pct,
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, sorted.length * 28)}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, bottom: 5, left: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
        <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 10 }} width={60} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
          formatter={(value: number, name: string) => [`${value.toFixed(2)}%`, name === 'coupon' ? 'Coupon' : 'Rolldown']}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="coupon" stackId="a" fill="#34d399" radius={[0, 0, 0, 0]} />
        <Bar dataKey="rolldown" stackId="a" fill="#60a5fa" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
