import { useEffect, useMemo, useState } from 'react';
import { Search, Star, Download, RotateCcw, AlertTriangle, Brain, TrendingUp, PieChart, Clock, Bell, Calculator, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api, exportCsv } from '../lib/api';
import type { Bond, BondScore, CompanySummary } from '../lib/api';
import { useExchange } from '../lib/ExchangeContext';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';

type AnalyticsTab = 'bonds' | 'scores' | 'companies';

const ANALYTICS_SUB: { id: string; label: string; icon: React.ReactNode; path: string }[] = [
  { id: 'recommendations', label: 'Рекомендации', icon: <Brain size={16} />, path: '/recommendations' },
  { id: 'desk', label: 'Desk', icon: <TrendingUp size={16} />, path: '/desk' },
  { id: 'portfolio', label: 'Портфель', icon: <PieChart size={16} />, path: '/portfolio' },
  { id: 'forecast', label: 'Прогноз', icon: <Clock size={16} />, path: '/forecast' },
  { id: 'alerts', label: 'Алерты', icon: <Bell size={16} />, path: '/alerts' },
  { id: 'calculator', label: 'Калькулятор', icon: <Calculator size={16} />, path: '/calculator' },
];

export default function AnalyticsPage() {
  const { t } = useI18n();
  usePageMeta(t('meta.analytics'));
  const { exchange } = useExchange();
  const [tab, setTab] = useState<AnalyticsTab>('bonds');

  return (
    <>
      {/* Warning banner */}
      <div style={{
        margin: '16px 0 0',
        background: '#fffaeb', border: '1px solid #fedf89', borderRadius: 10,
        padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 10,
        fontSize: 13, color: '#93370d',
      }}>
        <AlertTriangle size={18} color="#dc6803" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <div style={{ fontWeight: 600 }}>В настоящий момент на бирже нет актуального предложения ценных бумаг либо торги не проводятся.</div>
          <div style={{ fontSize: 12, marginTop: 4, color: '#b54708' }}>
            Расписание торговых сессий: {exchange === 'BCSE' ? '10:30–12:20 и 13:45–15:45 в рабочие дни' : '10:00–19:00 в рабочие дни в РБ и РФ'}. Статистика предыдущего торгового дня:
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginTop: 20, borderBottom: '1px solid #d6e2e6' }}>
        {(['bonds', 'scores', 'companies'] as AnalyticsTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '10px 20px', border: 'none', background: 'none',
              fontSize: 15, fontWeight: 500, cursor: 'pointer', position: 'relative',
              color: tab === t ? '#01121a' : '#717680',
              fontFamily: "'Onest Variable', Onest, sans-serif",
            }}
          >
            {t === 'bonds' ? 'Облигации' : t === 'scores' ? 'Скоры' : 'Компании'}
            {tab === t && <div style={{ position: 'absolute', bottom: -1, left: 0, right: 0, height: 2, background: '#004b65', borderRadius: 2 }} />}
          </button>
        ))}
      </div>

      {/* Sub-navigation for analytics features — real routes */}
      <SubNav />

      {/* Title */}
      <h1 style={{
        fontSize: 24, fontWeight: 800, marginTop: 24, marginBottom: 8,
        fontFamily: "'Montserrat Variable', Montserrat, sans-serif", letterSpacing: '-0.5px',
      }}>
        {tab === 'bonds' ? `АНАЛИТИКА ${exchange === 'BCSE' ? 'БЕЛОРУССКОЙ' : 'МОСКОВСКОЙ'} БИРЖИ` :
         tab === 'scores' ? 'РЕЙТИНГ ОБЛИГАЦИЙ' : 'КОМПАНИИ-ЭМИТЕНТЫ'}
      </h1>

      {tab === 'bonds' && <BondsTab />}
      {tab === 'scores' && <ScoresTab />}
      {tab === 'companies' && <CompaniesTab />}
    </>
  );
}

function SubNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <div style={{ display: 'flex', gap: 4, marginTop: 16, flexWrap: 'wrap' }}>
      {ANALYTICS_SUB.map((item) => {
        const active = pathname.startsWith(item.path);
        return (
          <button
            key={item.id}
            onClick={() => navigate(item.path)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 500,
              background: active ? '#eef3f5' : '#ffffff',
              color: active ? '#004b65' : '#516c79',
              fontFamily: "'Onest Variable', Onest, sans-serif",
            }}
          >
            {item.icon} {item.label}
          </button>
        );
      })}
    </div>
  );
}

