import { useI18n } from '../../../i18n';

export function StatsSection() {
  const { t } = useI18n();

  return (
    <section className="border-y border-[#d6e2e6] bg-white">
      <div className="max-w-5xl mx-auto px-4 py-10 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
        <div>
          <p className="text-3xl font-bold text-[#004b65]">1500+</p>
          <p className="text-sm text-[#516c79] mt-1">{t('trust.stat1')}</p>
        </div>
        <div>
          <p className="text-3xl font-bold text-[#004b65]">6</p>
          <p className="text-sm text-[#516c79] mt-1">{t('trust.stat2')}</p>
        </div>
        <div>
          <p className="text-3xl font-bold text-[#004b65]">5</p>
          <p className="text-sm text-[#516c79] mt-1">{t('trust.stat3')}</p>
        </div>
        <div>
          <p className="text-3xl font-bold text-[#004b65]">24/7</p>
          <p className="text-sm text-[#516c79] mt-1">{t('trust.stat4')}</p>
        </div>
      </div>
    </section>
  );
}
