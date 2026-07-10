import { useState } from 'react';
import { TrendingUp, Shield, LineChart, PieChart, Brain, Bell, Star, ArrowRight, Check, X } from 'lucide-react';

const STEPS = [
  {
    title: 'Welcome to Aigenis Bonds',
    description: 'Your comprehensive bond fixed income intelligence platform. Let us show you around.',
    icon: <TrendingUp size={32} className="text-emerald-400" />,
  },
  {
    title: 'Market Overview',
    description: 'The Dashboard shows you key metrics: total bonds, active issues, top scores, and recent listings at a glance.',
    icon: <Shield size={32} className="text-purple-400" />,
  },
  {
    title: 'Fixed Income Desk',
    description: 'Access professional tools: yield curves, relative value analysis, duration, carry trades, repo deals, and stress testing.',
    icon: <LineChart size={32} className="text-blue-400" />,
  },
  {
    title: 'Portfolio & Forecast',
    description: 'Optimize your portfolio with mean-variance analysis, run USD/BYN scenarios, and forecast capital growth with Monte Carlo simulations.',
    icon: <PieChart size={32} className="text-amber-400" />,
  },
  {
    title: 'ML Recommendations',
    description: 'Get explainable buy/hold/wait/avoid recommendations from our scikit-learn pipeline, trained on historical bond data.',
    icon: <Brain size={32} className="text-pink-400" />,
  },
  {
    title: 'Alerts & Monitoring',
    description: 'Stay informed with real-time alerts on price changes, FX rates, and data quality — delivered to your Telegram.',
    icon: <Bell size={32} className="text-red-400" />,
  },
  {
    title: 'Free Trial Active',
    description: 'You have 7 days of full Pro access. Explore all features, then subscribe via Telegram Stars or credit card to continue.',
    icon: <Star size={32} className="text-amber-400" />,
    highlight: true,
  },
];

const STORAGE_KEY = 'aigenis_onboarding_done';

export function isOnboardingNeeded(): boolean {
  return !localStorage.getItem(STORAGE_KEY);
}

export function dismissOnboarding(): void {
  localStorage.setItem(STORAGE_KEY, '1');
}

export function OnboardingTour({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const handleNext = () => {
    if (isLast) {
      dismissOnboarding();
      onDone();
    } else {
      setStep(s => s + 1);
    }
  };

  const handleSkip = () => {
    dismissOnboarding();
    onDone();
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 max-w-md w-full relative">
        <button onClick={handleSkip} className="absolute top-4 right-4 text-gray-500 hover:text-white p-1">
          <X size={18} />
        </button>

        <div className="text-center mb-6">
          <div className={`w-16 h-16 ${current.highlight ? 'bg-amber-600/20' : 'bg-gray-800'} rounded-2xl flex items-center justify-center mx-auto mb-4`}>
            {current.icon}
          </div>
          <h2 className="text-xl font-bold mb-2">{current.title}</h2>
          <p className="text-sm text-gray-400 leading-relaxed">{current.description}</p>
        </div>

        {/* Progress dots */}
        <div className="flex justify-center gap-2 mb-6">
          {STEPS.map((_, i) => (
            <div key={i} className={`w-2 h-2 rounded-full ${i === step ? 'bg-emerald-400 w-4' : 'bg-gray-700'}`} />
          ))}
        </div>

        <button onClick={handleNext}
          className="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2">
          {isLast ? (
            <>Get Started <Check size={16} /></>
          ) : (
            <>Next <ArrowRight size={16} /></>
          )}
        </button>

        {!isLast && (
          <button onClick={handleSkip}
            className="w-full text-center text-sm text-gray-500 hover:text-gray-300 mt-3 transition-colors">
            Skip tour
          </button>
        )}
      </div>
    </div>
  );
}
