import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Wallet,
  Target,
  PieChart,
  Calculator,
  Save,
  Plus,
  Trash2,
  ExternalLink,
  TrendingUp,
  Sliders,
  AlertCircle,
  Activity,
  Briefcase,
} from 'lucide-react';
import { fetchLiveMarket, fetchLiveSearch } from '../live-demo-api';
import {
  fetchCustomOptimize,
  fetchCustomCalculate,
} from '../live-demo-api';
import type {
  CustomOptimizeResponse,
  CustomCalculateResponse,
  CustomExcluded,
  CustomMetrics,
} from '../live-demo-api';
import type { DemoBond } from '../types';
import { formatBondDisplayName, formatYtm } from '../demo-format';
import { bondDrawerStore } from '../drawer-store';
import { DEMO_PERSONA } from '../demo-config';

const OBJECTIVES = [
  { key: 'equal_weight', label: 'Равные веса' },
  { key: 'min_variance', label: 'Минимум дисперсии' },
  { key: 'risk_parity', label: 'Risk Parity (равный риск)' },
  { key: 'max_sharpe', label: 'Максимум коэф. Шарпа' },
];

const LS_KEY = 'aigenis_demo_portfolios';

interface NamedPortfolio {
  name: string;
  internal_ids: string[];
  amounts?: Record<string, number>;
  objective?: string;
  currency: string;
}

function MetricCard({
  label,
  value,
  color,
  icon,
}: {
  label: string;
  value: string;
  color: string;
  icon: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: '#fff',
        padding: 20,
        borderRadius: 12,
        border: '1px solid #d6e2e6',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          color: '#717680',
          fontSize: 13,
          fontWeight: 500,
        }}
      >
        {icon}
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color, marginTop: 8 }}>{value}</div>
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: CustomMetrics }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
        gap: 16,
        marginBottom: 24,
      }}
    >
      <MetricCard
        label="Ожидаемая доходность"
        value={`${metrics.expected_return.toFixed(2)}%`}
        color="#06b663"
        icon={<TrendingUp size={18} color="#06b663" />}
      />
      <MetricCard
        label="Взвешенная дюрация"
        value={`${metrics.weighted_duration.toFixed(1)} г.`}
        color="#0B526B"
        icon={<Sliders size={18} color="#0B526B" />}
      />
      <MetricCard
        label="Коэф. Шарпа"
        value={`${metrics.sharpe.toFixed(2)}`}
        color="#01121a"
        icon={<Sliders size={18} color="#0B526B" />}
      />
      <MetricCard
        label="Коэф. Сортино"
        value={`${metrics.sortino.toFixed(2)}`}
        color="#01121a"
        icon={<Sliders size={18} color="#0B526B" />}
      />
      <MetricCard
        label="Текущая доходность"
        value={`${metrics.weighted_current_yield.toFixed(2)}%`}
        color="#0B526B"
        icon={<Activity size={18} color="#0B526B" />}
      />
      <MetricCard
        label="Макс. просадка"
        value={`${metrics.max_drawdown.toFixed(2)}%`}
        color="#dc6803"
        icon={<AlertCircle size={18} color="#dc6803" />}
      />
      <MetricCard
        label="VaR 95%"
        value={`${metrics.var_95.toFixed(2)}%`}
        color="#dc6803"
        icon={<AlertCircle size={18} color="#dc6803" />}
      />
      <MetricCard
        label="Коэф. Калмара"
        value={`${metrics.calmar.toFixed(2)}`}
        color="#01121a"
        icon={<Sliders size={18} color="#0B526B" />}
      />
    </div>
  );
}

