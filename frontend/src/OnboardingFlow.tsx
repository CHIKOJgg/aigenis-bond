import { useState } from 'react';
import { TrendingUp, ArrowRight, Check, X, DollarSign, PieChart, ShieldCheck, Building2, Sparkles, User, BarChart3, Play } from 'lucide-react';
import { useI18n } from './i18n';
import { LoadingSkeleton, EmptyState } from './components/common';
import type { AnalyticsRecommendation, CompanySummary } from './lib/api';
import { api } from './lib/api';
import { RecommendationCard } from './components/RecommendationCard';

export type OnboardingPage = 'profile' | 'bonds' | 'scores' | 'desk' | 'subscribe' | 'recommendations' | 'companies';

const STORAGE_KEY = 'aigenis_onboarding_done';

export function isOnboardingNeeded(): boolean {
  return !localStorage.getItem(STORAGE_KEY);
}

export function dismissOnboarding(): void {
  localStorage.setItem(STORAGE_KEY, '1');
}

const INTERESTS: { id: string; label: string; icon: React.ReactNode; desc: string }[] = [
  { id: 'usd', label: 'Валютные (USD)', icon: <DollarSign size={20} className="text-blue-400" />, desc: 'Облигации в долларах США' },
  { id: 'byn', label: 'Белорусские (BYN)', icon: <PieChart size={20} className="text-green-400" />, desc: 'Облигации в белорусских рублях' },
  { id: 'metals', label: 'Металлы', icon: <ShieldCheck size={20} className="text-amber-400" />, desc: 'Золото, серебро, платина' },
  { id: 'companies', label: 'По компаниям', icon: <Building2 size={20} className="text-emerald-400" />, desc: 'Топ эмитентов и их облигации' },
];

