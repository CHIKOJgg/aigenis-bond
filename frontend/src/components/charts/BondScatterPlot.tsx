import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ZAxis,
} from 'recharts';
import type { Bond } from '../../lib/api';

interface Props {
  bonds: Bond[];
  xKey: 'duration' | 'yield_to_maturity' | 'price' | 'score';
  yKey: 'yield_to_maturity' | 'score' | 'price';
  colorKey?: 'currency' | 'tier';
  onSelect?: (bond: Bond) => void;
}

const CURRENCY_COLORS: Record<string, string> = {
  USD: '#60a5fa', BYN: '#34d399', EUR: '#a78bfa', XAU: '#f59e0b',
};

function getVal(b: Bond, key: string): number | null {
  if (key === 'duration') return null;
  return (b as Record<string, unknown>)[key] as number | null;
}

export default function BondScatterPlot({ bonds, xKey, yKey, onSelect }: Props) {
  const enriched = bonds
    .filter((b) => getVal(b, xKey) != null && getVal(b, yKey) != null)
    .map((b) => ({
      ...b,
      x: getVal(b, xKey) as number,
      y: getVal(b, yKey) as number,
    }));

  if (enriched.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных для графика</p>;
  }

  const currencies = [...new Set(enriched.map((b) => b.currency))];
  const dataByCurrency = currencies.map((cur) => ({
    currency: cur,
    data: enriched.filter((b) => b.currency === cur),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis
          type="number"
          dataKey="x"
          name={xKey}
          tick={{ fill: '#9ca3af', fontSize: 11 }}
          label={{ value: xKey, position: 'bottom', fill: '#9ca3af', fontSize: 11 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name={yKey}
          tick={{ fill: '#9ca3af', fontSize: 11 }}
          label={{ value: yKey, angle: -90, position: 'insideLeft', fill: '#9ca3af', fontSize: 11 }}
        />
        <ZAxis range={[40, 40]} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
          formatter={(_value: number, name: string) => [name === 'x' ? `${_value}` : `${_value}`, name]}
          labelFormatter={(_label, payload) => {
            const item = payload?.[0]?.payload as { internal_id?: string; name?: string } | undefined;
            return item?.name || item?.internal_id || '';
          }}
        />
        {dataByCurrency.map(({ currency, data }) => (
          <Scatter
            key={currency}
            name={currency}
            data={data}
            fill={CURRENCY_COLORS[currency] || '#9ca3af'}
            onClick={(entry) => onSelect?.(entry as unknown as Bond)}
            style={{ cursor: onSelect ? 'pointer' : 'default' }}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
