import { useState } from 'react';
import { ArrowRight, TrendingUp } from 'lucide-react';
import { useI18n } from '../../../i18n';
import { api, type Bond, type BondScore } from '../../../lib/api';

function CurrencyButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-5 py-3 rounded-xl text-sm font-medium transition-colors border ${
        active
          ? 'bg-[#004b65] border-[#004b65] text-white'
          : 'bg-white border-[#d6e2e6] text-[#01121a] hover:border-[#004b65]'
      }`}
    >
      {label}
    </button>
  );
}

export function BestBondsWidget({ onOpen }: { onOpen: () => void }) {
  const { t } = useI18n();
  const [currency, setCurrency] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<{ bond: Bond; score: number | null }[]>([]);

  const load = async (cur: string) => {
    setCurrency(cur);
    setLoading(true);
    setError(null);
    setRows([]);
    try {
      const [bonds, scores] = await Promise.all([
        api.bonds.list({ currency: cur, limit: 300 }),
        api.scores({ limit: 1000 }).catch(() => [] as BondScore[]),
      ]);
      const scoreMap: Record<string, number> = {};
      scores.forEach((s) => { scoreMap[s.internal_id] = s.score; });
      const merged = bonds
        .map((b) => ({ bond: b, score: scoreMap[b.internal_id] ?? null }))
        .sort((a, b) => {
          if (a.score != null && b.score != null) return b.score - a.score;
          if (a.score != null) return -1;
          if (b.score != null) return 1;
          return (b.bond.yield_to_maturity ?? -1) - (a.bond.yield_to_maturity ?? -1);
        });
      setRows(merged.slice(0, 8));
    } catch {
      setError(t('bestBonds.error'));
    } finally {
      setLoading(false);
    }
  };

  const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString() : '—');

  return (
    <section className="max-w-5xl mx-auto px-4 -mt-6 relative z-10">
      <div className="bg-white backdrop-blur border border-[#d6e2e6] rounded-2xl p-6 shadow-xl">
        <div className="flex items-start gap-3 mb-1">
          <TrendingUp className="text-[#004b65] mt-1 shrink-0" size={22} />
          <div>
            <h2 className="text-xl md:text-2xl font-bold">{t('bestBonds.title')}</h2>
            <p className="text-sm text-[#516c79] mt-1">{t('bestBonds.sub')}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 my-4">
          <CurrencyButton label={t('bestBonds.rub')} active={currency === 'RUB'} onClick={() => load('RUB')} />
          <CurrencyButton label={t('bestBonds.usd')} active={currency === 'USD'} onClick={() => load('USD')} />
          <CurrencyButton label={t('bestBonds.byn')} active={currency === 'BYN'} onClick={() => load('BYN')} />
          <CurrencyButton label={t('bestBonds.eur')} active={currency === 'EUR'} onClick={() => load('EUR')} />
        </div>

        {loading && <p className="text-sm text-[#516c79] py-6 text-center">{t('bestBonds.loading')}</p>}
        {error && <p className="text-sm text-[#b91c1c] py-6 text-center">{error}</p>}

        {!loading && !error && rows.length > 0 && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
              {rows.map(({ bond, score }) => (
                <div key={bond.internal_id} className="bg-[#f8fafb] border border-[#d6e2e6] rounded-xl p-4 flex flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-sm truncate">{bond.name}</p>
                      <p className="text-xs text-[#717680] font-mono">{bond.internal_id} · {bond.currency}</p>
                    </div>
                    {score != null && (
                      <span className="shrink-0 text-xs bg-[#eef3f5] text-[#004b65] border border-[#b2c9d1] rounded-full px-2 py-0.5">
                        {t('bestBonds.score')}: {score.toFixed(0)}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm">
                    <span className="text-[#516c79]">{t('bestBonds.ytm')}: <b className="text-[#01121a] font-mono">{bond.yield_to_maturity != null ? `${bond.yield_to_maturity.toFixed(2)}%` : '—'}</b></span>
                    <span className="text-[#516c79]">{t('bestBonds.coupon')}: <b className="text-[#01121a] font-mono">{bond.coupon_rate != null ? `${bond.coupon_rate.toFixed(2)}%` : '—'}</b></span>
                    <span className="text-[#516c79]">{t('bestBonds.maturity')}: <b className="text-[#01121a] font-mono">{fmtDate(bond.maturity_date)}</b></span>
                  </div>
                </div>
              ))}
            </div>
            <button
              onClick={onOpen}
              className="mt-5 w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-6 py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              {t('bestBonds.cta')} <ArrowRight size={16} />
            </button>
          </>
        )}

        {!loading && !error && currency && rows.length === 0 && (
          <p className="text-sm text-[#516c79] py-6 text-center">{t('bestBonds.empty')}</p>
        )}
      </div>
    </section>
  );
}