export function OnboardingFlow({ onDone, onNavigate }: { onDone: () => void; onNavigate?: (page: OnboardingPage) => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState<0 | 1 | 2 | 3>(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [userType, setUserType] = useState<'retail' | 'semipro' | 'institution' | null>(null);
  const [recs, setRecs] = useState<AnalyticsRecommendation[]>([]);
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [loading, setLoading] = useState(false);

  const chooseInterest = (id: string) => {
    setSelected(id);
    setStep(1);
    setLoading(true);
    const recPromise = api.analytics.recommendations(5).catch(() => [] as AnalyticsRecommendation[]);
    const companiesPromise = id === 'companies'
      ? api.analytics.companies({ limit: 6 }).catch(() => [] as CompanySummary[])
      : Promise.resolve([] as CompanySummary[]);
    Promise.all([recPromise, companiesPromise]).then(([r, c]) => {
      setRecs(r); setCompanies(c); setLoading(false);
    });
  };

  const finish = () => {
    dismissOnboarding();
    onNavigate?.(selected === 'companies' ? 'companies' : 'recommendations');
    onDone();
  };

  const skip = () => { dismissOnboarding(); onDone(); };

  const steps = [
    { label: 'Интересы' }, { label: 'Профиль' }, { label: 'Рекомендации' }, { label: 'Старт' },
  ];

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4 animate-fadeIn overflow-y-auto" role="dialog" aria-modal="true">
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 sm:p-8 max-w-3xl w-full my-8 relative outline-none">
        <button onClick={skip} className="absolute top-4 right-4 text-gray-500 hover:text-white p-1"><X size={18} /></button>

        <div className="flex items-center gap-2 mb-6">
          {steps.map((s, i) => (
            <div key={s.label} className="flex items-center gap-2 flex-1">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${step >= i ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-500'}`}>
                {step > i ? <Check size={14} /> : i + 1}
              </div>
              <span className={`text-xs ${step >= i ? 'text-gray-300' : 'text-gray-600'} hidden sm:inline`}>{s.label}</span>
              {i < steps.length - 1 && <div className={`flex-1 h-px ${step > i ? 'bg-emerald-600' : 'bg-gray-800'}`} />}
            </div>
          ))}
        </div>

        {step === 0 && (
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-emerald-600/20 rounded-2xl flex items-center justify-center"><Sparkles size={24} className="text-emerald-400" /></div>
              <div><h2 className="text-xl font-bold">{t('onboarding.welcome')}</h2><p className="text-sm text-gray-400">{t('onboarding.welcomeDesc')}</p></div>
            </div>
            <p className="text-sm font-medium text-gray-300 mb-3">Кто вы как инвестор?</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-5">
              {[
                { id: 'retail' as const, label: 'Розничный', desc: 'Личные инвестиции' },
                { id: 'semipro' as const, label: 'Полу-про', desc: 'Активный трейдер' },
                { id: 'institution' as const, label: 'Институциональный', desc: 'Управление активами' },
              ].map((t) => (
                <button key={t.id} onClick={() => setUserType(t.id)}
                  className={`py-3 px-4 rounded-xl text-sm font-medium border transition-colors ${
                    userType === t.id ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300' : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
                  }`}>
                  {t.label}<span className="block text-xs text-gray-500 font-normal mt-0.5">{t.desc}</span>
                </button>
              ))}
            </div>
            <p className="text-sm text-emerald-300 mb-4">Что вас интересует в первую очередь?</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {INTERESTS.map((it) => (
                <button key={it.id} onClick={() => chooseInterest(it.id)}
                  className="flex items-center gap-3 bg-gray-800/60 hover:bg-gray-800 border border-gray-700 hover:border-emerald-600 rounded-xl p-4 text-left transition-colors">
                  <span className="w-10 h-10 rounded-lg bg-gray-900 flex items-center justify-center shrink-0">{it.icon}</span>
                  <span className="min-w-0"><span className="block font-semibold text-white">{it.label}</span><span className="block text-xs text-gray-500">{it.desc}</span></span>
                  <ArrowRight size={16} className="text-gray-500 ml-auto shrink-0" />
                </button>
              ))}
            </div>
            <button onClick={skip} className="mt-5 text-sm text-gray-500 hover:text-gray-300">{t('onboarding.skip')}</button>
          </div>
        )}

        {step === 1 && (
          <div>
            <h2 className="text-lg font-bold mb-4 flex items-center gap-2"><User size={20} className="text-emerald-400" /> Демо-тур по продукту</h2>
            <div className="space-y-3 mb-6">
              {[
                { icon: <BarChart3 size={20} />, title: 'Дашборд', desc: 'Ключевые метрики рынка: статистика, тренды, лучшее по скору' },
                { icon: <TrendingUp size={20} />, title: 'Fixed Income Desk', desc: 'Кривые доходности, RV, Carry — профессиональный инструментарий' },
                { icon: <ShieldCheck size={20} />, title: 'Скоринг и ML', desc: 'Оценка риска каждой облигации + прогнозы buy/hold/wait/avoid' },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3 bg-gray-800/40 rounded-xl p-4">
                  <div className="w-10 h-10 bg-gray-800 rounded-lg flex items-center justify-center text-emerald-400 shrink-0">{item.icon}</div>
                  <div><p className="font-medium text-sm text-white">{item.title}</p><p className="text-xs text-gray-400 mt-0.5">{item.desc}</p></div>
                </div>
              ))}
            </div>
            <div className="flex gap-3">
              <button onClick={skip} className="text-sm text-gray-500 hover:text-gray-300">Пропустить</button>
              <button onClick={() => setStep(2)} className="ml-auto bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium">Дальше <ArrowRight size={16} className="inline" /></button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold flex items-center gap-2"><TrendingUp size={20} className="text-emerald-400" />
                {selected === 'companies' ? 'Топ компаний-эмитентов' : 'Персональные рекомендации'}</h2>
              <button onClick={finish} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-1.5">
                {t('onboarding.getStarted')} <Check size={16} /></button>
            </div>
            {loading ? <LoadingSkeleton /> : (
              <div className="space-y-4">
                {selected === 'companies' ? companies.length === 0 ? <EmptyState message="Пока нет данных по компаниям." /> : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {companies.map((c) => (
                      <button key={c.issuer} onClick={() => onNavigate?.('companies')}
                        className="text-left bg-gray-800/60 hover:bg-gray-800 border border-gray-700 rounded-xl p-4 transition-colors">
                        <div className="font-semibold text-white truncate">{c.name}</div>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          {c.sector && <span className="px-2 py-0.5 rounded text-xs bg-gray-900 text-gray-300">{c.sector}</span>}
                          <span className="text-xs text-gray-500">{c.bond_count} выпусков</span>
                          {c.avg_yield_to_maturity != null && <span className="text-xs text-emerald-400">YTM {c.avg_yield_to_maturity}%</span>}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : recs.length === 0 ? <EmptyState message="Пока нет рекомендаций." /> : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {recs.map((r) => <RecommendationCard key={r.internal_id} rec={r} rank={r.rank} title={r.name} subtitle={r.issuer || undefined} />)}
                  </div>
                )}
                <p className="text-xs text-gray-500 text-center">Нажмите «Начать», чтобы открыть полный раздел.</p>
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="text-center">
            <Play size={48} className="mx-auto mb-4 text-emerald-400" />
            <h2 className="text-xl font-bold mb-2">Всё готово!</h2>
            <p className="text-gray-400 mb-6">Загрузите свой портфель через XLSX или начните с изучения рынка</p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button onClick={finish} className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-3 rounded-xl text-sm font-medium">Начать изучение</button>
              <button onClick={skip} className="border border-gray-700 hover:border-gray-600 text-gray-300 px-6 py-3 rounded-xl text-sm font-medium">Загрузить портфель</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
