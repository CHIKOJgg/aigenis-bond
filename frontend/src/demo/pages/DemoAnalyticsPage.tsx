import { useState, useMemo, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { getBonds, getScore, getMarketSummary } from '../demo-api';
import { filterAndSortBonds } from '../demo-filter';
import { formatYtm, formatDurationYears } from '../demo-format';
import type { ScoreStatus, TermFilter } from '../types';
import { SCORE_STATUS_LABEL } from '../demo-config';
import AnalyticsKpiStrip from '../components/AnalyticsKpiStrip';
import AnalyticsFilters from '../components/AnalyticsFilters';
import BondScoreBadge from '../components/BondScoreBadge';
import BondDetailDrawer from '../components/BondDetailDrawer';
import { fetchLiveMarket, type LiveMarketSnapshot } from '../live-demo-api';

export default function DemoAnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const market = (searchParams.get('market') || 'BCSE') as 'BCSE' | 'MOEX';
  const [currency, setCurrency] = useState('ALL');
  const [term, setTerm] = useState<TermFilter>('all');
  const [status, setStatus] = useState<ScoreStatus | 'all'>('all');
  const [liquidity, setLiquidity] = useState('all');
  const [sortKey, setSortKey] = useState<'score' | 'ytm'>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [live, setLive] = useState<LiveMarketSnapshot | null>(null);
  const [liveError, setLiveError] = useState('');

  useEffect(() => {
    if (market !== 'BCSE') return;
    fetchLiveMarket('bcse').then(setLive).catch(() => setLiveError('Не удалось получить актуальные данные BCSE'));
  }, [market]);

  const fixtureSummary = getMarketSummary();
  const summary = live ? {
    ...fixtureSummary,
    global: { ...fixtureSummary.global, updated_at: live.as_of ?? fixtureSummary.global.updated_at },
  } : fixtureSummary;
  const bonds = (market === 'BCSE' && live ? live.bonds : getBonds(market));

  const filtered = useMemo(
    () => filterAndSortBonds(bonds, { currency, term, status, sortKey, sortDir }, getScore),
    [bonds, currency, term, status, sortKey, sortDir],
  );

  const uniqueCurrencies = useMemo(() => {
    const set = new Set(bonds.map((b) => b.currency));
    return ['ALL', ...Array.from(set)];
  }, [bonds]);

  const marketStats = summary.markets[market.toLowerCase()];

  const handleMarketChange = (m: string) => {
    setSearchParams({ market: m });
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>Аналитика облигаций</h1>
        <p style={{ color: '#516c79', fontSize: 14, margin: 0 }}>
          Сравнение доходности, риска и ликвидности в одном месте
        </p>
      </div>

      <AnalyticsKpiStrip
        attractive={market === 'BCSE' ? bonds.filter((b) => (b.yield_to_maturity ?? 0) >= 12).length : marketStats?.attractive_ideas ?? 0}
        review={marketStats?.needs_review ?? 0}
        bestYield={market === 'BCSE' ? Math.max(...bonds.map((b) => b.yield_to_maturity ?? 0), 0) : marketStats?.best_yield_pct ?? 0}
        asOf={summary.global.updated_at}
      />

      {liveError && <div style={{ color: '#b42318', marginBottom: 12 }}>{liveError}</div>}
      {live && <div style={{ color: '#516c79', fontSize: 12, marginBottom: 12 }}>Источник: {live.source} · актуально на {new Date(live.as_of ?? '').toLocaleString('ru-RU')}</div>}

      <AnalyticsFilters
        market={market}
        onMarketChange={handleMarketChange}
        currency={currency}
        currencies={uniqueCurrencies}
        onCurrencyChange={setCurrency}
        term={term}
        onTermChange={setTerm}
        status={status}
        onStatusChange={setStatus}
        liquidity={liquidity}
        onLiquidityChange={setLiquidity}
        sortKey={sortKey}
        sortDir={sortDir}
        onSortChange={(k, d) => { setSortKey(k); setSortDir(d); }}
      />

      <div style={{ overflowX: 'auto' }}>
        <table className="aigenis-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #d6e2e6', textAlign: 'left' }}>
              <th style={thStyle}>Бумага</th>
              <th style={thStyle}>Score</th>
              <th style={thStyle}>Статус</th>
              <th style={thStyle}>YTM</th>
              <th style={thStyle}>Погашение</th>
              <th style={thStyle}>Дюрация</th>
              <th style={{ ...thStyle, textAlign: 'center' }}></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#717680' }}>
                  Нет бумаг, соответствующих фильтрам
                </td>
              </tr>
            ) : (
              filtered.map((bond) => (
                <tr
                  key={bond.internal_id}
                  onClick={() => setSelectedId(bond.internal_id)}
                  style={{
                    borderBottom: '1px solid #eef3f5',
                    cursor: 'pointer',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f9fb'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = ''; }}
                >
                  <td style={tdStyle}>
                    <div style={{ fontWeight: 600 }}>{bond.name}</div>
                    <div style={{ fontSize: 12, color: '#717680' }}>{bond.issuer}</div>
                  </td>
                  <td style={tdStyle}>
                    <BondScoreBadge score={getScore(bond.internal_id)} />
                  </td>
                  <td style={tdStyle}>
                    <StatusCell status={getScore(bond.internal_id)?.status ?? 'no_data'} />
                  </td>
                  <td style={tdStyle}>
                    {formatYtm(bond.yield_to_maturity)}
                  </td>
                  <td style={tdStyle}>{bond.maturity_date ?? '—'}</td>
                  <td style={tdStyle}>
                    {formatDurationYears(bond.term_days)}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); setSelectedId(bond.internal_id); }}
                      style={{
                        padding: '6px 14px',
                        borderRadius: 6,
                        border: '1px solid #d6e2e6',
                        background: '#ffffff',
                        color: '#0B526B',
                        fontSize: 13,
                        fontWeight: 500,
                        cursor: 'pointer',
                      }}
                    >
                      Открыть
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selectedId && (
        <BondDetailDrawer
          bondId={selectedId}
          bond={bonds.find((b) => b.internal_id === selectedId)}
          onClose={() => setSelectedId(null)}
          onPortfolioImpact={() => navigate(`/demo/portfolio-impact/${encodeURIComponent(selectedId)}?market=${market}`)}
          onAlert={() => {}}
          onOrder={() => {}}
        />
      )}
    </div>
  );
}

function StatusCell({ status }: { status: ScoreStatus }) {
  const colors: Record<ScoreStatus, string> = {
    attractive: '#06b663',
    neutral: '#35aaac',
    review: '#dc6803',
    high_risk: '#e03400',
    no_data: '#717680',
  };
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 13,
        fontWeight: 500,
        color: colors[status],
      }}
    >
      <span style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: colors[status],
      }} />
      {SCORE_STATUS_LABEL[status] || status}
    </span>
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
