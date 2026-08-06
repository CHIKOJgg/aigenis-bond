import { AlertTriangle, Clock, Eye, ShieldAlert, Target, TrendingDown } from 'lucide-react';
import { useI18n } from '../../../i18n';

function PainCard({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 hover:border-[#b91c1c]/40 transition-colors group">
      <div className="w-12 h-12 bg-[#fee2e2] rounded-xl flex items-center justify-center mb-4 text-[#b91c1c] group-hover:bg-[#fecaca] transition-colors">
        {icon}
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-[#516c79] leading-relaxed">{description}</p>
    </div>
  );
}

export function PainPointsSection() {
  const { t } = useI18n();

  return (
    <section id="pain-points" className="max-w-7xl mx-auto px-4 py-20">
      <div className="text-center mb-16">
        <div className="inline-flex items-center gap-2 bg-red-900/20 border border-red-800/30 rounded-full px-4 py-1.5 text-sm text-red-300 mb-6">
          <AlertTriangle size={14} /> {t('pain.noTools')}
        </div>
        <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('pain.title')}</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <PainCard
          icon={<Eye size={24} />}
          title={t('pain.p1Title')}
          description={t('pain.p1Desc')}
        />
        <PainCard
          icon={<ShieldAlert size={24} />}
          title={t('pain.p2Title')}
          description={t('pain.p2Desc')}
        />
        <PainCard
          icon={<TrendingDown size={24} />}
          title={t('pain.p3Title')}
          description={t('pain.p3Desc')}
        />
        <PainCard
          icon={<Clock size={24} />}
          title={t('pain.p4Title')}
          description={t('pain.p4Desc')}
        />
        <PainCard
          icon={<Target size={24} />}
          title={t('pain.p5Title')}
          description={t('pain.p5Desc')}
        />
      </div>
    </section>
  );
}
