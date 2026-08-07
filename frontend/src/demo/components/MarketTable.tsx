import { getBonds } from '../demo-api';

interface Props {
  market: string;
  bonds?: import('../types').DemoBond[];
}

export default function MarketTable({ market, bonds: liveBonds }: Props) {
  const bonds = liveBonds ?? getBonds(market);

  if (bonds.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#516c79' }}>
        Нет данных для рынка {market}
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="aigenis-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #d6e2e6', textAlign: 'left' }}>
            <th style={thStyle}>Название / ISIN</th>
            <th style={thStyle}>Цена</th>
            <th style={thStyle}>Доходность</th>
            <th style={thStyle}>Погашение</th>
            <th style={thStyle}>Статус</th>
          </tr>
        </thead>
        <tbody>
          {bonds.map((bond) => (
            <tr key={bond.internal_id} style={{ borderBottom: '1px solid #eef3f5' }}>
              <td style={tdStyle}>
                <div style={{ fontWeight: 600 }}>{bond.name}</div>
                <div style={{ fontSize: 12, color: '#717680' }}>{bond.isin || bond.internal_id}</div>
              </td>
              <td style={tdStyle}>
                {bond.price != null ? `${bond.price} ${bond.currency}` : '—'}
              </td>
              <td style={tdStyle}>
                {bond.yield_to_maturity != null ? `${bond.yield_to_maturity}%` : '—'}
              </td>
              <td style={tdStyle}>
                {bond.maturity_date ?? '—'}
              </td>
              <td style={tdStyle}>
                <span style={statusStyle(bond.status)}>{bond.status}</span>
              </td>
            </tr>
          ))}
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
  verticalAlign: 'top',
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
