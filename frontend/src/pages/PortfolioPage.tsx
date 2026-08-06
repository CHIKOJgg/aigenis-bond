import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import type { Position, PortfolioIncome, AnalyticsPortfolio } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useGated, UpgradePrompt } from '../lib/gate';
import { LoadingSkeleton, ErrorBanner, EmptyState, CurrencyBadge } from '../components/common';
import { MetricRow } from './ui';

export default function PortfolioPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  usePageMeta(t('meta.portfolio'));
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('nav.portfolio')}</h2>
      <ModelPortfolioSection onSubscribe={onSubscribe} />
      <MyPositionsSection onSubscribe={onSubscribe} />
    </div>
  );
}

function ModelPortfolioSection({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: alloc, loading, error, locked } = useGated<AnalyticsPortfolio>(() => api.analytics.portfolio());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;
  if (!alloc) return <EmptyState message={t('portfolio.empty')} />;

  return (
    <div>
      <h3 className="text-lg font-semibold mb-3">{t('portfolio.modelPortfolio')}</h3>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <h3 className="text-lg font-semibold mb-3">{t('portfolio.metrics')}</h3>
          <div className="space-y-3">
            <MetricRow label={t('portfolio.strategy')} value={alloc.strategy} />
            <MetricRow label={t('portfolio.expReturn')} value={`${alloc.expected_return.toFixed(2)}%`} color="text-[#004b65]" />
            <MetricRow label={t('portfolio.sharpe')} value={alloc.sharpe.toFixed(2)} color="text-[#004b65]" />
            <MetricRow label={t('portfolio.sortino')} value={alloc.sortino.toFixed(2)} color="text-[#004b65]" />
            <MetricRow label={t('portfolio.maxDrawdown')} value={`${alloc.max_drawdown.toFixed(1)}%`} color="text-[#e03400]" />
            <MetricRow label={t('portfolio.var')} value={`${alloc.var_95.toFixed(1)}%`} color="text-[#e03400]" />
          </div>
        </div>
        <div className="lg:col-span-2 bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
          <h3 className="text-lg font-semibold p-4 pb-2">{t('portfolio.forecast')}</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#d6e2e6] text-[#516c79]">
                <th className="text-left p-3">{t('portfolio.horizon')}</th>
                <th className="text-right p-3">{t('portfolio.pessimistic')}</th>
                <th className="text-right p-3">{t('portfolio.expected')}</th>
                <th className="text-right p-3">{t('portfolio.optimistic')}</th>
              </tr>
            </thead>
            <tbody>
              {alloc.forecast.map((f, i) => (
                <tr key={i} className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50">
                  <td className="p-3 font-semibold">{f.horizon_years}Y</td>
                  <td className="p-3 text-right text-[#e03400] font-mono">{Math.round(f.pessimistic_capital).toLocaleString()}</td>
                  <td className="p-3 text-right text-[#004b65] font-mono font-semibold">{Math.round(f.expected_capital).toLocaleString()}</td>
                  <td className="p-3 text-right text-[#004b65] font-mono">{Math.round(f.optimistic_capital).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function MyPositionsSection({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const [positions, setPositions] = useState<Position[]>([]);
  const [income, setIncome] = useState<PortfolioIncome | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [newId, setNewId] = useState('');
  const [newAmount, setNewAmount] = useState('');

  const load = async () => {
    setLoading(true); setError(null); setLocked(false);
    try {
      const pos = await api.portfolio.positions();
      setPositions(pos.positions);
      try {
        const inc = await api.portfolio.income();
        setIncome(inc);
      } catch (e: unknown) {
        if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
        else setIncome(null);
      }
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const addPosition = async () => {
    const amt = Number(newAmount);
    if (!newId.trim() || isNaN(amt) || amt <= 0) return;
    setBusy(true);
    try {
      await api.portfolio.addPosition(newId.trim().toUpperCase(), amt);
      setNewId(''); setNewAmount('');
      await load();
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed to add');
    } finally { setBusy(false); }
  };

  const removePosition = async (id: string) => {
    if (!window.confirm(t('settings.deleteConfirm', { id }))) return;
    setBusy(true);
    try {
      await api.portfolio.removePosition(id);
      await load();
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed to delete');
    } finally { setBusy(false); }
  };

  const myPosTitle = t('portfolio.myPositions');
  if (loading) return (
    <div>
      <h3 className="text-lg font-semibold mb-3">{myPosTitle}</h3>
      <LoadingSkeleton />
    </div>
  );
  if (locked) return (
    <div>
      <h3 className="text-lg font-semibold mb-3">{myPosTitle}</h3>
      <UpgradePrompt onSubscribe={onSubscribe} />
    </div>
  );
  if (error) return (
    <div>
      <h3 className="text-lg font-semibold mb-3">{myPosTitle}</h3>
      <ErrorBanner message={error} />
    </div>
  );

  return (
    <div>
      <h3 className="text-lg font-semibold mb-3">{myPosTitle}</h3>

      {income && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-3">
            <p className="text-xs text-[#516c79]">{t('portfolio.totalInvested')}</p>
            <p className="text-lg font-bold font-mono">{income.total_invested.toFixed(2)}</p>
          </div>
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-3">
            <p className="text-xs text-[#516c79]">{t('portfolio.annualIncome')}</p>
            <p className="text-lg font-bold font-mono text-[#004b65]">{income.annual_income.toFixed(2)}</p>
          </div>
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-3">
            <p className="text-xs text-[#516c79]">{t('portfolio.yieldOnCost')}</p>
            <p className="text-lg font-bold font-mono">{income.yield_on_cost.toFixed(2)}%</p>
          </div>
          <div className="bg-white rounded-xl border border-[#d6e2e6] p-3">
            <p className="text-xs text-[#516c79]">{t('portfolio.nextPayment')}</p>
            <p className="text-lg font-bold font-mono">{income.next_payment ? new Date(income.next_payment).toLocaleDateString() : '—'}</p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden mb-4">
        {positions.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#d6e2e6] text-[#516c79]">
                <th className="text-left p-3">{t('common.name')}</th>
                <th className="text-left p-3">{t('common.currencyShort')}</th>
                <th className="text-right p-3">{t('portfolio.amount')}</th>
                <th className="text-right p-3">{t('common.ytm')}</th>
                <th className="text-right p-3">{t('common.price')}</th>
                <th className="text-right p-3"></th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.internal_id} className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50">
                  <td className="p-3">
                    <div className="text-[#01121a] font-medium truncate max-w-[180px]">{p.name ?? p.internal_id}</div>
                    <div className="text-xs text-[#717680] font-mono">{p.internal_id}</div>
                  </td>
                  <td className="p-3"><CurrencyBadge currency={p.currency || '—'} /></td>
                  <td className="p-3 text-right font-mono">{p.amount.toFixed(2)}</td>
                  <td className="p-3 text-right font-mono">{p.yield_to_maturity != null ? `${p.yield_to_maturity.toFixed(2)}%` : '—'}</td>
                  <td className="p-3 text-right font-mono">{p.price != null ? p.price.toFixed(2) : '—'}</td>
                  <td className="p-3 text-right">
                    <button onClick={() => removePosition(p.internal_id)} className="text-[#717680] hover:text-[#e03400]" aria-label={t('alerts.remove')}>
                      <X size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState message={t('portfolio.noPositions')} />
        )}
      </div>

      <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
        <h4 className="text-sm font-semibold mb-3">{t('portfolio.addPosition')}</h4>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[140px]">
            <label className="text-xs text-[#516c79] block mb-1">{t('common.id')}</label>
            <input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="OP-51"
              className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
          </div>
          <div className="flex-1 min-w-[140px]">
            <label className="text-xs text-[#516c79] block mb-1">Сумма</label>
            <input value={newAmount} onChange={(e) => setNewAmount(e.target.value)} type="number" step="0.01"
              className="w-full bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm" />
          </div>
          <button onClick={addPosition} disabled={busy}
            className="bg-[#004b65] hover:bg-[#387387] disabled:bg-[#d9e4e8] text-white px-4 py-2 rounded-lg text-sm transition-colors">{t('alerts.add')}</button>
        </div>
      </div>
    </div>
  );
}
