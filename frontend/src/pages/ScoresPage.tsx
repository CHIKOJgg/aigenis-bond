import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { api, exportCsv } from '../lib/api';
import type { Bond, BondScore } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { usePaywall } from '../lib/PaywallContext';
import BondDetailModal from '../components/BondDetailModal';
import { TierBadge, LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';

export default function ScoresPage() {
  const { t } = useI18n();
  usePageMeta(t('meta.scores'));
  const { openPaywall } = usePaywall();
  const [scores, setScores] = useState<BondScore[]>([]);
  const [minScore, setMinScore] = useState('');
  const [debouncedMinScore, setDebouncedMinScore] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Bond | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedMinScore(minScore), 300);
    return () => clearTimeout(timer);
  }, [minScore]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.scores({ min_score: debouncedMinScore ? Number(debouncedMinScore) : undefined, limit: 100 })
      .then((s) => { if (alive) setScores(s); })
      .catch(() => { if (alive) setError('Failed to load scores'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [debouncedMinScore]);

  const openDetail = async (id: string) => {
    try {
      const b = await api.bonds.get(id);
      setDetail(b);
    } catch {
      /* ignore */
    }
  };

  const exportNow = () => {
    exportCsv(
      'scores.csv',
      ['Bond ID', 'Score', 'Tier'],
      scores.map((s) => [s.internal_id, s.score.toFixed(2), s.tier ?? '']),
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('scores.title')}</h2>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <input value={minScore} onChange={e => setMinScore(e.target.value)} placeholder={t('common.minScore')} type="number" step="0.1"
            className="bg-[#f8fafb] border border-[#b2c9d1] rounded-lg px-3 py-2 text-[#01121a] text-sm w-full sm:w-32" />
          <button onClick={exportNow} disabled={scores.length === 0}
            className="flex items-center gap-1.5 bg-[#f8fafb] hover:bg-[#d9e4e8] disabled:opacity-40 text-[#01121a] px-3 py-2 rounded-lg text-sm transition-colors">
            <Download size={15} /> {t('bonds.csv')}
          </button>
        </div>
      </div>
      {loading && <LoadingSkeleton />}
      {error && <ErrorBanner message={error} />}
      {!loading && !error && (
        <div className="bg-white rounded-xl border border-[#d6e2e6] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#d6e2e6] text-[#516c79]">
                <th className="text-left p-3">#</th>
                <th className="text-left p-3">Bond ID</th>
                <th className="text-right p-3">Score</th>
                <th className="text-left p-3">Tier</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s, i) => (
                <tr key={s.internal_id} onClick={() => openDetail(s.internal_id)}
                  className="border-b border-[#d6e2e6] hover:bg-[#f8fafb]/50 cursor-pointer transition-colors">
                  <td className="p-3 text-[#717680] text-xs">{i + 1}</td>
                  <td className="p-3 font-mono text-xs text-[#516c79]">{s.internal_id}</td>
                  <td className="p-3 text-right font-mono text-[#004b65]">{s.score.toFixed(2)}</td>
                  <td className="p-3"><TierBadge tier={s.tier} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {scores.length === 0 && <EmptyState message={t('scores.empty')} />}
        </div>
      )}
      {detail && <BondDetailModal bond={detail} onClose={() => setDetail(null)} onSubscribe={() => openPaywall('portfolio')} onOpenBond={openDetail} />}
    </div>
  );
}
