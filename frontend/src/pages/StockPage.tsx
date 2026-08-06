import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, TrendingUp } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { api } from '../lib/api';
import type { Stock, StockHistoryPoint } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { ROUTES } from '../app/paths';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';

const HISTORY_DAYS = 180;

export default function StockPage() {
  const { internalId } = useParams<{ internalId: string }>();
  const { t } = useI18n();
  const navigate = useNavigate();
  usePageMeta(t('meta.stockDetail'));
  const [stock, setStock] = useState<Stock | null>(null);
  const [history, setHistory] = useState<StockHistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!internalId) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    Promise.all([
      api.stocks.get(internalId),
      api.stocks.history(internalId, HISTORY_DAYS).catch(() => [] as StockHistoryPoint[]),
    ])
      .then(([s, h]) => { setStock(s); setHistory(h); })
      .catch(() => {
        setNotFound(true);
        setError(t('stocks.notFound'));
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [internalId]);

  const chartData = useMemo(() => history.map((h) => ({
    date: h.date ? new Date(h.date).toLocaleDateString() : '',
    price: h.close_price ?? h.weighted_avg_price ?? null,
  })), [history]);

  const changePct = stock && stock.price != null && stock.prev_price != null && stock.prev_price > 0
    ? ((stock.price - stock.prev_price) / stock.prev_price) * 100
    : null;

  const fmtBig = (n: number | null) => {
    if (n == null) return '-';
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return n.toFixed(2);
  };

  if (loading) return <LoadingSkeleton />;
  if (error) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(ROUTES.stocks)} className="flex items-center gap-1.5 text-sm text-[#516c79] hover:text-[#004b65]">
          <ArrowLeft size={16} /> {t('common.back')}
        </button>
        <ErrorBanner message={error} />
        {notFound && <EmptyState message={t('stocks.notFound')} />}
      </div>
    );
  }
  if (!stock) return null;

  const metrics: { label: string; value: string }[] = [
    { label: t('stocks.secid'), value: stock.secid },
    { label: t('common.currency'), value: stock.currency },
    { label: t('stocks.board'), value: stock.board },
    { label: t('stocks.lotSize'), value: stock.lot_size != null ? String(stock.lot_size) : '-' },
    { label: t('stocks.isin'), value: stock.isin ?? '-' },
    { label: t('common.issuer'), value: stock.issuer ?? '-' },
    { label: t('stocks.open'), value: stock.open_price != null ? stock.open_price.toFixed(2) : '-' },
    { label: t('stocks.high'), value: stock.high_price != null ? stock.high_price.toFixed(2) : '-' },
    { label: t('stocks.low'), value: stock.low_price != null ? stock.low_price.toFixed(2) : '-' },
    { label: t('stocks.volume'), value: stock.volume != null ? fmtBig(stock.volume) : '-' },
    { label: t('stocks.valueTraded'), value: stock.value_traded != null ? fmtBig(stock.value_traded) : '-' },
    { label: t('stocks.pe'), value: stock.pe_ratio != null ? stock.pe_ratio.toFixed(1) : '-' },
    { label: t('stocks.pbr'), value: stock.pbr_ratio != null ? stock.pbr_ratio.toFixed(1) : '-' },
    { label: t('stocks.dividendYield'), value: stock.dividend_yield != null ? `${stock.dividend_yield.toFixed(2)}%` : '-' },
    { label: t('stocks.eps'), value: stock.earnings_per_share != null ? stock.earnings_per_share.toFixed(2) : '-' },
    { label: t('stocks.marketCap'), value: fmtBig(stock.market_capitalization) },
    { label: t('stocks.sectorCol'), value: stock.sector ?? '-' },
    { label: t('common.status'), value: stock.status },
    { label: t('common.lastUpdated'), value: stock.fetched_at ? new Date(stock.fetched_at).toLocaleString() : '-' },
  ];

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(ROUTES.stocks)} className="flex items-center gap-1.5 text-sm text-[#516c79] hover:text-[#004b65]">
        <ArrowLeft size={16} /> {t('common.back')}
      </button>

      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <TrendingUp size={20} className="text-[#004b65]" />
            <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{stock.name}</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-[#516c79]">
            <span className="font-mono">{stock.secid}</span>
            <span className="px-2 py-0.5 rounded bg-[#f8fafb] border border-[#d6e2e6]">{stock.board}</span>
            {stock.sector && <span className="px-2 py-0.5 rounded bg-[#f8fafb] border border-[#d6e2e6]">{stock.sector}</span>}
            <span>{t('stocks.currencyLabel', { code: stock.currency })}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold font-mono text-[#01121a]">{stock.price != null ? stock.price.toFixed(2) : '-'} <span className="text-base text-[#516c79]">{stock.currency}</span></div>
          {changePct != null && (
            <div className={`font-mono text-sm ${changePct >= 0 ? 'text-[#06b663]' : 'text-[#e03400]'}`}>
              {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
            </div>
          )}
          <div className="text-xs text-[#717680] mt-1">{t('stocks.prevClose')} {stock.prev_price != null ? stock.prev_price.toFixed(2) : '-'}</div>
        </div>
      </div>

      {history.length > 0 && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <h3 className="text-sm font-semibold text-[#01121a] mb-3">{t('stocks.priceHistory')}</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#eef3f5" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#717680' }} minTickGap={40} />
                <YAxis tick={{ fontSize: 11, fill: '#717680' }} domain={['auto', 'auto']} width={52} />
                <Tooltip
                  contentStyle={{ borderRadius: 10, border: '1px solid #d6e2e6', fontSize: 12, fontFamily: "'Onest Variable', sans-serif" }}
                />
                <Line type="monotone" dataKey="price" stroke="#004b65" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-[#d6e2e6] p-4 sm:p-6">
        <h3 className="text-sm font-semibold text-[#01121a] mb-4">{t('stocks.metrics')}</h3>
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm">
          {metrics.map((m) => (
            <div key={m.label} className="flex justify-between gap-2 border-b border-[#eef3f5] pb-2">
              <dt className="text-xs text-[#717680]">{m.label}</dt>
              <dd className="font-mono text-[#01121a] text-right">{m.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
