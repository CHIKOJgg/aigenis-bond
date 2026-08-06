import { useEffect, useMemo, useState } from 'react';
import { Search, ExternalLink, Newspaper } from 'lucide-react';
import { api } from '../lib/api';
import type { NewsItem } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';

const NEWS_LIMIT = 100;

export default function NewsPage() {
  const { t } = useI18n();
  usePageMeta(t('meta.news'));
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.analytics.news({ limit: NEWS_LIMIT })
      .then(setNews)
      .catch(() => setError(t('dash.loadError')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return news.filter((n) => !q || n.title.toLowerCase().includes(q));
  }, [news, query]);

  const groups = useMemo(() => {
    const map = new Map<string, NewsItem[]>();
    filtered.forEach((n) => {
      const day = n.published_at ? n.published_at.slice(0, 10) : '—';
      const list = map.get(day) ?? [];
      list.push(n);
      map.set(day, list);
    });
    return Array.from(map.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [filtered]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('news.title')}</h2>
        <p className="text-sm text-[#516c79] mt-1">{t('news.subtitle')}</p>
      </div>

      <div className="relative flex-1 max-w-md">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a4a7ae]" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('news.searchPlaceholder')}
          className="w-full bg-white border border-[#d6e2e6] rounded-lg pl-9 pr-3 py-2 text-sm text-[#01121a] placeholder-[#a4a7ae] focus:outline-none focus:border-[#004b65]"
        />
      </div>

      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && groups.length === 0 && (
        <div className="bg-white rounded-xl border border-[#d6e2e6]">
          <EmptyState message={t('news.empty')} />
        </div>
      )}

      {!loading && !error && groups.length > 0 && (
        <div className="space-y-6">
          {groups.map(([day, items]) => (
            <div key={day}>
              <div className="flex items-center gap-2 mb-2">
                <Newspaper size={14} className="text-[#004b65]" />
                <span className="text-xs font-semibold text-[#516c79] uppercase tracking-wide">{day}</span>
              </div>
              <div className="space-y-2">
                {items.map((n) => (
                  <a
                    key={n.id ?? n.url}
                    href={n.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block bg-white rounded-xl border border-[#d6e2e6] p-4 hover:border-[#004b65] transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-[#01121a] leading-snug">{n.title}</p>
                      <ExternalLink size={14} className="text-[#004b65] shrink-0 mt-0.5" />
                    </div>
                    <div className="text-xs text-[#717680] mt-1.5">
                      {n.published_at ? new Date(n.published_at.replace(' ', 'T')).toLocaleString() : ''}
                    </div>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
