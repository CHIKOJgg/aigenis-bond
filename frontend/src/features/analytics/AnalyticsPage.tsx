import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { api, exportCsv } from '../../lib/api';
import type { Bond, BondScore, CompanySummary } from '../../lib/api';
import { useExchange } from '../../lib/ExchangeContext';
import { useI18n } from '../../i18n';
import { usePageMeta } from '../../app/usePageMeta';
import { AnalyticsTabs, AnalyticsSubNav, type AnalyticsTab } from './components/AnalyticsTabs';
import { AnalyticsToolbar } from './components/AnalyticsToolbar';
import { BondsTable, type SortDir } from './components/BondsTable';
import { ScoresTable } from './components/ScoresTable';
import { CompaniesGrid } from './components/CompaniesGrid';

const PRESETS: { id: string; filter: (b: Bond, sc?: number) => boolean }[] = [
  { id: 'ytm10', filter: (b: Bond) => (b.yield_to_maturity ?? 0) >= 10 },
  { id: 'score70', filter: (_: Bond, sc: number | undefined) => (sc ?? 0) >= 70 },
  { id: 'active', filter: (b: Bond) => b.status === 'active' },
  { id: 'short', filter: (b: Bond) => {
    if (!b.maturity_date) return false;
    const yrs = (new Date(b.maturity_date).getTime() - Date.now()) / (365.25 * 24 * 3600 * 1000);
    return yrs > 0 && yrs < 3;
  }},
  { id: 'fav', filter: () => true },
];

export default function AnalyticsPage() {
  const { t } = useI18n();
  usePageMeta(t('meta.analytics'));
  const { exchange } = useExchange();
  const [tab, setTab] = useState<AnalyticsTab>('bonds');

  const title =
    tab === 'bonds'
      ? `АНАЛИТИКА ${exchange === 'BCSE' ? 'БЕЛОРУССКОЙ' : 'МОСКОВСКОЙ'} БИРЖИ`
      : tab === 'scores'
        ? 'РЕЙТИНГ ОБЛИГАЦИЙ'
        : 'КОМПАНИИ-ЭМИТЕНТЫ';

  return (
    <section aria-label="Аналитика">
      <MarketWarningBanner exchange={exchange} />

      <AnalyticsTabs tab={tab} onChange={setTab} />
      <AnalyticsSubNav />

      <h1 className="text-2xl font-extrabold mt-6 mb-2 font-aigenis-heading tracking-tight">{title}</h1>

      {tab === 'bonds' && <BondsTabContainer />}
      {tab === 'scores' && <ScoresTabContainer />}
      {tab === 'companies' && <CompaniesTabContainer />}
    </section>
  );
}

function MarketWarningBanner({ exchange }: { exchange: 'BCSE' | 'MOEX' }) {
  return (
    <div className="mt-4 bg-aigenis-warning-50 border border-aigenis-warning-500 rounded-[10px] px-4 py-3 flex items-start gap-2.5 text-[13px] text-aigenis-warning-600">
      <AlertTriangle size={18} color="#dc6803" className="shrink-0 mt-0.5" aria-hidden="true" />
      <div>
        <div className="font-semibold">В настоящий момент на бирже нет актуального предложения ценных бумаг либо торги не проводятся.</div>
        <div className="text-xs mt-1 text-aigenis-warning-600">
          Расписание торговых сессий: {exchange === 'BCSE' ? '10:30–12:20 и 13:45–15:45 в рабочие дни' : '10:00–19:00 в рабочие дни в РБ и РФ'}. Статистика предыдущего торгового дня:
        </div>
      </div>
    </div>
  );
}

function useBondsData() {
  const bondsQuery = useQuery({
    queryKey: ['analytics', 'bonds'],
    queryFn: () => api.bonds.list({ limit: 2000 }),
  });
  const scoresQuery = useQuery({
    queryKey: ['analytics', 'scores'],
    queryFn: () => api.scores({ limit: 2000 }).catch(() => [] as BondScore[]),
  });
  const scoreMap = useMemo(() => {
    const m: Record<string, number> = {};
    (scoresQuery.data ?? []).forEach((s) => { m[s.internal_id] = s.score; });
    return m;
  }, [scoresQuery.data]);
  return { bonds: bondsQuery.data ?? [], scoreMap, loading: bondsQuery.isPending || scoresQuery.isPending };
}

function BondsTabContainer() {
  const { bonds: allBonds, scoreMap, loading } = useBondsData();
  const [search, setSearch] = useState('');
  const [activePresets, setActivePresets] = useState<Set<string>>(new Set());
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState('score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const togglePreset = (id: string) => {
    setActivePresets((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const filtered = useMemo(() => {
    let rows = allBonds.filter((b) => {
      if (search) {
        const q = search.toLowerCase();
        if (!b.name?.toLowerCase().includes(q) && !b.internal_id?.toLowerCase().includes(q)) return false;
      }
      for (const p of PRESETS) {
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
      else { av = (a as unknown as Record<string, unknown>)[sortKey] as number ?? -Infinity; bv = (b as unknown as Record<string, unknown>)[sortKey] as number ?? -Infinity; }
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
  }, [allBonds, search, activePresets, sortKey, sortDir, scoreMap, favorites]);

  const doSort = (key: string) => {
    setSortKey((prev) => {
      if (prev === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      else setSortDir('desc');
      return key;
    });
  };

  const toggleFav = (id: string) => {
    setFavorites((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const handleExportCsv = () => {
    exportCsv('bonds_analytics.csv',
      ['ID', 'Наименование', 'Вал', 'Цена', 'YTM %', 'Купон %', 'Скор', 'Погашение', 'Статус'],
      filtered.map((b) => [b.internal_id, b.name, b.currency, b.price?.toFixed(2) ?? '', b.yield_to_maturity?.toFixed(2) ?? '', b.coupon_rate?.toFixed(2) ?? '', scoreMap[b.internal_id]?.toFixed(1) ?? '', b.maturity_date ?? '', b.status]));
  };

  return (
    <>
      <AnalyticsToolbar
        search={search}
        onSearch={setSearch}
        activePresets={activePresets}
        onTogglePreset={togglePreset}
        onReset={() => setActivePresets(new Set())}
        found={filtered.length}
        total={allBonds.length}
      />
      <BondsTable
        loading={loading}
        bonds={filtered}
        scoreMap={scoreMap}
        favorites={favorites}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={doSort}
        onToggleFav={toggleFav}
        onExportCsv={handleExportCsv}
      />
    </>
  );
}

function ScoresTabContainer() {
  const scoresQuery = useQuery({
    queryKey: ['analytics', 'scores'],
    queryFn: () => api.scores({ limit: 500 }).catch(() => [] as BondScore[]),
  });
  return <ScoresTable loading={scoresQuery.isPending} scores={scoresQuery.data ?? []} />;
}

function CompaniesTabContainer() {
  const companiesQuery = useQuery({
    queryKey: ['analytics', 'companies'],
    queryFn: () => api.analytics.companies({ limit: 50 }).catch(() => [] as CompanySummary[]),
  });
  return <CompaniesGrid loading={companiesQuery.isPending} companies={companiesQuery.data ?? []} />;
}
