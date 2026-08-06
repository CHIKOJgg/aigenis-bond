import { useI18n } from '../i18n';

export function PageFallback() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4" role="status" aria-live="polite">
      <div className="w-9 h-9 rounded-full border-2 border-[#d6e2e6] border-t-[#004b65] animate-spin" />
      <div className="text-sm text-[#516c79] animate-pulse">{t('common.loading')}</div>
    </div>
  );
}
