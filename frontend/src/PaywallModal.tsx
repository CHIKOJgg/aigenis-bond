import { useEffect, useState } from 'react';
import {
  Lock, Star, TrendingUp, X, Check, Globe2, LineChart, Brain, CreditCard, ExternalLink,
} from 'lucide-react';
import { Modal } from './lib/Modal';
import { usePaywall } from './lib/PaywallContext';
import { useAuth } from './lib/AuthContext';
import { api, type SubscribeInfo } from './lib/api';
import { useI18n } from './i18n';

const ICONS: Record<string, React.ReactNode> = {
  lock: <Lock size={26} className="text-amber-400" />,
  currencies: <Globe2 size={26} className="text-amber-400" />,
  desk: <LineChart size={26} className="text-amber-400" />,
  ml: <Brain size={26} className="text-amber-400" />,
};

const TIER_FEATURES: { label: string; free: boolean; pro: boolean; ent: boolean }[] = [
  { label: 'paywall.f1', free: true, pro: true, ent: true },
  { label: 'paywall.f2', free: true, pro: true, ent: true },
  { label: 'paywall.f3', free: true, pro: false, ent: false },
  { label: 'paywall.f4', free: false, pro: true, ent: true },
  { label: 'paywall.f5', free: false, pro: true, ent: true },
  { label: 'paywall.f6', free: false, pro: true, ent: true },
  { label: 'paywall.f7', free: false, pro: true, ent: true },
  { label: 'paywall.f8', free: false, pro: true, ent: true },
  { label: 'paywall.f9', free: false, pro: false, ent: true },
];

