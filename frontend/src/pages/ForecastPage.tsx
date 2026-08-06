import { api } from '../lib/api';
import type { AnalyticsForecast } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useGated, UpgradePrompt } from '../lib/gate';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';

export default function ForecastPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  usePageMeta(t('meta.forecast'));
  const { data: horizons, loading, error, locked } = useGated<AnalyticsForecast[]>(() => api.analytics.forecast());

  if (loading) return <LoadingSkeleton />;
  if (locked) return <UpgradePrompt onSubscribe={onSubscribe} />;
  if (error) return <ErrorBanner message={error} />;

  const rows = horizons ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('portfolio.forecast')}</h2>
      <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
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
            {rows.map((h, i) => (
              <tr key={i} className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50">
                <td className="p-3 font-semibold">{h.horizon_years} Year{h.horizon_years > 1 ? 's' : ''}</td>
                <td className="p-3 text-right text-[#e03400] font-mono">{Math.round(h.pessimistic_capital).toLocaleString()}</td>
                <td className="p-3 text-right text-[#004b65] font-mono font-semibold">{Math.round(h.expected_capital).toLocaleString()}</td>
                <td className="p-3 text-right text-[#004b65] font-mono">{Math.round(h.optimistic_capital).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState message={t('forecast.empty')} />}
      </div>
    </div>
  );
}
