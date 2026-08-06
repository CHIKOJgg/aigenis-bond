import { ArrowRight, Zap } from 'lucide-react';
import { useI18n } from '../../../i18n';

interface HeroSectionProps {
  onRegister: () => void;
  scrollTo: (id: string) => void;
}

export function HeroSection({ onRegister, scrollTo }: HeroSectionProps) {
  const { t } = useI18n();

  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-[#d9e4e8] via-[#f5f9fb] to-[#e7f0f4] animate-gradient" />
      <div className="relative max-w-7xl mx-auto px-4 py-20 md:py-32 text-center">
        <div className="inline-flex items-center gap-2 bg-[#eef3f5] border border-[#b2c9d1] rounded-full px-4 py-1.5 text-sm text-[#004b65] mb-8">
          <Zap size={14} /> {t('landing.badge')}
        </div>
        <h1 className="text-4xl md:text-6xl font-bold mb-6 leading-tight">
          {t('landing.hero1')}<br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#004b65] to-[#387387]">
            {t('landing.hero2')}
          </span>
        </h1>
        <p className="text-lg md:text-xl text-[#516c79] max-w-2xl mx-auto mb-10">
          {t('landing.heroDesc')}
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <button onClick={onRegister}
            className="bg-[#004b65] hover:bg-[#387387] text-white px-8 py-3 rounded-xl text-base font-medium transition-colors flex items-center gap-2 animate-pulseGlow">
            {t('landing.startTrial')} <ArrowRight size={18} />
          </button>
          <button onClick={() => scrollTo('features')}
            className="border border-[#b2c9d1] hover:border-[#387387] text-[#516c79] hover:text-[#01121a] px-8 py-3 rounded-xl text-base font-medium transition-colors">
            {t('landing.explore')}
          </button>
        </div>
        <p className="text-sm text-[#717680] mt-4">{t('landing.trialNote')}</p>
      </div>
    </section>
  );
}
