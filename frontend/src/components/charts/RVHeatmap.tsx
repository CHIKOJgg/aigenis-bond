import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';

interface Signal {
  internal_id: string;
  z_score: number;
  currency: string;
  issuer: string;
}

interface Props {
  signals: Signal[];
}

function zScoreColor(z: number): string {
  if (z < -1) return '#22c55e';
  if (z < -0.5) return '#86efac';
  if (z < 0.5) return '#6b7280';
  if (z < 1) return '#fca5a5';
  return '#ef4444';
}

interface TreemapItem {
  name: string;
  size: number;
  z_score: number;
  fill: string;
}

export default function RVHeatmap({ signals }: Props) {
  if (signals.length === 0) {
    return <p className="text-xs text-gray-500">Нет данных для heatmap</p>;
  }

  const data: TreemapItem[] = signals.map((s) => ({
    name: s.internal_id,
    size: Math.max(Math.abs(s.z_score) * 10, 1),
    z_score: s.z_score,
    fill: zScoreColor(s.z_score),
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={250}>
        <Treemap
          data={data}
          dataKey="size"
          nameKey="name"
          stroke="#1f2937"
          content={({ x, y, width, height, name, z_score }: {
            x: number; y: number; width: number; height: number; name: string; z_score: number;
          }) => {
            if (width < 30 || height < 20) return null;
            return (
              <g>
                <rect x={x} y={y} width={width} height={height} fill={zScoreColor(z_score)} rx={4} />
                {width > 40 && height > 16 && (
                  <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="central"
                    fill="white" fontSize={10} fontWeight={600}>
                    {name}
                  </text>
                )}
                {width > 50 && height > 28 && (
                  <text x={x + width / 2} y={y + height / 2 + 12} textAnchor="middle" dominantBaseline="central"
                    fill="white" fontSize={9} opacity={0.8}>
                    z={z_score.toFixed(2)}
                  </text>
                )}
              </g>
            );
          }}
        />
      </ResponsiveContainer>
      <Tooltip
        contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
        formatter={(_value: number, _name: string, props: { payload?: TreemapItem }) => {
          const item = props.payload;
          return item ? [`z=${item.z_score.toFixed(3)}`, item.name] : ['', ''];
        }}
      />
      <div className="flex items-center justify-center gap-3 mt-2 text-[10px] text-gray-500">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#22c55e' }} /> Cheap</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#6b7280' }} /> Fair</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#ef4444' }} /> Rich</span>
      </div>
    </div>
  );
}
