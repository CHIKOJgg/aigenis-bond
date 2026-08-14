import { useState, useMemo, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ZAxis,
} from 'recharts';
import type { TooltipProps } from 'recharts';
import { getScore, getMarketSummary, getBonds, getAllBonds, scoreFromLiveBond } from '../demo-api';
import { filterAndSortBonds } from '../demo-filter';
import { formatYtm, formatYears, formatTermDays, formatBondDisplayName } from '../demo-format';
import type { DemoBond, DemoScore, ScoreStatus, TermFilter } from '../types';
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

  const market = (searchParams.get('market') || 'BCSE').toUpperCase();
  const [currency, setCurrency] = useState('ALL');
  const [term, setTerm] = useState<TermFilter>('all');
  const [status, setStatus] = useState<ScoreStatus | 'all'>('all');
  const [liquidity, setLiquidity] = useState('all');
  const [sortKey, setSortKey] = useState<'score' | 'ytm'>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [live, setLive] = useState<LiveMarketSnapshot | null>(null);
  const [liveLoading, setLiveLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLive(null);
    setLiveLoading(true);

    // ALL = сводный универсум обоих рынков (BCSE + MOEX).
    const markets = market === 'ALL' ? ['bcse', 'moex'] : [API_MARKET[market] ?? 'bcse'];
    Promise.all(markets.map((m) => fetchLiveMarket(m)))
      .then((snaps) => {
        if (cancelled) return;
        const merged = snaps.flatMap((s) => s.bonds);
        setLive({
          source: snaps[0]?.source ?? 'Aigenis',
          market: market,
          currency: null,
          as_of: snaps[0]?.as_of ?? null,
          count: merged.length,
          bonds: merged,
          disclaimer: snaps[0]?.disclaimer ?? '',
        });
        setLiveLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLive(null);
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
  const bonds = live?.bonds ?? (market === 'ALL' ? getAllBonds() : getBonds(market.toUpperCase()));

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

    // Для ALL-режима сводная статистика = сумма по обоим рынкам.
  const marketStats = useMemo(() => (
    market === 'ALL'
      ? {
          attractive_ideas: (summary.markets.bcse?.attractive_ideas ?? 0)
            + (summary.markets.moex?.attractive_ideas ?? 0),
          needs_review: (summary.markets.bcse?.needs_review ?? 0)
            + (summary.markets.moex?.needs_review ?? 0),
          best_yield_pct: Math.max(
            summary.markets.bcse?.best_yield_pct ?? 0,
            summary.markets.moex?.best_yield_pct ?? 0,
          ),
        }
      : summary.markets[market.toLowerCase()]
  ), [market, summary]);

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

      {live ? (
        <div style={{ color: '#516c79', fontSize: 12, marginBottom: 12 }}>
          Источник: {live.source} · актуально на {new Date(live.as_of ?? '').toLocaleString('ru-RU')}
        </div>
      ) : (
        <div style={{ color: '#516c79', fontSize: 12, marginBottom: 12 }}>
          Источник: Aigenis (демо-копия)
        </div>
      )}

      <ScoreYtmChart bonds={bonds} scoreLookup={scoreLookup} />

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
                    <div style={{ fontWeight: 600 }}>{formatBondDisplayName(bond.name, bond.internal_id, bond.isin)}</div>
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
                    {bond.duration_years != null ? formatYears(bond.duration_years) : formatTermDays(bond.term_days)}
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

function ScoreYtmChart({
  bonds,
  scoreLookup,
}: {
  bonds: DemoBond[];
  scoreLookup: (id: string) => DemoScore | undefined;
}) {
  type Point = { internal_id: string; name: string; score: number; ytm: number; status?: ScoreStatus; ticker?: string; isin?: string | null; currency?: string; issuer_risk?: { level: string; score: number } | null; distressed?: boolean };
  const points: Point[] = useMemo(() => bonds
    .map<Point | null>((bond) => {
      const score = scoreLookup(bond.internal_id)?.score ?? null;
      const ytm = bond.yield_to_maturity ?? null;
      if (score == null || ytm == null || ytm <= 0) return null;
      return {
        internal_id: bond.internal_id,
        name: bond.name,
        score,
        ytm,
        status: bond.score_status ?? undefined,
        ticker: bond.internal_id,
        isin: bond.isin ?? null,
        currency: bond.currency,
        issuer_risk: bond.issuer_risk ?? null,
        distressed: bond.distressed,
      };
    })
    .filter((p): p is Point => p !== null)
    .slice(0, 500), [bonds, scoreLookup]);

  type View = { scoreMin: number; scoreMax: number; ytmMin: number; ytmMax: number };

  const ytmMax = useMemo(() => {
    if (!points.length) return 30;
    return Math.max(8, Math.ceil(Math.max(...points.map((p) => p.ytm)) / 5) * 5);
  }, [points]);

  const fullView: View = { scoreMin: 0, scoreMax: 100, ytmMin: 0, ytmMax };
  const [view, setView] = useState<View>(fullView);
  const panRef = useRef<{ x: number; y: number; view: View; moved: boolean } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setView({ scoreMin: 0, scoreMax: 100, ytmMin: 0, ytmMax });
  }, [ytmMax]);

  const visibleCount = points.filter((p) =>
    p.score >= view.scoreMin && p.score <= view.scoreMax &&
    p.ytm >= view.ytmMin && p.ytm <= view.ytmMax,
  ).length;

  if (points.length < 2) return null;

  const zoomFactor = (f: number) =>
    setView((v) => {
      const cX = (v.scoreMin + v.scoreMax) / 2;
      const cY = (v.ytmMin + v.ytmMax) / 2;
      const spanX = ((v.scoreMax - v.scoreMin) * f) / 2;
      const spanY = ((v.ytmMax - v.ytmMin) * f) / 2;
      return {
        scoreMin: Math.max(0, cX - spanX),
        scoreMax: Math.min(100, cX + spanX),
        ytmMin: Math.max(0, cY - spanY),
        ytmMax: Math.min(ytmMax, cY + spanY),
      };
    });

  const zoomIn = () => zoomFactor(0.65);
  const zoomOut = () => zoomFactor(1.35);

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoomFactor(e.deltaY > 0 ? 1.25 : 0.8);
  };

  const recenter = () => setView(fullView);

  const startPan = (e: React.MouseEvent<HTMLDivElement>) => {
    panRef.current = { x: e.clientX, y: e.clientY, view, moved: false };
    if (chartWrapRef.current) chartWrapRef.current.style.cursor = 'grabbing';
  };

  const movePan = (e: React.MouseEvent<HTMLDivElement>) => {
    const p = panRef.current;
    if (!p) return;
    if (Math.abs(e.clientX - p.x) + Math.abs(e.clientY - p.y) < 5) return;
    p.moved = true;
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = ((e.clientX - p.x) / rect.width) * (view.scoreMax - view.scoreMin);
    const dy = ((e.clientY - p.y) / rect.height) * (view.ytmMax - view.ytmMin);
    setView({
      scoreMin: Math.max(0, Math.min(100 - (view.scoreMax - view.scoreMin), p.view.scoreMin - dx)),
      scoreMax: Math.min(100, Math.max(100 - (view.scoreMax - view.scoreMin), p.view.scoreMax - dx)),
      ytmMin: Math.max(0, Math.min(ytmMax - (view.ytmMax - view.ytmMin), p.view.ytmMin + dy)),
      ytmMax: Math.min(ytmMax, Math.max(ytmMax - (view.ytmMax - view.ytmMin), p.view.ytmMax + dy)),
    });
  };

  const endPan = () => {
    panRef.current = null;
    if (chartWrapRef.current) chartWrapRef.current.style.cursor = 'grab';
  };

  const handlePointClick = (point: Point) => {
    bondDrawerStore.open(point.internal_id);
  };

  const handleChartClick = (e: { activePayload?: { payload?: Point }[] } | null) => {
    const payload = e && 'activePayload' in e ? e.activePayload?.[0]?.payload : undefined;
    if (payload) handlePointClick(payload);
  };

  const handleChartContainerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (panRef.current?.moved) return;
    const wrap = chartWrapRef.current;
    if (!wrap) return;
    const svg = wrap.querySelector('svg.recharts-surface');
    if (!svg) return;
    const svgRect = svg.getBoundingClientRect();
    const plotLeft = svgRect.left + 12;
    const plotTop = svgRect.top + 12;
    const plotWidth = svgRect.width - 12 - 24;
    const plotHeight = svgRect.height - 12 - 32;
    const px = e.clientX - plotLeft;
    const py = e.clientY - plotTop;
    if (px < 0 || py < 0 || px > plotWidth || py > plotHeight) return;
    const score = view.scoreMin + (px / plotWidth) * (view.scoreMax - view.scoreMin);
    const ytm = view.ytmMax - (py / plotHeight) * (view.ytmMax - view.ytmMin);
    let best: Point | null = null;
    let bestDist = Infinity;
    for (const p of points) {
      const dx = ((p.score - score) / Math.max(1, view.scoreMax - view.scoreMin)) * plotWidth;
      const dy = ((p.ytm - ytm) / Math.max(1, view.ytmMax - view.ytmMin)) * plotHeight;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < bestDist && d < 24) {
        bestDist = d;
        best = p;
      }
    }
    if (best) handlePointClick(best);
  };

  const statusColor = (status?: ScoreStatus) => {
    switch (status) {
      case 'attractive': return '#06b663';
      case 'review': return '#dc6803';
      case 'high_risk': return '#e03400';
      case 'neutral': return '#0B526B';
      case 'no_data': return '#516c79';
      default: return '#0B526B';
    }
  };

  return (
    <div
      ref={containerRef}
      style={{ marginBottom: 20, padding: '16px 18px', background: '#fff', border: '1px solid #eef3f5', borderRadius: 10 }}
      onWheel={handleWheel}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Карта возможностей рынка</div>
          <div style={{ fontSize: 12, color: '#516c79' }}>
            Score и YTM по live-универсу · клик по кружочку — карточка облигации · +/− — приблизить/отдалить · drag — сдвиг ·
            показано {visibleCount} из {points.length}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#717680', marginRight: 4 }}>
            {Math.round(((view.scoreMax - view.scoreMin) / 100) * 100)}% видимости · клик по точке — детали · +/− — zoom · drag — сдвиг
          </span>
          <button onClick={zoomOut} aria-label="Уменьшить" style={zoomBtnStyle}><ZoomOut size={14} /></button>
          <button onClick={zoomIn} aria-label="Увеличить" style={zoomBtnStyle}><ZoomIn size={14} /></button>
          <button onClick={recenter} aria-label="Сбросить масштаб" style={zoomBtnStyle}><RotateCcw size={14} /></button>
        </div>
      </div>
      <div
        ref={chartWrapRef}
        style={{
          height: 380,
          width: '100%',
          cursor: 'grab',
          userSelect: 'none',
          touchAction: 'none',
        }}
        onMouseDown={startPan}
        onMouseMove={movePan}
        onMouseUp={endPan}
        onMouseLeave={endPan}
        onClick={handleChartContainerClick}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart
            margin={{ top: 12, right: 24, bottom: 32, left: 12 }}
            onClick={handleChartClick}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#eef3f5" />
            <XAxis
              type="number"
              dataKey="score"
              domain={[view.scoreMin, view.scoreMax]}
              tick={{ fontSize: 11, fill: '#516c79' }}
              label={{ value: 'Score', position: 'insideBottom', offset: -10, fontSize: 12, fill: '#516c79' }}
              tickCount={6}
            />
            <YAxis
              type="number"
              dataKey="ytm"
              domain={[view.ytmMin, view.ytmMax]}
              tick={{ fontSize: 11, fill: '#516c79' }}
              label={{ value: 'YTM %', angle: -90, position: 'insideLeft', offset: 10, fontSize: 12, fill: '#516c79' }}
              tickCount={6}
            />
              <ZAxis range={[60, 60]} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={(props: TooltipProps<number, string>) => {
                  const { active, payload } = props;
                  if (!active || !payload || !payload.length) return null;
                  const item = payload[0];
                  if (!item || typeof item.payload !== 'object') return null;
                  const p = item.payload as unknown as Point;
                  return (
                    <div style={tooltipStyle}>
                      <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>
                        {formatBondDisplayName(p.name, p.internal_id, p.isin)}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'auto auto', gap: '2px 8px', fontSize: 11 }}>
                        <span style={{ color: '#717680' }}>ISIN:</span><span>{p.isin ?? '—'}</span>
                        <span style={{ color: '#717680' }}>Score:</span><span style={{ fontWeight: 600 }}>{p.score.toFixed(1)}</span>
                        <span style={{ color: '#717680' }}>YTM:</span><span style={{ fontWeight: 600 }}>{p.ytm.toFixed(2)}%</span>
                        <span style={{ color: '#717680' }}>Валюта:</span><span>{p.currency ?? '—'}</span>
                        {p.issuer_risk && (
                          <>
                            <span style={{ color: '#717680' }}>Риск эмитента:</span>
                            <span>{p.issuer_risk.level} · {p.issuer_risk.score}/100</span>
                          </>
                        )}
                        {p.distressed && (
                          <>
                            <span style={{ color: '#e03400' }}>Distressed:</span>
                            <span style={{ color: '#e03400' }}>да</span>
                          </>
                        )}
                      </div>
                      <div style={{ fontSize: 10, color: '#717680', marginTop: 4 }}>Кликните для деталей →</div>
                    </div>
                  );
                }}
              />
              <Scatter
                data={points}
                fill="#0B526B"
                shape={(props: { cx?: number; cy?: number; payload?: Point }) => {
                  const payload = props.payload;
                  if (!props.cx || !props.cy || !payload) return <g />;
                return (
                  <circle
                    cx={props.cx}
                    cy={props.cy}
                    r={payload.distressed ? 6 : 5}
                    fill={statusColor(payload.status)}
                    stroke="#fff"
                    strokeWidth={1}
                    style={{ cursor: 'pointer', opacity: 0.85, pointerEvents: 'auto' }}
                    tabIndex={0}
                    role="button"
                    aria-label={`${payload.name}, Score ${payload.score.toFixed(1)}, YTM ${payload.ytm.toFixed(2)}%`}
                    onKeyDown={(e: React.KeyboardEvent) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handlePointClick(payload);
                      }
                    }}
                  />
                );
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
      </div>
      <div style={{ display: 'flex', gap: 14, marginTop: 8, fontSize: 11, color: '#516c79', flexWrap: 'wrap' }}>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#06b663', verticalAlign: 'middle', marginRight: 4 }} />Привлекательная</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#0B526B', verticalAlign: 'middle', marginRight: 4 }} />Нейтральная</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#dc6803', verticalAlign: 'middle', marginRight: 4 }} />Проверка</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#e03400', verticalAlign: 'middle', marginRight: 4 }} />Высокий риск</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', border: '2px solid #e03400', verticalAlign: 'middle', marginRight: 4 }} />Distressed (тонкая граница)</span>
      </div>
      <details style={{ marginTop: 8 }}>
        <summary style={{ cursor: 'pointer', fontSize: 11, color: '#516c79' }}>Как читать график</summary>
        <div style={{ fontSize: 11, color: '#516c79', marginTop: 6, lineHeight: 1.5 }}>
          Ось X — Reward/Risk Score (0–100, выше = сильнее профиль).
          Ось Y — доходность к погашению (YTM, %).
          Цвет точки: зелёный — привлекательная, синий — нейтральная,
          оранжевый — на проверке, красный — высокий риск.
          Бумаги с YTM выше 30% и ценой ниже 80% номинала помечены как
          Distressed (тонкая красная граница): высокая доходность может
          означать не выгоду, а сигнал о риске дефолта.
          Используйте Ctrl + scroll для зума, drag для панорамирования.
        </div>
      </details>
    </div>
  );
}

const zoomBtnStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #d6e2e6',
  borderRadius: 6,
  width: 28,
  height: 28,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  color: '#516c79',
};

const tooltipStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #d6e2e6',
  borderRadius: 8,
  padding: '8px 10px',
  boxShadow: '0 4px 12px rgba(11, 82, 107, 0.12)',
  maxWidth: 320,
  pointerEvents: 'auto',
};
