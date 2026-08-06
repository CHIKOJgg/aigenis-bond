import { useEffect, useState } from 'react';
import { Lock, Star } from 'lucide-react';
import { ApiError } from './api';
import { useI18n } from '../i18n';

export function useGated<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  // The dependency array is supplied by the caller via `deps`; `fetcher` is
  // intentionally excluded so callers control re-fetch behaviour.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true); setError(null); setLocked(false);
    fetcher()
      .then(d => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (!alive || controller.signal.aborted) return;
        if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
        else setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, loading, error, locked };
}

export function UpgradePrompt({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="bg-gradient-to-br from-[#eef3f5] to-white border border-[#d6e2e6] rounded-xl p-8 text-center max-w-lg mx-auto">
      <div className="w-14 h-14 bg-[#004b65]/20 rounded-full flex items-center justify-center mx-auto mb-4">
        <Lock size={26} className="text-[#004b65]" />
      </div>
      <h3 className="text-lg font-bold mb-2">{t('upgrade.title')}</h3>
      <p className="text-sm text-[#516c79] mb-5">
        {t('upgrade.desc')}
      </p>
      {onSubscribe && (
        <button onClick={onSubscribe}
          className="inline-flex items-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors">
          <Star size={16} /> {t('upgrade.cta')}
        </button>
      )}
    </div>
  );
}
