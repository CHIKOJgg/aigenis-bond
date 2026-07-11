import { Lock, Star, TrendingUp, X, Check, Globe2, LineChart, Brain } from 'lucide-react';
import { Modal } from './lib/Modal';
import { usePaywall } from './lib/PaywallContext';
import { useAuth } from './lib/AuthContext';

const ICONS: Record<string, React.ReactNode> = {
  lock: <Lock size={26} className="text-amber-400" />,
  currencies: <Globe2 size={26} className="text-amber-400" />,
  desk: <LineChart size={26} className="text-amber-400" />,
  ml: <Brain size={26} className="text-amber-400" />,
};

const PRO_BENEFITS = [
  'Fixed Income Desk: кривая доходности, RV, Carry, РЕПО, стресс-тесты',
  'ML-рекомендации и прогнозы капитала',
  'Портфель и его оптимизация',
  'Трекер всех валют (бирж) одновременно',
  'Алерты и приоритетная поддержка',
];

export function PaywallModal({ onSubscribe }: { onSubscribe: () => void }) {
  const { state, closePaywall } = usePaywall();
  const { user } = useAuth();

  if (!state.open) return null;

  const isPaid = user && user.subscription_tier !== 'free';

  const handleSubscribe = () => {
    closePaywall();
    onSubscribe();
  };

  return (
    <Modal onClose={closePaywall} className="relative max-w-md w-full border-amber-800/50">
      <button
        onClick={closePaywall}
        className="absolute top-3 right-3 text-gray-500 hover:text-white p-1 z-10"
        aria-label="Закрыть"
      >
        <X size={18} />
      </button>

      <div className="bg-gradient-to-br from-amber-600/20 to-gray-900 px-6 pt-8 pb-6 text-center">
        <div className="w-14 h-14 bg-amber-600/20 rounded-full flex items-center justify-center mx-auto mb-3">
          {ICONS[state.feature.icon] ?? ICONS.lock}
        </div>
        <h3 className="text-xl font-bold">{state.feature.title}</h3>
        <p className="text-sm text-gray-400 mt-2">{state.feature.description}</p>
      </div>

      <div className="px-6 py-5">
        <p className="text-xs uppercase tracking-wide text-gray-500 mb-2 font-semibold">
          Что входит в Pro / Enterprise
        </p>
        <ul className="space-y-2">
          {PRO_BENEFITS.map((b) => (
            <li key={b} className="flex items-start gap-2 text-sm text-gray-300">
              <Check size={16} className="text-emerald-400 mt-0.5 shrink-0" />
              <span>{b}</span>
            </li>
          ))}
        </ul>

        {isPaid ? (
          <p className="mt-4 text-center text-sm text-emerald-300 bg-emerald-900/30 border border-emerald-800 rounded-lg py-2">
            Подписка уже активна — доступ скоро обновится.
          </p>
        ) : (
          <div className="mt-5 space-y-2">
            <button
              onClick={handleSubscribe}
              className="w-full inline-flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-500 text-white py-3 rounded-xl text-sm font-semibold transition-colors"
            >
              <Star size={16} /> Оформить подписку
            </button>
            <button
              onClick={closePaywall}
              className="w-full text-gray-400 hover:text-white text-sm py-2 transition-colors"
            >
              Позже
            </button>
          </div>
        )}
      </div>

      <div className="px-6 py-3 bg-gray-950/50 text-center">
        <p className="text-xs text-gray-600 flex items-center justify-center gap-1">
          <TrendingUp size={12} /> Aigenis Bonds
        </p>
      </div>
    </Modal>
  );
}
