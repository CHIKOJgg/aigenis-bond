import { useEffect, useState, type FormEvent } from 'react';
import { Bell, Plus, Trash2 } from 'lucide-react';
import { api, ApiError } from '../lib/api';
import type { AlertRule, AlertFeedItem } from '../lib/api';
import { useI18n } from '../i18n';

export interface AlertRuleInput {
  internal_id: string;
  metric: 'price' | 'ytm';
  direction: 'above' | 'below';
  threshold: number;
  note?: string;
}

export function useUserAlerts() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [feed, setFeed] = useState<AlertFeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setLocked(false);
    Promise.all([api.userAlerts.rules(), api.userAlerts.feed(50)])
      .then(([r, f]) => {
        if (!alive) return;
        setRules(r);
        setFeed(f);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
        else setError(e instanceof Error ? e.message : 'Failed to load alerts');
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const addRule = async (input: AlertRuleInput) => {
    setBusy(true);
    setError(null);
    try {
      const rule = await api.userAlerts.createRule(input);
      setRules((prev) => [...prev, rule]);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed to create alert rule');
    } finally {
      setBusy(false);
    }
  };

  const removeRule = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      await api.userAlerts.deleteRule(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
    } catch (e: unknown) {
      if (e instanceof ApiError && e.upgradeRequired) setLocked(true);
      else setError(e instanceof Error ? e.message : 'Failed to delete alert rule');
    } finally {
      setBusy(false);
    }
  };

  return { rules, feed, loading, error, locked, busy, addRule, removeRule };
}

export function UserAlertsPanel({
  rules,
  feed,
  busy,
  onAdd,
  onRemove,
  emptyLabel,
}: {
  rules: AlertRule[];
  feed: AlertFeedItem[];
  busy: boolean;
  onAdd: (input: AlertRuleInput) => Promise<void> | void;
  onRemove: (id: number) => Promise<void> | void;
  emptyLabel: string;
}) {
  const { t } = useI18n();
  const [bondId, setBondId] = useState('');
  const [metric, setMetric] = useState<'price' | 'ytm'>('ytm');
  const [direction, setDirection] = useState<'above' | 'below'>('above');
  const [threshold, setThreshold] = useState('12');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = parseFloat(threshold.replace(',', '.'));
    if (!bondId.trim() || Number.isNaN(value)) {
      setError('Alerts: заполните ID облигации и корректный порог.');
      return;
    }
    setError(null);
    await onAdd({
      internal_id: bondId.trim().toUpperCase(),
      metric,
      direction,
      threshold: value,
      note: note.trim() || undefined,
    });
    setBondId('');
    setNote('');
  };

  const metricLabel = (m: string) =>
    m === 'price' ? t('alerts.metricPrice') : m === 'ytm' ? t('alerts.metricYtm') : t('alerts.metricScore');

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#d6e2e6] p-4">
        <h4 className="text-sm font-semibold mb-3">{t('alerts.addRule')}</h4>
        <form onSubmit={submit} className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end">
          <div className="col-span-2">
            <label className="block text-xs text-[#516c79] mb-1">{t('alerts.bondId')}</label>
            <input
              value={bondId}
              onChange={(e) => setBondId(e.target.value)}
              placeholder="SU29008RMFS8"
              className="w-full px-3 py-2 rounded-lg border border-[#d6e2e6] text-sm focus:border-[#004b65] outline-none"
            />
          </div>
          <div>
            <label className="block text-xs text-[#516c79] mb-1">{t('alerts.metric')}</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as 'price' | 'ytm')}
              className="w-full px-3 py-2 rounded-lg border border-[#d6e2e6] text-sm bg-white outline-none"
            >
              <option value="price">{t('alerts.metricPrice')}</option>
              <option value="ytm">{t('alerts.metricYtm')}</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#516c79] mb-1">{t('alerts.direction')}</label>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as 'above' | 'below')}
              className="w-full px-3 py-2 rounded-lg border border-[#d6e2e6] text-sm bg-white outline-none"
            >
              <option value="above">{t('alerts.above')}</option>
              <option value="below">{t('alerts.below')}</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#516c79] mb-1">{t('alerts.threshold')}</label>
            <input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              type="number"
              step="0.01"
              className="w-full px-3 py-2 rounded-lg border border-[#d6e2e6] text-sm focus:border-[#004b65] outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="inline-flex items-center justify-center gap-1.5 bg-[#004b65] hover:bg-[#387387] disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={15} /> {t('alerts.add')}
          </button>
        </form>
        {error && <p className="mt-2 text-xs text-[#e03400]">{error}</p>}
      </div>

      {rules.length === 0 ? (
        <div className="text-sm text-[#516c79]">{emptyLabel}</div>
      ) : (
        <div className="bg-white rounded-xl border border-[#d6e2e6] divide-y divide-[#eef3f5]">
          {rules.map((r) => (
            <div key={r.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <Bell size={15} className="text-[#004b65] shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-[#01121a]">{r.internal_id}</div>
                <div className="text-xs text-[#516c79]">
                  {metricLabel(r.metric)} {r.direction === 'above' ? t('alerts.above') : t('alerts.below')} {r.threshold}
                  {r.last_value != null && ` · ${t('alerts.current')}: ${r.last_value}`}
                </div>
              </div>
              <button
                onClick={() => onRemove(r.id)}
                disabled={busy}
                className="text-[#717680] hover:text-[#e03400] p-1 disabled:opacity-40"
                aria-label={t('alerts.remove')}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold mb-2">{t('alerts.feedTitle')}</h4>
        {feed.length === 0 ? (
          <div className="text-sm text-[#516c79]">{t('alerts.feedEmpty')}</div>
        ) : (
          <div className="bg-white rounded-xl border border-[#d6e2e6] divide-y divide-[#eef3f5]">
            {feed.map((f) => (
              <div key={f.id} className="px-4 py-3 text-sm">
                <div className="font-medium text-[#01121a]">{f.internal_id}</div>
                <div className="text-xs text-[#516c79] mt-0.5">{f.message}</div>
                {f.created_at && <div className="text-[11px] text-[#717680] mt-1">{new Date(f.created_at).toLocaleString()}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
