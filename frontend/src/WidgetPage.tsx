import { useEffect, useState } from 'react';
import { TrendingUp, ArrowUpRight } from 'lucide-react';
import { I18nProvider, useI18n } from './i18n';

interface WidgetBond {
  internal_id: string;
  name: string;
  currency: string;
  yield_to_maturity: number | null;
  maturity_date: string | null;
  issuer: string | null;
  score: number | null;
  tier: string | null;
}

const BASE = '';

async function loadWidget(currency: string | null, limit: number): Promise<WidgetBond[]> {
  const q = new URLSearchParams();
  q.set('limit', String(limit));
  if (currency) q.set('currency', currency);
  const res = await fetch(`${BASE}/widget/top?${q}`);
  if (!res.ok) throw new Error('widget_load_failed');
  return res.json();
}

function WidgetPageInner() {
  const { t } = useI18n();
  const [currency, setCurrency] = useState<string | null>(null);
  const [rows, setRows] = useState<WidgetBond[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const params = new URLSearchParams(window.location.search);
  const origin = params.get('origin') || window.location.origin;
  const appUrl = `${origin}/?ref=widget`;

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadWidget(currency, 10)
      .then((data) => { if (active) { setRows(data); setError(null); } })
      .catch(() => { if (active) setError(t('widget.error')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currency, t]);

  const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString() : '—');
  const scoreColor = (s: number | null) =>
    s == null ? 'text-gray-400' : s >= 75 ? 'text-emerald-400' : s >= 50 ? 'text-yellow-400' : 'text-orange-400';

  const currencies: { key: string | null; label: string }[] = [
    { key: null, label: t('widget.all') },
    { key: 'RUB', label: 'RUB' },
    { key: 'USD', label: 'USD' },
    { key: 'BYN', label: 'BYN' },
    { key: 'EUR', label: 'EUR' },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="flex items-center gap-2 mb-1">
          <TrendingUp className="text-emerald-400" size={20} />
          <h2 className="text-lg font-bold">{t('widget.title')}</h2>
        </div>
        <p className="text-xs text-gray-400 mb-4">{t('widget.sub')}</p>

        <div className="flex flex-wrap gap-2 mb-4">
          {currencies.map((c) => (
            <button
              key={c.label}
              onClick={() => setCurrency(c.key)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                currency === c.key
                  ? 'bg-emerald-600 border-emerald-500 text-white'
                  : 'bg-gray-900 border-gray-700 text-gray-300 hover:border-gray-600'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>

        {loading && <p className="text-sm text-gray-400 py-6 text-center">{t('widget.loading')}</p>}
        {error && <p className="text-sm text-red-400 py-6 text-center">{error}</p>}

        {!loading && !error && rows.length === 0 && (
          <p className="text-sm text-gray-400 py-6 text-center">{t('widget.empty')}</p>
        )}

        {!loading && !error && rows.length > 0 && (
          <div className="space-y-2">
            {rows.map((b, i) => (
              <div
                key={b.internal_id}
                className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 w-5">{i + 1}</span>
                    <span className="font-medium truncate">{b.name}</span>
                    <span className="text-[10px] uppercase text-gray-500 bg-gray-800 rounded px-1.5 py-0.5">
                      {b.currency}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5 ml-7">
                    {b.issuer ? `${b.issuer} · ` : ''}YTM {b.yield_to_maturity != null ? `${b.yield_to_maturity.toFixed(2)}%` : '—'} · {fmtDate(b.maturity_date)}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <div className={`text-lg font-bold ${scoreColor(b.score)}`}>
                      {b.score != null ? b.score.toFixed(0) : '—'}
                    </div>
                    <div className="text-[10px] text-gray-500">{t('widget.score')}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <a
          href={appUrl}
          className="mt-6 flex items-center justify-center gap-1 w-full bg-emerald-600 hover:bg-emerald-500 text-white py-2.5 rounded-xl text-sm font-medium transition-colors"
        >
          {t('widget.cta')} <ArrowUpRight size={16} />
        </a>
      </div>
    </div>
  );
}

export function WidgetPage() {
  return (
    <I18nProvider>
      <WidgetPageInner />
    </I18nProvider>
  );
}
