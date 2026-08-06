import { useNavigate } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { useI18n } from '../i18n';
import { usePageMeta } from '../app/usePageMeta';
import { ROUTES } from '../app/paths';

export default function NotFoundPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  usePageMeta(t('meta.notFound'));

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-16 h-16 bg-[#004b65]/10 rounded-2xl flex items-center justify-center mb-5">
        <Compass size={30} className="text-[#004b65]" />
      </div>
      <h1 className="text-3xl font-extrabold font-[Montserrat,sans-serif] mb-2">404</h1>
      <p className="text-[#516c79] mb-6">{t('meta.notFoundDesc')}</p>
      <button
        onClick={() => navigate(ROUTES.home)}
        className="bg-[#004b65] hover:bg-[#387387] text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
      >
        {t('common.back')}
      </button>
    </div>
  );
}
