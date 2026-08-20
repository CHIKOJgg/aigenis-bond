import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Star, Download, X, GitCompare, ArrowLeft } from 'lucide-react';
import { api, exportCsv } from '../lib/api';
import type { Bond, BondScore } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useAuth } from '../lib/AuthContext';
import { usePaywall } from '../lib/PaywallContext';
import { ROUTES } from '../app/paths';
import { BondFilters, defaultFilters, type BondFiltersState } from '../BondFilters';
import { Modal } from '../lib/Modal';
import { BondDetailContent } from '../components/BondDetailModal';
import { CurrencyBadge, LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';
import { BondIcon, maturityBucket, defaultForPreset } from './ui';

const MAX_COMPARE = 4;
const PAGE_SIZE = 25;

export default function BondsPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { internalId } = useParams<{ internalId: string }>();
  usePageMeta(internalId ? `${internalId} — ${t('meta.bonds')}` : t('meta.bonds'));
  const { openPaywall } = usePaywall();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [allBonds, setAllBonds] = useState<Bond[]>([]);
  const [scoreMap, setScoreMap] = useState<Record<string, number>>({});
  const [filters, setFilters] = useState<BondFiltersState>({ ...defaultFilters });
  const [activePresets, setActivePresets] = useState<Set<string>>(new Set());
  const [sort, setSort] = useState<{ key: 'yield_to_maturity' | 'price' | 'coupon_rate' | 'score' | 'name'; dir: 'asc' | 'desc' }>({ key: 'yield_to_maturity', dir: 'desc' });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [compareOpen, setCompareOpen] = useState(false);
  const [detailBond, setDetailBond] = useState<Bond | null>(null);
  const [detailError, setDetailError] = useState(false);

  const currencyParam = searchParams.get('currency');

  useEffect(() => {
    setLoading(true);
    setError(null);
    setPage(1);
    Promise.all([
      api.bonds.list({ limit: 2000 }),
      api.scores({ limit: 2000 }).catch(() => [] as BondScore[]),
    ])
      .then(([bs, sc]) => {
        setAllBonds(bs);
        const m: Record<string, number> = {};
        sc.forEach((s) => { m[s.internal_id] = s.score; });
        setScoreMap(m);
      })
      .catch(() => setError('Failed to load bonds'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!currencyParam) return;
    setFilters((f) => ({
      ...f,
      currencies: f.currencies.includes(currencyParam) ? f.currencies : [...f.currencies, currencyParam],
    }));
    setSearchParams({}, { replace: true });
  }, [currencyParam, setSearchParams]);

  useEffect(() => {
    if (!internalId) return;
    const found = allBonds.find((b) => b.internal_id === internalId);
    if (found) {
      setDetailBond(found);
      setDetailError(false);
      return;
    }
    api.bonds.get(internalId)
      .then((b) => { setDetailBond(b); setDetailError(false); })
      .catch(() => { setDetailBond(null); setDetailError(true); });
  }, [internalId, allBonds]);

  useEffect(() => {
    if (!user) return;
    api.bonds.watchlist()
      .then((items) => setFavorites(new Set(items.map((i) => i.internal_id))))
      .catch(() => {});
  }, [user]);

  const toggleFav = async (id: string) => {
    try {
      if (favorites.has(id)) {
        const r = await api.bonds.removeFromWatchlist(id);
        setFavorites(new Set(r.watchlist));
      } else {
        const r = await api.bonds.addToWatchlist(id);
        setFavorites(new Set(r.watchlist));
      }
    } catch {
      /* ignore */
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < MAX_COMPARE) {
        next.add(id);
      }
      return next;
    });
  };

  const filtered = useMemo(() => {
    const f = filters;
    const q = f.search.trim().toLowerCase();
    const ytmLo = f.ytm[0] != null ? f.ytm[0] : null;
    const ytmHi = f.ytm[1] != null ? f.ytm[1] : null;
    const couponLo = f.coupon[0] != null ? f.coupon[0] : null;
    const couponHi = f.coupon[1] != null ? f.coupon[1] : null;

    let rows = allBonds.filter((b) => {
      if (q && ![b.name, b.internal_id, b.issuer, b.isin].some((v) => v && v.toLowerCase().includes(q))) return false;
      if (f.currencies.length && !f.currencies.includes(b.currency)) return false;
      if (f.statuses.length && !f.statuses.includes(b.status)) return false;
      if (f.favoritesOnly && !favorites.has(b.internal_id)) return false;

      if (b.yield_to_maturity != null) {
        if (ytmLo != null && b.yield_to_maturity < ytmLo) return false;
        if (ytmHi != null && b.yield_to_maturity > ytmHi) return false;
      } else if (ytmLo != null || ytmHi != null) {
        return false;
      }

      if (b.price != null) {
        if (f.price[0] != null && b.price < f.price[0]) return false;
        if (f.price[1] != null && b.price > f.price[1]) return false;
      } else if (f.price[0] != null || f.price[1] != null) {
        return false;
      }

      if (b.coupon_rate != null) {
        if (couponLo != null && b.coupon_rate < couponLo) return false;
        if (couponHi != null && b.coupon_rate > couponHi) return false;
      } else if (couponLo != null || couponHi != null) {
        return false;
      }

      const sc = scoreMap[b.internal_id];
      if (sc != null) {
        if (f.score[0] != null && sc < f.score[0]) return false;
        if (f.score[1] != null && sc > f.score[1]) return false;
      } else if (f.score[0] != null || f.score[1] != null) {
        return false;
      }

      if (f.maturities.length) {
        const bucket = maturityBucket(b);
        if (!bucket || !f.maturities.includes(bucket)) return false;
      }

      return true;
    });

    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      let av: number | string | null;
      let bv: number | string | null;
      if (sort.key === 'score') {
        av = scoreMap[a.internal_id] ?? -Infinity;
        bv = scoreMap[b.internal_id] ?? -Infinity;
      } else if (sort.key === 'name') {
        av = a.name.toLowerCase();
        bv = b.name.toLowerCase();
      } else {
        av = (a as unknown as Record<string, number | null>)[sort.key];
        bv = (b as unknown as Record<string, number | null>)[sort.key];
      }
      if (av == null) av = -Infinity;
      if (bv == null) bv = -Infinity;
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [allBonds, filters, sort, scoreMap, favorites]);

  const togglePreset = (p: { id: string; apply: Partial<BondFiltersState> }) => {
    setActivePresets((prev) => {
      const next = new Set(prev);
      if (next.has(p.id)) {
        next.delete(p.id);
        setFilters((f) => ({ ...f, ...defaultForPreset(p.id) }));
      } else {
        next.add(p.id);
        setFilters((f) => ({ ...f, ...p.apply }));
      }
      return next;
    });
  };

  const presets: { id: string; label: string; apply: Partial<BondFiltersState> }[] = [
    { id: 'ytm10', label: t('bonds.presetYtm'), apply: { ytm: [10, null] } },
    { id: 'score70', label: t('bonds.presetScore'), apply: { score: [70, null] } },
    { id: 'active', label: t('bonds.presetActive'), apply: { statuses: ['active'] } },
    { id: 'short', label: t('bonds.presetShort'), apply: { maturities: ['<1y', '1-3y'] } },
    { id: 'fav', label: t('common.favorites'), apply: { favoritesOnly: true } },
  ];

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const statusOptions = Array.from(new Set(allBonds.map((b) => b.status))).sort();
  const currencyOptions = Array.from(new Set(allBonds.map((b) => b.currency))).sort();

  const pageIds = pageRows.map((b) => b.internal_id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => { if (next.size < MAX_COMPARE) next.add(id); });
      }
      return next;
    });
  };

  const exportNow = () => {
    const headers = ['Name', 'ID', 'Currency', 'Price', 'YTM %', 'Coupon %', 'Maturity', 'Status', 'Score'];
    const rows = filtered.map((b) => [
      b.name,
      b.internal_id,
      b.currency,
      b.price != null ? b.price.toFixed(2) : '',
      b.yield_to_maturity != null ? b.yield_to_maturity.toFixed(2) : '',
      b.coupon_rate != null ? b.coupon_rate.toFixed(2) : '',
      b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '',
      b.status,
      scoreMap[b.internal_id] != null ? scoreMap[b.internal_id].toFixed(2) : '',
    ]);
    exportCsv('bonds.csv', headers, rows);
  };

  const setSortKey = (key: typeof sort.key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  };

  const SortHeader = ({ label, k, className = '' }: { label: string; k: typeof sort.key; className?: string }) => (
    <th
      className={`text-left p-3 cursor-pointer select-none hover:text-[#004b65] ${className} ${sort.key === k ? 'text-[#004b65]' : 'text-[#516c79]'}`}
      onClick={() => setSortKey(k)}
    >
      {label} {sort.key === k ? (sort.dir === 'asc' ? '▲' : '▼') : ''}
    </th>
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] xl:gap-6 xl:items-start">
        <div className={internalId ? 'hidden xl:block space-y-4' : 'space-y-4'}>
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('bonds.title')}</h2>
            <button onClick={exportNow} disabled={filtered.length === 0}
              className="flex items-center gap-1.5 bg-[#f8fafb] hover:bg-[#d9e4e8] disabled:opacity-40 text-[#01121a] px-3 py-2 rounded-lg text-sm transition-colors">
              <Download size={15} /> {t('bonds.csv')}
            </button>
          </div>

          <BondFilters
            filters={filters}
            onChange={(next) => { setFilters(next); setPage(1); }}
            currencyOptions={currencyOptions}
            statusOptions={statusOptions}
            resultCount={filtered.length}
            totalCount={allBonds.length}
          />

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-[#717680]">{t('common.quickFilters')}</span>
            {presets.map((p) => {
              const active = activePresets.has(p.id);
              return (
                <button key={p.id} onClick={() => togglePreset(p)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    active
                      ? 'bg-[#004b65] border-[#004b65] text-white'
                      : 'bg-[#f8fafb] hover:bg-[#d9e4e8] text-[#01121a] border-[#b2c9d1]'
                  }`}>
                  {p.label}
                </button>
              );
            })}
          </div>

          {loading && <LoadingSkeleton />}
          {error && <ErrorBanner message={error} />}
          {!loading && !error && (
            <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#d6e2e6]">
                    <th className="text-left p-3 w-8">
                      <input type="checkbox" checked={allPageSelected} onChange={toggleSelectAll} className="accent-[#004b65]" aria-label={t('common.selectAll')} />
                    </th>
                    <th className="text-left p-3 w-8 hidden sm:table-cell"></th>
                    <SortHeader label={t('common.name')} k="name" />
                    <th className="text-left p-3 w-8 hidden sm:table-cell">{t('common.id')}</th>
                    <th className="text-left p-3">{t('common.currencyShort')}</th>
                    <SortHeader label={t('common.price')} k="price" className="text-right" />
                    <SortHeader label={t('common.ytm')} k="yield_to_maturity" className="text-right hidden md:table-cell" />
                    <SortHeader label={t('common.coupon')} k="coupon_rate" className="text-right hidden lg:table-cell" />
                    <SortHeader label={t('common.score')} k="score" className="text-right" />
                    <th className="text-left p-3 hidden lg:table-cell">{t('common.maturity')}</th>
                    <th className="text-left p-3">{t('common.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((b) => (
                    <tr key={b.internal_id} onClick={() => navigate(ROUTES.bondDetail(b.internal_id))}
                      className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50 cursor-pointer transition-colors">
                      <td className="p-3" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={selectedIds.has(b.internal_id)} onChange={() => toggleSelect(b.internal_id)} className="accent-[#004b65]" aria-label={t('bonds.selectOne', { id: b.internal_id })} />
                      </td>
                      <td className="p-3" onClick={(e) => e.stopPropagation()}>
                        <button onClick={() => toggleFav(b.internal_id)} className="text-[#717680] hover:text-[#004b65]" title={t('common.addToFavorites')}>
                          <Star size={15} className={favorites.has(b.internal_id) ? 'fill-amber-400 text-[#004b65]' : ''} />
                        </button>
                      </td>
                      <td className="p-3 text-[#01121a] font-medium max-w-[200px] truncate flex items-center gap-2">
                        <BondIcon issuer={b.issuer} logo={b.issuer_logo} />
                        <span className="truncate">{b.name}</span>
                      </td>
                      <td className="p-3 text-[#516c79] font-mono text-xs hidden sm:table-cell">{b.internal_id}</td>
                      <td className="p-3"><CurrencyBadge currency={b.currency} /></td>
                      <td className="p-3 text-right font-mono">{b.price?.toFixed(2) ?? '-'}</td>
                      <td className="p-3 text-right font-mono hidden md:table-cell">{b.yield_to_maturity != null ? `${(b.yield_to_maturity).toFixed(2)}%` : '-'}</td>
                      <td className="p-3 text-right font-mono hidden lg:table-cell">{b.coupon_rate != null ? `${(b.coupon_rate).toFixed(2)}%` : '-'}</td>
                      <td className="p-3 text-right font-mono text-[#004b65]">{scoreMap[b.internal_id] != null ? scoreMap[b.internal_id].toFixed(1) : '-'}</td>
                      <td className="p-3 text-[#516c79] text-xs hidden lg:table-cell">{b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '-'}</td>
                      <td className="p-3">{b.status === 'active' ? <span className="px-2 py-0.5 rounded text-xs bg-[#ebfff2] text-[#06b663]">active</span> : <span className="px-2 py-0.5 rounded text-xs bg-[#f8fafb] text-[#516c79]">{b.status}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length === 0 && <EmptyState message={t('bonds.empty')} />}
            </div>
          )}

          {!loading && !error && totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 text-sm">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
                className="px-3 py-1.5 rounded-lg bg-[#f8fafb] hover:bg-[#d9e4e8] disabled:opacity-40 text-[#01121a]">{t('common.back')}</button>
              <span className="text-[#516c79]">{page} / {totalPages}</span>
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg bg-[#f8fafb] hover:bg-[#d9e4e8] disabled:opacity-40 text-[#01121a]">{t('common.next')}</button>
            </div>
          )}
        </div>

        {internalId && (
          <div className="min-w-0">
            <div className="xl:sticky xl:top-[72px]">
              {detailError ? (
                <div className="bg-white rounded-xl border border-[#d6e2e6] p-6">
                  <div className="xl:hidden flex items-center justify-between mb-3">
                    <button onClick={() => navigate(ROUTES.bonds)} className="flex items-center gap-1.5 text-sm text-[#516c79] hover:text-[#004b65]">
                      <ArrowLeft size={16} /> {t('common.back')}
                    </button>
                  </div>
                  <EmptyState message={t('bonds.notFound')} />
                </div>
              ) : detailBond ? (
                <div className="bg-white rounded-xl border border-[#d6e2e6] p-4 sm:p-6">
                  <div className="xl:hidden flex items-center justify-between mb-3">
                    <button onClick={() => navigate(ROUTES.bonds)} className="flex items-center gap-1.5 text-sm text-[#516c79] hover:text-[#004b65]">
                      <ArrowLeft size={16} /> {t('common.back')}
                    </button>
                  </div>
                  <BondDetailContent
                    bond={detailBond}
                    onSubscribe={() => openPaywall('portfolio')}
                    onOpenCompany={(issuer) => navigate(ROUTES.companyDetail(issuer))}
                    onOpenBond={(id) => navigate(ROUTES.bondDetail(id))}
                    headerAction={
                      <button onClick={() => toggleFav(detailBond.internal_id)} className="text-[#a4a7ae] hover:text-[#004b65] p-1" title={t('common.addToFavorites')}>
                        <Star size={18} className={favorites.has(detailBond.internal_id) ? 'fill-[#004b65] text-[#004b65]' : ''} />
                      </button>
                    }
                  />
                </div>
              ) : (
                <LoadingSkeleton />
              )}
            </div>
          </div>
        )}
      </div>

      {selectedIds.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 bg-white border border-[#b2c9d1] rounded-full px-4 py-2 shadow-lg">
          <span className="text-sm text-[#516c79]">{t('bonds.selected', { n: selectedIds.size, max: MAX_COMPARE })}</span>
          <button onClick={() => setCompareOpen(true)} disabled={selectedIds.size < 2}
            className="flex items-center gap-1.5 bg-[#004b65] hover:bg-[#387387] disabled:opacity-40 text-white px-3 py-1.5 rounded-full text-sm transition-colors">
            <GitCompare size={15} /> {t('common.compare')}
          </button>
          <button onClick={() => setSelectedIds(new Set())} className="text-[#516c79] hover:text-[#004b65] text-sm px-2">{t('common.clear')}</button>
        </div>
      )}

      {compareOpen && (
        <ComparisonModal
          bonds={allBonds.filter((b) => selectedIds.has(b.internal_id))}
          scoreMap={scoreMap}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </div>
  );
}

function ComparisonModal({ bonds, scoreMap, onClose }: { bonds: Bond[]; scoreMap: Record<string, number>; onClose: () => void }) {
  const { t } = useI18n();
  const metrics: { label: string; get: (b: Bond) => string }[] = [
    { label: t('common.currency'), get: (b) => b.currency },
    { label: t('common.price'), get: (b) => (b.price != null ? b.price.toFixed(2) : '-') },
    { label: t('common.ytm'), get: (b) => (b.yield_to_maturity != null ? `${(b.yield_to_maturity).toFixed(2)}%` : '-') },
    { label: t('common.coupon'), get: (b) => (b.coupon_rate != null ? `${(b.coupon_rate).toFixed(2)}%` : '-') },
    { label: t('common.frequency'), get: (b) => (b.coupon_frequency != null ? `${b.coupon_frequency}x/${t('calc.freqYear')}` : '-') },
    { label: t('common.maturity'), get: (b) => (b.maturity_date ? new Date(b.maturity_date).toLocaleDateString() : '-') },
    { label: t('common.status'), get: (b) => b.status },
    { label: t('common.score'), get: (b) => (scoreMap[b.internal_id] != null ? scoreMap[b.internal_id].toFixed(1) : '-') },
  ];

  return (
    <Modal onClose={onClose} className="max-w-4xl w-full max-h-[85vh] overflow-auto">
      <div className="flex items-center justify-between p-6 pb-2">
        <h3 className="text-lg font-bold" id="comparison-title">{t('bonds.compareTitle', { n: bonds.length })}</h3>
        <button onClick={onClose} className="text-[#516c79] hover:text-[#004b65] p-1" aria-label={t('action.close')}><X size={18} /></button>
      </div>
      <div className="px-6 pb-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#d6e2e6] text-[#516c79]">
              <th className="text-left p-3 sticky left-0 bg-white">{t('bonds.metric')}</th>
              {bonds.map((b) => (
                <th key={b.internal_id} className="text-left p-3 min-w-[150px]">
                  <div className="flex items-center gap-2">
                    <BondIcon issuer={b.issuer} logo={b.issuer_logo} size={24} />
                    <div>
                      <div className="font-semibold text-[#01121a]">{b.name}</div>
                      <div className="text-xs text-[#717680] font-mono">{b.internal_id}</div>
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.label} className="border-b border-[#d6e2e6]">
                <td className="p-3 text-[#516c79] sticky left-0 bg-white">{m.label}</td>
                {bonds.map((b) => (
                  <td key={b.internal_id} className="p-3 font-mono">{m.get(b)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
