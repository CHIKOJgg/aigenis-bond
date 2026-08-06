import { useEffect, useState } from 'react';
import {
  Banknote, Activity, Shield, BarChart3, Globe2, Building2, Star,
  Bell, Lock, Clock, Download,
} from 'lucide-react';
import { api, exportCsv } from '../lib/api';
import type { Bond, BondScore, Stats, WatchlistItem, CompanySummary } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useAuth } from '../lib/AuthContext';
import { usePaywall } from '../lib/PaywallContext';
import { tierLimits } from '../lib/tiers';
import { CurrencyBadge, TierBadge, LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';
import { StatCard, BondRow } from './ui';
import { useUserAlerts, UserAlertsPanel } from './alerts';
import { UpgradePrompt } from '../lib/gate';

export default function DashboardPage({ onPickCurrency, onOpenCompany, onSubscribe }: {
  onPickCurrency?: (cur: string) => void;
  onOpenCompany?: (issuer: string) => void;
  onSubscribe?: () => void;
}) {
  const { t } = useI18n();
  usePageMeta(t('meta.dashboard'));
  const [stats, setStats] = useState<Stats | null>(null);
  const [bonds, setBonds] = useState<Bond[]>([]);
  const [scores, setScores] = useState<BondScore[]>([]);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.stats().catch(() => null),
      api.bonds.list({ limit: 5 }).catch(() => []),
      api.scores({ limit: 5 }).catch(() => []),
      api.health().catch(() => null),
      api.analytics.companies({ limit: 6 }).catch(() => []),
    ]).then(([s, b, sc, h, c]) => {
      if (!s && b.length === 0) {
        setError(t('dash.loadError'));
        return;
      }
      setStats(s);
      setBonds(b);
      setScores(sc);
      setHealth(h);
      setCompanies(c as CompanySummary[]);
    }).catch(() => setError(t('dash.loadError')))
    .finally(() => setLoading(false));
  }, [t]);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('dash.title')}</h2>
        {health && (
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${health.status === 'ok' ? 'bg-[#06b663]' : 'bg-[#e03400]'}`} />
            <span className="text-[#516c79]">{health.status}</span>
            <span className="text-[#a4a7ae]">|</span>
            <span className="text-[#516c79]">{t('dash.db')}: {health.db}</span>
            <Clock size={12} className="text-[#717680]" />
            <span className="text-[#717680]">{Math.floor(health.uptime_seconds || 0)}s</span>
          </div>
        )}
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Banknote} label={t('dash.totalBonds')} value={stats.total_bonds} color="from-[#004b65] to-[#387387]" />
          <StatCard icon={Activity} label={t('dash.activeBonds')} value={stats.active_bonds} color="from-[#387387] to-[#5f9ba8]" />
          <StatCard icon={Shield} label={t('dash.topScore')} value={scores[0]?.score?.toFixed(1) || '-'} color="from-[#0a7ba6] to-[#1a9cc4]" />
          {Object.entries(stats.by_currency).slice(0, 1).map(([cur, count]) => (
            <StatCard key={cur} icon={BarChart3} label={t('dash.currencyBonds', { cur })} value={count as number} color="from-[#516c79] to-[#7a93a0]" />
          ))}
        </div>
      )}

      <CurrencyTracker />

      <MarketsOverview onPick={onPickCurrency} />

      {companies.length > 0 && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Building2 size={16} className="text-[#004b65]" /> {t('dash.topCompanies')}
            </h3>
            <button onClick={() => onOpenCompany?.(companies[0].issuer)} className="text-xs text-[#004b65] hover:underline">
              {t('dash.viewAll')}
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {companies.map((c) => (
              <button
                key={c.issuer}
                onClick={() => onOpenCompany?.(c.issuer)}
                className="text-left bg-[#f8fafb]/40 hover:bg-[#f8fafb] border border-[#d6e2e6] hover:border-[#004b65] rounded-lg p-3 transition-colors"
              >
                <div className="font-medium text-[#01121a] truncate">{c.name}</div>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  {c.sector && <span className="px-2 py-0.5 rounded text-xs bg-white text-[#516c79]">{c.sector}</span>}
                  <span className="text-xs text-[#717680]">{c.bond_count} выпусков</span>
                  {c.avg_yield_to_maturity != null && (
                    <span className="text-xs text-[#004b65]">YTM {c.avg_yield_to_maturity}%</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <AlertsWidget onSubscribe={onSubscribe} />

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2"><Banknote size={16} className="text-[#004b65]" /> {t('dash.recent')}</h3>
          <div className="space-y-1">
            {bonds.map(b => <BondRow key={b.internal_id} bond={b} />)}
          </div>
          {bonds.length === 0 && <EmptyState message={t('dash.noBonds')} />}
        </div>
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2"><Shield size={16} className="text-[#004b65]" /> {t('dash.topScores')}</h3>
          <div className="space-y-1">
            {scores.map(s => (
              <div key={s.internal_id} className="flex items-center justify-between py-2 border-b border-[#d6e2e6] last:border-0">
                <span className="text-sm text-[#516c79] font-mono text-xs">{s.internal_id}</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono text-[#004b65]">{s.score.toFixed(2)}</span>
                  {s.tier && <TierBadge tier={s.tier} />}
                </div>
              </div>
            ))}
          </div>
        </div>
        <WatchlistCard />
      </div>
    </div>
  );
}

export function CurrencyTracker() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { openPaywall } = usePaywall();
  const limits = tierLimits(user?.subscription_tier);
  const isFree = user?.subscription_tier === 'free';

  const [available, setAvailable] = useState<string[]>(['USD', 'BYN', 'EUR', 'XAU', 'XAG', 'XPT', 'CNY']);
  const [selected, setSelected] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);

  const storageKey = `watched_currencies_${user?.id ?? 'anon'}`;

  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as string[];
        setSelected(parsed.slice(0, Math.max(limits.maxCurrencies, parsed.length)));
      } catch {
        setSelected(limits.maxCurrencies >= 1 ? ['USD'] : []);
      }
    } else {
      setSelected(limits.maxCurrencies >= 1 ? ['USD'] : []);
    }
    setLoaded(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, limits.maxCurrencies]);

  useEffect(() => {
    api.stats()
      .then((s) => {
        const curs = Object.keys(s.by_currency);
        if (curs.length) setAvailable(curs);
      })
      .catch(() => {});
  }, []);

  const persist = (next: string[]) => {
    setSelected(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };

  const toggle = (cur: string) => {
    if (selected.includes(cur)) {
      persist(selected.filter((c) => c !== cur));
      return;
    }
    if (isFree && selected.length >= limits.maxCurrencies) {
      openPaywall('currencies');
      return;
    }
    persist([...selected, cur]);
  };

  const atLimit = isFree && selected.length >= limits.maxCurrencies;

  return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Globe2 size={16} className="text-[#004b65]" /> {t('tracker.title')}
        </h3>
        {isFree && (
          <span className={`text-xs px-2 py-0.5 rounded border ${atLimit ? 'text-[#004b65] bg-amber-50 border-amber-200' : 'text-[#516c79] bg-[#f8fafb] border-[#b2c9d1]'}`}>
            {selected.length}/{limits.maxCurrencies}
          </span>
        )}
      </div>
      <p className="text-xs text-[#717680] mb-3">
        {isFree
          ? t('tracker.freeHint')
          : t('tracker.hint')}
      </p>
      <div className="flex flex-wrap gap-2">
        {available.map((cur) => {
          const active = selected.includes(cur);
          const blocked = isFree && !active && atLimit;
          return (
            <button
              key={cur}
              onClick={() => toggle(cur)}
              disabled={loaded && blocked}
              className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${active
                ? 'bg-[#004b65] text-white border-[#004b65]'
                : 'bg-[#f8fafb] text-[#516c79] border-[#b2c9d1] hover:border-[#a4a7ae]'
                } ${blocked ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              {cur}
            </button>
          );
        })}
      </div>
      {isFree && atLimit && (
        <button
          onClick={() => openPaywall('currencies')}
          className="mt-3 inline-flex items-center gap-1.5 text-sm text-[#004b65] hover:text-[#387387] transition-colors"
        >
          <Lock size={14} /> {t('tracker.unlock')}
        </button>
      )}
    </div>
  );
}

export function WatchlistCard() {
  const { t } = useI18n();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.bonds.watchlist()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <h3 className="text-lg font-semibold flex items-center gap-2">
        <Star size={16} className="text-[#004b65]" /> {t('watchlist.title')}
      </h3>
      <div className="mt-3 space-y-2">
        {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-[#f8fafb] rounded animate-pulse" />)}
      </div>
    </div>
  );
  if (items.length === 0) return null;

  const exportNow = () => {
    exportCsv(
      'watchlist.csv',
      ['Bond ID', 'Name', 'Score'],
      items.map((it) => [it.internal_id, it.name, it.score != null ? it.score.toFixed(2) : '']),
    );
  };

  return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Star size={16} className="text-[#004b65]" /> {t('watchlist.title')}
          <span className="text-xs text-[#717680] font-normal">{items.length}</span>
        </h3>
        <button onClick={exportNow}
          className="flex items-center gap-1 text-[#516c79] hover:text-[#004b65]" title={t('action.exportCsv')}>
          <Download size={14} />
        </button>
      </div>
      <div className="space-y-1">
        {items.slice(0, 8).map((it) => (
          <div key={it.internal_id} className="flex items-center justify-between py-2 border-b border-[#d6e2e6] last:border-0">
            <span className="text-sm text-[#516c79] font-mono text-xs truncate">{it.internal_id}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono text-[#004b65]">{it.score != null ? it.score.toFixed(1) : '-'}</span>
              {it.score != null && <TierBadge tier={it.score >= 80 ? 'A' : it.score >= 60 ? 'B' : it.score >= 40 ? 'C' : 'D'} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MarketsOverview({ onPick }: { onPick?: (cur: string) => void }) {
  const { t } = useI18n();
  const [tiles, setTiles] = useState<{ currency: string; count: number; avg: number | null }[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([
      api.stats().then((s) => s.by_currency).catch(() => ({}) as Record<string, number>),
      api.bonds.list({ limit: 1000 }).catch(() => [] as Bond[]),
      api.scores({ limit: 1000 }).catch(() => [] as BondScore[]),
    ])
      .then(([byCur, bonds, sc]) => {
        const scoreMap: Record<string, number> = {};
        sc.forEach((s) => { scoreMap[s.internal_id] = s.score; });
        const sums: Record<string, { n: number; sum: number }> = {};
        bonds.forEach((b) => {
          const s = scoreMap[b.internal_id];
          if (s == null) return;
          if (!sums[b.currency]) sums[b.currency] = { n: 0, sum: 0 };
          sums[b.currency].n += 1;
          sums[b.currency].sum += s;
        });
        const rows = Object.entries(byCur as Record<string, number>).map(([cur, count]) => ({
          currency: cur,
          count,
          avg: sums[cur] ? sums[cur].sum / sums[cur].n : null,
        })).sort((a, b) => b.count - a.count);
        setTiles(rows);
      })
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return null;
  if (tiles.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Globe2 size={16} className="text-[#004b65]" /> {t('markets.title')}
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {tiles.map((tile) => {
          const avg = tile.avg;
          const tint = avg == null
            ? 'bg-[#f8fafb] border-[#b2c9d1]'
            : avg >= 70
              ? 'bg-[#ebfff2] border-[#06b663]'
              : avg >= 50
                ? 'bg-amber-50 border-amber-200'
                : 'bg-[#fff1ee] border-[#e03400]';
          return (
            <button key={tile.currency} onClick={() => onPick?.(tile.currency)}
              className={`rounded-lg border p-3 text-left transition-colors hover:border-[#004b65] ${tint}`}>
              <div className="flex items-center justify-between">
                <CurrencyBadge currency={tile.currency} />
                <span className="text-xs text-[#516c79]">{tile.count}</span>
              </div>
              <p className="mt-1 text-sm font-mono">{avg != null ? avg.toFixed(1) : '—'}</p>
              <p className="text-[10px] text-[#717680]">{t('dash.avgScore')}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function AlertsWidget({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { rules, feed, loading, error, locked, busy, addRule, removeRule } = useUserAlerts();

  if (loading) return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <h3 className="text-lg font-semibold flex items-center gap-2">
        <Bell size={16} className="text-[#004b65]" /> {t('alerts.title')}
      </h3>
      <div className="mt-3 space-y-2">
        {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-[#f8fafb] rounded animate-pulse" />)}
      </div>
    </div>
  );
  if (locked) return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Bell size={16} className="text-[#004b65]" /> {t('alerts.title')}
      </h3>
      <UpgradePrompt onSubscribe={onSubscribe} />
    </div>
  );
  if (error) return (
    <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
      <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Bell size={16} className="text-[#004b65]" /> {t('alerts.title')}
      </h3>
      <ErrorBanner message={error} />
    </div>
  );

  return (
    <UserAlertsPanel
      rules={rules}
      feed={feed}
      busy={busy}
      onAdd={addRule}
      onRemove={removeRule}
      emptyLabel={t('alerts.noRules')}
    />
  );
}
