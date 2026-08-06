import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { useI18n } from '../../../i18n';
import { api } from '../../../lib/api';

interface PricingSectionProps {
  onRegister: () => void;
}

const DISCOUNT = 0.8;

export function PricingSection({ onRegister }: PricingSectionProps) {
  const { t } = useI18n();
  const [billing, setBilling] = useState<'month' | 'year'>('month');
  const [plans, setPlans] = useState<Record<string, { id: string; name: string; price: number; currency: string; features: string[] }>>({});
  const [starsPlans, setStarsPlans] = useState<Record<string, number>>({});

  useEffect(() => {
    api.billing.plans()
      .then((data) => {
        const byId: Record<string, { id: string; name: string; price: number; currency: string; features: string[] }> = {};
        for (const p of data) byId[p.id] = p;
        setPlans(byId);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    api.subscribeInfo()
      .then((info) => {
        const byTier: Record<string, number> = {};
        for (const p of info.plans ?? []) byTier[p.tier] = p.stars;
        setStarsPlans(byTier);
      })
      .catch(() => {});
  }, []);

  return (
    <section id="pricing" className="max-w-5xl mx-auto px-4 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('pricing.highlight')}</h2>
        <p className="text-[#516c79] mb-8">{t('pricing.startFree')}</p>
        <div className="inline-flex items-center bg-white rounded-xl p-1 border border-[#d6e2e6]">
          <button onClick={() => setBilling('month')}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${billing === 'month' ? 'bg-[#004b65] text-white shadow-lg shadow-[#004b65]/20' : 'text-[#516c79] hover:text-[#01121a]'}`}>
            {t('billing.monthly')}
          </button>
          <button onClick={() => setBilling('year')}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${billing === 'year' ? 'bg-[#004b65] text-white shadow-lg shadow-[#004b65]/20' : 'text-[#516c79] hover:text-[#01121a]'}`}>
            {t('billing.yearly')}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Free */}
        <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 flex flex-col">
          <h3 className="text-lg font-bold mb-1">{t('landing.planFree')}</h3>
          <p className="text-sm text-[#516c79] mb-4">{t('landing.planFreeDesc')}</p>
          <p className="text-3xl font-bold mb-6">0 BYN</p>
          <ul className="space-y-3 text-sm mb-8 flex-1">
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatBondDetails')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatScoring')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatStats')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeat10Api')}</li>
          </ul>
          <button onClick={onRegister}
            className="w-full border border-[#b2c9d1] hover:border-[#387387] text-[#004b65] py-2.5 rounded-xl text-sm font-medium transition-colors">
            {t('landing.getStarted')}
          </button>
        </div>

        {/* Pro */}
        <div className="bg-gradient-to-b from-[#eef3f5] to-white rounded-2xl border border-[#004b65] p-6 flex flex-col relative">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[#004b65] text-white text-xs font-semibold px-4 py-1 rounded-full">
            {t('landing.mostPopular')}
          </div>
          <div className="flex items-start justify-between mb-1">
            <h3 className="text-lg font-bold">Pro</h3>
            {billing === 'year' && (
              <span className="text-xs bg-[#eef3f5] text-[#004b65] border border-[#b2c9d1] rounded-full px-2.5 py-0.5 font-medium">{t('billing.save')}</span>
            )}
          </div>
          <p className="text-sm text-[#516c79] mb-4">{t('pricing.upgradeNote')}</p>
          <p className="text-3xl font-bold mb-2">
            {billing === 'year' ? (
              <>{Math.round((plans.pro?.price ?? 2900) * DISCOUNT)} <span className="text-base line-through text-[#a4a7ae]">{plans.pro?.price ?? 2900}</span></>
            ) : plans.pro?.price ?? 2900}
            <span className="text-base text-[#717680] font-normal"> {billing === 'year' ? '/мес при оплате за год' : t('landing.planPerMonth')}</span>
          </p>
          <p className="text-sm text-[#717680] mb-6">{t('landing.or')} {starsPlans.pro ?? 150} Stars</p>
          <ul className="space-y-3 text-sm mb-8 flex-1">
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatFree')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatDesk')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatOptimizer')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatMl')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatAlerts')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeat60Api')}</li>
          </ul>
          <button onClick={onRegister}
            className="w-full bg-[#004b65] hover:bg-[#387387] text-white py-2.5 rounded-xl text-sm font-medium transition-colors">
            {t('landing.startTrial')}
          </button>
        </div>

        {/* Enterprise */}
        <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 flex flex-col">
          <h3 className="text-lg font-bold mb-1">Enterprise</h3>
          <p className="text-sm text-[#516c79] mb-4">{t('landing.planEntDesc')}</p>
          <p className="text-3xl font-bold mb-2">
            {billing === 'year' ? (
              <>{Math.round((plans.enterprise?.price ?? 9900) * DISCOUNT)} <span className="text-base line-through text-[#a4a7ae]">{plans.enterprise?.price ?? 9900}</span></>
            ) : plans.enterprise?.price ?? 9900}
            <span className="text-base text-[#717680] font-normal"> {billing === 'year' ? '/мес при оплате за год' : t('landing.planPerMonth')}</span>
          </p>
          <p className="text-sm text-[#717680] mb-6">{t('landing.or')} {starsPlans.enterprise ?? 500} Stars</p>
          <ul className="space-y-3 text-sm mb-8 flex-1">
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatFree')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeat300Api')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatPriority')}</li>
            <li className="flex items-start gap-2"><Check size={16} className="text-[#004b65] shrink-0 mt-0.5" /> {t('landing.planFeatCustom')}</li>
          </ul>
          <button onClick={onRegister}
            className="w-full border border-[#b2c9d1] hover:border-[#387387] text-[#004b65] py-2.5 rounded-xl text-sm font-medium transition-colors">
            {t('landing.planContact')}
          </button>
        </div>
      </div>

      <p className="text-center text-sm text-[#717680] mt-8">
        {t('landing.trialNoteRu')}
      </p>
    </section>
  );
}
