import { useState } from 'react';
import { TrendingUp, Shield, LineChart, PieChart, Brain, Bell, Star, ArrowRight, Check, X, User, List, Gauge, CreditCard } from 'lucide-react';
import { useI18n } from './i18n';

export type OnboardingPage = 'profile' | 'bonds' | 'scores' | 'desk' | 'subscribe';

const STEPS: {
  title: string;
  description: string;
  icon: React.ReactNode;
  actionLabel?: string;
  goTo?: OnboardingPage;
  highlight?: boolean;
}[] = [
  {
    title: 'onboarding.welcome',
    description: 'onboarding.welcomeDesc',
    icon: <TrendingUp size={32} className="text-emerald-400" />,
  },
  {
    title: 'onboarding.stepProfile',
    description: 'onboarding.stepProfileDesc',
    icon: <User size={32} className="text-purple-400" />,
    actionLabel: 'onboarding.goProfile',
    goTo: 'profile',
  },
  {
    title: 'onboarding.stepBonds',
    description: 'onboarding.stepBondsDesc',
    icon: <List size={32} className="text-blue-400" />,
    actionLabel: 'onboarding.goBonds',
    goTo: 'bonds',
  },
  {
    title: 'onboarding.stepScores',
    description: 'onboarding.stepScoresDesc',
    icon: <Gauge size={32} className="text-cyan-400" />,
    actionLabel: 'onboarding.goScores',
    goTo: 'scores',
  },
  {
    title: 'onboarding.stepDesk',
    description: 'onboarding.stepDeskDesc',
    icon: <LineChart size={32} className="text-amber-400" />,
    actionLabel: 'onboarding.goDesk',
    goTo: 'desk',
    highlight: true,
  },
  {
    title: 'onboarding.stepSubscribe',
    description: 'onboarding.stepSubscribeDesc',
    icon: <CreditCard size={32} className="text-emerald-400" />,
    actionLabel: 'onboarding.goSubscribe',
    goTo: 'subscribe',
  },
];

const STORAGE_KEY = 'aigenis_onboarding_done';

export function isOnboardingNeeded(): boolean {
  return !localStorage.getItem(STORAGE_KEY);
}

export function dismissOnboarding(): void {
  localStorage.setItem(STORAGE_KEY, '1');
}

export function OnboardingTour({ onDone, onNavigate }: { onDone: () => void; onNavigate?: (page: OnboardingPage) => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  const [done, setDone] = useState<Set<number>>(new Set());
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const markDone = (i: number) => {
    setDone((prev) => new Set(prev).add(i));
  };

  const handleNext = () => {
    markDone(step);
    if (isLast) {
      dismissOnboarding();
      onDone();
    } else {
      setStep((s) => s + 1);
    }
  };

  const handleAction = () => {
    markDone(step);
    if (current.goTo && onNavigate) {
      onNavigate(current.goTo);
    }
    // If last step, also dismiss after navigating
    if (isLast) {
      dismissOnboarding();
      onDone();
    } else {
      setStep((s) => s + 1);
    }
  };

  const handleSkip = () => {
    dismissOnboarding();
    onDone();
  };

  const progress = Math.round((done.size / STEPS.length) * 100);

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4 animate-fadeIn"
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
    >
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 max-w-md w-full relative outline-none">
        <button onClick={handleSkip} className="absolute top-4 right-4 text-gray-500 hover:text-white p-1" aria-label={t('onboarding.skipAria')}>
          <X size={18} />
        </button>

        {/* Progress bar */}
        <div className="w-full h-1.5 bg-gray-800 rounded-full mb-6 overflow-hidden">
          <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>

        <div className="text-center mb-6">
          <div className={`w-16 h-16 ${current.highlight ? 'bg-amber-600/20' : 'bg-gray-800'} rounded-2xl flex items-center justify-center mx-auto mb-4`}>
            {current.icon}
          </div>
          <h2 id="onboarding-title" className="text-xl font-bold mb-2">{t(current.title)}</h2>
          <p className="text-sm text-gray-400 leading-relaxed">{t(current.description)}</p>
        </div>

        {/* Checklist */}
        <div className="space-y-2 mb-6">
          {STEPS.map((s, i) => (
            <div
              key={i}
              className={`flex items-center gap-2 text-sm ${i === step ? 'text-white' : 'text-gray-500'} ${done.has(i) ? 'opacity-60' : ''}`}
            >
              <span className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${done.has(i) ? 'bg-emerald-600 text-white' : i === step ? 'bg-emerald-900 text-emerald-300' : 'bg-gray-800 text-gray-500'}`}>
                {done.has(i) ? <Check size={12} /> : i + 1}
              </span>
              <span className={done.has(i) ? 'line-through' : ''}>{t(s.title)}</span>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          {current.actionLabel && current.goTo ? (
            <button onClick={handleAction}
              className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2">
              {t(current.actionLabel)} <ArrowRight size={16} />
            </button>
          ) : (
            <button onClick={handleNext}
              className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2">
              {isLast ? (
                <>{t('onboarding.getStarted')} <Check size={16} /></>
              ) : (
                <>{t('onboarding.next')} <ArrowRight size={16} /></>
              )}
            </button>
          )}
          {!isLast && (
            <button onClick={handleSkip}
              className="px-4 text-sm text-gray-500 hover:text-gray-300 transition-colors">
              {t('onboarding.skip')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
