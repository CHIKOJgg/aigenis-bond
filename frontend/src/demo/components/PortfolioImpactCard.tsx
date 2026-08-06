import { getPortfolioImpact } from '../demo-api';

interface Props {
  bondId: string;
  allocationPct: number;
}

export default function PortfolioImpactCard({ bondId, allocationPct }: Props) {
  const impact = getPortfolioImpact({
    portfolio_template: 'moderate_byn',
    bond_id: bondId,
    allocation_pct: allocationPct,
  });

  return (
    <div style={{
      padding: 24,
      background: '#ffffff',
      border: '1px solid #eef3f5',
      borderRadius: 12,
    }}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 20 }}>
        После добавления {allocationPct}% позиции
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 20 }}>
        <MetricBox label="Ожидаемая доходность" before={`${impact.before.expected_yield_pct}%`} after={`${impact.after.expected_yield_pct}%`} delta={`${impact.deltas.expected_yield_pp >= 0 ? '+' : ''}${impact.deltas.expected_yield_pp} п.п.`} />
        <MetricBox label="Средняя дюрация" before={`${impact.before.duration_years} г.`} after={`${impact.after.duration_years} г.`} delta={`${impact.deltas.duration_years >= 0 ? '+' : ''}${impact.deltas.duration_years} г.`} />
        <div style={{ padding: '16px', background: '#f5f9fb', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#717680', marginBottom: 4 }}>РИСК-ПРОФИЛЬ</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#0B526B' }}>Умеренный</div>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        {impact.constraints.map((c) => (
          <div key={c.name} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 0', borderBottom: '1px solid #f5f5f5', fontSize: 13,
          }}>
            <span style={{
              display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
              backgroundColor: c.status === 'ok' ? '#06b663' : c.status === 'warning' ? '#dc6803' : '#e03400',
            }} />
            <span style={{ color: '#01121a' }}>{c.name}</span>
            <span style={{ color: '#717680', marginLeft: 'auto' }}>{c.detail}</span>
          </div>
        ))}
      </div>

      <div style={{
        padding: '14px 16px',
        background: impact.deltas.expected_yield_pp >= 0 ? '#f0fdf6' : '#fdf6f0',
        borderRadius: 8,
        fontSize: 14,
        fontWeight: 600,
        color: impact.deltas.expected_yield_pp >= 0 ? '#06b663' : '#dc6803',
        marginBottom: 12,
      }}>
        {impact.summary}
      </div>

      <div style={{ fontSize: 11, color: '#717680', lineHeight: 1.5 }}>
        {impact.disclaimer}
      </div>
    </div>
  );
}

function MetricBox({ label, before, after, delta }: {
  label: string; before: string; after: string; delta: string;
}) {
  return (
    <div style={{ padding: '16px', background: '#f5f9fb', borderRadius: 8 }}>
      <div style={{ fontSize: 11, color: '#717680', marginBottom: 8 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 14, color: '#516c79', textDecoration: 'line-through' }}>{before}</span>
        <span style={{ fontSize: 20, fontWeight: 700, color: '#01121a' }}>{after}</span>
      </div>
      <div style={{ fontSize: 13, color: delta.startsWith('+') ? '#06b663' : '#e03400', marginTop: 4 }}>
        {delta}
      </div>
    </div>
  );
}
