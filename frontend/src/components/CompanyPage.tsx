import { useEffect, useState } from 'react';
import { Building2, ExternalLink, ArrowLeft, TrendingUp } from 'lucide-react';
import { api } from '../lib/api';
import type { CompanyDetail } from '../lib/api';
import { LoadingSkeleton, ErrorBanner, EmptyState, TierBadge } from './common';
import { RecommendationCard } from './RecommendationCard';

interface Props {
  issuer: string;
  onBack?: () => void;
  onOpenBond: (internalId: string) => void;
}

export function CompanyPage({ issuer, onBack, onOpenBond }: Props) {
  const [data, setData] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .analytics.company(issuer)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch(() => {
        if (alive) setError('Не удалось загрузить данные компании.');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [issuer]);

  if (loading) return <LoadingSkeleton />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <EmptyState message="Компания не найдена." />;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        {onBack && (
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft size={16} /> Назад
          </button>
        )}
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-start gap-4">
          {data.logo_url ? (
            <img src={data.logo_url} alt={data.name} className="w-14 h-14 rounded-xl object-cover bg-gray-800 ring-1 ring-gray-700" />
          ) : (
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-700 to-emerald-900 flex items-center justify-center text-2xl font-bold text-emerald-200 shrink-0">
              {(data.name || '?').charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold text-white">{data.name}</h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {data.sector && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-800 text-gray-300">{data.sector}</span>
              )}
              <span className="text-sm text-gray-500">{data.bond_count} выпуск(ов) в базе</span>
            </div>
            {data.website && (
              <a
                href={data.website}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline mt-1"
              >
                <ExternalLink size={12} /> Сайт компании
              </a>
            )}
          </div>
        </div>

        {data.description && (
          <p className="text-sm text-gray-300 mt-4 leading-relaxed">{data.description}</p>
        )}
        {data.why_important && (
          <div className="mt-4 flex items-start gap-2 bg-emerald-950/30 border border-emerald-900 rounded-lg p-3">
            <Building2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="text-xs font-semibold text-emerald-300 mb-1">Почему эта компания важна</div>
              <p className="text-sm text-emerald-100/90">{data.why_important}</p>
            </div>
          </div>
        )}
      </div>

      {data.recommendation && (
        <div>
          <h2 className="text-xl font-bold mb-3 flex items-center gap-2">
            <TrendingUp size={20} className="text-emerald-400" /> Рекомендация по компании
          </h2>
          <RecommendationCard
            rec={data.recommendation}
            title={data.name}
            subtitle={data.sector || undefined}
          />
        </div>
      )}

      <div>
        <h2 className="text-xl font-bold mb-3">Облигации эмитента</h2>
        {data.bonds.length === 0 ? (
          <EmptyState message="У этой компании пока нет облигаций в базе." />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.bonds.map((b) => (
              <button
                key={b.internal_id}
                onClick={() => onOpenBond(b.internal_id)}
                className="text-left bg-gray-900 rounded-xl border border-gray-800 p-4 hover:border-emerald-700 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-white truncate">{b.name}</span>
                  {b.tier && <TierBadge tier={b.tier} />}
                </div>
                <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                  <span className="font-mono">{b.internal_id}</span>
                  <span className="uppercase">{b.currency}</span>
                  {b.yield_to_maturity != null && (
                    <span>YTM {b.yield_to_maturity.toFixed(2)}%</span>
                  )}
                  {b.score != null && <span>Score {b.score.toFixed(1)}</span>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
