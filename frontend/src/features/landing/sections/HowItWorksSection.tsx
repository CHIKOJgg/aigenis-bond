import { useI18n } from '../../../i18n';

export function HowItWorksSection() {
  const { t } = useI18n();

  return (
    <section className="bg-white border-y border-[#d6e2e6]">
      <div className="max-w-5xl mx-auto px-4 py-20">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-16">{t('how.resultTitle')}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="text-center">
            <div className="w-14 h-14 bg-[#eef3f5] rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-[#004b65]">1</span>
            </div>
            <h3 className="text-lg font-semibold mb-2">{t('how.step1Title')}</h3>
            <p className="text-sm text-[#516c79]">{t('how.step1Desc')}</p>
          </div>
          <div className="text-center">
            <div className="w-14 h-14 bg-[#eef3f5] rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-[#387387]">2</span>
            </div>
            <h3 className="text-lg font-semibold mb-2">{t('how.step2Title')}</h3>
            <p className="text-sm text-[#516c79]">{t('how.step2Desc')}</p>
          </div>
          <div className="text-center">
            <div className="w-14 h-14 bg-[#fef3c7] rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-[#b45309]">3</span>
            </div>
            <h3 className="text-lg font-semibold mb-2">{t('how.step3Title')}</h3>
            <p className="text-sm text-[#516c79]">{t('how.step3Desc')}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
