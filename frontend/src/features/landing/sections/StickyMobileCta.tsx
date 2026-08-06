import { ArrowRight } from 'lucide-react';
import { useI18n } from '../../../i18n';

export function StickyMobileCta({ onRegister }: { onRegister: () => void }) {
  const { t } = useI18n();

  return (
    <div className="fixed bottom-0 inset-x-0 z-50 md:hidden bg-white/95 backdrop-blur border-t border-[#d6e2e6] px-4 py-3">
      <button
        onClick={onRegister}
        className="w-full bg-[#004b65] hover:bg-[#387387] text-white py-3 rounded-xl text-sm font-semibold transition-colors flex items-center justify-center gap-2 animate-pulseGlow"
      >
        {t('landing.startTrial')} <ArrowRight size={16} />
      </button>
    </div>
  );
}
