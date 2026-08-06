import { ArrowRight } from 'lucide-react';
import { useI18n } from '../../../i18n';

export function CtaSection({ onRegister }: { onRegister: () => void }) {
  const { t } = useI18n();

  return (
    <section className="bg-gradient-to-r from-[#eef3f5] to-[#d9e4e8] border-y border-[#d6e2e6]">
      <div className="max-w-4xl mx-auto px-4 py-20 text-center">
        <p className="text-sm text-[#b45309] mb-4">{t('cta.urgency')}</p>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.ctaTitle')}</h2>
        <p className="text-lg text-[#516c79] mb-8 max-w-xl mx-auto">
          {t('landing.ctaSub')}
        </p>
        <button onClick={onRegister}
          className="bg-[#004b65] hover:bg-[#387387] text-white px-8 py-3 rounded-xl text-base font-medium transition-colors inline-flex items-center gap-2">
          {t('cta.tryNow')} <ArrowRight size={18} />
        </button>
      </div>
    </section>
  );
}
