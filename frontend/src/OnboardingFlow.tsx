import { useState } from 'react';
import { TrendingUp, ArrowRight, Check, X, DollarSign, PieChart, ShieldCheck, Building2, Sparkles } from 'lucide-react';
import { useI18n } from './i18n';
import { api } from './lib/api';
import type { AnalyticsRecommendation, CompanySummary } from './lib/api';
import { LoadingSkeleton, EmptyState } from './components/common';
import { RecommendationCard } from './components/RecommendationCard';

export type OnboardingPage = 'profile' | 'bonds' | 'scores' | 'desk' | 'subscribe' | 'recommendations' | 'companies';

const INTERESTS: { id: string; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: 'usd', label: 'Валютные (USD)', icon: <DollarSign size={20} className="text-blue-400" />, desc: 'Облигации в долларах США' },
  { id: 'byn', label: 'Белорусские (BYN)', icon: <PieChart size={20} className="text-green-400" />, desc: 'Облигации в белорусских рублях' },
  { id: 'metals', label: 'Металлы', icon: <ShieldCheck size={20} className="text-amber-400" />, desc: 'Золото, серебро, платина' },
  { id: 'companies', label: 'По компаниям', icon: <Building2 size={20} className="text-emerald-400" />, desc: 'Топ эмитентов и их облигации' },
];

const STORAGE_KEY = 'aigenis_onboarding_done';

export function isOnboardingNeeded(): boolean {
  return !localStorage.getItem(STORAGE_KEY);
}

export function dismissOnboarding(): void {
  localStorage.setItem(STORAGE_KEY, '1');
}

export function OnboardingFlow({ onDone, onNavigate }: { onDone: () => void; onNavigate?: (page: OnboardingPage) => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState<0 | 1>(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [recs, setRecs] = useState<AnalyticsRecommendation[]>([]);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [loading, setLoading] = useState(false);

  const choose = (id: string) => {
    setSelected(id);
    setStep(1);
    setLoading(true);
    const topK = 5;
    const recPromise = api.analytics.recommendations(topK).catch(() => [] as AnalyticsRecommendation[]);
    const companiesPromise = id === 'companies'
      ? api.analytics.companies({ limit: 6 }).catch(() => [] as CompanySummary[])
      : Promise.resolve([] as CompanySummary[]);
    Promise.all([recPromise, companiesPromise]).then(([r, c]) => {
      setRecs(r);
      setCompanies(c);
      setLoading(false);
    });
  };

  const finish = () => {
    dismissOnboarding();
    if (selected === 'companies' && onNavigate) {
      onNavigate('companies');
    } else {
      onNavigate?.('recommendations');
    }
    onDone();
  };

  const skip = () => {
    dismissOnboarding();
    onDone();
  };

  return (
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4 animate-fadeIn overflow-y-auto"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 sm:p-8 max-w-3xl w-full my-8 relative outline-none">
        <button onClick={skip} className="absolute top-4 right-4 text-gray-500 hover:text-white p-1" aria-label={t('onboarding.skipAria')}>
          <X size={18} />
        </button>

        {step === 0 ? (
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-12 h-12 bg-emerald-600/20 rounded-2xl flex items-center justify-center">
                <Sparkles size={24} className="text-emerald-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold">{t('onboarding.welcome')}</h2>
                <p className="text-sm text-gray-400">{t('onboarding.welcomeDesc')}</p>
              </div>
            </div>
            <p className="text-sm text-emerald-300 mb-4">Что вас интересует в первую очередь? Подберём рекомендации сразу.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {INTERESTS.map((it) => (
                <button
                  key={it.id}
                  onClick={() => choose(it.id)}
                  className="flex items-center gap-3 bg-gray-800/60 hover:bg-gray-800 border border-gray-700 hover:border-emerald-600 rounded-xl p-4 text-left transition-colors"
                >
                  <span className="w-10 h-10 rounded-lg bg-gray-900 flex items-center justify-center shrink-0">{it.icon}</span>
                  <span className="min-w-0">
                    <span className="block font-semibold text-white">{it.label}</span>
                    <span className="block text-xs text-gray-500">{it.desc}</span>
                  </span>
                  <ArrowRight size={16} className="text-gray-500 ml-auto shrink-0" />
                </button>
              ))}
            </div>
            <button onClick={skip} className="mt-5 text-sm text-gray-500 hover:text-gray-300 transition-colors">
              {t('onboarding.skip')}
            </button>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <TrendingUp size={20} className="text-emerald-400" />
                {selected === 'companies' ? 'Топ компаний-эмитентов' : 'Персональные рекомендации'}
              </h2>
              <button onClick={finish} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5">
                {t('onboarding.getStarted')} <Check size={16} />
              </button>
            </div>

            {loading ? (
              <LoadingSkeleton />
            ) : (
              <div className="space-y-4">
                {selected === 'companies' ? (
                  companies.length === 0 ? (
                    <EmptyState message="Пока нет данных по компаниям." />
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {companies.map((c) => (
                        <button
                          key={c.issuer}
                          onClick={() => onNavigate?.('companies')}
                          className="text-left bg-gray-800/60 hover:bg-gray-800 border border-gray-700 rounded-xl p-4 transition-colors"
                        >
                          <div className="font-semibold text-white truncate">{c.name}</div>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            {c.sector && <span className="px-2 py-0.5 rounded text-xs bg-gray-900 text-gray-300">{c.sector}</span>}
                            <span className="text-xs text-gray-500">{c.bond_count} выпусков</span>
                            {c.avg_yield_to_maturity != null && <span className="text-xs text-emerald-400">YTM {c.avg_yield_to_maturity}%</span>}
                          </div>
                        </button>
                      ))}
                    </div>
                  )
                ) : recs.length === 0 ? (
                  <EmptyState message="Пока нет рекомендаций." />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {recs.map((r) => (
                      <RecommendationCard
                        key={r.internal_id}
                        rec={r}
                        rank={r.rank}
                        title={r.name}
                        subtitle={r.issuer || undefined}
                      />
                    ))}
                  </div>
                )}
                <p className="text-xs text-gray-500 text-center">Нажмите «Начать», чтобы открыть полный раздел.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
