import { Star } from 'lucide-react';
import { useI18n } from '../../../i18n';

export function TestimonialsSection() {
  const { t } = useI18n();

  return (
    <section className="max-w-5xl mx-auto px-4 py-20">
      <h2 className="text-3xl md:text-4xl font-bold text-center mb-12">
        {t('testimonials.title')}
      </h2>
      <div className="grid md:grid-cols-3 gap-6">
        {[0, 1, 2].map(i => (
          <div key={i} className="bg-white rounded-2xl border border-[#d6e2e6] p-6 hover:border-[#b2c9d1] transition-colors">
            <div className="flex items-center gap-1 mb-4">
              {[...Array(5)].map((_, si) => (
                <Star key={si} size={14} className="fill-amber-400 text-amber-400" />
              ))}
            </div>
            <p className="text-sm text-[#01121a] mb-4 leading-relaxed">{t(`testimonials.q${i}`)}</p>
            <p className="text-xs text-[#717680]">{t(`testimonials.author${i}`)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
