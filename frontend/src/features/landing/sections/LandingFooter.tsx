import { CreditCard, Star, TrendingUp } from 'lucide-react';
import { useI18n } from '../../../i18n';

interface LandingFooterProps {
  onTerms?: () => void;
  onPrivacy?: () => void;
  scrollTo: (id: string) => void;
}

export function LandingFooter({ onTerms, onPrivacy, scrollTo }: LandingFooterProps) {
  const { t } = useI18n();

  return (
    <footer className="border-t border-[#d6e2e6] bg-white">
      <div className="max-w-7xl mx-auto px-4 py-10">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          <div>
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="text-[#004b65]" size={20} />
              <span className="font-bold">Aigenis Bonds</span>
            </div>
            <p className="text-sm text-[#717680]">{t('landing.badge')}</p>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-3">{t('landing.footerProduct')}</h4>
            <div className="space-y-2 text-sm text-[#516c79]">
              <button onClick={() => scrollTo('pain-points')} className="block hover:text-[#01121a] transition-colors">{t('pain.title')}</button>
              <button onClick={() => scrollTo('features')} className="block hover:text-[#01121a] transition-colors">{t('landing.features')}</button>
              <button onClick={() => scrollTo('pricing')} className="block hover:text-[#01121a] transition-colors">{t('landing.pricing')}</button>
              <button onClick={() => scrollTo('faq')} className="block hover:text-[#01121a] transition-colors">FAQ</button>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-3">{t('landing.footerLegal')}</h4>
            <div className="space-y-2 text-sm text-[#516c79]">
              <button onClick={onTerms} className="block hover:text-[#01121a] transition-colors text-left">{t('footer.terms')}</button>
              <button onClick={onPrivacy} className="block hover:text-[#01121a] transition-colors text-left">{t('footer.privacy')}</button>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-3">{t('landing.footerPayMethods')}</h4>
            <div className="space-y-2 text-sm text-[#516c79]">
              <p className="flex items-center gap-2"><Star size={14} /> Telegram Stars</p>
              <p className="flex items-center gap-2"><CreditCard size={14} /> {t('landing.footerBankCard')}</p>
            </div>
          </div>
        </div>
        <div className="border-t border-[#d6e2e6] pt-6 text-center text-sm text-[#717680]">
          &copy; {new Date().getFullYear()} Aigenis Parser. {t('common.allRights')}
        </div>
      </div>
    </footer>
  );
}
