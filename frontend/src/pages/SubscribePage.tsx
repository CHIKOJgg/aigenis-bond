import { useEffect, useState } from 'react';
import { Star, CreditCard, ExternalLink } from 'lucide-react';
import { api } from '../lib/api';
import type { SubscribeInfo } from '../lib/api';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { useAuth } from '../lib/AuthContext';
import { LoadingSkeleton, ErrorBanner } from '../components/common';

export default function SubscribePage() {
  const { t } = useI18n();
  usePageMeta(t('meta.subscribe'));
  const [info, setInfo] = useState<SubscribeInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [payError, setPayError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    api.subscribeInfo().then(setInfo).catch(() => setInfo(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSkeleton />;

  const isPaid = user && user.subscription_tier !== 'free';
  const isOnTrial = user?.trial_end && new Date(user.trial_end) > new Date();
  const trialDaysLeft = isOnTrial && user?.trial_end ? Math.ceil((new Date(user.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : 0;

  const trialDaysWord = (n: number) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return 'день';
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return 'дня';
    return 'дней';
  };

  const handleYooKassaPayment = async (plan: string) => {
    try {
      setPayError(null);
      setPaying(true);
      const base = window.location.origin;
      const refCode = new URLSearchParams(window.location.search).get('ref');
      const result = await api.billing.createPayment(plan, `${base}/dashboard?success=1`, `${base}/subscribe`, refCode);
      if (result.confirmation_url) window.location.href = result.confirmation_url;
    } catch (e: unknown) {
      setPayError(e instanceof Error ? e.message : t('payment.error'));
      setPaying(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="text-center">
        <div className="w-14 h-14 bg-[#004b65]/20 rounded-full flex items-center justify-center mx-auto mb-3">
          <Star size={26} className="text-[#004b65]" />
        </div>
        <h2 className="text-2xl font-bold font-[Montserrat,sans-serif]">{t('subscribe.title')}</h2>
        <p className="text-sm text-[#516c79] mt-2">
          {t('subscribe.desc')}
        </p>
        {isOnTrial && (
          <p className="mt-3 inline-block bg-[#eef3f5] border border-[#d6e2e6] text-[#004b65] text-sm px-3 py-1.5 rounded-lg">
            {t('trial.daysLeftFull', { days: trialDaysLeft, daysWord: trialDaysWord(trialDaysLeft) })}
          </p>
        )}
        {payError && <ErrorBanner message={payError} />}
        {isPaid && !isOnTrial && (
          <p className="mt-3 inline-block bg-[#ebfff2] border border-[#06b663] text-[#06b663] text-sm px-3 py-1.5 rounded-lg">
            {t('subscribe.currentTier', { tier: user!.subscription_tier })}
          </p>
        )}
      </div>

      {info?.yookassa_configured && info.yookassa_plans.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <CreditCard size={18} className="text-[#004b65]" /> {t('subscribe.cardTitle')}
          </h3>
          <p className="text-sm text-[#717680] mb-3">{t('subscribe.cardHint')}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {info.yookassa_plans.map(p => (
              <div key={p.tier} className="bg-white rounded-xl border border-[#d6e2e6] p-5 flex flex-col">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-bold">{p.name}</h3>
                  <span className="text-[#004b65] font-semibold">{p.price} {p.currency}/{p.interval}</span>
                </div>
                <p className="text-sm text-[#516c79] flex-1">
                  {p.tier === 'pro' ? t('subscribe.proDesc') : t('subscribe.entDesc')}
                </p>
                <button onClick={() => handleYooKassaPayment(p.tier)}
                  disabled={paying}
                  className="mt-4 w-full bg-[#004b65] hover:bg-[#387387] disabled:bg-[#d9e4e8] disabled:cursor-wait text-white py-2 rounded-lg text-sm font-medium transition-colors">
                  {paying ? t('subscribe.processing') : t('subscribe.payCard')}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Star size={18} className="text-[#004b65]" /> Telegram Stars
        </h3>
        {(info?.plans ?? []).length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {(info?.plans ?? []).map(p => (
              <div key={p.tier} className="bg-white rounded-xl border border-[#d6e2e6] p-5 flex flex-col">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-bold">{p.name}</h3>
                  <span className="flex items-center gap-1 text-[#004b65] font-semibold"><Star size={15} />{p.stars}</span>
                </div>
                <p className="text-sm text-[#516c79] flex-1">{p.blurb}</p>
                <p className="text-xs text-[#717680] mt-3">{t('subscribe.duration', { days: p.duration_days })}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#717680]">{t('subscribe.starsUnavailable')}</p>
        )}

        {info?.deep_link ? (
          <a href={info.deep_link} target="_blank" rel="noopener noreferrer"
            className="mt-4 flex items-center justify-center gap-2 bg-[#004b65] hover:bg-[#387387] text-white py-3 rounded-xl text-sm font-medium transition-colors">
            <ExternalLink size={16} /> {t('subscribe.inBot')}
          </a>
        ) : (
          <p className="mt-4 text-center text-sm text-[#717680]">
            {t('subscribe.openBot')}
          </p>
        )}
      </div>
    </div>
  );
}
