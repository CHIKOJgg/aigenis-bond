import { useEffect, useState } from 'react';
import { TrendingUp, Sparkles } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import type { AnalyticsRecommendation } from '../lib/api';
import { LoadingSkeleton, ErrorBanner, EmptyState } from './common';
import { RecommendationCard } from './RecommendationCard';

interface Props {
  topK?: number;
  title?: string;
  compact?: boolean;
  onSubscribe?: () => void;
  onOpenBond: (internalId: string) => void;
}

export function RecommendationsPage({ topK = 20, title = 'Рекомендации', compact, onSubscribe, onOpenBond }: Props) {
  const [data, setData] = useState<AnalyticsRecommendation[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setLocked(false);
    api
      .analytics.recommendations(topK)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
        else setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [topK]);

  if (loading) return <LoadingSkeleton />;
  if (locked) {
    return (
      <div className="bg-gradient-to-br from-amber-900/30 to-gray-900 border border-amber-800/50 rounded-xl p-8 text-center max-w-lg mx-auto">
        <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-4">🔒</div>
        <h3 className="text-lg font-bold mb-2">Рекомендации доступны в Pro</h3>
        <p className="text-sm text-gray-400 mb-5">Откройте подписку, чтобы видеть детальные рекомендации по покупке облигаций.</p>
        {onSubscribe && (
          <button onClick={onSubscribe} className="bg-amber-600 hover:bg-amber-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors">
            Подписаться
          </button>
        )}
      </div>
    );
  }
  if (error) return <ErrorBanner message={error} />;

  const recs = data ?? [];
  const limit = compact ? Math.min(recs.length, 6) : recs.length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <TrendingUp size={22} className="text-emerald-400" /> {title}
        </h2>
        <span className="text-xs text-gray-500 flex items-center gap-1">
          <Sparkles size={13} className="text-emerald-400" /> вердикт + причины «за» и «против»
        </span>
      </div>
      {recs.length === 0 ? (
        <EmptyState message="Пока нет рекомендаций." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {recs.slice(0, limit).map((r) => (
            <RecommendationCard
              key={r.internal_id}
              rec={r}
              rank={r.rank}
              title={r.name}
              subtitle={r.issuer || undefined}
              onOpen={() => onOpenBond(r.internal_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
