import { useState } from 'react';
import { LineChart, Zap } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import type { AnalyticsCurve, AnalyticsRV, AnalyticsCarry, AnalyticsRepo, AnalyticsStress } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useGated, UpgradePrompt } from '../lib/gate';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';
import YieldCurveChart from '../components/charts/YieldCurveChart';
import RVHeatmap from '../components/charts/RVHeatmap';
import CarryBarChart from '../components/charts/CarryBarChart';
import StressWaterfall from '../components/charts/StressWaterfall';
import { InputField, DetailRow } from './ui';

export default function DeskPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  usePageMeta(t('meta.desk'));
  const [tab, setTab] = useState<'curve' | 'rv' | 'carry' | 'repo' | 'stress'>('curve');

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('desk.title')}</h2>
      <div className="flex gap-2 flex-wrap">
        {(['curve', 'rv', 'carry', 'repo', 'stress'] as const).map(tt => (
          <button key={tt} onClick={() => setTab(tt)}
            className={`px-4 py-2 rounded-lg text-sm capitalize ${tab === tt ? 'bg-[#004b65] text-white' : 'bg-[#f8fafb] text-[#516c79] hover:text-[#004b65]'}`}>
            {tt === 'curve' ? t('desk.tabCurve') : tt === 'rv' ? t('desk.tabRv') : tt === 'carry' ? t('desk.tabCarry') : tt === 'repo' ? t('desk.tabRepo') : t('desk.tabStress')}
          </button>
        ))}
      </div>
      {tab === 'curve' && <DeskCurve onSubscribe={onSubscribe} />}
      {tab === 'rv' && <DeskRV onSubscribe={onSubscribe} />}
      {tab === 'carry' && <DeskCarry onSubscribe={onSubscribe} />}
      {tab === 'repo' && <DeskRepo onSubscribe={onSubscribe} />}
      {tab === 'stress' && <DeskStress onSubscribe={onSubscribe} />}
    </div>
  );
}

function DeskCurve({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: curves, loading, error, locked } = useGated<AnalyticsCurve[]>(() => api.analytics.curve());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <LineChart size={16} className="text-[#004b65]" /> {t('desk.tabCurve')}
        </h3>
        <YieldCurveChart currencies={(curves ?? []).map((c) => ({ currency: c.currency, points: c.points }))} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(curves ?? []).map(c => (
          <div key={c.currency} className="bg-white rounded-xl border border-[#d6e2e6] p-4">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <LineChart size={14} className="text-[#004b65]" /> {c.currency} Curve
              <span className="text-xs text-[#717680] font-normal ml-auto">{t('desk.slope')} {c.slope.toFixed(2)}</span>
            </h3>
            <div className="space-y-1">
              {c.points.filter(p => p.years > 0).slice(0, 15).map((p, i) => (
                <div key={i} className="flex justify-between text-sm py-1 border-b border-[#d6e2e6]/50">
                  <span className="text-[#516c79] font-mono text-xs">{p.tenor}</span>
                  <span className="text-[#004b65] font-mono">{p.rate_pct.toFixed(2)}%</span>
                </div>
              ))}
            </div>
          </div>
        ))}
        {(curves ?? []).length === 0 && <EmptyState message={t('desk.curveEmpty')} className="col-span-full" />}
      </div>
    </div>
  );
}

