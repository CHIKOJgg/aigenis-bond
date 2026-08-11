import { getBonds, scoreFromLiveBond } from '../demo-api';
import BondScoreBadge from './BondScoreBadge';
import { formatPrice, formatYtm } from '../demo-format';
import type { DemoScore } from '../types';
import { DistressedChip } from '../pages/DemoAnalyticsPage';

interface Props {
  market: string;
  bonds?: import('../types').DemoBond[];
  loading?: boolean;
  onSelect?: (internalId: string) => void;
}

const STATUS_LABEL: Record<string, string> = {
  active: 'Активна',
  delisted: 'Исключена',
  matured: 'Погашена',
  unknown: 'Статус не определён',
};

export default function MarketTable({ market, bonds: liveBonds, loading, onSelect }: Props) {
  const bonds = liveBonds ?? getBonds(market);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#516c79' }}>
        Загрузка данных рынка…
      </div>
    );
  }

  if (bonds.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#516c79' }}>
        Нет данных для рынка {market}
      </div>
    );
  }

  const scoreLookup = (id: string): DemoScore | undefined => {
    const bond = bonds.find((b) => b.internal_id === id);
    return bond ? scoreFromLiveBond(bond) : undefined;
  };

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="aigenis-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #d6e2e6', textAlign: 'left' }}>
            <th style={thStyle}>Название / ISIN</th>
            <th style={thStyle}>Цена</th>
            <th style={thStyle}>Доходность</th>
            <th style={thStyle}>Погашение</th>
            <th style={thStyle}>Score</th>
            <th style={thStyle}>Статус</th>
          </tr>
        </thead>
        <tbody>
          {bonds.map((bond) => {
            const score = scoreLookup(bond.internal_id);
            return (
              <tr
                key={bond.internal_id}
                onClick={() => onSelect?.(bond.internal_id)}
                style={{
                  borderBottom: '1px solid #eef3f5',
                  cursor: onSelect ? 'pointer' : 'default',
                }}
                onMouseEnter={(e) => { if (onSelect) e.currentTarget.style.background = '#f5f9fb'; }}
                onMouseLeave={(e) => { if (onSelect) e.currentTarget.style.background = ''; }}
              >
                <td style={tdStyle}>
                    <div style={{ fontWeight: 600 }}>{bond.name}</div>
                    <div style={{ fontSize: 12, color: '#717680' }}>{bond.isin || bond.internal_id}</div>
                    {bond.issuer_risk && (
                      <div style={{ fontSize: 11, color: '#516c79', marginTop: 3 }}>
                        Эмитент: {bond.issuer_risk.level} риск · {bond.issuer_risk.score}/100
                      </div>
                    )}
                </td>
                <td style={tdStyle}>{formatPrice(bond.price)}</td>
                <td style={tdStyle}>
                  <div>{formatYtm(bond.yield_to_maturity)}</div>
                  {bond.distressed && <DistressedChip />}
                </td>
                <td style={tdStyle}>{bond.maturity_date ?? '—'}</td>
                <td style={tdStyle}>
                  <BondScoreBadge score={score} />
                </td>
                <td style={tdStyle}>
                  <span style={statusStyle(bond.status)}>
                    {STATUS_LABEL[bond.status] || bond.status}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: '12px 16px',
  fontWeight: 600,
  color: '#516c79',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const tdStyle: React.CSSProperties = {
  padding: '14px 16px',
  verticalAlign: 'middle',
};

function statusStyle(status: string): React.CSSProperties {
  const colors: Record<string, string> = {
    active: '#06b663',
    delisted: '#e03400',
    matured: '#717680',
  };
  return {
    display: 'inline-block',
    padding: '2px 10px',
    borderRadius: 12,
    fontSize: 12,
    fontWeight: 500,
    background: `${colors[status] || '#717680'}15`,
    color: colors[status] || '#717680',
  };
}
