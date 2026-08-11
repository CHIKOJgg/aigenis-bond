import { AlertTriangle } from 'lucide-react';
import { getPortfolioImpact } from '../demo-api';
import type { DemoBond } from '../types';
import { DEMO_PERSONA } from '../demo-config';

interface Props {
  bondId: string;
  allocationPct: number;
  allocationLabel?: string;
  bond?: DemoBond;
}

// A distressed bond prices near-default (price < 80%, YTM > 30%): its
// coupon-schedule yield is not an achievable return, so the portfolio effect
// is computed on a conservative capped yield instead of the headline YTM.
const DISTRESSED_YIELD_CAP = 20;

export default function PortfolioImpactCard({ bondId, allocationPct, allocationLabel, bond }: Props) {
  const fallback = getPortfolioImpact({
    portfolio_template: 'moderate_byn',
    bond_id: bondId,
    allocation_pct: allocationPct,
  });
  const allocation = allocationPct / 100;
  const positionAmount = DEMO_PERSONA.portfolio_byn * allocation;
  const headlineYield = bond?.yield_to_maturity ?? 0;
  const effectiveYield = bond?.distressed
    ? Math.min(headlineYield, DISTRESSED_YIELD_CAP)
    : headlineYield;
  const liveDuration = bond?.duration_years ?? (bond?.term_days ? bond.term_days / 365.25 : 3);
  const riskLabel = bond?.score_status === 'high_risk'
    ? 'Повышенный риск'
    : bond?.score_status === 'review'
      ? 'Требует проверки'
      : 'Умеренный';
  const impact = bond ? {
    ...fallback,
    after: {
      expected_yield_pct: +(fallback.before.expected_yield_pct * (1 - allocation) + effectiveYield * allocation).toFixed(1),
      duration_years: +(fallback.before.duration_years * (1 - allocation) + liveDuration * allocation).toFixed(1),
    },
    deltas: {
      expected_yield_pp: +((effectiveYield - fallback.before.expected_yield_pct) * allocation).toFixed(1),
      duration_years: +((liveDuration - fallback.before.duration_years) * allocation).toFixed(1),
    },
    constraints: [
      {
        name: 'Качество live-данных',
        status: bond.fetched_at ? 'ok' as const : 'warning' as const,
        detail: bond.fetched_at ? `Актуально на ${new Date(bond.fetched_at).toLocaleString('ru-RU')}` : 'Дата источника не указана',
      },
      {
        name: 'Ликвидность',
        status: bond.in_stock && bond.price != null ? 'ok' as const : 'warning' as const,
        detail: bond.in_stock && bond.price != null ? 'Есть котировка и активный статус' : 'Проверьте доступность торгов',
      },
      {
        name: 'Соответствие риск-профилю',
        status: bond.score_status === 'high_risk' ? 'warning' as const : 'ok' as const,
        detail: bond.score_status === 'high_risk' ? 'Score указывает на повышенный риск' : 'Нет сигнала повышенного риска',
      },
    ],
    summary: bond.score_status === 'high_risk'
      ? 'Доходность повышает потенциал, но бумага требует проверки из-за риск-профиля.'
      : fallback.summary,
  } : fallback;

  return (
    <div style={{
      padding: 24,
      background: '#ffffff',
      border: '1px solid #eef3f5',
      borderRadius: 12,
    }}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 20 }}>
        <div>После добавления {allocationPct}% позиции</div>
        <div style={{ fontSize: 12, color: '#516c79', fontWeight: 400, marginTop: 4 }}>
          {positionAmount.toLocaleString('ru-RU')} BYN из портфеля {DEMO_PERSONA.portfolio_byn.toLocaleString('ru-RU')} BYN
          {allocationLabel && allocationLabel !== `${allocationPct}%` ? ` · ${allocationLabel}` : ''}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 20 }}>
        <MetricBox label="Ожидаемая доходность" before={`${impact.before.expected_yield_pct}%`} after={`${impact.after.expected_yield_pct}%`} delta={`${impact.deltas.expected_yield_pp >= 0 ? '+' : ''}${impact.deltas.expected_yield_pp} п.п.`} />
        <MetricBox label="Средняя дюрация" before={`${impact.before.duration_years} г.`} after={`${impact.after.duration_years} г.`} delta={`${impact.deltas.duration_years >= 0 ? '+' : ''}${impact.deltas.duration_years} г.`} />
        <div style={{ padding: '16px', background: '#f5f9fb', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 11, color: '#717680', marginBottom: 4 }}>РИСК-ПРОФИЛЬ</div>
           <div style={{ fontSize: 14, fontWeight: 600, color: bond?.score_status === 'high_risk' ? '#dc6803' : '#0B526B' }}>{riskLabel}</div>
        </div>
      </div>

      {bond && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: 10,
          padding: 14,
          marginBottom: 20,
          background: '#eef8f4',
          border: '1px solid #c8eadb',
          borderRadius: 8,
        }}>
          <LiveMetric label="Live Score" value={bond.score != null ? `${bond.score.toFixed(1)} / 100` : '—'} />
          <LiveMetric label="Риск эмитента" value={bond.issuer_risk ? `${bond.issuer_risk.level} · ${bond.issuer_risk.score}/100` : '—'} />
          <LiveMetric label="YTM" value={bond.yield_to_maturity != null ? `${bond.yield_to_maturity.toFixed(2)}%` : '—'} />
          <LiveMetric label="Дюрация" value={bond.duration_years != null ? `${bond.duration_years.toFixed(1)} г.` : '—'} />
          <LiveMetric
            label="Доход на позиции/год"
            value={effectiveYield > 0 ? `${Math.round(positionAmount * effectiveYield / 100).toLocaleString('ru-RU')} BYN` : '—'}
          />
        </div>
      )}

      <ImpactBars
        beforeYield={impact.before.expected_yield_pct}
        afterYield={impact.after.expected_yield_pct}
        beforeDuration={impact.before.duration_years}
        afterDuration={impact.after.duration_years}
      />

      {bond?.distressed && (
        <div style={{
          display: 'flex',
          gap: 10,
          alignItems: 'flex-start',
          padding: '12px 16px',
          background: '#e0340012',
          border: '1px solid #e0340026',
          borderRadius: 8,
          marginBottom: 16,
          fontSize: 12,
          color: '#7a2e16',
          lineHeight: 1.45,
        }}>
          <AlertTriangle size={15} style={{ color: '#e03400', flexShrink: 0, marginTop: 1 }} />
          <span>
            Дистрибуция: цена ниже 80% при доходности выше 30%. Эффект оценён на
            консервативной доходности {DISTRESSED_YIELD_CAP}% вместо заявленных{' '}
            {headlineYield}% — полный YTM достижим только при исполнении всех выплат.
          </span>
        </div>
      )}

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

function LiveMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: '#36715b', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: '#146c4b' }}>{value}</div>
    </div>
  );
}

function ImpactBars({ beforeYield, afterYield, beforeDuration, afterDuration }: {
  beforeYield: number;
  afterYield: number;
  beforeDuration: number;
  afterDuration: number;
}) {
  const maxYield = Math.max(beforeYield, afterYield, 1);
  const maxDuration = Math.max(beforeDuration, afterDuration, 1);
  return (
    <div style={{ padding: '14px 16px', marginBottom: 20, background: '#fafcfd', border: '1px solid #eef3f5', borderRadius: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Изменение профиля портфеля</div>
      <ComparisonBar label="Доходность" before={beforeYield} after={afterYield} max={maxYield} suffix="%" />
      <ComparisonBar label="Дюрация" before={beforeDuration} after={afterDuration} max={maxDuration} suffix=" г." />
      <div style={{ display: 'flex', gap: 14, marginTop: 10, fontSize: 11, color: '#717680' }}>
        <span><i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: '#b2c9d1', marginRight: 5 }} />До</span>
        <span><i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: '#0B526B', marginRight: 5 }} />После</span>
      </div>
    </div>
  );
}

function ComparisonBar({ label, before, after, max, suffix }: {
  label: string;
  before: number;
  after: number;
  max: number;
  suffix: string;
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#516c79', marginBottom: 4 }}>
        <span>{label}</span>
        <span>{before.toFixed(1)}{suffix} → <strong style={{ color: '#0B526B' }}>{after.toFixed(1)}{suffix}</strong></span>
      </div>
      <div style={{ display: 'grid', gap: 3 }}>
        <div style={{ height: 6, width: `${Math.max(2, before / max * 100)}%`, background: '#b2c9d1', borderRadius: 3 }} />
        <div style={{ height: 6, width: `${Math.max(2, after / max * 100)}%`, background: '#0B526B', borderRadius: 3 }} />
      </div>
    </div>
  );
}