function ResultNotices({
  excluded,
  warning,
}: {
  excluded?: CustomExcluded[];
  warning?: string | null;
}) {
  if ((!excluded || excluded.length === 0) && !warning) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
      {warning && (
        <div
          style={{
            background: '#fff8f0',
            border: '1px solid #f0c76a',
            borderRadius: 12,
            padding: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <AlertCircle size={18} color="#dc6803" />
          <span style={{ fontSize: 13, color: '#516c79' }}>{warning}</span>
        </div>
      )}
      {excluded && excluded.length > 0 && (
        <div style={{ background: '#fdf3f3', border: '1px solid #f0a9a9', borderRadius: 12, padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#a4262c', marginBottom: 8 }}>
            Исключены из портфеля ({excluded.length})
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: '#516c79' }}>
            {excluded.map((e, i) => (
              <li key={i} style={{ marginBottom: 2 }}>
                <strong>{e.name || e.internal_id}</strong>
                {e.reason ? ` — ${e.reason}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConcentrationBar({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).slice(0, 6);
  if (!entries.length) return null;
  return (
    <div style={{ marginTop: 8 }}>
      {entries.map(([issuer, pct]) => (
        <div key={issuer} style={{ marginBottom: 8 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: 12,
              color: '#516c79',
              marginBottom: 4,
            }}
          >
            <span style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {issuer}
            </span>
            <span>{pct}%</span>
          </div>
          <div style={{ height: 6, background: '#eef3f5', borderRadius: 4, overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.min(pct, 100)}%`,
                height: '100%',
                background: pct > 40 ? '#dc6803' : '#0B526B',
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DemoPortfolioLabPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const routeMarket = (searchParams.get('market') ?? 'BCSE').toUpperCase();
  const market = routeMarket === 'MOEX' ? 'MOEX' : 'BCSE';

  const [liveBonds, setLiveBonds] = useState<DemoBond[]>([]);

  // ----- My Portfolio (demo user) -----
  const [userResult, setUserResult] = useState<CustomCalculateResponse | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);

  // ----- Builder -----
  const [mode, setMode] = useState<'optimize' | 'calculate'>('optimize');
  const [capital, setCapital] = useState(50000);
  const [currency, setCurrency] = useState(market === 'MOEX' ? 'RUB' : 'BYN');
  const [objective, setObjective] = useState('equal_weight');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [amounts, setAmounts] = useState<Record<string, number>>({});
  const [result, setResult] = useState<CustomOptimizeResponse | CustomCalculateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ----- Search -----
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<DemoBond[]>([]);
  const [searching, setSearching] = useState(false);

  // ----- Named portfolios (localStorage) -----
  const [saved, setSaved] = useState<NamedPortfolio[]>([]);
  const [portfolioName, setPortfolioName] = useState('');

  const bondMap = useMemo(() => {
    const m: Record<string, DemoBond> = {};
    for (const b of [...liveBonds, ...searchResults]) m[b.internal_id] = b;
    return m;
  }, [liveBonds, searchResults]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) setSaved(JSON.parse(raw) as NamedPortfolio[]);
    } catch {
      /* ignore */
    }
  }, []);

  const persistSaved = useCallback((next: NamedPortfolio[]) => {
    setSaved(next);
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  }, []);

  const loadMarket = useCallback(async () => {
    try {
      const snap = await fetchLiveMarket(market.toLowerCase(), 'ALL');
      setLiveBonds(snap.bonds);
    } catch {
      setLiveBonds([]);
    }
  }, [market]);

  useEffect(() => {
    loadMarket();
  }, [loadMarket]);

  // Demo user's portfolio: top holdings derived from live data (deterministic).
  useEffect(() => {
    const computeUser = async () => {
      setLoadingUser(true);
      try {
        const localCurrency = market === 'MOEX' ? 'RUB' : 'BYN';
        const personaCapital =
          market === 'MOEX' ? DEMO_PERSONA.portfolio_rub : DEMO_PERSONA.portfolio_byn;
        const snap = await fetchLiveMarket(market.toLowerCase(), localCurrency);
        const pool = snap.bonds
          .filter((b) => b.yield_to_maturity != null && (b.score ?? 0) > 0)
          .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
          .slice(0, 6);
        if (!pool.length) {
          setUserResult(null);
          return;
        }
        const per = Math.round(personaCapital / pool.length);
        const holdings = pool.map((b) => ({ internal_id: b.internal_id, amount: per }));
        const res = await fetchCustomCalculate(holdings, localCurrency);
        setUserResult(res);
      } catch {
        setUserResult(null);
      } finally {
        setLoadingUser(false);
      }
    };
    computeUser();
  }, [market]);

  const runBuilder = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (mode === 'optimize') {
        if (!selectedIds.length) {
          setError('Добавьте хотя бы одну облигацию в портфель.');
          setLoading(false);
          return;
        }
        const res = await fetchCustomOptimize({
          internal_ids: selectedIds,
          capital,
          currency,
          objective,
          market: market.toLowerCase(),
        });
        setResult(res);
      } else {
        const holdings = selectedIds.map((id) => ({
          internal_id: id,
          amount: amounts[id] ?? 10000,
        }));
        if (!holdings.length) {
          setError('Добавьте хотя бы одну облигацию в портфель.');
          setLoading(false);
          return;
        }
        const res = await fetchCustomCalculate(holdings, currency);
        setResult(res);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка расчёта портфеля.');
    } finally {
      setLoading(false);
    }
  }, [mode, selectedIds, capital, currency, objective, amounts, market]);

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setSearchResults([]);
        return;
      }
      setSearching(true);
      try {
        const r = await fetchLiveSearch(q, market.toLowerCase());
        setSearchResults(r.bonds.slice(0, 20));
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    },
    [market],
  );

  const addBond = (id: string) => {
    if (!selectedIds.includes(id)) {
      setSelectedIds((prev) => [...prev, id]);
      setAmounts((prev) => ({ ...prev, [id]: prev[id] ?? 10000 }));
    }
  };
  const removeBond = (id: string) => {
    setSelectedIds((prev) => prev.filter((x) => x !== id));
  };
  const setAmount = (id: string, value: number) => {
    setAmounts((prev) => ({ ...prev, [id]: value }));
  };

  const savePortfolio = () => {
    const name = portfolioName.trim() || `Портфель ${saved.length + 1}`;
    const next: NamedPortfolio = {
      name,
      internal_ids: selectedIds,
      amounts: mode === 'calculate' ? { ...amounts } : undefined,
      objective: mode === 'optimize' ? objective : undefined,
      currency,
    };
    persistSaved([...saved, next]);
    setPortfolioName('');
  };

  const loadNamed = (p: NamedPortfolio) => {
    setSelectedIds(p.internal_ids);
    setCurrency(p.currency);
    if (p.amounts) {
      setAmounts(p.amounts);
      setMode('calculate');
    } else {
      setMode('optimize');
      setObjective(p.objective ?? 'equal_weight');
    }
  };

  const deleteNamed = (idx: number) => {
    persistSaved(saved.filter((_, i) => i !== idx));
  };

  const setMarketParam = (next: 'BCSE' | 'MOEX') => {
    const params = new URLSearchParams(searchParams);
    params.set('market', next);
    setSearchParams(params);
    if (next === 'MOEX' && currency === 'BYN') setCurrency('RUB');
    if (next === 'BCSE' && currency === 'RUB') setCurrency('BYN');
  };

  const localCurrency = market === 'MOEX' ? 'RUB' : 'BYN';

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: '#01121a' }}>
          Лаборатория Портфелей: Оптимизатор и Калькулятор
        </h1>
        <p style={{ color: '#516c79', fontSize: 14, marginTop: 4, margin: 0 }}>
          Соберите свой портфель из любых облигаций рынка — система покажет реальный YTM и все
          параметры риска/доходности. Без жёстких стратегий.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', background: '#eef3f5', padding: 3, borderRadius: 8 }}>
          {(['BCSE', 'MOEX'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMarketParam(m)}
              style={{
                padding: '8px 16px',
                borderRadius: 6,
                border: 'none',
                background: market === m ? '#0B526B' : 'transparent',
                color: market === m ? '#fff' : '#516c79',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {m === 'BCSE' ? 'BCSE (Беларусь)' : 'MOEX (Россия)'}
            </button>
          ))}
        </div>
      </div>

      {/* ===== Section 1: My Portfolio ===== */}
      <Section title="Мой портфель (демо-пользователь)" icon={<Wallet size={20} color="#0B526B" />}>
        <p style={{ fontSize: 13, color: '#516c79', marginTop: 0 }}>
          {DEMO_PERSONA.name} · {DEMO_PERSONA.label} · цель: «{DEMO_PERSONA.goal}». Реальные
          показатели по удерживаемым бумагам.
        </p>
        {loadingUser && <Loading text="Загрузка портфеля пользователя..." />}
        {!loadingUser && !userResult && (
          <Empty text="Нет доступных облигаций для формирования демо-портфеля." />
        )}
        {!loadingUser && userResult && (
          <>
            <MetricsGrid metrics={userResult.metrics} />
            <HoldingsTable
              holdings={userResult.metrics.holdings}
              onOpen={(id) => bondDrawerStore.open(id)}
            />
            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                Концентрация по эмитенту
              </div>
              <ConcentrationBar data={userResult.metrics.concentration_by_issuer} />
            </div>
          </>
        )}
      </Section>

      {/* ===== Section 2: Builder ===== */}
      <Section title="Конструктор портфеля" icon={<Briefcase size={20} color="#0B526B" />}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <Toggle active={mode === 'optimize'} onClick={() => setMode('optimize')}>
            <Target size={16} /> Оптимизатор (аллокация)
          </Toggle>
          <Toggle active={mode === 'calculate'} onClick={() => setMode('calculate')}>
            <Calculator size={16} /> Калькулятор (свои суммы)
          </Toggle>
        </div>

        {mode === 'optimize' && (
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', padding: '8px 14px', borderRadius: 8, border: '1px solid #d6e2e6' }}>
              <span style={{ fontSize: 13, color: '#717680', fontWeight: 500 }}>Капитал:</span>
              <input
                type="number"
                value={capital}
                onChange={(e) => setCapital(Number(e.target.value) || 10000)}
                style={{ width: 110, border: 'none', fontWeight: 700, fontSize: 15, color: '#01121a', outline: 'none' }}
              />
              <span style={{ fontSize: 13, color: '#717680', fontWeight: 600 }}>{currency}</span>
            </div>
            <div style={{ display: 'flex', background: '#eef3f5', padding: 3, borderRadius: 8 }}>
              <button
                onClick={() => setCurrency(localCurrency)}
                style={curBtn(currency === localCurrency)}
              >
                {localCurrency}
              </button>
              <button onClick={() => setCurrency('USD')} style={curBtn(currency === 'USD')}>
                USD
              </button>
            </div>
          </div>
        )}

        {mode === 'optimize' && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, fontWeight: 600, color: '#516c79', display: 'block', marginBottom: 10 }}>
              Цель оптимизации:
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
              {OBJECTIVES.map((o) => {
                const active = o.key === objective;
                return (
                  <button
                    key={o.key}
                    onClick={() => setObjective(o.key)}
                    style={{
                      padding: 14,
                      borderRadius: 10,
                      border: active ? '2px solid #0B526B' : '1px solid #d6e2e6',
                      background: active ? '#f5f9fb' : '#fff',
                      textAlign: 'left',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: 14,
                      color: active ? '#0B526B' : '#01121a',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Sliders size={16} color={active ? '#0B526B' : '#717680'} />
                      {o.label}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Search + selected */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 16 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>Поиск облигаций</div>
            <input
              type="text"
              placeholder="Название, ISIN, эмитент, ID..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                doSearch(e.target.value);
              }}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 8,
                border: '1px solid #d6e2e6',
                fontSize: 14,
                outline: 'none',
              }}
            />
            <div style={{ marginTop: 8, maxHeight: 320, overflowY: 'auto' }}>
              {searching && <div style={{ fontSize: 12, color: '#8fa0a8' }}>Поиск...</div>}
              {!searching &&
                searchResults.map((b) => (
                  <div
                    key={b.internal_id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '8px 10px',
                      borderBottom: '1px solid #f0f4f8',
                    }}
                  >
                    <div style={{ fontSize: 13 }}>
                      <div style={{ fontWeight: 600, color: '#0B526B' }}>
                        {formatBondDisplayName(b.name, b.internal_id, b.isin)}
                      </div>
                      <div style={{ fontSize: 11, color: '#8fa0a8' }}>
                        YTM {formatYtm(b.yield_to_maturity)} · {b.currency}
                      </div>
                    </div>
                    <button
                      onClick={() => addBond(b.internal_id)}
                      disabled={selectedIds.includes(b.internal_id)}
                      style={{
                        border: 'none',
                        background: selectedIds.includes(b.internal_id) ? '#eef3f5' : '#0B526B',
                        color: selectedIds.includes(b.internal_id) ? '#8fa0a8' : '#fff',
                        borderRadius: 6,
                        padding: '6px 10px',
                        cursor: 'pointer',
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                ))}
            </div>
          </div>

          <div>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
              Выбрано ({selectedIds.length})
            </div>
            <div style={{ marginTop: 8, maxHeight: 320, overflowY: 'auto' }}>
              {selectedIds.length === 0 && (
                <div style={{ fontSize: 13, color: '#8fa0a8' }}>Портфель пуст — добавьте бумаги слева.</div>
              )}
              {selectedIds.map((id) => {
                const b = bondMap[id];
                return (
                  <div
                    key={id}
                    style={{
                      padding: '8px 10px',
                      borderBottom: '1px solid #f0f4f8',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 6,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: '#0B526B' }}>
                        {b ? formatBondDisplayName(b.name, b.internal_id, b.isin) : id}
                      </span>
                      <button
                        onClick={() => removeBond(id)}
                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#dc6803' }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    {mode === 'calculate' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 12, color: '#717680' }}>Сумма:</span>
                        <input
                          type="number"
                          value={amounts[id] ?? 10000}
                          onChange={(e) => setAmount(id, Number(e.target.value) || 0)}
                          style={{ width: 120, padding: '4px 8px', borderRadius: 6, border: '1px solid #d6e2e6', fontSize: 13 }}
                        />
                        <span style={{ fontSize: 12, color: '#717680' }}>{currency}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={runBuilder}
            disabled={loading}
            style={{
              padding: '12px 22px',
              borderRadius: 8,
              border: 'none',
              background: '#0B526B',
              color: '#fff',
              fontWeight: 700,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            {loading ? 'Расчёт...' : mode === 'optimize' ? 'Оптимизировать портфель' : 'Рассчитать портфель'}
          </button>

          <input
            type="text"
            placeholder="Название портфеля..."
            value={portfolioName}
            onChange={(e) => setPortfolioName(e.target.value)}
            style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid #d6e2e6', fontSize: 14 }}
          />
          <button
            onClick={savePortfolio}
            disabled={!selectedIds.length}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid #0B526B',
              background: '#fff',
              color: '#0B526B',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Save size={14} /> Сохранить
          </button>
        </div>

        {error && (
          <div style={{ marginTop: 16, background: '#fff8f0', border: '1px solid #f0c76a', borderRadius: 12, padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
            <AlertCircle size={20} color="#dc6803" />
            <span style={{ fontSize: 13, color: '#516c79' }}>{error}</span>
          </div>
        )}

        {/* Result */}
        {result && result.mode === 'optimize' && (result as CustomOptimizeResponse).allocations.length > 0 && (
          <OptimizeResult res={result as CustomOptimizeResponse} onOpen={(id) => bondDrawerStore.open(id)} />
        )}
        {result && result.mode === 'calculate' && (result as CustomCalculateResponse).metrics.holdings.length > 0 && (
          <CalcResult res={result as CustomCalculateResponse} onOpen={(id) => bondDrawerStore.open(id)} />
        )}
        {result && ((result.mode === 'optimize' && (result as CustomOptimizeResponse).allocations.length === 0) ||
          (result.mode === 'calculate' && (result as CustomCalculateResponse).metrics.holdings.length === 0)) && (
          <div style={{ marginTop: 16, background: '#fff8f0', border: '1px solid #f0c76a', borderRadius: 12, padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
            <AlertCircle size={20} color="#dc6803" />
            <span style={{ fontSize: 13, color: '#516c79' }}>
              {result.warning || 'Недостаточно данных для расчёта по выбранным облигациям.'}
            </span>
          </div>
        )}
      </Section>

      {/* ===== Section 3: Named portfolios ===== */}
      <Section title="Сохранённые портфели" icon={<Save size={20} color="#0B526B" />}>
        {saved.length === 0 && (
          <Empty text="Пока нет сохранённых портфелей. Соберите портфель выше и нажмите «Сохранить»." />
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
          {saved.map((p, idx) => (
            <div key={idx} style={{ border: '1px solid #d6e2e6', borderRadius: 10, padding: 14, background: '#fff' }}>
              <div style={{ fontWeight: 700, color: '#01121a' }}>{p.name}</div>
              <div style={{ fontSize: 12, color: '#516c79', marginTop: 4 }}>
                {p.internal_ids.length} бумаг · {p.currency}
                {p.objective ? ` · ${OBJECTIVES.find((o) => o.key === p.objective)?.label ?? p.objective}` : ' · свои суммы'}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button
                  onClick={() => loadNamed(p)}
                  style={{ flex: 1, padding: '8px', borderRadius: 6, border: 'none', background: '#0B526B', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}
                >
                  Открыть
                </button>
                <button
                  onClick={() => deleteNamed(idx)}
                  style={{ padding: '8px', borderRadius: 6, border: 'none', background: '#fff8f0', color: '#dc6803', cursor: 'pointer' }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function curBtn(active: boolean): React.CSSProperties {
  return {
    padding: '8px 16px',
    borderRadius: 6,
    border: 'none',
    background: active ? '#0B526B' : 'transparent',
    color: active ? '#fff' : '#516c79',
    fontWeight: 600,
    cursor: 'pointer',
    fontSize: 13,
  };
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '10px 16px',
        borderRadius: 8,
        border: active ? '2px solid #0B526B' : '1px solid #d6e2e6',
        background: active ? '#f5f9fb' : '#fff',
        color: active ? '#0B526B' : '#516c79',
        fontWeight: 600,
        cursor: 'pointer',
        fontSize: 13,
      }}
    >
      {children}
    </button>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        background: '#fff',
        borderRadius: 12,
        border: '1px solid #d6e2e6',
        padding: 24,
        marginBottom: 24,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 18, marginBottom: 16, color: '#01121a' }}>
        {icon}
        {title}
      </div>
      {children}
    </section>
  );
}

function Loading({ text }: { text: string }) {
  return <div style={{ textAlign: 'center', padding: 24, color: '#717680', fontSize: 13 }}>{text}</div>;
}

function Empty({ text }: { text: string }) {
  return <div style={{ padding: 16, color: '#8fa0a8', fontSize: 13 }}>{text}</div>;
}

function HoldingsTable({
  holdings,
  onOpen,
}: {
  holdings: Array<{
    internal_id: string;
    name: string;
    issuer: string | null;
    currency: string | null;
    amount: number;
    weight_pct: number;
    ytm: number;
    duration_years: number;
    current_yield: number;
  }>;
  onOpen: (id: string) => void;
}) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 16, marginBottom: 16 }}>
        <PieChart size={20} color="#0B526B" /> Состав портфеля
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #e1e9ed', textAlign: 'left', color: '#5a6e78' }}>
              <th style={{ padding: 8 }}>Облигация</th>
              <th style={{ padding: 8 }}>Доля</th>
              <th style={{ padding: 8 }}>Сумма</th>
              <th style={{ padding: 8 }}>YTM</th>
              <th style={{ padding: 8 }}>Дюрация</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => (
              <tr
                key={h.internal_id}
                onClick={() => onOpen(h.internal_id)}
                style={{ borderBottom: '1px solid #f0f4f8', cursor: 'pointer' }}
              >
                <td style={{ padding: 10, fontWeight: 600, color: '#0B526B' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span>{formatBondDisplayName(h.name, h.internal_id)}</span>
                    <ExternalLink size={12} color="#8fa0a8" />
                  </div>
                </td>
                <td style={{ padding: 10, color: '#0B526B', fontWeight: 600 }}>{h.weight_pct.toFixed(1)}%</td>
                <td style={{ padding: 10, color: '#516c79' }}>
                  {Math.round(h.amount).toLocaleString('ru-RU')} {h.currency ?? ''}
                </td>
                <td style={{ padding: 10, color: '#06b663', fontWeight: 600 }}>{formatYtm(h.ytm)}</td>
                <td style={{ padding: 10, color: '#516c79' }}>{h.duration_years.toFixed(1)} г.</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OptimizeResult({
  res,
  onOpen,
}: {
  res: CustomOptimizeResponse;
  onOpen: (id: string) => void;
}) {
  return (
    <>
      <MetricsGrid metrics={res.metrics} />
      <ResultNotices excluded={res.excluded} warning={res.warning} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 16, marginBottom: 16 }}>
            <PieChart size={20} color="#0B526B" /> Целевая аллокация ({res.objective_ru})
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e1e9ed', textAlign: 'left', color: '#5a6e78' }}>
                  <th style={{ padding: 8 }}>Облигация</th>
                  <th style={{ padding: 8 }}>Доля</th>
                  <th style={{ padding: 8 }}>Сумма</th>
                  <th style={{ padding: 8 }}>YTM</th>
                </tr>
              </thead>
              <tbody>
                {res.allocations.map((a) => (
                  <tr
                    key={a.internal_id}
                    onClick={() => onOpen(a.internal_id)}
                    style={{ borderBottom: '1px solid #f0f4f8', cursor: 'pointer' }}
                  >
                    <td style={{ padding: 10, fontWeight: 600, color: '#0B526B' }}>
                      {formatBondDisplayName(a.name, a.internal_id, a.isin)}
                    </td>
                    <td style={{ padding: 10, color: '#0B526B', fontWeight: 600 }}>{a.weight_pct.toFixed(1)}%</td>
                    <td style={{ padding: 10, color: '#516c79' }}>
                      {Math.round(a.amount).toLocaleString('ru-RU')} {a.currency ?? res.currency}
                    </td>
                    <td style={{ padding: 10, color: '#06b663', fontWeight: 600 }}>{formatYtm(a.ytm)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, fontSize: 16, marginBottom: 16 }}>
            <Activity size={20} color="#0B526B" /> Биржевые ордера
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {res.order_tickets.map((t, i) => (
              <div
                key={i}
                onClick={() => onOpen(t.internal_id)}
                style={{
                  padding: 14,
                  background: '#f5f9fb',
                  borderRadius: 8,
                  border: '1px solid #d6e2e6',
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 13, color: '#01121a' }}>
                  <span style={{ background: '#06b663', color: '#fff', padding: '2px 8px', borderRadius: 4, fontSize: 11 }}>{t.action}</span>
                  <span>{formatBondDisplayName(t.name, t.internal_id)}</span>
                </div>
                <div style={{ fontSize: 12, color: '#717680', marginTop: 4 }}>{t.rationale}</div>
                <div style={{ textAlign: 'right', fontWeight: 700, fontSize: 14, color: '#0B526B', marginTop: 4 }}>
                  {t.lots} шт. · ~{(t.est_cost ?? 0).toLocaleString('ru-RU')} {t.currency ?? res.currency}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>Концентрация по эмитенту</div>
        <ConcentrationBar data={res.metrics.concentration_by_issuer} />
      </div>
    </>
  );
}

function CalcResult({
  res,
  onOpen,
}: {
  res: CustomCalculateResponse;
  onOpen: (id: string) => void;
}) {
  return (
    <>
      <MetricsGrid metrics={res.metrics} />
      <ResultNotices excluded={res.excluded} warning={res.warning} />
      <HoldingsTable holdings={res.metrics.holdings} onOpen={onOpen} />
      <div style={{ marginTop: 16 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>Концентрация по эмитенту</div>
        <ConcentrationBar data={res.metrics.concentration_by_issuer} />
      </div>
    </>
  );
}