function BondsTab() {
  const [allBonds, setAllBonds] = useState<Bond[]>([]);
  const [scoreMap, setScoreMap] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activePresets, setActivePresets] = useState<Set<string>>(new Set());
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.bonds.list({ limit: 2000 }),
      api.scores({ limit: 2000 }).catch(() => [] as BondScore[]),
    ]).then(([bs, sc]) => {
      setAllBonds(bs);
      const m: Record<string, number> = {};
      sc.forEach((s) => { m[s.internal_id] = s.score; });
      setScoreMap(m);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const togglePreset = (id: string) => {
    setActivePresets((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const presets = [
    { id: 'ytm10', label: 'YTM ≥ 10%', filter: (b: Bond) => (b.yield_to_maturity ?? 0) >= 10 },
    { id: 'score70', label: 'Скор ≥ 70', filter: (_: Bond, sc: number | undefined) => (sc ?? 0) >= 70 },
    { id: 'active', label: 'Только active', filter: (b: Bond) => b.status === 'active' },
    { id: 'short', label: 'Короткие (<3 г)', filter: (b: Bond) => {
      if (!b.maturity_date) return false;
      const yrs = (new Date(b.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 3600 * 1000);
      return yrs > 0 && yrs < 3;
    }},
    { id: 'fav', label: 'Избранное', filter: () => true },
  ];

  const filtered = useMemo(() => {
    let rows = allBonds.filter((b) => {
      if (search) {
        const q = search.toLowerCase();
        if (!b.name?.toLowerCase().includes(q) && !b.internal_id?.toLowerCase().includes(q)) return false;
      }
      for (const p of presets) {
        if (activePresets.has(p.id) && p.id !== 'fav') {
          const sc = scoreMap[b.internal_id];
          if (!p.filter(b, sc)) return false;
        }
      }
      if (activePresets.has('fav') && !favorites.has(b.internal_id)) return false;
      return true;
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      let av: number; let bv: number;
      if (sortKey === 'score') { av = scoreMap[a.internal_id] ?? -Infinity; bv = scoreMap[b.internal_id] ?? -Infinity; }
      else { av = (a as any)[sortKey] ?? -Infinity; bv = (b as any)[sortKey] ?? -Infinity; }
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
  }, [allBonds, search, activePresets, sortKey, sortDir, scoreMap, favorites]);

  const doSort = (key: string) => {
    setSortKey((prev) => { setSortDir((d) => prev === key ? (d === 'asc' ? 'desc' : 'asc') : 'desc'); return key; });
  };

  const toggleFav = (id: string) => {
    setFavorites((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const fmtDate = (d: string | null) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const tierStyle = (score: number | undefined) => {
    const s = score ?? 0;
    if (s >= 80) return { bg: '#387387', color: '#ffffff' };
    if (s >= 60) return { bg: '#759eac', color: '#001d25' };
    if (s >= 40) return { bg: '#f79009', color: '#ffffff' };
    return { bg: '#e03400', color: '#ffffff' };
  };

  const tierLetter = (score: number | undefined) => {
    const s = score ?? 0;
    if (s >= 80) return 'A'; if (s >= 60) return 'B'; if (s >= 40) return 'C'; return 'D';
  };

  return (
    <>
      {/* Search */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        border: '1px solid #d6e2e6', borderRadius: 10, padding: '10px 16px',
        background: '#ffffff', marginBottom: 14, maxWidth: 400,
      }}>
        <Search size={18} color="#a4a7ae" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию"
          style={{ border: 'none', outline: 'none', flex: 1, fontSize: 14, color: '#01121a', background: 'transparent', fontFamily: "'Onest Variable', Onest, sans-serif" }}
        />
        {search && (
          <button onClick={() => setSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#a4a7ae', padding: 0 }}>
            <X size={16} />
          </button>
        )}
      </div>

      {/* Preset filters */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => togglePreset(p.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 16px', borderRadius: 9999,
              border: activePresets.has(p.id) ? '1.5px solid #004b65' : '1px solid #d6e2e6',
              background: activePresets.has(p.id) ? '#eef3f5' : '#ffffff',
              color: activePresets.has(p.id) ? '#004b65' : '#516c79',
              fontSize: 13, fontWeight: 500, cursor: 'pointer',
              fontFamily: "'Onest Variable', Onest, sans-serif",
            }}
          >
            {p.id === 'fav' && <Star size={14} fill={activePresets.has('fav') ? '#004b65' : 'none'} />}
            {p.label}
          </button>
        ))}
        {activePresets.size > 0 && (
          <button onClick={() => setActivePresets(new Set())} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', borderRadius: 9999, border: 'none', background: 'transparent', color: '#717680', fontSize: 12, cursor: 'pointer', fontFamily: "'Onest Variable', Onest, sans-serif" }}>
            <RotateCcw size={13} /> Сбросить
          </button>
        )}
        <span style={{ fontSize: 12, color: '#a4a7ae', display: 'flex', alignItems: 'center', marginLeft: 8 }}>
          Найдено: <b style={{ color: '#01121a', margin: '0 4px' }}>{filtered.length}</b> из {allBonds.length}
        </span>
      </div>

      {/* Table */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#a4a7ae' }}>Загрузка данных…</div>
      ) : (
        <div style={{ background: '#ffffff', borderRadius: 12, border: '1px solid #d6e2e6', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#fafafa' }}>
                  <th style={{ ...thStyle, width: 36, textAlign: 'center' }}><input type="checkbox" style={{ accentColor: '#004b65' }} /></th>
                  <th style={{ ...thStyle, width: 36 }}></th>
                  <Th k="name" label="Наименование" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="internal_id" label="ID" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="currency" label="Вал" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="yield_to_maturity" label="Доходность" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="price" label="Цена" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="coupon_rate" label="Купон" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="score" label="Скор" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="maturity_date" label="Погашение" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                  <Th k="status" label="Статус" sortKey={sortKey} sortDir={sortDir} onSort={doSort} />
                </tr>
              </thead>
              <tbody>
                {filtered.map((b) => {
                  const sc = scoreMap[b.internal_id];
                  const tier = tierLetter(sc);
                  const ts = tierStyle(sc);
                  return (
                    <tr key={b.internal_id} style={{ borderBottom: '1px solid #f2f2f2' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#f8fafb')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = '')}>
                      <td style={{ padding: '12px', textAlign: 'center' }}><input type="checkbox" style={{ accentColor: '#004b65' }} /></td>
                      <td style={{ padding: '12px' }}>
                        <button onClick={() => toggleFav(b.internal_id)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                          <Star size={16} fill={favorites.has(b.internal_id) ? '#004b65' : 'none'} color={favorites.has(b.internal_id) ? '#004b65' : '#d6e2e6'} />
                        </button>
                      </td>
                      <td style={{ padding: '12px 12px 12px 0' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <BondIcon name={b.name} />
                          <div>
                            <div style={{ fontWeight: 500, fontSize: 13 }}>{b.name}</div>
                            {b.issuer && <div style={{ fontSize: 11, color: '#a4a7ae', marginTop: 1 }}>{b.issuer}</div>}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: 11, color: '#717680' }}>{b.internal_id}</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{ padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 600, background: '#f5f5f5', color: '#516c79' }}>{b.currency}</span>
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', fontWeight: 500 }}>
                        {b.yield_to_maturity != null ? `${b.yield_to_maturity.toFixed(2)}%` : '—'}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{b.price?.toFixed(2) ?? '—'}</td>
                      <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', color: '#717680' }}>{b.coupon_rate?.toFixed(2)}%</td>
                      <td style={{ ...tdStyle, textAlign: 'right' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                          <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#004b65' }}>{sc?.toFixed(1) ?? '—'}</span>
                          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 22, height: 20, borderRadius: 6, fontSize: 11, fontWeight: 700, fontFamily: "'Montserrat Variable', Montserrat, sans-serif", ...ts }}>{tier}</span>
                        </div>
                      </td>
                      <td style={{ ...tdStyle, fontSize: 12, color: '#717680' }}>{fmtDate(b.maturity_date)}</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{ fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 6, background: b.status === 'active' ? '#ebfff2' : '#f5f5f5', color: b.status === 'active' ? '#06b663' : '#717680' }}>{b.status}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: '#a4a7ae' }}>Ничего не найдено. Попробуйте изменить фильтры.</div>}
        </div>
      )}

      {filtered.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <button
            onClick={() => exportCsv('bonds_analytics.csv',
              ['ID', 'Наименование', 'Вал', 'Цена', 'YTM %', 'Купон %', 'Скор', 'Погашение', 'Статус'],
              filtered.map(b => [b.internal_id, b.name, b.currency, b.price?.toFixed(2) ?? '', b.yield_to_maturity?.toFixed(2) ?? '', b.coupon_rate?.toFixed(2) ?? '', scoreMap[b.internal_id]?.toFixed(1) ?? '', b.maturity_date ?? '', b.status])
            )}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '8px 20px', borderRadius: 9999, border: '1px solid #d6e2e6', background: '#ffffff', color: '#01121a', fontSize: 13, fontWeight: 500, cursor: 'pointer', fontFamily: "'Onest Variable', Onest, sans-serif" }}
          >
            <Download size={15} /> Экспорт CSV
          </button>
        </div>
      )}
    </>
  );
}

function ScoresTab() {
  const [scores, setScores] = useState<BondScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    api.scores({ limit: 500 }).then(setScores).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const rows = q
    ? scores.filter((s) => s.internal_id.toLowerCase().includes(q.toLowerCase()))
    : scores.slice(0, 200);

  const tierLetter = (score: number) => {
    if (score >= 80) return 'A'; if (score >= 60) return 'B'; if (score >= 40) return 'C'; return 'D';
  };
  const tierStyle = (score: number) => {
    if (score >= 80) return { bg: '#387387', color: '#ffffff' };
    if (score >= 60) return { bg: '#759eac', color: '#001d25' };
    if (score >= 40) return { bg: '#f79009', color: '#ffffff' };
    return { bg: '#e03400', color: '#ffffff' };
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#a4a7ae' }}>Загрузка данных…</div>;

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, border: '1px solid #d6e2e6', borderRadius: 10, padding: '10px 16px', background: '#ffffff', marginBottom: 14, maxWidth: 400 }}>
        <Search size={18} color="#a4a7ae" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по ID"
          style={{ border: 'none', outline: 'none', flex: 1, fontSize: 14, color: '#01121a', background: 'transparent', fontFamily: "'Onest Variable', Onest, sans-serif" }} />
      </div>
      <div style={{ background: '#ffffff', borderRadius: 12, border: '1px solid #d6e2e6', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={thStyle}>#</th>
              <th style={thStyle}>Bond ID</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Score</th>
              <th style={thStyle}>Tier</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <tr key={s.internal_id} style={{ borderBottom: '1px solid #f2f2f2' }}>
                <td style={{ padding: '12px', color: '#a4a7ae', fontSize: 12 }}>{i + 1}</td>
                <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: 12, color: '#516c79' }}>{s.internal_id}</td>
                <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: '#004b65' }}>{s.score.toFixed(2)}</td>
                <td style={{ padding: '12px' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 22, height: 20, borderRadius: 6, fontSize: 11, fontWeight: 700, fontFamily: "'Montserrat Variable', Montserrat, sans-serif", ...tierStyle(s.score) }}>{tierLetter(s.score)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: '#a4a7ae' }}>Ничего не найдено</div>}
      </div>
    </>
  );
}

function CompaniesTab() {
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.analytics.companies({ limit: 50 }).then(setCompanies).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#a4a7ae' }}>Загрузка данных…</div>;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
      {companies.map((c) => (
        <div key={c.issuer} style={{ background: '#ffffff', borderRadius: 12, border: '1px solid #d6e2e6', padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <BondIcon name={c.name} size={36} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
              <div style={{ fontSize: 11, color: '#a4a7ae', marginTop: 1 }}>{c.issuer}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 12, fontSize: 12, color: '#516c79' }}>
            {c.sector && <span style={{ padding: '2px 8px', borderRadius: 6, background: '#f5f5f5', color: '#516c79', fontWeight: 500 }}>{c.sector}</span>}
            <span><b style={{ color: '#01121a' }}>{c.bond_count}</b> выпусков</span>
            {c.avg_yield_to_maturity != null && <span>YTM <b style={{ color: '#004b65' }}>{c.avg_yield_to_maturity}%</b></span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ──── Table header ──── */
function Th({ k, label, sortKey, sortDir, onSort }: { k: string; label: string; sortKey: string; sortDir: string; onSort: (key: string) => void }) {
  return (
    <th
      onClick={() => onSort(k)}
      style={{
        ...thStyle, textAlign: 'left', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
        color: sortKey === k ? '#004b65' : '#a4a7ae',
      }}
    >
      {label}{sortKey === k && <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>}
    </th>
  );
}

/* ──── Bond icon ──── */
function BondIcon({ name, size = 36 }: { name?: string | null; size?: number }) {
  const letter = (name ?? '?').charAt(0).toUpperCase();
  return (
    <div style={{
      width: size, height: size, borderRadius: 8, background: '#004b65',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#ffffff', fontSize: size * 0.42, fontWeight: 700,
      fontFamily: "'Montserrat Variable', Montserrat, sans-serif", flexShrink: 0,
    }}>{letter}</div>
  );
}

const thStyle: React.CSSProperties = {
  padding: '12px', fontSize: 12, fontWeight: 600, color: '#a4a7ae',
  textTransform: 'uppercase', letterSpacing: '.5px', borderBottom: '1px solid #d6e2e6',
  fontFamily: "'Montserrat Variable', Montserrat, sans-serif", whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '12px',
};
