import { Sparkles } from 'lucide-react';
import { useI18n } from '../../../i18n';

export function RoiSection() {
  const { t } = useI18n();

  return (
    <section className="max-w-5xl mx-auto px-4 py-20">
      <div className="bg-gradient-to-br from-[#eef3f5] to-[#d9e4e8] rounded-2xl border border-[#b2c9d1] p-8 md:p-12">
        <div className="text-center">
          <Sparkles className="text-[#004b65] mx-auto mb-4" size={32} />
          <h2 className="text-3xl md:text-4xl font-bold mb-6">{t('roi.title')}</h2>
          <p className="text-lg text-[#01121a] max-w-2xl mx-auto mb-8">
            {t('roi.calc', { diff: '1 200' })}
          </p>
          <p className="text-sm text-[#516c79] max-w-xl mx-auto">
            {t('roi.subNote')}
          </p>
        </div>
      </div>
    </section>
  );
}
