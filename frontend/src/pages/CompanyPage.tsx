import { useEffect, useState } from 'react';
import { Building2, ExternalLink, ArrowLeft, TrendingUp, Newspaper } from 'lucide-react';
import { api } from '../lib/api';
import type { CompanyDetail, NewsItem } from '../lib/api';
import { LoadingSkeleton, ErrorBanner, EmptyState, TierBadge } from '../components/common';
import { RecommendationCard } from '../components/RecommendationCard';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';

interface Props {
  issuer: string;
  onBack?: () => void;
  onOpenBond: (internalId: string) => void;
}

export function CompanyPage({ issuer, onBack, onOpenBond }: Props) {
  const { t } = useI18n();
  usePageMeta(t('meta.company'), issuer);
  const [data, setData] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);

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
    api.analytics
      .news({ issuer, limit: 6 })
      .then((items) => {
        if (alive) setNews(items);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setNewsLoading(false);
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
            className="flex items-center gap-1.5 text-sm text-[#516c79] hover:text-[#01121a] transition-colors"
          >
            <ArrowLeft size={16} /> Назад
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl border border-[#d6e2e6] p-6">
        <div className="flex items-start gap-4">
          {data.logo_url ? (
            <img src={data.logo_url} alt={data.name} className="w-14 h-14 rounded-xl object-cover bg-[#f8fafb] ring-1 ring-[#d6e2e6]" />
          ) : (
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-[#004b65] to-[#387387] flex items-center justify-center text-2xl font-bold text-white shrink-0">
              {(data.name || '?').charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold text-[#01121a]">{data.name}</h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {data.sector && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-[#f8fafb] text-[#516c79]">{data.sector}</span>
              )}
              <span className="text-sm text-[#717680]">{data.bond_count} выпуск(ов) в базе</span>
            </div>
            {data.website && (
              <a
                href={data.website}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-[#004b65] hover:underline mt-1"
              >
                <ExternalLink size={12} /> Сайт компании
              </a>
            )}
          </div>
        </div>

        {data.description && (
          <p className="text-sm text-[#516c79] mt-4 leading-relaxed">{data.description}</p>
        )}
        {data.why_important && (
          <div className="mt-4 flex items-start gap-2 bg-[#eef3f5] border border-[#b2c9d1] rounded-lg p-3">
            <Building2 size={16} className="text-[#004b65] shrink-0 mt-0.5" />
            <div>
              <div className="text-xs font-semibold text-[#004b65] mb-1">Почему эта компания важна</div>
              <p className="text-sm text-[#516c79]">{data.why_important}</p>
            </div>
          </div>
        )}
      </div>

      {data.recommendation && (
        <div>
          <h2 className="text-xl font-bold mb-3 flex items-center gap-2">
            <TrendingUp size={20} className="text-[#004b65]" /> Рекомендация по компании
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
                className="text-left bg-white rounded-xl border border-[#d6e2e6] p-4 hover:border-[#004b65] transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-[#01121a] truncate">{b.name}</span>
                  {b.tier && <TierBadge tier={b.tier} />}
                </div>
                <div className="flex items-center gap-3 mt-2 text-xs text-[#717680]">
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

      {news.length > 0 && (
        <div>
          <h2 className="text-xl font-bold mb-3 flex items-center gap-2">
            <Newspaper size={20} className="text-[#004b65]" /> Новости
          </h2>
          {newsLoading && <LoadingSkeleton />}
          <div className="space-y-3">
            {news.map((n) => (
              <a
                key={n.id ?? n.url}
                href={n.url}
                target="_blank"
                rel="noreferrer"
                className="block bg-white rounded-xl border border-[#d6e2e6] p-4 hover:border-[#004b65] transition-colors"
              >
                <p className="text-sm text-[#01121a] leading-snug">{n.title}</p>
                <div className="flex items-center gap-2 mt-2 text-xs text-[#717680]">
                  <span>{n.published_at ? new Date(n.published_at.replace(' ', 'T')).toLocaleString() : ''}</span>
                  <ExternalLink size={12} className="text-[#004b65]" />
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
