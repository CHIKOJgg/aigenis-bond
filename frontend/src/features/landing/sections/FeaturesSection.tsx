import { BarChart3, Bell, Brain, LineChart, PieChart, Shield } from 'lucide-react';
import { useI18n } from '../../../i18n';

function FeatureCard({ icon, title, description, color }: { icon: React.ReactNode; title: string; description: string; color: string }) {
  return (
    <div className="bg-white rounded-2xl border border-[#d6e2e6] p-6 hover:border-[#b2c9d1] transition-colors">
      <div className={`w-12 h-12 bg-gradient-to-br ${color} rounded-xl flex items-center justify-center mb-4`}>
        {icon}
      </div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-[#516c79] leading-relaxed">{description}</p>
    </div>
  );
}

export function FeaturesSection() {
  const { t } = useI18n();

  return (
    <section id="features" className="max-w-7xl mx-auto px-4 py-20">
      <div className="text-center mb-16">
        <h2 className="text-3xl md:text-4xl font-bold mb-4">{t('landing.featuresTitle')}</h2>
        <p className="text-[#516c79] max-w-2xl mx-auto">{t('landing.featuresSub')}</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <FeatureCard
          icon={<BarChart3 size={24} />}
          title={t('feat.result1')}
          description={t('feat.result1Desc')}
          color="from-[#004b65] to-[#003545]"
        />
        <FeatureCard
          icon={<Shield size={24} />}
          title={t('feat.result2')}
          description={t('feat.result2Desc')}
          color="from-purple-500 to-purple-700"
        />
        <FeatureCard
          icon={<LineChart size={24} />}
          title={t('feat.result3')}
          description={t('feat.result3Desc')}
          color="from-blue-500 to-blue-700"
        />
        <FeatureCard
          icon={<PieChart size={24} />}
          title={t('feat.result4')}
          description={t('feat.result4Desc')}
          color="from-amber-500 to-amber-700"
        />
        <FeatureCard
          icon={<Brain size={24} />}
          title={t('feat.result5')}
          description={t('feat.result5Desc')}
          color="from-pink-500 to-pink-700"
        />
        <FeatureCard
          icon={<Bell size={24} />}
          title={t('feat.result6')}
          description={t('feat.result6Desc')}
          color="from-red-500 to-red-700"
        />
      </div>
    </section>
  );
}
