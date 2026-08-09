import { useState, useMemo, useEffect } from 'react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { getBonds, getScore, getMarketSummary, scoreFromLiveBond } from '../demo-api';
import { filterAndSortBonds } from '../demo-filter';
import { formatYtm, formatYears, formatDurationYears } from '../demo-format';
import type { DemoScore, ScoreStatus, TermFilter } from '../types';
import { SCORE_STATUS_LABEL } from '../demo-config';
import AnalyticsKpiStrip from '../components/AnalyticsKpiStrip';
import AnalyticsFilters from '../components/AnalyticsFilters';
import BondScoreBadge from '../components/BondScoreBadge';
import { bondDrawerStore } from '../drawer-store';
import { fetchLiveMarket, type LiveMarketSnapshot } from '../live-demo-api';

const API_MARKET: Record<string, 'bcse' | 'moex'> = { BCSE: 'bcse', MOEX: 'moex' };

export default function DemoAnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const params = useParams<{ internalId?: string }>();

  const market = (searchParams.get('market') || 'BCSE') as 'BCSE' | 'MOEX';
  const [currency, setCurrency] = useState('ALL');
  const [term, setTerm] = useState<TermFilter>('all');
  const [status, setStatus] = useState<ScoreStatus | 'all'>('all');
  const [liquidity, setLiquidity] = useState('all');
  const [sortKey, setSortKey] = useState<'score' | 'ytm'>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [live, setLive] = useState<LiveMarketSnapshot | null>(null);
  const [liveLoading, setLiveLoading] = useState(true);
  const [liveError, setLiveError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLive(null);
    setLiveLoading(true);
    setLiveError('');
    fetchLiveMarket(API_MARKET[market])
      .then((snap) => {
        if (cancelled) return;
        setLive(snap);
        setLiveLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLiveError('Не удалось получить актуальные данные — показаны демо-данные');
        setLiveLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [market]);

  useEffect(() => {
    if (params.internalId) bondDrawerStore.open(decodeURIComponent(params.internalId));
  }, [params.internalId]);

  const fixtureSummary = getMarketSummary();
  const summary = live ? {
    ...fixtureSummary,
    global: { ...fixtureSummary.global, updated_at: live.as_of ?? fixtureSummary.global.updated_at },
  } : fixtureSummary;
  const bonds = (live ? live.bonds : getBonds(market));

  const scoreLookup = useMemo(() => {
    if (!live) return getScore;
    const liveById = new Map(live.bonds.map((b) => [b.internal_id, b]));
    return (id: string): DemoScore | undefined =>
      (() => {
        const bond = liveById.get(id);
        const liveScore = bond ? scoreFromLiveBond(bond) : undefined;
        return liveScore ?? getScore(id);
      })();
  }, [live]);

  const filtered = useMemo(
    () => filterAndSortBonds(bonds, { currency, term, status, sortKey, sortDir }, scoreLookup),
    [bonds, currency, term, status, sortKey, sortDir, scoreLookup],
  );

  const uniqueCurrencies = useMemo(() => {
    const set = new Set(bonds.map((b) => b.currency));
    return ['ALL', ...Array.from(set)];
  }, [bonds]);

  const marketStats = summary.markets[market.toLowerCase()];

  // KPIs computed from the visible universe (live or fixtures). The "best
  // yield" card is deliberately computed on non-distressed bonds only: a
  // bond trading below 80% with YTM > 30% prices near-default, and its
  // coupon-schedule yield is not an achievable return.
  const kpis = useMemo(() => {
    if (!live) {
      return {
        attractive: marketStats?.attractive_ideas ?? 0,
        review: marketStats?.needs_review ?? 0,
        distressed: 0,
        bestYield: marketStats?.best_yield_pct ?? 0,
      };
    }
    const withScore = bonds.filter((b) => scoreLookup(b.internal_id));
    const attractive = withScore.filter((b) => scoreLookup(b.internal_id)?.status === 'attractive').length;
    const review = withScore.filter((b) => scoreLookup(b.internal_id)?.status === 'review').length;
    const distressed = bonds.filter((b) => b.distressed).length;
    const clean = bonds.filter((b) => !b.distressed && (b.yield_to_maturity ?? 0) > 0);
    const bestYield = clean.length
      ? Math.max(...clean.map((b) => b.yield_to_maturity ?? 0))
      : marketStats?.best_yield_pct ?? 0;
    return { attractive, review, distressed, bestYield };
  }, [live, bonds, scoreLookup, marketStats]);

  const handleMarketChange = (m: string) => {
    setSearchParams({ market: m });
  };

  const openBond = (id: string) => {
    bondDrawerStore.open(id);
    navigate(`/demo/analytics/bonds/${encodeURIComponent(id)}?market=${market}`, { replace: true });
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
        attractive={kpis.attractive}
        review={kpis.review}
        distressed={kpis.distressed}
        bestYield={kpis.bestYield}
        asOf={summary.global.updated_at}
      />

      {liveError && (
        <div style={{
          color: '#b42318', fontSize: 13, marginBottom: 12,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <AlertTriangle size={14} /> {liveError}
        </div>
      )}
      {live && (
        <div style={{ color: '#516c79', fontSize: 12, marginBottom: 12 }}>
          Источник: {live.source} · актуально на {new Date(live.as_of ?? '').toLocaleString('ru-RU')}
        </div>
      )}

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
            {liveLoading ? (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#717680' }}>
                  Загрузка данных рынка…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#717680' }}>
                  Нет бумаг, соответствующих фильтрам
                </td>
              </tr>
            ) : (
              filtered.map((bond) => (
                <tr
                  key={bond.internal_id}
                  onClick={() => openBond(bond.internal_id)}
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
                    <BondScoreBadge score={scoreLookup(bond.internal_id)} />
                  </td>
                  <td style={tdStyle}>
                    <StatusCell status={scoreLookup(bond.internal_id)?.status ?? 'no_data'} />
                  </td>
                  <td style={tdStyle}>
                    <div>{formatYtm(bond.yield_to_maturity)}</div>
                    {bond.distressed && <DistressedChip />}
                  </td>
                  <td style={tdStyle}>{bond.maturity_date ?? '—'}</td>
                  <td style={tdStyle}>
                    {bond.duration_years != null ? formatYears(bond.duration_years) : formatDurationYears(bond.term_days)}
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'center' }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); openBond(bond.internal_id); }}
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
    </div>
  );
}

export function DistressedChip() {
  return (
    <span
      title="Цена ниже 80% при доходности выше 30% — рынок закладывает дефолт; расчётная доходность не является достижимой"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        marginTop: 4,
        padding: '1px 8px',
        borderRadius: 10,
        fontSize: 11,
        fontWeight: 600,
        color: '#e03400',
        background: '#e0340014',
      }}
    >
      <AlertTriangle size={11} /> дистрибуция
    </span>
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
