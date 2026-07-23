import { Lock, ArrowRight } from 'lucide-react';
import { usePaywall } from '../lib/PaywallContext';

interface UpgradeCTAProps {
  featureKey?: string;
  title?: string;
  description?: string;
  compact?: boolean;
}

export default function UpgradeCTA({
  featureKey = 'default',
  title = 'Эта функция доступна в Pro',
  description = 'Расблокируйте полный функционал для анализа облигаций',
  compact = false,
}: UpgradeCTAProps) {
  const { openPaywall } = usePaywall();

  if (compact) {
    return (
      <button
        onClick={() => openPaywall(featureKey)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600/10 border border-amber-500/30 text-amber-400 text-xs font-medium hover:bg-amber-600/20 transition-colors"
      >
        <Lock size={12} />
        Pro
        <ArrowRight size={12} />
      </button>
    );
  }

  return (
    <div className="rounded-xl bg-gradient-to-br from-amber-900/20 to-gray-900 border border-amber-500/20 p-6 text-center">
      <div className="w-12 h-12 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-3">
        <Lock size={20} className="text-amber-400" />
      </div>
      <h3 className="text-base font-semibold text-white mb-1">{title}</h3>
      <p className="text-sm text-gray-400 mb-4 max-w-sm mx-auto">{description}</p>
      <button
        onClick={() => openPaywall(featureKey)}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-sm font-semibold transition-colors"
      >
        Расблокировать <ArrowRight size={16} />
      </button>
    </div>
  );
}
