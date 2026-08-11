import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { fetchLiveSearch } from '../live-demo-api';
import { scoreFromLiveBond } from '../demo-api';
import { bondDrawerStore } from '../drawer-store';
import { formatPrice, formatYtm } from '../demo-format';
import BondScoreBadge from '../components/BondScoreBadge';
import { DistressedChip } from './DemoAnalyticsPage';
import { SCORE_STATUS_LABEL } from '../demo-config';
import type { DemoBond, ScoreStatus } from '../types';
import { scoreStatusColor } from '../components/BondDetailDrawer';

type MarketFilter = 'ALL' | 'BCSE' | 'MOEX';

const MARKET_BUTTONS: { value: MarketFilter; label: string }[] = [
  { value: 'ALL', label: 'Все рынки' },
  { value: 'BCSE', label: 'BCSE' },
  { value: 'MOEX', label: 'MOEX' },
];

export default function DemoSearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';
  const initialMarket = (searchParams.get('market') ?? 'ALL') as MarketFilter;
  const [q, setQ] = useState(initialQ);
  const [market, setMarket] = useState<MarketFilter>(initialMarket);
  const [results, setResults] = useState<DemoBond[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [source, setSource] = useState<'live' | 'fixtures' | ''>('');

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults([]);
      setSource('');
      setError('');
      return;
    }
    setSearchParams({ q: term, market }, { replace: true });
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const data = await fetchLiveSearch(term, market === 'ALL' ? undefined : market);
        if (cancelled) return;
        setResults(data.bonds);
        setSource('live');
      } catch {
        if (cancelled) return;
        setResults([]);
        setSource('');
        setError('Live-источник временно недоступен');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [q, market, setSearchParams]);

  const openBond = (id: string) => {
    bondDrawerStore.open(id);
    setSearchParams({ q, market }, { replace: true });
  };

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>Поиск облигаций</h1>
        <p style={{ color: '#516c79', fontSize: 14, margin: 0 }}>
          Найдите бумагу по названию, эмитенту, ISIN или внутреннему идентификатору
        </p>
      </div>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        background: '#ffffff',
        border: '1px solid #d6e2e6',
        borderRadius: 12,
        marginBottom: 16,
      }}>
        <Search size={18} style={{ color: '#516c79', flexShrink: 0 }} />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Введите название, эмитента, ISIN или код…"
          autoFocus
          style={{
            flex: 1,
            border: 'none',
            outline: 'none',
            fontSize: 16,
            color: '#01121a',
            background: 'transparent',
          }}
        />
        <div style={{ display: 'flex', gap: 6 }}>
          {MARKET_BUTTONS.map((m) => (
            <button
              key={m.value}
              onClick={() => setMarket(m.value)}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                border: market === m.value ? '1px solid #0B526B' : '1px solid #d6e2e6',
                background: market === m.value ? '#eef3f5' : '#ffffff',
                color: market === m.value ? '#0B526B' : '#516c79',
                fontWeight: market === m.value ? 600 : 400,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 12, color: '#717680', marginBottom: 8 }}>
        {loading ? 'Поиск…' :
          !q.trim() ? 'Введите запрос для поиска' :
          results.length === 0 ? 'Ничего не найдено' :
          `Найдено бумаг: ${results.length}`}
        {source && (
          <span style={{ marginLeft: 8, color: source === 'live' ? '#06b663' : '#717680' }}>
            · источник: {source === 'live' ? 'live' : 'демо-фикстуры'}
          </span>
        )}
      </div>

      {error && <div style={{ color: '#b42318', marginBottom: 8, fontSize: 13 }}>{error}</div>}

      {results.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="aigenis-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #d6e2e6', textAlign: 'left' }}>
                <th style={thStyle}>Бумага</th>
                <th style={thStyle}>ISIN / ID</th>
                <th style={thStyle}>Рынок</th>
                <th style={thStyle}>YTM</th>
                <th style={thStyle}>Цена</th>
                <th style={thStyle}>Score</th>
              </tr>
            </thead>
            <tbody>
              {results.map((bond) => {
                const score = scoreFromLiveBond(bond);
                const status: ScoreStatus = score?.status ?? 'no_data';
                return (
                  <tr
                    key={bond.internal_id}
                    onClick={() => openBond(bond.internal_id)}
                    style={{
                      borderBottom: '1px solid #eef3f5',
                      cursor: 'pointer',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f9fb'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = ''; }}
                  >
                    <td style={tdStyle}>
                      <div style={{ fontWeight: 600 }}>{bond.name}</div>
                      <div style={{ fontSize: 12, color: '#717680' }}>{bond.issuer}</div>
                    </td>
                    <td style={{ ...tdStyle, fontSize: 12, color: '#516c79' }}>
                      {bond.isin ?? bond.internal_id}
                    </td>
                    <td style={tdStyle}>
                      <span style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        background: bond.market.toUpperCase() === 'BCSE' ? '#eef3f5' : '#fff3e0',
                        color: bond.market.toUpperCase() === 'BCSE' ? '#0B526B' : '#a85a00',
                        borderRadius: 4,
                        fontSize: 12,
                        fontWeight: 600,
                      }}>
                        {bond.market.toUpperCase()}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <div>{formatYtm(bond.yield_to_maturity)}</div>
                      {bond.distressed && <DistressedChip />}
                    </td>
                    <td style={tdStyle}>{formatPrice(bond.price)}</td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <BondScoreBadge score={score} />
                        <span style={{ fontSize: 12, color: scoreStatusColor(status) }}>
                          {SCORE_STATUS_LABEL[status]}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
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