function DeskRV({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data: signals, loading, error, locked } = useGated<AnalyticsRV[]>(() => api.analytics.rv());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = signals ?? [];
  const heatmapData = rows
    .filter((s) => s.z_score != null)
    .map((s) => ({
      internal_id: s.internal_id,
      z_score: s.z_score!,
      currency: 'BYN',
      issuer: s.internal_id,
    }));
  return (
    <div className="space-y-4">
      {heatmapData.length > 0 && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <h3 className="text-sm font-semibold mb-3 text-[#516c79]">{t('desk.rvTitle')}</h3>
          <RVHeatmap signals={heatmapData} />
        </div>
      )}
      <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#d6e2e6] text-[#516c79]">
              <th className="text-left p-3">{t('common.id')}</th>
              <th className="text-right p-3">{t('desk.rvSpread')}</th>
              <th className="text-right p-3">{t('desk.rvZscore')}</th>
              <th className="text-left p-3">{t('desk.rvSignal')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 40).map((s, i) => (
              <tr key={i} className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50">
                <td className="p-3 font-mono text-xs text-[#516c79]">{s.internal_id}</td>
                <td className="p-3 text-right font-mono">{s.spread_pct != null ? `${s.spread_pct.toFixed(2)}%` : '-'}</td>
                <td className="p-3 text-right font-mono">{s.z_score != null ? s.z_score.toFixed(2) : '-'}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${s.side === 'buy' ? 'bg-[#ebfff2] text-[#06b663]' : s.side === 'sell' ? 'bg-[#fff1ee] text-[#e03400]' : 'bg-[#f8fafb] text-[#516c79]'}`}>
                    {s.side.toUpperCase()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState message={t('desk.rvEmpty')} />}
      </div>
    </div>
  );
}

function DeskCarry({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const [funding, setFunding] = useState('5.0');
  const { data: trades, loading, error, locked } = useGated<AnalyticsCarry[]>(
    () => api.analytics.carry(parseFloat(funding) || 5), [funding]
  );

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = trades ?? [];
  return (
    <div className="space-y-4">
      {rows.length > 0 && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <h3 className="text-sm font-semibold mb-3 text-[#516c79]">{t('desk.carryTitle')}</h3>
          <CarryBarChart trades={rows.map((t) => ({ internal_id: t.internal_id, expected_pnl_pct: t.expected_pnl_pct, coupon_pct: t.coupon_pct }))} />
        </div>
      )}
      <div className="flex items-center gap-3">
        <label className="text-sm text-[#516c79]">{t('desk.fundingRate')}</label>
        <input value={funding} onChange={e => setFunding(e.target.value)} type="number" step="0.1" className="bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-1.5 text-[#01121a] text-sm w-24" />
        <span className="text-sm text-[#717680]">%</span>
      </div>
      <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#d6e2e6] text-[#516c79]">
              <th className="text-left p-3">{t('common.id')}</th>
              <th className="text-right p-3">{t('common.coupon')}</th>
              <th className="text-right p-3">{t('desk.carryRolldown')}</th>
              <th className="text-right p-3">{t('desk.carryPnl')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 30).map((t, i) => (
              <tr key={i} className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50">
                <td className="p-3 font-mono text-xs text-[#516c79]">{t.internal_id}</td>
                <td className="p-3 text-right font-mono">{t.coupon_pct.toFixed(2)}%</td>
                <td className="p-3 text-right font-mono">{t.rolldown_bps.toFixed(1)}bp</td>
                <td className={`p-3 text-right font-mono ${t.expected_pnl_pct > 0 ? 'text-[#004b65]' : 'text-[#e03400]'}`}>{t.expected_pnl_pct > 0 ? '+' : ''}{t.expected_pnl_pct.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState message={t('desk.carryEmpty')} />}
      </div>
    </div>
  );
}

function DeskRepo({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const [bondId, setBondId] = useState('');
  const [notional, setNotional] = useState('1000');
  const [tenor, setTenor] = useState('30');
  const [result, setResult] = useState<AnalyticsRepo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);

  const calculate = async () => {
    if (!bondId) return;
    const n = parseFloat(notional);
    const tenorVal = parseInt(tenor);
    if (isNaN(n) || isNaN(tenorVal) || n <= 0 || tenorVal <= 0) {
      setError('desk.repoInvalidInput');
      return;
    }
    setBusy(true); setError(null); setLocked(false);
    try {
      const r = await api.analytics.repo({ bond_id: bondId, notional: n, tenor_days: tenorVal });
      setResult(r);
    } catch (e: unknown) {
      setResult(null);
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  if (locked) return (
    <div className="space-y-4">
      <UpgradePrompt onSubscribe={onSubscribe} />
      <button onClick={() => setLocked(false)} className="text-sm text-[#516c79] hover:text-[#004b65] transition-colors">
        {t('action.back')}
      </button>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#d6e2e6] p-4 max-w-md">
        <h3 className="text-lg font-semibold mb-4">{t('desk.repoCalc')}</h3>
        <div className="space-y-3">
          <InputField label={t('desk.repoBondId')} value={bondId} onChange={setBondId} placeholder="OP-51" />
          <InputField label={t('desk.repoNotional')} value={notional} onChange={setNotional} type="number" />
          <InputField label={t('desk.repoTenor')} value={tenor} onChange={setTenor} type="number" />
          <button onClick={calculate} disabled={busy} className="w-full bg-[#004b65] hover:bg-[#387387] disabled:bg-[#d9e4e8] text-white py-2 rounded-lg text-sm font-medium transition-colors">{busy ? t('desk.repoCalculating') : t('desk.repoCalculate')}</button>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      {result && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4 max-w-md">
          <h3 className="text-lg font-semibold mb-3">{t('desk.repoResults')}</h3>
          <div className="space-y-2 text-sm">
            <DetailRow label={t('common.bond')} value={result.internal_id} />
            <DetailRow label={t('desk.repoHaircut')} value={`${result.haircut_pct.toFixed(2)}%`} />
            <DetailRow label={t('desk.repoRate')} value={`${result.repo_rate_pct.toFixed(2)}%`} />
            <DetailRow label={t('desk.repoTenorShort')} value={`${result.tenor_days}d`} />
            <DetailRow label={t('desk.repoCashLent')} value={result.cash_lent.toFixed(2)} />
            <DetailRow label={t('desk.repoCollateral')} value={result.collateral_value.toFixed(2)} />
            <DetailRow label={t('desk.repoAccrued')} value={result.accrued_interest.toFixed(4)} />
          </div>
        </div>
      )}
    </div>
  );
}

function DeskStress({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  const { data, loading, error, locked } = useGated<AnalyticsStress[]>(() => api.analytics.stress());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const results = data ?? [];
  const waterfallData = results.map((r) => ({ scenario_name: r.scenario, pnl_pct: r.pnl_pct }));
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold flex items-center gap-2"><Zap size={16} className="text-[#004b65]" /> {t('desk.stressTitle')}</h3>
      {waterfallData.length > 0 && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
          <StressWaterfall runs={waterfallData} />
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {results.map(r => (
          <div key={r.scenario} className="bg-white rounded-xl border border-[#d6e2e6] p-4">
            <h4 className="font-semibold mb-2 capitalize">{r.scenario.replace(/_/g, ' ')}</h4>
            <div className="space-y-1 text-sm">
              <p className={`text-2xl font-bold ${r.pnl_pct >= 0 ? 'text-[#004b65]' : 'text-[#e03400]'}`}>{r.pnl_pct >= 0 ? '+' : ''}{r.pnl_pct.toFixed(2)}%</p>
              <p className="text-[#516c79]">{t('desk.stressPnl')} {r.pnl >= 0 ? '+' : ''}{r.pnl.toFixed(0)}</p>
              <p className="text-[#717680] text-xs">{r.kind}</p>
            </div>
          </div>
        ))}
      </div>
      {results.length === 0 && <EmptyState message={t('desk.stressEmpty')} />}
    </div>
  );
}