export function PaywallModal({ onSubscribe }: { onSubscribe: () => void }) {
  const { t } = useI18n();
  const { state, closePaywall } = usePaywall();
  const { user } = useAuth();
  const [info, setInfo] = useState<SubscribeInfo | null>(null);

  useEffect(() => {
    if (state.open) api.subscribeInfo().then(setInfo).catch(() => setInfo(null));
  }, [state.open]);

  if (!state.open) return null;

  const isPaid = user != null && user.subscription_tier !== 'free';
  const isFreeUser = user != null && user.subscription_tier === 'free';
  const planFor = (tier: 'pro' | 'enterprise') => info?.plans?.find((p) => p.tier === tier);
  const pro = planFor('pro');
  const ent = planFor('enterprise');

  const openInBot = () => {
    if (info?.deep_link) {
      window.open(info.deep_link, '_blank', 'noopener');
    } else {
      onSubscribe();
      closePaywall();
    }
  };

  const TierCard = ({
    name,
    price,
    period,
    highlight,
    cta,
  }: {
    name: string;
    price: string;
    period?: string;
    highlight?: boolean;
    cta: React.ReactNode;
  }) => (
    <div
      className={`flex flex-col rounded-xl border p-4 ${
        highlight ? 'border-amber-500 bg-amber-500/5' : 'border-gray-800 bg-gray-900'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <h4 className="font-bold text-base">{name}</h4>
        {highlight && (
            <span className="text-[10px] uppercase tracking-wide bg-amber-600 text-white px-2 py-0.5 rounded-full">
              {t('paywall.recommended')}
            </span>
        )}
      </div>
      <div className="mb-3">
        <span className="text-2xl font-bold text-white">{price}</span>
        {period && <span className="text-sm text-gray-400 ml-1">{period}</span>}
      </div>
      <div className="mt-auto">{cta}</div>
    </div>
  );

  return (
    <Modal onClose={closePaywall} className="relative max-w-3xl w-full border-amber-800/50 max-h-[88vh] overflow-y-auto">
      <button
        onClick={closePaywall}
        className="absolute top-3 right-3 text-gray-500 hover:text-white p-1 z-10"
        aria-label={t('action.close')}
      >
        <X size={18} />
      </button>

      <div className="bg-gradient-to-br from-amber-600/20 to-gray-900 px-6 pt-8 pb-6 text-center">
        <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-3">
          {ICONS[state.feature.icon] ?? ICONS.lock}
        </div>
        <h3 className="text-xl font-bold">{t(state.feature.title)}</h3>
        <p className="text-sm text-gray-400 mt-2">{t(state.feature.description)}</p>
      </div>

      <div className="px-6 py-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <TierCard
            name="Free"
            price={t('paywall.freePrice')}
            cta={
              <button
                disabled={isFreeUser}
                className="w-full text-sm py-2 rounded-lg border border-gray-700 text-gray-300 disabled:opacity-50 disabled:cursor-default"
              >
                {isFreeUser ? t('paywall.currentPlan') : t('paywall.basic')}
              </button>
            }
          />
          <TierCard
            name="Pro"
            price={pro ? `${pro.stars} ⭐` : 'Pro'}
            period={pro ? `${pro.duration_days} ${t('paywall.days')}` : undefined}
            highlight
            cta={
              isPaid ? (
                <button disabled className="w-full text-sm py-2 rounded-lg bg-gray-800 text-gray-400">
                  {t('paywall.accessOpen')}
                </button>
              ) : (
                <button
                  onClick={openInBot}
                  className="w-full inline-flex items-center justify-center gap-1.5 bg-amber-600 hover:bg-amber-500 text-white py-2 rounded-lg text-sm font-semibold transition-colors"
                >
                  <Star size={15} /> {t('paywall.payStars')}
                </button>
              )
            }
          />
          <TierCard
            name="Enterprise"
            price={ent ? `${ent.stars} ⭐` : 'Enterprise'}
            period={ent ? `${ent.duration_days} ${t('paywall.days')}` : undefined}
            cta={
              isPaid ? (
                <button disabled className="w-full text-sm py-2 rounded-lg bg-gray-800 text-gray-400">
                  {t('paywall.accessOpen')}
                </button>
              ) : (
                <button
                  onClick={openInBot}
                  className="w-full inline-flex items-center justify-center gap-1.5 bg-gray-800 hover:bg-gray-700 text-white py-2 rounded-lg text-sm font-semibold transition-colors"
                >
                   <Star size={15} /> {t('paywall.payStars')}
                </button>
              )
            }
          />
        </div>

        <div className="mt-6">
          <p className="text-xs uppercase tracking-wide text-gray-500 mb-3 font-semibold">
            {t('paywall.whatIncluded')}
          </p>
          <div className="space-y-1">
            {TIER_FEATURES.map((f) => (
              <div
                key={f.label}
                className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 py-1.5 border-b border-gray-800/60 text-sm"
              >
                <span className="text-gray-300">{t(f.label)}</span>
                <Check size={16} className={f.free ? 'text-emerald-400' : 'text-gray-700'} />
                <Check size={16} className={f.pro ? 'text-emerald-400' : 'text-gray-700'} />
                <Check size={16} className={f.ent ? 'text-emerald-400' : 'text-gray-700'} />
              </div>
            ))}
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 pt-2 text-[10px] uppercase text-gray-500">
              <span />
              <span className="text-center">Free</span>
              <span className="text-center">Pro</span>
              <span className="text-center">Ent</span>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-col sm:flex-row gap-3">
          <button
            onClick={openInBot}
            className="flex-1 inline-flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-500 text-white py-3 rounded-xl text-sm font-semibold transition-colors"
          >
            <ExternalLink size={16} /> {t('paywall.payTelegram')}
          </button>
          <button
            onClick={() => { closePaywall(); onSubscribe(); }}
            className="flex-1 inline-flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-white py-3 rounded-xl text-sm font-semibold transition-colors"
          >
            <CreditCard size={16} /> {t('paywall.payCard')}
          </button>
        </div>
        {info?.yookassa_configured && (
          <p className="mt-3 text-center text-xs text-gray-500">
            {t('paywall.yookassaNote')}
          </p>
        )}
      </div>

      <div className="px-6 py-3 bg-gray-950/50 text-center">
        <p className="text-xs text-gray-600 flex items-center justify-center gap-1">
          <TrendingUp size={12} /> Aigenis Bonds
        </p>
      </div>
    </Modal>
  );
}
