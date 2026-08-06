import { Bell } from 'lucide-react';
import { api } from '../lib/api';
import type { AnalyticsAlert } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useGated, UpgradePrompt } from '../lib/gate';
import { LoadingSkeleton, ErrorBanner, EmptyState } from '../components/common';
import { useUserAlerts, UserAlertsPanel } from './alerts';

export default function AlertsPage({ onSubscribe }: { onSubscribe?: () => void }) {
  const { t } = useI18n();
  usePageMeta(t('meta.alerts'));
  const { data, loading, error, locked } = useGated<AnalyticsAlert[]>(() => api.analytics.alerts(20));
  const { rules, feed, busy, addRule, removeRule } = useUserAlerts();

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('nav.alerts')}</h2>

      <section>
        <h3 className="text-lg font-semibold mb-3">{t('alerts.systemNotifications')}</h3>
        {loading ? <LoadingSkeleton /> : locked ? <UpgradePrompt onSubscribe={onSubscribe} /> : error ? <ErrorBanner message={error} /> : (
          (data ?? []).length > 0 ? (
            <div className="space-y-3">
              {(data ?? []).map((a, i) => (
                <div key={i} className="bg-white rounded-xl border border-[#d6e2e6] p-4">
                  <div className="flex items-start gap-3">
                    <Bell size={16} className="text-[#004b65] mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <h4 className="font-semibold text-sm">{a.title}</h4>
                      <p className="text-sm text-[#516c79] mt-1">{a.message}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState message={t('alerts.pageEmpty')} />
        )}
      </section>

      <section>
        <h3 className="text-lg font-semibold mb-3">{t('alerts.myAlerts')}</h3>
        <UserAlertsPanel rules={rules} feed={feed} busy={busy} onAdd={addRule} onRemove={removeRule} emptyLabel={t('alerts.noRules')} />
      </section>
    </div>
  );
}
