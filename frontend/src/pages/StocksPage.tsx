import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, Search } from 'lucide-react';
import { api } from '../lib/api';
import type { Stock, StockSectorSummary, StockStats } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { ROUTES } from '../app/paths';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';

const LIST_LIMIT = 250;

export default function StocksPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  usePageMeta(t('meta.stocks'));
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [stats, setStats] = useState<StockStats | null>(null);
  const [sectors, setSectors] = useState<StockSectorSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [activeSector, setActiveSector] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.stocks.list({ limit: LIST_LIMIT }),
      api.stocks.stats(),
      api.stocks.sectors().catch(() => [] as StockSectorSummary[]),
    ])
      .then(([s, st, sec]) => {
        setStocks(s);
        setStats(st);
        setSectors(sec);
      })
      .catch(() => setError(t('dash.loadError')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return stocks.filter((s) => {
      if (activeSector && s.sector !== activeSector) return false;
      if (q && !(s.name.toLowerCase().includes(q) || s.secid.toLowerCase().includes(q) || (s.isin ?? '').toLowerCase().includes(q))) return false;
      return true;
    });
  }, [stocks, query, activeSector]);

  const fmtBig = (n: number | null) => {
    if (n == null) return '-';
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return n.toFixed(2);
  };

  const changePct = (s: Stock) =>
    s.price != null && s.prev_price != null && s.prev_price > 0 ? ((s.price - s.prev_price) / s.prev_price) * 100 : null;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('stocks.title')}</h2>
        <p className="text-sm text-[#516c79] mt-1">{t('stocks.subtitle')}</p>
      </div>

      {!loading && !error && stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
            <div className="text-xs text-[#717680]">{t('stocks.total')}</div>
            <div className="text-2xl font-bold text-[#01121a] font-mono">{stats.total_stocks}</div>
          </div>
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
            <div className="text-xs text-[#717680]">{t('stocks.active')}</div>
            <div className="text-2xl font-bold text-[#06b663] font-mono">{stats.active_stocks}</div>
          </div>
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
            <div className="text-xs text-[#717680]">{t('stocks.sectors')}</div>
            <div className="text-2xl font-bold text-[#004b65] font-mono">{Object.keys(stats.by_sector).length}</div>
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a4a7ae]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('stocks.searchPlaceholder')}
            className="w-full bg-white border border-[#d6e2e6] rounded-lg pl-9 pr-3 py-2 text-sm text-[#01121a] placeholder-[#a4a7ae] focus:outline-none focus:border-[#004b65]"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setActiveSector(null)}
          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
            activeSector === null ? 'bg-[#004b65] border-[#004b65] text-white' : 'bg-[#f8fafb] hover:bg-[#d9e4e8] text-[#01121a] border-[#b2c9d1]'
          }`}
        >
          {t('stocks.all')}
        </button>
        {sectors.slice(0, 12).map((s) => (
          <button
            key={s.sector}
            onClick={() => setActiveSector(activeSector === s.sector ? null : s.sector)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              activeSector === s.sector ? 'bg-[#004b65] border-[#004b65] text-white' : 'bg-[#f8fafb] hover:bg-[#d9e4e8] text-[#01121a] border-[#b2c9d1]'
            }`}
          >
            {s.sector} <span className="opacity-60">· {s.count}</span>
          </button>
        ))}
      </div>

      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#d6e2e6] text-[#516c79]">
                <th className="text-left p-3">{t('common.name')}</th>
                <th className="text-left p-3 hidden md:table-cell">{t('stocks.secid')}</th>
                <th className="text-left p-3 hidden lg:table-cell">{t('stocks.sectorCol')}</th>
                <th className="text-right p-3">{t('common.price')}</th>
                <th className="text-right p-3 hidden sm:table-cell">Δ</th>
                <th className="text-right p-3 hidden md:table-cell">{t('stocks.pe')}</th>
                <th className="text-right p-3 hidden md:table-cell">{t('stocks.dividendYield')}</th>
                <th className="text-right p-3">{t('stocks.marketCap')}</th>
                <th className="text-left p-3 hidden lg:table-cell">{t('common.status')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const chg = changePct(s);
                return (
                  <tr
                    key={s.internal_id}
                    onClick={() => navigate(ROUTES.stockDetail(s.internal_id))}
                    className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50 cursor-pointer transition-colors"
                  >
                    <td className="p-3 text-[#01121a] font-medium max-w-[260px] truncate">
                      <span className="flex items-center gap-2">
                        <TrendingUp size={14} className="text-[#004b65] shrink-0" />
                        <span className="truncate">{s.name}</span>
                      </span>
                    </td>
                    <td className="p-3 text-[#516c79] font-mono text-xs hidden md:table-cell">{s.secid}</td>
                    <td className="p-3 text-[#516c79] text-xs hidden lg:table-cell">{s.sector ?? '-'}</td>
                    <td className="p-3 text-right font-mono">{s.price != null ? s.price.toFixed(2) : '-'}</td>
                    <td className="p-3 text-right font-mono hidden sm:table-cell">
                      {chg != null ? (
                        <span className={chg >= 0 ? 'text-[#06b663]' : 'text-[#e03400]'}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                      ) : '-'}
                    </td>
                    <td className="p-3 text-right font-mono hidden md:table-cell">{s.pe_ratio != null ? s.pe_ratio.toFixed(1) : '-'}</td>
                    <td className="p-3 text-right font-mono hidden md:table-cell">{s.dividend_yield != null ? `${s.dividend_yield.toFixed(2)}%` : '-'}</td>
                    <td className="p-3 text-right font-mono">{fmtBig(s.market_capitalization)}</td>
                    <td className="p-3 hidden lg:table-cell">
                      {s.status === 'active'
                        ? <span className="px-2 py-0.5 rounded text-xs bg-[#ebfff2] text-[#06b663]">active</span>
                        : <span className="px-2 py-0.5 rounded text-xs bg-[#f8fafb] text-[#516c79]">{s.status}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && <EmptyState message={t('stocks.empty')} />}
        </div>
      )}
    </div>
  );
}
